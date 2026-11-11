"""
@file: src/application/stage_director/stage_preview_coordinator.py
@brief: 统一演播时钟监听、多机器人轨迹与动作姿态采样及安全防撞协调器
@exports: StagePreviewCoordinator
"""
import logging
import math
import time
from typing import Any, Dict, List, Optional, Tuple
from PySide6.QtCore import QObject, Signal

from src.domain.simulation.stage_performance_sampler import (
    AvatarSimulationState,
    StagePerformanceSampler,
)
from src.domain.trajectory.ugc_guard_validator import UgcGuardValidator

logger = logging.getLogger("StagePreviewCoordinator")


class StagePreviewCoordinator(QObject):
    """协调统一播放器时钟、多机器人双层时间轴采样与时空防撞安全态势"""

    posesUpdated = Signal(dict)
    collisionDiagnosed = Signal(dict)

    def __init__(self, parent: Optional[QObject] = None, load_defaults: bool = True) -> None:
        super().__init__(parent)
        self._sampler = StagePerformanceSampler()
        self._robot_tracks: Dict[str, Dict[str, Any]] = {}
        self._safe_dist: float = 0.65
        self._warn_dist: float = 1.00
        if load_defaults:
            self._init_default_tracks()

    def clear_tracks(self) -> None:
        """清空所有机器人轨道，进入纯净空状态"""
        self._robot_tracks.clear()

    def _init_default_tracks(self) -> None:
        self._robot_tracks = {
            "Robot_1": {
                "id": 1,
                "trajectories": [{
                    "start_s": 1.0, "duration_s": 5.0,
                    "points": [(-2.0, 0.0), (-1.5, 1.5), (0.0, 2.5), (1.5, 1.5), (2.0, 0.0)],
                }],
                "actions": [
                    {"name": "POPPING1", "start_s": 1.0, "duration_s": 3.0},
                    {"name": "POPPING2", "start_s": 4.5, "duration_s": 2.5},
                ],
            },
            "Robot_2": {
                "id": 2,
                "trajectories": [{
                    "start_s": 1.5, "duration_s": 5.0,
                    "points": [(2.0, 0.0), (1.5, -1.5), (0.0, -2.5), (-1.5, -1.5), (-2.0, 0.0)],
                }],
                "actions": [
                    {"name": "中华武术", "start_s": 1.5, "duration_s": 4.0},
                ],
            },
        }

    def set_robot_track(self, alias: str, trajectories: List[Dict[str, Any]], actions: List[Dict[str, Any]]) -> None:
        self._robot_tracks[alias] = {
            "trajectories": trajectories,
            "actions": actions,
        }

    def set_robot_tracks(self, tracks: Dict[str, Dict[str, Any]]) -> None:
        """全量设置多机器人编排轨道"""
        self._robot_tracks = dict(tracks)

    def on_player_tick(self, time_ms: int, _external_poses: Optional[dict] = None) -> None:
        poses = self.sample_at_time(time_ms)
        collision_info = self.check_collision_status(poses)
        self.posesUpdated.emit(poses)
        self.collisionDiagnosed.emit(collision_info)

    def sample_at_time(self, time_ms: int) -> Dict[str, AvatarSimulationState]:
        curr_s = max(0.0, time_ms / 1000.0)
        poses: Dict[str, AvatarSimulationState] = {}
        for alias, track in self._robot_tracks.items():
            pose = self._sampler.sample_robot_pose(
                robot_alias=alias,
                current_time_s=curr_s,
                trajectory_blocks=track.get("trajectories", []),
                action_blocks=track.get("actions", []),
            )
            # Annotate active action name
            actions = track.get("actions", [])
            act_name = "STAND"
            for act in actions:
                s_s = float(act.get("start_s", 0.0))
                d_s = float(act.get("duration_s", 1.0))
                if s_s <= curr_s <= s_s + d_s:
                    act_name = str(act.get("name", "STAND"))
                    break
            setattr(pose, "action_name", act_name)
            poses[alias] = pose
        return poses

    def check_collision_status(self, poses: Dict[str, AvatarSimulationState]) -> Dict[str, Any]:
        aliases = sorted(poses.keys())
        if len(aliases) < 2:
            return {"status": "NORMAL", "min_distance": 999.0, "alerts": []}

        min_d = 999.0
        alerts: List[Dict[str, Any]] = []

        for i in range(len(aliases)):
            for j in range(i + 1, len(aliases)):
                a1, a2 = aliases[i], aliases[j]
                p1, p2 = poses[a1], poses[a2]
                dist = math.hypot(p1.x - p2.x, p1.y - p2.y)
                if dist < min_d:
                    min_d = dist
                if dist < self._safe_dist:
                    alerts.append({
                        "level": "BLOCKED", "robots": (a1, a2), "distance": round(dist, 3),
                        "msg": f"机群硬冲突: {a1} 与 {a2} 间距 {dist:.2f}m < {self._safe_dist}m"
                    })
                elif dist < self._warn_dist:
                    alerts.append({
                        "level": "WARNING", "robots": (a1, a2), "distance": round(dist, 3),
                        "msg": f"安全距离预警: {a1} 与 {a2} 间距 {dist:.2f}m < {self._warn_dist}m"
                    })

        status = "NORMAL"
        if any(a["level"] == "BLOCKED" for a in alerts):
            status = "BLOCKED"
        elif any(a["level"] == "WARNING" for a in alerts):
            status = "WARNING"

        return {
            "status": status,
            "min_distance": round(min_d, 3),
            "alerts": alerts,
        }
