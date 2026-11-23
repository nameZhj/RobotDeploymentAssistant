# @file: src/services/studio_state_service.py
# @brief: Central decoupled application state facade coordinating SQLite repos, event bus, undo stack, and Wi-Fi HTTP.
# @exports: StudioStateService

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from src.algorithms.timeline_collision_worker import CollisionInterval, detect_timeline_collisions
from src.core.event_bus import StudioEvent, StudioEventBus, get_event_bus
from src.core.settings import get_settings
from src.core.undo_stack import StudioUndoStack
from src.domain import (
    ActionEntity,
    InitPointConfig,
    PcdMapEntity,
    SceneEntity,
    TaskEntity,
    TimelineBlockEntity,
    TrackEntity,
    TrajectoryEntity,
    TrajectoryGroupEntity,
)
from src.math.trajectory_sampler import evaluate_trajectory_pose, sample_trajectory_50fps
from src.persistence import (
    ActionRepository,
    CsvPointCodec,
    MapFragmentRepository,
    SceneTaskRepository,
    StudioDatabase,
    TrajectoryRepository,
    UniUniJsonCodec,
    get_database,
)
from src.protocol import (
    AuthorityStateMachine,
    HttpCallbackListener,
    HttpTrajectoryClient,
    RobotHttpClient,
    SlamMappingClient,
)
from src.services.studio_http_ops import (
    compile_and_upload_chains_http_op,
    dispatch_command_http_op,
    start_task_chains_http_op,
    stop_all_robots_to_origin_http_op,
    sync_actions_from_http_op,
)
from src.services.studio_state_ops import (
    apply_settings_update_op,
    bind_trajectory_tracks_op,
    clamp_robot_drag_xy_op,
    commit_block_change_op,
    delete_track_with_undo_op,
    load_fragment_at_op,
    sync_actions_from_serial_op,
    upsert_track_validated_op,
    validate_init_points_op,
)


