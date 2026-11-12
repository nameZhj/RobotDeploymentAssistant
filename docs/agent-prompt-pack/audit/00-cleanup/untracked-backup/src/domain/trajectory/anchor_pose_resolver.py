"""
@file: src/domain/trajectory/anchor_pose_resolver.py
@brief: 轨迹起点锚定定律解析器与任意时刻多机世界坐标采样器
@exports: AnchorPoseResolver, sample_robot_world_pose_at, resolve_anchor_pose_at, sample_robot_motion_at, anchor_pose_resolver
"""
import math
from typing import Any, Dict, List, Optional, Tuple, Union
from src.domain.trajectory.trajectory_compiler import TrajectoryCompiler


class AnchorPoseResolver:
    """严格实现轨迹起点锚定定律：后序轨迹/静止姿态始终锚定在前序最近轨迹终点"""

    @classmethod
    def resolve_anchor_pose(
        cls,
        robot_id: int,
        target_t: float,
        init_points: List[Dict[str, Any]],
        track_state: List[Dict[str, Any]],
        traj_dict_map: Dict[int, Any]
    ) -> Tuple[float, float, float]:
        traj_blocks = [
            b for b in track_state
            if int(b.get("robot_id", 0)) == int(robot_id)
            and int(b.get("ignored", 0)) == 0
            and str(b.get("type", "")) == "trajectory"
            and float(b.get("end_time", 0.0)) <= float(target_t) + 1e-5
        ]

        if traj_blocks:
            traj_blocks.sort(key=lambda b: float(b.get("end_time", 0.0)))
            last_blk = traj_blocks[-1]
            traj_no = int(last_blk.get("no", 0))
            raw_data = traj_dict_map.get(traj_no)

            pts: List[Tuple[float, float, float, float]] = []
            if isinstance(raw_data, str):
                pts = TrajectoryCompiler.parse_trajectory_data(raw_data)
            elif isinstance(raw_data, list):
                pts = raw_data

            if pts:
                last_pt = pts[-1]
                return float(last_pt[1]), float(last_pt[2]), float(last_pt[3])

        for pt in init_points:
            if int(pt.get("robot_id", 0)) == int(robot_id):
                return float(pt.get("x", 0.0)), float(pt.get("y", 0.0)), float(pt.get("yaw", 0.0))

        return 0.0, 0.0, 0.0

    @classmethod
    def sample_robot_world_pose_at(
        cls,
        robot_id: int,
        t_sec: float,
        init_points: List[Dict[str, Any]],
        track_state: List[Dict[str, Any]],
        traj_dict_map: Dict[int, Any]
    ) -> Dict[str, Any]:
        active_traj = next((
            b for b in track_state
            if int(b.get("robot_id", 0)) == int(robot_id)
            and int(b.get("ignored", 0)) == 0
            and str(b.get("type", "")) == "trajectory"
            and float(b.get("start_time", 0.0)) <= float(t_sec) <= float(b.get("end_time", 0.0))
        ), None)

        if active_traj:
            traj_no = int(active_traj.get("no", 0))
            raw_data = traj_dict_map.get(traj_no)
            pts: List[Tuple[float, float, float, float]] = []
            if isinstance(raw_data, str):
                pts = TrajectoryCompiler.parse_trajectory_data(raw_data)
            elif isinstance(raw_data, list):
                pts = raw_data

            if pts:
                t_start = float(active_traj.get("start_time", 0.0))
                t_end = float(active_traj.get("end_time", 0.0))
                duration = max(1e-4, t_end - t_start)
                t_local = max(0.0, min(float(t_sec) - t_start, duration))
                ratio = t_local / duration

                n_pts = len(pts)
                idx_f = ratio * (n_pts - 1)
                idx_i = min(int(idx_f), max(0, n_pts - 2))
                alpha = idx_f - idx_i if n_pts > 1 else 0.0

                p0 = pts[idx_i]
                p1 = pts[min(idx_i + 1, n_pts - 1)]

                x = p0[1] + alpha * (p1[1] - p0[1])
                y = p0[2] + alpha * (p1[2] - p0[2])

                dyaw = (p1[3] - p0[3] + 180.0) % 360.0 - 180.0
                yaw = (p0[3] + alpha * dyaw + 180.0) % 360.0 - 180.0

                step_dist = math.hypot(p1[1] - p0[1], p1[2] - p0[2])
                step_dt = duration / max(1, n_pts - 1)
                spd = step_dist / max(step_dt, 1e-4)

                yaw_rad = math.radians(yaw)
                vx = spd * math.cos(yaw_rad)
                vy = spd * math.sin(yaw_rad)
                v = math.hypot(vx, vy)
                omega = dyaw / max(step_dt, 1e-4)

                return {
                    "x": round(float(x), 4),
                    "y": round(float(y), 4),
                    "yaw": round(float(yaw), 2),
                    "vx": round(float(vx), 3),
                    "vy": round(float(vy), 3),
                    "v": round(float(v), 3),
                    "omega": round(float(omega), 3),
                    "is_moving": True,
                    "active_traj_no": traj_no
                }

        ax, ay, ayaw = cls.resolve_anchor_pose(robot_id, t_sec, init_points, track_state, traj_dict_map)
        return {
            "x": round(float(ax), 4),
            "y": round(float(ay), 4),
            "yaw": round(float(ayaw), 2),
            "vx": 0.0,
            "vy": 0.0,
            "v": 0.0,
            "omega": 0.0,
            "is_moving": False,
            "active_traj_no": None
        }


def resolve_anchor_pose_at(
    robot_id: int,
    t_sec: float = 0.0,
    init_points: Optional[List[Dict[str, Any]]] = None,
    track_state: Optional[List[Dict[str, Any]]] = None,
    traj_map: Optional[Dict[int, Any]] = None,
    **kwargs: Any
) -> Tuple[float, float, float]:
    mapping = traj_map if traj_map is not None else kwargs.get("traj_dict_map", {})
    time_val = t_sec if "t_sec" in kwargs or t_sec != 0.0 else kwargs.get("target_t", t_sec)
    return AnchorPoseResolver.resolve_anchor_pose(
        robot_id=robot_id,
        target_t=time_val,
        init_points=init_points or [],
        track_state=track_state or [],
        traj_dict_map=mapping
    )


def sample_robot_motion_at(
    robot_id: int,
    t_sec: float = 0.0,
    init_points: Optional[List[Dict[str, Any]]] = None,
    track_state: Optional[List[Dict[str, Any]]] = None,
    traj_map: Optional[Dict[int, Any]] = None,
    **kwargs: Any
) -> Dict[str, Any]:
    mapping = traj_map if traj_map is not None else kwargs.get("traj_dict_map", {})
    return AnchorPoseResolver.sample_robot_world_pose_at(
        robot_id=robot_id,
        t_sec=t_sec,
        init_points=init_points or [],
        track_state=track_state or [],
        traj_dict_map=mapping
    )


sample_robot_world_pose_at = AnchorPoseResolver.sample_robot_world_pose_at
anchor_pose_resolver = AnchorPoseResolver()

