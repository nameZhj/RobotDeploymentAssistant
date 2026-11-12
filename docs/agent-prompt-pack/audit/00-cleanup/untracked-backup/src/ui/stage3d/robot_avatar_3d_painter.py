"""
@file: src/ui/stage3d/robot_avatar_3d_painter.py
@brief: 3D 机器人数字孪生渲染引擎，支持真实关键帧、URDF正向运动学与安全防撞态势
@exports: RobotAvatar3DPainter
"""
import math
from typing import Any, Callable, Dict, List, Optional, Tuple
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen

from src.domain.simulation.dance_motion_library import DanceMotionLibrary
from src.domain.simulation.urdf_fk_solver import UrdfFkSolver


class RobotAvatar3DPainter:
    """3D 机器人化身渲染器：支持正向运动学骨骼、真实关键帧与防撞危险态势"""

    def __init__(self, mode: str = "ECO") -> None:
        self.mode = mode.upper()
        self.fk_solver = UrdfFkSolver()
        self.motion_lib = DanceMotionLibrary()

    def set_render_mode(self, mode: str) -> None:
        self.mode = mode.upper()

    def render_robot(
        self, p: QPainter,
        project_fn: Callable[[float, float, float], Optional[Tuple[float, float, float]]],
        base_pose: Tuple[float, float, float, float],
        action_name: str,
        t_sec: float,
        color_hex: str = "#38BDF8",
        robot_id: str = "1",
        is_walking: bool = False,
        collision_level: str = "NORMAL",
        joint_angles_override: Optional[Dict[str, float]] = None,
        keyframe_positions: Optional[Dict[str, Tuple[float, float, float]]] = None,
        pose_status: str = "NORMAL",
        is_model_missing: bool = False,
    ) -> None:
        x, y, z, yaw = base_pose
        if is_model_missing:
            self._draw_ground_halo_and_shadow(p, project_fn, x, y, "WARNING")
            top_proj = project_fn(x, y, z + 0.8)
            if top_proj is not None:
                self._draw_billboard(p, top_proj[0], top_proj[1], robot_id, "模型缺失", "WARNING", "#EF4444")
            return

        proj_pts: Dict[str, Tuple[float, float, float]] = {}
        if keyframe_positions:
            for name, pos in keyframe_positions.items():
                proj = project_fn(pos[0], pos[1], pos[2])
                if proj is not None:
                    proj_pts[name] = proj
        else:
            joints = joint_angles_override or self.motion_lib.get_motion_frame(action_name, t_sec)
            positions = self.fk_solver.get_link_positions(base_pose, joints)
            for name, pos in positions.items():
                proj = project_fn(pos[0], pos[1], pos[2])
                if proj is not None:
                    proj_pts[name] = proj

        if "pelvis" not in proj_pts:
            self._draw_ground_halo_and_shadow(p, project_fn, x, y, "WARNING")
            top_proj = project_fn(x, y, z + 0.8)
            if top_proj is not None:
                self._draw_billboard(p, top_proj[0], top_proj[1], robot_id, "模型缺失", "WARNING", "#EF4444")
            return

        self._draw_ground_halo_and_shadow(p, project_fn, x, y, collision_level)
        self._draw_skeleton_bones(p, proj_pts, color_hex)
        self._draw_joint_nodes(p, proj_pts, color_hex)
        self._draw_sensor_head(p, proj_pts)

        top_proj = project_fn(x, y, z + 1.15)
        if top_proj is not None:
            display_act = action_name
            if pose_status == "POSE_UNAVAILABLE":
                display_act = f"{action_name} [姿态不可用]"
            elif pose_status == "STAND_FALLBACK" and action_name == "STAND":
                display_act = "标准待机"
            self._draw_billboard(p, top_proj[0], top_proj[1], robot_id, display_act, collision_level, color_hex)

    def _draw_ground_halo_and_shadow(
        self, p: QPainter, project_fn: Callable, x: float, y: float, level: str
    ) -> None:
        shadow_proj = project_fn(x, y, 0.01)
        if shadow_proj is None:
            return

        scale = max(2.0, min(30.0, 180.0 / shadow_proj[2]))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 70)))
        p.drawEllipse(QPointF(shadow_proj[0], shadow_proj[1]), scale * 1.5, scale * 0.8)

        if level in ("WARNING", "BLOCKED"):
            halo_color = QColor("#EF4444" if level == "BLOCKED" else "#F59E0B")
            p.setPen(QPen(halo_color, 2, Qt.DashLine if level == "WARNING" else Qt.SolidLine))
            p.setBrush(QBrush(QColor(halo_color.red(), halo_color.green(), halo_color.blue(), 45)))
            halo_radius_px = scale * 2.8
            p.drawEllipse(QPointF(shadow_proj[0], shadow_proj[1]), halo_radius_px, halo_radius_px * 0.5)

    def _draw_skeleton_bones(
        self, p: QPainter, proj_pts: Dict[str, Tuple[float, float, float]], color_hex: str
    ) -> None:
        bones = [
            ("pelvis", "torso_link", 8), ("torso_link", "mid360_link", 10),
            ("pelvis", "left_hip_pitch_link", 6), ("left_hip_pitch_link", "left_knee_link", 5),
            ("left_knee_link", "left_ankle_pitch_link", 5), ("left_ankle_pitch_link", "left_ankle_roll_link", 4),
            ("pelvis", "right_hip_pitch_link", 6), ("right_hip_pitch_link", "right_knee_link", 5),
            ("right_knee_link", "right_ankle_pitch_link", 5), ("right_ankle_pitch_link", "right_ankle_roll_link", 4),
            ("torso_link", "left_shoulder_pitch_link", 5), ("left_shoulder_pitch_link", "left_elbow_link", 4),
            ("left_elbow_link", "left_wrist_roll_rubber_hand", 4),
            ("torso_link", "right_shoulder_pitch_link", 5), ("right_shoulder_pitch_link", "right_elbow_link", 4),
            ("right_elbow_link", "right_wrist_roll_rubber_hand", 4),
        ]
        main_color = QColor(color_hex)
        bone_color = QColor("#0F172A" if self.mode == "PRO" else "#1E293B")

        for p1_name, p2_name, w_base in bones:
            if p1_name in proj_pts and p2_name in proj_pts:
                p1, p2 = proj_pts[p1_name], proj_pts[p2_name]
                depth_avg = (p1[2] + p2[2]) / 2.0
                pen_w = max(2.0, min(14.0, (w_base * 18.0) / depth_avg))
                p.setPen(QPen(bone_color, pen_w, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(int(p1[0]), int(p1[1]), int(p2[0]), int(p2[1]))
                if self.mode == "PRO":
                    p.setPen(QPen(main_color.lighter(130), max(1.0, pen_w * 0.4), Qt.SolidLine, Qt.RoundCap))
                    p.drawLine(int(p1[0]), int(p1[1]), int(p2[0]), int(p2[1]))

    def _draw_joint_nodes(
        self, p: QPainter, proj_pts: Dict[str, Tuple[float, float, float]], color_hex: str
    ) -> None:
        main_color = QColor(color_hex)
        for k, pt in proj_pts.items():
            rad = max(2.0, min(10.0, 55.0 / pt[2]))
            p.setBrush(QBrush(main_color))
            p.setPen(QPen(Qt.white, 1))
            p.drawEllipse(QPointF(pt[0], pt[1]), rad, rad)

    def _draw_sensor_head(self, p: QPainter, proj_pts: Dict[str, Tuple[float, float, float]]) -> None:
        head_proj = proj_pts.get("mid360_link") or proj_pts.get("torso_link")
        if head_proj:
            hr = max(4.0, min(14.0, 90.0 / head_proj[2]))
            p.setBrush(QBrush(QColor("#0EA5E9")))
            p.setPen(QPen(Qt.white, 1.5))
            p.drawEllipse(QPointF(head_proj[0], head_proj[1] - hr * 0.8), hr, hr)

    def _draw_billboard(
        self, p: QPainter, sx: float, sy: float, robot_id: str, action: str, level: str, color_hex: str
    ) -> None:
        p.setFont(QFont("Segoe UI", 8, QFont.Bold))
        status_suffix = f" [{level}]" if level != "NORMAL" else ""
        text = f"ID: {robot_id} ({action}){status_suffix}"
        badge_w, badge_h = max(90, len(text) * 7 + 10), 22
        rect = QRectF(sx - badge_w / 2.0, sy - badge_h - 6, badge_w, badge_h)

        border_color = QColor("#EF4444" if level == "BLOCKED" else ("#F59E0B" if level == "WARNING" else color_hex))
        p.setBrush(QBrush(QColor(15, 23, 42, 220)))
        p.setPen(QPen(border_color, 1.5))
        p.drawRoundedRect(rect, 4, 4)

        p.setPen(QColor("#EF4444" if level == "BLOCKED" else ("#FBBF24" if level == "WARNING" else "#F8FAFC")))
        p.drawText(rect, Qt.AlignCenter, text)
