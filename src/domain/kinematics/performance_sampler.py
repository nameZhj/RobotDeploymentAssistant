"""
@file: src/domain/kinematics/performance_sampler.py
@brief: 时间轴全状态 3D 走位移动、双足步态与全身舞蹈动作混合采样器
@exports: StagePerformanceSampler, sample_robot_performance
"""
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from src.domain.kinematics.urdf_fk_solver import ForwardKinematicsSolver
from src.domain.trajectory.anchor_resolver import sample_robot_motion_at


class StagePerformanceSampler:
    """结合时间轴双子层排布与样条插值，输出任意时刻多机世界坐标与骨骼矩阵"""

    def __init__(self, fk_solver: Optional[ForwardKinematicsSolver] = None) -> None:
        self.fk = fk_solver or ForwardKinematicsSolver()

    @staticmethod
    def generate_walk_gait(t_sec: float, v: float, omega: float = 0.0) -> Tuple[Dict[str, float], float]:
        phi = 2.0 * math.pi * 1.6 * t_sec
        spd = max(abs(v), abs(omega) * 0.4)
        stride = 0.45 * min(1.0, max(0.1, spd / 1.0)) * math.sin(phi)
        roll_sway = 0.05 * math.sin(phi)
        z_offset = -0.025 * abs(math.sin(phi))
        joints = {
            "left_hip_pitch_joint": stride,
            "right_hip_pitch_joint": -stride,
            "left_hip_roll_joint": roll_sway,
            "right_hip_roll_joint": -roll_sway,
            "left_knee_joint": max(0.0, -1.2 * stride),
            "right_knee_joint": max(0.0, 1.2 * stride),
            "left_ankle_pitch_joint": -0.5 * stride,
            "right_ankle_pitch_joint": 0.5 * stride,
            "left_shoulder_pitch_joint": -0.35 * math.sin(phi),
            "right_shoulder_pitch_joint": 0.35 * math.sin(phi),
            "left_elbow_joint": 0.35,
            "right_elbow_joint": 0.35
        }
        return joints, z_offset

    @staticmethod
    def generate_dance_angles(action_name: str, local_t: float) -> Dict[str, float]:
        """Deterministic stand/action fallback posture without sine wave pseudo-motion."""
        act = str(action_name).upper()
        q: Dict[str, float] = {
            "waist_yaw_joint": 0.0,
            "left_shoulder_pitch_joint": 0.0,
            "right_shoulder_pitch_joint": 0.0,
            "left_shoulder_roll_joint": 0.0,
            "right_shoulder_roll_joint": 0.0,
            "left_elbow_joint": 0.0,
            "right_elbow_joint": 0.0,
            "left_hip_pitch_joint": 0.0,
            "right_hip_pitch_joint": 0.0,
            "left_hip_roll_joint": 0.0,
            "right_hip_roll_joint": 0.0,
            "left_knee_joint": 0.0,
            "right_knee_joint": 0.0,
            "left_ankle_pitch_joint": 0.0,
            "right_ankle_pitch_joint": 0.0,
        }
        if "芭蕾" in act or "BALLET" in act:
            q.update({
                "left_shoulder_pitch_joint": -1.1,
                "right_shoulder_pitch_joint": -1.1,
                "left_shoulder_roll_joint": 0.8,
                "right_shoulder_roll_joint": -0.8,
                "left_knee_joint": 0.2,
                "right_knee_joint": 0.1,
            })
        elif "POPPING" in act:
            q.update({
                "left_shoulder_pitch_joint": -0.5,
                "right_shoulder_pitch_joint": -0.5,
                "left_elbow_joint": 0.7,
                "right_elbow_joint": 0.7,
            })
        return q

    def sample_robot_full_state(
        self, robot_id: int, t_sec: float, init_points: List[Dict[str, Any]],
        track_state: List[Dict[str, Any]], traj_map: Dict[int, Any]
    ) -> Dict[str, Any]:
        motion = sample_robot_motion_at(robot_id, t_sec, init_points, track_state, traj_map)
        rx, ry, ryaw = motion["x"], motion["y"], motion["yaw"]
        v, omega = motion.get("v", 0.0), motion.get("omega", 0.0)
        is_moving = abs(v) > 0.02 or abs(omega) > 0.05 or bool(motion.get("is_moving", False))

        active_action = next((
            b for b in track_state if int(b.get("robot_id", 0)) == int(robot_id)
            and int(b.get("ignored", 0)) == 0 and str(b.get("type", "")) == "active"
            and float(b.get("start_time", 0.0)) <= float(t_sec) <= float(b.get("end_time", 0.0))
        ), None)

        blended_q: Dict[str, float] = {}
        rz = 0.75
        if is_moving:
            walk_q, z_off = self.generate_walk_gait(t_sec, v, omega)
            blended_q.update(walk_q)
            rz += z_off

        if active_action:
            local_t = float(t_sec) - float(active_action.get("start_time", 0.0))
            act_name = str(active_action.get("name", "POPPING"))
            dance_q = self.generate_dance_angles(act_name, local_t)
            if is_moving:
                leg_keys = {"hip", "knee", "ankle"}
                for k, val in dance_q.items():
                    if not any(lk in k for lk in leg_keys):
                        blended_q[k] = val
            else:
                blended_q.update(dance_q)

        fk_res = self.fk.solve_full_body_fk((rx, ry, rz), ryaw, blended_q)
        return {
            "robot_id": robot_id, "time_sec": round(float(t_sec), 3),
            "world_pos": (rx, ry, round(float(rz), 4)), "yaw_deg": ryaw,
            "v": v, "omega": omega, "is_moving": is_moving,
            "active_action": active_action.get("name") if active_action else None,
            "active_traj_no": motion.get("active_traj_no"), "joint_angles": blended_q,
            "link_matrices": fk_res["link_world_matrices"], "joint_coords": fk_res["joint_coords"]
        }


def sample_robot_performance(*args, **kwargs) -> Dict[str, Any]:
    return StagePerformanceSampler().sample_robot_full_state(*args, **kwargs)
