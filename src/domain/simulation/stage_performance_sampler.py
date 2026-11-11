"""
@file: src/domain/simulation/stage_performance_sampler.py
@brief: 机器人时空轨迹连续线性插值与舞蹈全身关节/关键帧姿态解算器
@exports: AvatarSimulationState, StagePerformanceSampler, stage_performance_sampler
"""
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("StagePerformanceSampler")

LINK_NAMES_21 = [
    "pelvis", "spine", "torso_link", "neck", "mid360_link",
    "left_shoulder_pitch_link", "left_elbow_link", "left_wrist_pitch_link", "left_wrist_roll_rubber_hand",
    "right_shoulder_pitch_link", "right_elbow_link", "right_wrist_pitch_link", "right_wrist_roll_rubber_hand",
    "left_hip_pitch_link", "left_knee_link", "left_ankle_pitch_link", "left_ankle_roll_link",
    "right_hip_pitch_link", "right_knee_link", "right_ankle_pitch_link", "right_ankle_roll_link",
]


@dataclass
class AvatarSimulationState:
    """Real-time sampled spatial pose and joint angles for a single robot at time t."""
    timestamp_s: float
    robot_alias: str
    x: float
    y: float
    z: float
    yaw_deg: float
    joint_angles: Dict[str, float] = field(default_factory=dict)
    keyframe_positions: Optional[Dict[str, Tuple[float, float, float]]] = None
    pose_status: str = "NORMAL"
    action_name: str = "STAND"
    trajectory_name: str = ""
    model_missing: bool = False


