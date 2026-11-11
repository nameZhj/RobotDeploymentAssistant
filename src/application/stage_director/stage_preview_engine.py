"""
@file: src/application/stage_director/stage_preview_engine.py
@brief: 时间轴编排到 3D 虚拟预演数据链路编译、真实NPZ动作缓存与时空校验引擎
@exports: StagePreviewEngine
"""
import json
import logging
import math
import os
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from src.domain.simulation.stage_performance_sampler import (
    AvatarSimulationState,
    StagePerformanceSampler,
)
from src.domain.timeline.timeline_clip_asset import TimelineClipAsset, TrackLayerType
from src.domain.trajectory.group_trajectory import GroupTrajectory
from src.domain.trajectory.group_trajectory_compiler import GroupTrajectoryCompiler
from src.domain.trajectory.trajectory_asset import TrajectoryAsset, TrajectoryPoint
from src.infrastructure.storage.choreo_sqlite_store import ChoreoSqliteStore
from src.infrastructure.storage.group_trajectory_sqlite_adapter import (
    GroupTrajectorySqliteAdapter,
)
from src.infrastructure.storage.timeline_clip_sqlite_adapter import (
    TimelineClipSqliteAdapter,
)
from src.infrastructure.storage.trajectory_sqlite_adapter import (
    TrajectorySqliteAdapter,
)

logger = logging.getLogger("StagePreviewEngine")


def _map_member_alias(member_id: str, index: int = 0) -> str:
    m = str(member_id).strip()
    if m.startswith("Robot_"):
        return m
    if m.isdigit():
        return f"Robot_{m}"
    m_up = m.upper()
    if m_up in ("A", "1"):
        return "Robot_1"
    if m_up in ("B", "2"):
        return "Robot_2"
    if m_up in ("C", "3"):
        return "Robot_3"
    return f"Robot_{index + 1}"