class StudioStateService:
    """Single source of truth mediating L2-L6 engines and L8 UniUni pages."""

    def __init__(
        self,
        db: Optional[StudioDatabase] = None,
        bus: Optional[StudioEventBus] = None,
        serial_manager: Optional[Any] = None,
        dance_updater: Optional[Any] = None,
        ssh_channel: Optional[Any] = None,
    ) -> None:
        self.db = db or get_database()
        self.bus = bus or get_event_bus()
        self.undo_stack = StudioUndoStack()
        self.serial_manager = serial_manager
        self.dance_updater = dance_updater
        self.ssh_channel = ssh_channel

        self.scene_repo = SceneTaskRepository(self.db)
        self.traj_repo = TrajectoryRepository(self.db)
        self.action_repo = ActionRepository(self.db)
        self.map_repo = MapFragmentRepository(self.db)
        self.json_codec = UniUniJsonCodec(self.db)

        self.arbiter = AuthorityStateMachine()
        self.http_client = HttpTrajectoryClient()
        self.http_rpc = RobotHttpClient()
        self.callback_listener = HttpCallbackListener(bus=self.bus)
        self.slam_client = SlamMappingClient(arbiter=self.arbiter, frame_sender=None, http_client=self.http_rpc)

        self.scene: SceneEntity = self.scene_repo.get_active_scene()
        self.task: TaskEntity = self.scene_repo.get_active_task(self.scene.id or 1)
        self.tracks: List[TrackEntity] = []
        self.blocks: List[TimelineBlockEntity] = []
        self.trajectories: Dict[int, TrajectoryEntity] = {}
        self.sampled_trajs: Dict[int, np.ndarray] = {}
        self.collisions: List[CollisionInterval] = []
        self.active_map: Optional[PcdMapEntity] = None
        self.playhead_s: float = 0.0
        self.reload_all()

    def reload_all(self) -> None:
        """Refresh in-memory scene, task, tracks, blocks, trajectory samples, and collisions."""
        self.scene = self.scene_repo.get_active_scene()
        self.task = self.scene_repo.get_active_task(self.scene.id or 1)
        tid = self.task.id or 1
        self.tracks = self.scene_repo.list_tracks(tid)
        self.blocks = self.scene_repo.list_blocks(tid)
        all_trajs = self.traj_repo.list_trajectories()
        self.trajectories = {t.id: t for t in all_trajs if t.id is not None}
        self._rebuild_sampled_trajs()
        self.active_map = self.map_repo.get_map(self.scene.active_map_id) if self.scene.active_map_id else None
        self.recompute_collisions()

    def _rebuild_sampled_trajs(self) -> None:
        self.sampled_trajs.clear()
        for tid, traj in self.trajectories.items():
            if traj.point_data_csv:
                arr = CsvPointCodec.decode_points(traj.point_data_csv)
                if len(arr) >= 2:
                    self.sampled_trajs[tid] = arr
                    continue
            arr, _ = sample_trajectory_50fps(traj)
            self.sampled_trajs[tid] = arr

    def recompute_collisions(self) -> List[CollisionInterval]:
        cfg = get_settings().stage_defaults
        self.collisions = detect_timeline_collisions(
            self.tracks, self.blocks, self.trajectories,
            safety_dist=cfg.safety_distance_m, time_step=cfg.collision_check_dt_s,
        )
        self.bus.publish(StudioEvent.COLLISION_UPDATED, self.collisions)
        return self.collisions

    def total_duration(self) -> float:
        max_blk = max((b.end_time for b in self.blocks if not b.is_ignored), default=0.0)
        return max(float(self.task.total_duration), max_blk, 10.0)

    def evaluate_robot_pose(self, track: TrackEntity, t: float) -> Tuple[float, float, float]:
        cur_pose = (track.init_x, track.init_y, track.init_yaw)
        if t <= 1e-6:
            return cur_pose
        track_blocks = sorted(
            (b for b in self.blocks if b.track_id == track.id and not b.is_ignored and b.block_type == "trajectory"),
            key=lambda x: x.start_time,
        )
        for blk in track_blocks:
            arr = self.sampled_trajs.get(blk.ref_id)
            if arr is None or len(arr) == 0:
                continue
            if blk.start_time <= t <= blk.end_time:
                return evaluate_trajectory_pose(arr, t - blk.start_time)
            if blk.end_time < t:
                cur_pose = (float(arr[-1, 1]), float(arr[-1, 2]), float(arr[-1, 3]))
        return cur_pose

    def active_action_at(self, track: TrackEntity, t: float) -> Optional[ActionEntity]:
        if t <= 1e-6:
            return None
        for blk in self.blocks:
            if (
                blk.track_id == track.id and not blk.is_ignored
                and blk.block_type == "action" and blk.start_time <= t <= blk.end_time
            ):
                return self.action_repo.get_action(blk.ref_id)
        return None

    def notify(self, message: str, tone: str = "info") -> None:
        self.bus.publish(StudioEvent.STATUS_NOTIFICATION, {"text": message, "tone": tone})

    def list_groups(self) -> List[TrajectoryGroupEntity]:
        return self.traj_repo.list_groups(self.scene.id or 1)

    def list_init_configs(self) -> List[InitPointConfig]:
        return self.scene_repo.list_init_configs(self.scene.id or 1)

    def next_track_end_time(self, track_id: int) -> float:
        return round(max((b.end_time for b in self.blocks if b.track_id == track_id and not b.is_ignored), default=0.0), 2)

    def upsert_track_validated(self, track: TrackEntity) -> TrackEntity:
        return upsert_track_validated_op(self, track)

    def delete_track_with_undo(self, track_id: int) -> Optional[str]:
        return delete_track_with_undo_op(self, track_id)

    def commit_block_change(
        self, before: Optional[TimelineBlockEntity], after: Optional[TimelineBlockEntity], description: str
    ) -> Optional[TimelineBlockEntity]:
        return commit_block_change_op(self, before, after, description)

    def load_fragment_at(self, fragment_id: int, insert_time_s: float) -> int:
        return load_fragment_at_op(self, fragment_id, insert_time_s)

    def apply_settings_update(self, safety_dist: float, http_virtual_fallback: bool) -> None:
        apply_settings_update_op(self, safety_dist, http_virtual_fallback)

    def validate_init_points(self, points: List[Tuple[str, float, float]]) -> None:
        validate_init_points_op(points)

    def clamp_robot_drag_xy(self, track: TrackEntity, wx: float, wy: float) -> Tuple[float, float]:
        return clamp_robot_drag_xy_op(self, track, wx, wy)

    def sync_actions_from_serial(self, timeout: float = 3.0) -> Tuple[bool, int, str]:
        return sync_actions_from_serial_op(self, timeout=timeout)

    def sync_actions_from_http(self) -> Tuple[bool, int, str]:
        return sync_actions_from_http_op(self)

    def dispatch_command_http(
        self, target_id: str, command: str, params: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        return dispatch_command_http_op(self, target_id, command, params)

    def compile_and_upload_chains_http(
        self, plan_id: str = "8001", run_id: str = "9001", prep: bool = True
    ) -> List[Dict[str, Any]]:
        return compile_and_upload_chains_http_op(self, plan_id=plan_id, run_id=run_id, prep=prep)

    def start_task_chains_http(self, run_id: str = "9001") -> List[Dict[str, Any]]:
        return start_task_chains_http_op(self, run_id=run_id)

    def stop_all_robots_and_return_origin_http(self) -> List[Dict[str, Any]]:
        return stop_all_robots_to_origin_http_op(self)

    def set_trajectory_visibility(self, traj_id: int, visible: bool) -> None:
        traj = self.trajectories.get(traj_id) or self.traj_repo.get_trajectory(traj_id)
        if traj is None:
            return
        traj.visible_on_map = bool(visible)
        self.traj_repo.upsert_trajectory(traj)
        self.reload_all()
        self.bus.publish(StudioEvent.TRAJECTORY_LIB_UPDATED, traj_id)

    def bind_trajectory_tracks(self, traj_id: int, track_nos: List[int], sync_to_timeline: bool = True) -> int:
        return bind_trajectory_tracks_op(self, traj_id, track_nos, sync_to_timeline=sync_to_timeline)

    def save_project_snapshot(self) -> str:
        self.scene_repo.update_scene(self.scene)
        self.recompute_collisions()
        self.bus.publish(StudioEvent.SCENE_CHANGED, self.scene.id)
        msg = f"工程 [{self.task.name}] 已保存 ({len(self.tracks)} 轨道 / {len(self.blocks)} 任务节点)"
        self.notify(msg, "ok")
        return msg

    def clear_all_tracks(self) -> None:
        if self.task.id is not None:
            self.scene_repo.clear_task_tracks_and_blocks(self.task.id)
        self.undo_stack.clear()
        self.reload_all()
        self.bus.publish(StudioEvent.TRACKS_UPDATED, None)
        self.bus.publish(StudioEvent.TIMELINE_UPDATED, None)
        self.notify("已清空当前任务的所有机器人轨道与任务链", "info")

    def load_demo_swarm_preset(self) -> int:
        from src.persistence.seed_builtin_data import seed_demo_swarm_preset
        added = seed_demo_swarm_preset(self.db)
        self.reload_all()
        self.bus.publish(StudioEvent.TRACKS_UPDATED, None)
        self.bus.publish(StudioEvent.INIT_POINTS_UPDATED, None)
        self.notify(f"已手动载入 {added} 台示例机器人", "ok")
        return added

    def _send_raw_lrmp(self, raw_bytes: bytes) -> bool:
        line = raw_bytes.decode("utf-8", errors="ignore").strip()
        if "|" in line and self.serial_manager is not None and hasattr(self.serial_manager, "send_command"):
            tgt, rest = line.split("|", 1)
            self.serial_manager.send_command(tgt, rest)
            return True
        return True