class StagePerformanceSampler:
    """
    Synchronously samples dual-layer choreo timeline tracks at cursor timestamp t:
    1. Lower Trajectory Blocks -> Spatial waypoint interpolation (x(t), y(t), yaw(t))
    2. Upper Action Blocks -> Real NPZ keyframe interpolation or neutral stand fallback.
    """

    def __init__(self) -> None:
        pass

    def sample_robot_pose(
        self,
        robot_alias: str,
        current_time_s: float,
        trajectory_blocks: List[Dict[str, Any]],
        action_blocks: List[Dict[str, Any]],
    ) -> AvatarSimulationState:
        """Calculate spatial coordinate and joint posture for a robot at time t."""
        world_x, world_y, yaw = self._interpolate_trajectory(current_time_s, trajectory_blocks)
        kf_pos, pose_status, act_name = self._resolve_action_pose(
            current_time_s, action_blocks, world_x, world_y, yaw
        )
        joint_angles = self._resolve_joint_angles(current_time_s, action_blocks)

        traj_name = ""
        for tb in trajectory_blocks:
            s_s = float(tb.get("start_s", 0.0))
            d_s = max(0.1, float(tb.get("duration_s", 1.0)))
            if s_s <= current_time_s <= s_s + d_s:
                traj_name = str(tb.get("name", ""))
                break

        return AvatarSimulationState(
            timestamp_s=current_time_s,
            robot_alias=robot_alias,
            x=world_x,
            y=world_y,
            z=0.0,
            yaw_deg=yaw,
            joint_angles=joint_angles,
            keyframe_positions=kf_pos,
            pose_status=pose_status,
            action_name=act_name,
            trajectory_name=traj_name,
        )

    def _interpolate_trajectory(
        self,
        t: float,
        trajectory_blocks: List[Dict[str, Any]],
    ) -> Tuple[float, float, float]:
        """Linearly interpolate (x, y, yaw) across time-anchored waypoint spline."""
        if not trajectory_blocks:
            return 0.0, 0.0, 0.0

        for block in trajectory_blocks:
            start_s = float(block.get("start_s", 0.0))
            duration_s = max(0.1, float(block.get("duration_s", 1.0)))
            points: List[Tuple[float, float]] = block.get("points", [(0.0, 0.0)])

            if start_s <= t <= start_s + duration_s:
                if len(points) == 1:
                    p = points[0]
                    y_deg = p[2] if len(p) >= 3 else 0.0
                    return p[0], p[1], round(y_deg, 1)

                progress = (t - start_s) / duration_s
                scaled_idx = progress * (len(points) - 1)
                idx0 = int(math.floor(scaled_idx))
                idx1 = min(len(points) - 1, idx0 + 1)
                alpha = scaled_idx - idx0

                p0, p1 = points[idx0], points[idx1]
                x = p0[0] + (p1[0] - p0[0]) * alpha
                y = p0[1] + (p1[1] - p0[1]) * alpha

                if len(p0) >= 3 and len(p1) >= 3:
                    y0, y1 = float(p0[2]), float(p1[2])
                    diff = (y1 - y0 + 180.0) % 360.0 - 180.0
                    yaw = (y0 + diff * alpha) % 360.0
                else:
                    dx = p1[0] - p0[0]
                    dy = p1[1] - p0[1]
                    yaw = math.degrees(math.atan2(dy, dx)) if (abs(dx) > 1e-4 or abs(dy) > 1e-4) else 0.0
                return round(x, 3), round(y, 3), round(yaw, 1)

            elif t > start_s + duration_s:
                last = points[-1] if points else (0.0, 0.0)
                last_yaw = last[2] if len(last) >= 3 else 0.0
                return last[0], last[1], round(last_yaw, 1)

        first_pts = trajectory_blocks[0].get("points", [(0.0, 0.0)])
        first_yaw = first_pts[0][2] if len(first_pts[0]) >= 3 else 0.0
        return first_pts[0][0], first_pts[0][1], round(first_yaw, 1)

    def _resolve_action_pose(
        self,
        t: float,
        action_blocks: List[Dict[str, Any]],
        world_x: float,
        world_y: float,
        yaw_deg: float,
    ) -> Tuple[Optional[Dict[str, Tuple[float, float, float]]], str, str]:
        """Interpolate verified NPZ keyframe positions or fallback to neutral stand."""
        if not action_blocks:
            return None, "STAND_FALLBACK", "STAND"

        for block in action_blocks:
            start_s = float(block.get("start_s", 0.0))
            duration_s = max(0.1, float(block.get("duration_s", 1.0)))
            act_name = str(block.get("name", "ACTION"))

            if start_s <= t <= start_s + duration_s:
                pos_arr = block.get("npz_positions")
                is_verified = bool(block.get("is_verified", False))
                if not is_verified or pos_arr is None or len(pos_arr) == 0:
                    return None, "POSE_UNAVAILABLE", act_name

                fps = float(block.get("fps", 50.0))
                t_rel = t - start_s
                n_frames = len(pos_arr)
                frame_float = max(0.0, min(float(n_frames - 1), t_rel * fps))
                idx0 = int(math.floor(frame_float))
                idx1 = min(n_frames - 1, idx0 + 1)
                alpha = frame_float - idx0

                interp = (1.0 - alpha) * pos_arr[idx0] + alpha * pos_arr[idx1]
                yaw_rad = math.radians(yaw_deg)
                cy, sy = math.cos(yaw_rad), math.sin(yaw_rad)

                kf_dict: Dict[str, Tuple[float, float, float]] = {}
                for k_idx, link_name in enumerate(LINK_NAMES_21):
                    if k_idx < interp.shape[0]:
                        lx, ly, lz = float(interp[k_idx, 0]), float(interp[k_idx, 1]), float(interp[k_idx, 2])
                        wx = round(world_x + lx * cy - ly * sy, 3)
                        wy = round(world_y + lx * sy + ly * cy, 3)
                        wz = round(lz, 3)
                        kf_dict[link_name] = (wx, wy, wz)
                return kf_dict, "NORMAL", act_name

        return None, "STAND_FALLBACK", "STAND"

    def _resolve_joint_angles(
        self,
        t: float,
        action_blocks: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """Neutral stand posture angles (deterministic zero values, zero fake waves)."""
        return {
            "waist_yaw_joint": 0.0,
            "left_shoulder_pitch_joint": 0.0,
            "right_shoulder_pitch_joint": 0.0,
            "left_elbow_joint": 0.0,
            "right_elbow_joint": 0.0,
            "left_knee_joint": 0.0,
            "right_knee_joint": 0.0,
        }


stage_performance_sampler = StagePerformanceSampler()