class StagePreviewEngine:
    """提供从当前持久化编排时间轴提取、编译单机器人与群组机器人 3D 预演数据"""

    _npz_cache: Dict[str, Tuple[np.ndarray, float]] = {}

    @classmethod
    def build_preview_tracks(
        cls, store: Optional[Any] = None, task_name: str = "默认任务1"
    ) -> Dict[str, Any]:
        actual_store = store if isinstance(store, ChoreoSqliteStore) else ChoreoSqliteStore(store if isinstance(store, str) else None)
        adapter = TimelineClipSqliteAdapter(actual_store.db_path)
        clips = adapter.list_clips(task_name=task_name)

        robot_tracks: Dict[str, Dict[str, Any]] = {}
        trajectory_lines: Dict[str, List[Tuple[float, float]]] = {}
        validation_errors: List[str] = []
        unplayable_items: List[Dict[str, Any]] = []
        max_end_ms = 0

        for clip in clips:
            max_end_ms = max(max_end_ms, clip.end_ms)
            if clip.track_layer == TrackLayerType.ACTION:
                cls._process_action_clip(actual_store, clip, robot_tracks, validation_errors, unplayable_items)
            elif clip.track_layer == TrackLayerType.TRAJECTORY:
                cls._process_trajectory_clip(actual_store, clip, robot_tracks, trajectory_lines, validation_errors, unplayable_items)

        cls._validate_time_conflicts(robot_tracks, validation_errors)

        return {
            "robot_tracks": robot_tracks,
            "trajectory_lines": trajectory_lines,
            "duration_ms": max(1000, max_end_ms),
            "clip_count": len(clips),
            "active_robots": sorted(robot_tracks.keys()),
            "validation_errors": validation_errors,
            "unplayable_items": unplayable_items,
            "is_valid": len(validation_errors) == 0,
            "schedule_version": "v1.0.0",
        }

    @classmethod
    def _process_action_clip(
        cls, store: ChoreoSqliteStore, clip: TimelineClipAsset,
        tracks: Dict[str, Dict[str, Any]],
        errors: List[str], unplayable: List[Dict[str, Any]],
    ) -> None:
        rid = str(clip.robot_id).strip()
        alias = rid if rid.startswith("Robot_") else f"Robot_{rid}"
        if alias not in tracks:
            tracks[alias] = {"id": cls._extract_int_id(alias), "trajectories": [], "actions": []}

        file_path, is_verified, npz_pos, fps = cls._resolve_action_asset(store, clip)
        if not is_verified:
            err_msg = f"机器人 {alias} 动作素材缺失或未验证: {clip.name} (路径: {file_path})"
            errors.append(err_msg)
            unplayable.append({"robot_id": alias, "clip_id": clip.clip_id, "name": clip.name, "reason": "MOTION_FILE_MISSING", "path": file_path})

        tracks[alias]["actions"].append({
            "name": clip.name or f"Action_{clip.ref_id}",
            "start_s": clip.start_s,
            "duration_s": clip.duration_s,
            "action_id": clip.ref_id,
            "file_path": file_path,
            "is_verified": is_verified,
            "npz_positions": npz_pos,
            "fps": fps,
        })

    @classmethod
    def _resolve_action_asset(cls, store: ChoreoSqliteStore, clip: TimelineClipAsset) -> Tuple[str, bool, Optional[np.ndarray], float]:
        path = ""
        row = store.get_action(clip.ref_id)
        if row and row.get("animation_path"):
            path = str(row["animation_path"])
        if not path:
            norm_name = str(clip.name or "").upper()
            mapping = {
                "KUNG_FU": "preview/G1_KUNG_FU.npz", "太极": "preview/G1_KUNG_FU.npz",
                "MOONWALK": "preview/G1_MOONWALK.npz", "太空漫步": "preview/G1_MOONWALK.npz",
                "TIKTOK": "preview/G1_TIKTOK.npz", "手势舞": "preview/G1_TIKTOK.npz",
                "TURN_JUMP": "preview/G1_TURN_JUMP.npz", "旋转跳跃": "preview/G1_TURN_JUMP.npz",
                "WAVE": "preview/G2_WAVE.npz", "电流": "preview/G2_WAVE.npz",
                "CYBER": "preview/G3_CYBER.npz", "赛博": "preview/G3_CYBER.npz",
            }
            for k, p in mapping.items():
                if k in norm_name:
                    path = p
                    break

        if not path or not os.path.exists(path):
            return path, False, None, 50.0

        if path not in cls._npz_cache:
            try:
                data = np.load(path, allow_pickle=False)
                pos = data["positions"]
                fps_val = float(data["fps"]) if "fps" in data.files else 50.0
                cls._npz_cache[path] = (pos, fps_val)
            except Exception as e:
                logger.warning(f"Failed loading npz {path}: {e}")
                return path, False, None, 50.0

        cached_pos, cached_fps = cls._npz_cache[path]
        return path, True, cached_pos, cached_fps

    @classmethod
    def _process_trajectory_clip(
        cls, store: ChoreoSqliteStore, clip: TimelineClipAsset,
        tracks: Dict[str, Dict[str, Any]], lines: Dict[str, List[Tuple[float, float]]],
        errors: List[str], unplayable: List[Dict[str, Any]],
    ) -> None:
        if clip.is_group or str(clip.robot_id).upper() == "GROUP":
            cls._compile_group_trajectory(store, clip, tracks, lines, errors, unplayable)
        else:
            cls._compile_single_trajectory(store, clip, tracks, lines, errors, unplayable)

    @classmethod
    def _compile_single_trajectory(
        cls, store: ChoreoSqliteStore, clip: TimelineClipAsset,
        tracks: Dict[str, Dict[str, Any]], lines: Dict[str, List[Tuple[float, float]]],
        errors: List[str], unplayable: List[Dict[str, Any]],
    ) -> None:
        rid = str(clip.robot_id).strip()
        alias = rid if rid.startswith("Robot_") else f"Robot_{rid}"
        if alias not in tracks:
            tracks[alias] = {"id": cls._extract_int_id(alias), "trajectories": [], "actions": []}

        points = cls._extract_trajectory_points(store, clip.ref_id)
        if points == [(0.0, 0.0, 0.0)]:
            errors.append(f"机器人 {alias} 轨迹素材缺失或为空: {clip.name} (ID: {clip.ref_id})")
            unplayable.append({"robot_id": alias, "clip_id": clip.clip_id, "name": clip.name, "reason": "TRAJECTORY_ASSET_MISSING", "ref_id": clip.ref_id})

        tracks[alias]["trajectories"].append({
            "name": clip.name or f"Traj_{clip.ref_id}",
            "start_s": clip.start_s,
            "duration_s": clip.duration_s,
            "points": points,
            "trajectory_id": clip.ref_id,
        })
        lines[alias] = [(p[0], p[1]) for p in points]

    @classmethod
    def _compile_group_trajectory(
        cls, store: ChoreoSqliteStore, clip: TimelineClipAsset,
        tracks: Dict[str, Dict[str, Any]], lines: Dict[str, List[Tuple[float, float]]],
        errors: List[str], unplayable: List[Dict[str, Any]],
    ) -> None:
        group = GroupTrajectorySqliteAdapter.get_group(store, clip.ref_id)
        if not group:
            errors.append(f"群组轨迹不存在: {clip.name} (ID: {clip.ref_id})")
            return
        ref_asset = TrajectorySqliteAdapter.load_asset(store, group.reference_trajectory_id)
        if not ref_asset:
            errors.append(f"群组基准轨迹不存在: {clip.name} (基准ID: {group.reference_trajectory_id})")
            return

        compiled_list = GroupTrajectoryCompiler.compile(group, ref_asset)
        for idx, m_traj in enumerate(compiled_list):
            m_id = m_traj.robot_id
            alias = _map_member_alias(m_id, idx)
            if alias not in tracks:
                tracks[alias] = {"id": cls._extract_int_id(alias), "trajectories": [], "actions": []}
            m_pts = [(pt.x_m, pt.y_m, pt.yaw_deg) for pt in m_traj.sampled_points] or [(0.0, 0.0, 0.0)]
            tracks[alias]["trajectories"].append({
                "name": f"{clip.name} ({m_id})",
                "start_s": clip.start_s,
                "duration_s": clip.duration_s,
                "points": m_pts,
                "trajectory_id": f"{clip.ref_id}_{m_id}",
            })
            lines[alias] = [(p[0], p[1]) for p in m_pts]

    @classmethod
    def _extract_trajectory_points(cls, store: ChoreoSqliteStore, ref_id: str) -> List[Tuple[float, ...]]:
        try:
            asset = TrajectorySqliteAdapter.load_asset(store, ref_id)
            if asset and asset.sampled_points:
                return [(pt.x_m, pt.y_m, pt.yaw_deg) for pt in asset.sampled_points]
            if asset and asset.control_points:
                return [tuple(pt[:2]) for pt in asset.control_points]
        except Exception:
            pass
        return [(0.0, 0.0, 0.0)]

    @classmethod
    def _validate_time_conflicts(cls, tracks: Dict[str, Dict[str, Any]], errors: List[str]) -> None:
        for alias, track in tracks.items():
            trajs = track.get("trajectories", [])
            for i in range(len(trajs)):
                for j in range(i + 1, len(trajs)):
                    t1, t2 = trajs[i], trajs[j]
                    if (t1["start_s"] < t2["start_s"] + t2["duration_s"]) and (t2["start_s"] < t1["start_s"] + t1["duration_s"]):
                        errors.append(f"机器人 {alias} 轨迹时空重叠冲突: [{t1['name']}] 与 [{t2['name']}]")

    @classmethod
    def _extract_int_id(cls, alias: str) -> int:
        parts = alias.split("_")
        return int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 1

    @classmethod
    def interpolate_poses_at_time(cls, robot_tracks: Dict[str, Any], time_ms: int) -> Dict[str, AvatarSimulationState]:
        sampler = StagePerformanceSampler()
        curr_s = max(0.0, time_ms / 1000.0)
        poses: Dict[str, AvatarSimulationState] = {}
        for alias, track in robot_tracks.items():
            poses[alias] = sampler.sample_robot_pose(
                robot_alias=alias,
                current_time_s=curr_s,
                trajectory_blocks=track.get("trajectories", []),
                action_blocks=track.get("actions", []),
            )
        return poses
