"""
@file: src/domain/trajectory/anchor_resolver.py
@brief: 轨迹起点锚定定律解析器与机器人运动学参数采样器
@exports: AnchorResolver, resolve_anchor_pose_at, sample_robot_motion_at
"""
from typing import Any, Dict, List, Tuple
from src.domain.trajectory.anchor_pose_resolver import (
    AnchorPoseResolver,
    resolve_anchor_pose_at,
    sample_robot_motion_at,
)


class AnchorResolver(AnchorPoseResolver):
    """轨迹起点锚定解析器封装"""

    @classmethod
    def resolve_anchor(
        cls,
        robot_id: int,
        target_t: float,
        init_points: List[Dict[str, Any]],
        track_state: List[Dict[str, Any]],
        traj_dict_map: Dict[int, Any]
    ) -> Tuple[float, float, float]:
        return cls.resolve_anchor_pose(robot_id, target_t, init_points, track_state, traj_dict_map)

    @classmethod
    def sample_motion(
        cls,
        robot_id: int,
        t_sec: float,
        init_points: List[Dict[str, Any]],
        track_state: List[Dict[str, Any]],
        traj_dict_map: Dict[int, Any]
    ) -> Dict[str, Any]:
        return cls.sample_robot_world_pose_at(robot_id, t_sec, init_points, track_state, traj_dict_map)


__all__ = [
    "AnchorResolver",
    "resolve_anchor_pose_at",
    "sample_robot_motion_at"
]

