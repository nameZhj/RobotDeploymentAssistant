"""
@file: src/ui/stage3d/stage_viewport_3d.py
@brief: 3D 透视数字演播舞台视口：点云底图、多机骨骼透视、防撞态势及相机控制
@exports: StageViewport3D
"""
import logging
import math
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from src.domain.simulation.stage_performance_sampler import AvatarSimulationState
from src.ui.stage3d.preview_performance_monitor import PreviewPerformanceMonitor
from src.ui.stage3d.robot_avatar_3d_painter import RobotAvatar3DPainter

logger = logging.getLogger("StageViewport3D")


class StageViewport3D(QWidget):
    """3D 透视舞台视口，支持轨道相机、LOD 双模骨骼、多机走位与时空防撞安全呈现"""

    def __init__(self, parent: Optional[QWidget] = None, controller: Optional[Any] = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._yaw_deg = -45.0
        self._pitch_deg = -30.0
        self._distance = 18.0
        self._target_x = 0.0
        self._target_y = 0.0
        self._target_z = 0.6

        self._is_orbiting = False
        self._is_panning = False
        self._last_mouse_pos = QPointF()

        self._grid_visible = True
        self._render_mode = "ECO"
        self._collision_alerts: Dict[str, str] = {}

        self._trajectories: Dict[str, List[Tuple[float, float]]] = {}
        self._robot_meta: Dict[str, Dict[str, Any]] = {
            "Robot_1": {"id": 1, "color": "#38BDF8"},
            "Robot_2": {"id": 2, "color": "#10B981"},
        }
        self._robot_poses: Dict[str, AvatarSimulationState] = {
            "Robot_1": AvatarSimulationState(0.0, "Robot_1", -2.0, 0.0, 0.0, 0.0),
            "Robot_2": AvatarSimulationState(0.0, "Robot_2", 2.0, 0.0, 0.0, 180.0),
        }
        self._point_cloud: List[Tuple[float, float, float]] = []

        self.avatar_painter = RobotAvatar3DPainter(mode="ECO")
        self.perf_monitor = PreviewPerformanceMonitor()

        if self.controller and hasattr(self.controller, "playhead_updated"):
            self.controller.playhead_updated.connect(self._on_playhead_updated)

    def set_trajectories(self, trajectories: Dict[str, List[Tuple[float, float]]]) -> None:
        """更新 3D 舞台各机器人地面轨迹路径线"""
        self._trajectories = dict(trajectories)
        self.update()

    def set_point_cloud(self, points: Optional[List[Tuple[float, float, float]]]) -> None:
        """更新 3D 舞台本地 PCD 地图点云数据"""
        self._point_cloud = list(points) if points else []
        self.update()

    def clear_point_cloud(self) -> None:
        """清空点云，恢复 3D 纯净空状态"""
        self._point_cloud = []
        self.update()

    def set_render_mode(self, mode: str) -> None:
        self._render_mode = mode.upper()
        self.avatar_painter.set_render_mode(self._render_mode)
        self.update()

    def set_collision_diagnostics(self, diag_info: Dict[str, Any]) -> None:
        self._collision_alerts.clear()
        for alert in diag_info.get("alerts", []):
            level = alert.get("level", "WARNING")
            for r in alert.get("robots", ()):
                self._collision_alerts[str(r)] = level
        self.update()

    def update_robot_poses(self, poses: Dict[str, AvatarSimulationState]) -> None:
        self._robot_poses.update(poses)
        self.update()

    def set_robot_poses(self, poses: Dict[str, AvatarSimulationState]) -> None:
        """全量覆盖机器人位姿快照"""
        self._robot_poses = dict(poses)
        self.update()

    def clear_robot_poses(self) -> None:
        """清空所有机器人位姿，恢复空项目提示态"""
        self._robot_poses.clear()
        self.update()

    def focus_robot(self, alias: str) -> None:
        if alias in self._robot_poses:
            p = self._robot_poses[alias]
            self._target_x, self._target_y = p.x, p.y
            self.update()

    def reset_camera(self) -> None:
        self._yaw_deg, self._pitch_deg, self._distance = -45.0, -30.0, 18.0
        self._target_x, self._target_y, self._target_z = 0.0, 0.0, 0.6
        self.update()

    def set_grid_visible(self, visible: bool) -> None:
        self._grid_visible = visible
        self.update()

    def _on_playhead_updated(self, t: float, poses: dict) -> None:
        for rid, data in poses.items():
            alias = f"Robot_{rid}"
            x, y, yaw, act_name = data[0], data[1], data[2], data[3]
            state = AvatarSimulationState(t, alias, x, y, 0.0, math.degrees(yaw))
            setattr(state, "action_name", act_name)
            self._robot_poses[alias] = state
        self.update()

    def _project(self, x: float, y: float, z: float) -> Optional[Tuple[float, float, float]]:
        dx, dy, dz = x - self._target_x, y - self._target_y, z - self._target_z
        ryaw, rpitch = math.radians(self._yaw_deg), math.radians(self._pitch_deg)
        x1 = dx * math.cos(ryaw) - dy * math.sin(ryaw)
        y1 = dx * math.sin(ryaw) + dy * math.cos(ryaw)
        y2 = y1 * math.cos(rpitch) - dz * math.sin(rpitch)
        z2 = y1 * math.sin(rpitch) + dz * math.cos(rpitch)
        depth = self._distance + y2
        if depth <= 0.5:
            return None
        scale = (self.height() * 1.1) / depth
        return self.width() * 0.5 + x1 * scale, self.height() * 0.5 - z2 * scale, depth

    def paintEvent(self, event) -> None:
        t0 = time.perf_counter()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(0, 0, self.width(), self.height(), QColor("#0B0F19"))

        if self._grid_visible:
            self._draw_ground_grid(p)
        self._draw_point_cloud(p)
        self._draw_trajectories(p)
        self._draw_robots(p)
        self._draw_xyz_indicator(p)

        dt_ms = (time.perf_counter() - t0) * 1000.0
        self.perf_monitor.record_frame(dt_ms)

    def _draw_ground_grid(self, p: QPainter) -> None:
        p.setPen(QPen(QColor("#1E293B"), 1))
        for i in range(-10, 11, 2):
            p1, p2 = self._project(float(i), -10.0, 0.0), self._project(float(i), 10.0, 0.0)
            if p1 and p2:
                p.drawLine(QPointF(p1[0], p1[1]), QPointF(p2[0], p2[1]))
            p3, p4 = self._project(-10.0, float(i), 0.0), self._project(10.0, float(i), 0.0)
            if p3 and p4:
                p.drawLine(QPointF(p3[0], p3[1]), QPointF(p4[0], p4[1]))

    def _draw_point_cloud(self, p: QPainter) -> None:
        p.setPen(Qt.NoPen)
        for px, py, pz in self._point_cloud:
            pt = self._project(px, py, pz)
            if pt:
                p.setBrush(QBrush(QColor(56, 189, 248, 160)))
                p.drawEllipse(QPointF(pt[0], pt[1]), 3, 3)

    def _draw_trajectories(self, p: QPainter) -> None:
        for alias, waypoints in self._trajectories.items():
            meta = self._robot_meta.get(alias, {"color": "#38BDF8"})
            p.setPen(QPen(QColor(meta["color"]), 2, Qt.DashLine))
            screen_pts = [self._project(x, y, 0.0) for x, y in waypoints]
            valid_pts = [pt for pt in screen_pts if pt]
            for i in range(len(valid_pts) - 1):
                p.drawLine(QPointF(valid_pts[i][0], valid_pts[i][1]), QPointF(valid_pts[i + 1][0], valid_pts[i + 1][1]))

    def _draw_robots(self, p: QPainter) -> None:
        if not self._robot_poses:
            p.setFont(QFont("Segoe UI", 10, QFont.Bold))
            p.setPen(QColor("#64748B"))
            rect = QRectF(0, self.height() / 2.0 - 20, self.width(), 40)
            p.drawText(rect, Qt.AlignCenter, "【3D 虚拟预演】等待时间轴编排数据 / 当前无活动机器人")
            return

        palette = ["#38BDF8", "#10B981", "#F59E0B", "#EC4899", "#8B5CF6", "#14B8A6"]
        for idx, (alias, pose) in enumerate(self._robot_poses.items()):
            meta = self._robot_meta.get(alias)
            if not meta:
                color = palette[idx % len(palette)]
                int_id = int(alias.split("_")[1]) if "_" in alias and alias.split("_")[1].isdigit() else (idx + 1)
                meta = {"id": int_id, "color": color}
                self._robot_meta[alias] = meta

            act_name = getattr(pose, "action_name", "STAND")
            is_walk = ("STAND" not in act_name and "轨" in act_name) or ("TRAJ" in act_name)
            lvl = self._collision_alerts.get(alias, "NORMAL")
            is_missing = getattr(pose, "model_missing", False)
            kf_pos = getattr(pose, "keyframe_positions", None)
            p_status = getattr(pose, "pose_status", "NORMAL")
            self.avatar_painter.render_robot(
                p=p,
                project_fn=self._project,
                base_pose=(pose.x, pose.y, pose.z, math.radians(pose.yaw_deg)),
                action_name=act_name,
                t_sec=pose.timestamp_s,
                color_hex=meta.get("color", "#38BDF8"),
                robot_id=str(meta.get("id", 1)),
                is_walking=is_walk,
                collision_level=lvl,
                joint_angles_override=pose.joint_angles,
                keyframe_positions=kf_pos,
                pose_status=p_status,
                is_model_missing=is_missing,
            )

    def _draw_xyz_indicator(self, p: QPainter) -> None:
        cx, cy = self.width() - 50.0, self.height() - 50.0
        ryaw, rpitch = math.radians(self._yaw_deg), math.radians(self._pitch_deg)
        axes = [((1.0, 0.0, 0.0), "#EF4444", "X"), ((0.0, 1.0, 0.0), "#10B981", "Y"), ((0.0, 0.0, 1.0), "#3B82F6", "Z")]
        for (vx, vy, vz), col_hex, label in axes:
            x1 = vx * math.cos(ryaw) - vy * math.sin(ryaw)
            y1 = vx * math.sin(ryaw) + vy * math.cos(ryaw)
            z2 = y1 * math.sin(rpitch) + vz * math.cos(rpitch)
            ex, ey = cx + x1 * 28.0, cy - z2 * 28.0
            p.setPen(QPen(QColor(col_hex), 2))
            p.drawLine(QPointF(cx, cy), QPointF(ex, ey))
            p.setFont(QFont("Segoe UI", 7, QFont.Bold))
            p.drawText(QPointF(ex + 3, ey + 3), label)

    def mousePressEvent(self, event) -> None:
        self._last_mouse_pos = event.pos()
        if event.button() == Qt.LeftButton:
            self._is_orbiting = not (event.modifiers() & Qt.AltModifier)
            self._is_panning = bool(event.modifiers() & Qt.AltModifier)
        elif event.button() in (Qt.RightButton, Qt.MiddleButton):
            self._is_panning = True

    def mouseMoveEvent(self, event) -> None:
        dx = event.x() - self._last_mouse_pos.x()
        dy = event.y() - self._last_mouse_pos.y()
        self._last_mouse_pos = event.pos()
        if self._is_orbiting:
            self._yaw_deg = (self._yaw_deg + dx * 0.4) % 360.0
            self._pitch_deg = max(-85.0, min(-5.0, self._pitch_deg - dy * 0.4))
            self.update()
        elif self._is_panning:
            self._target_x -= dx * 0.02
            self._target_y += dy * 0.02
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        self._is_orbiting = False
        self._is_panning = False

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y() / 120.0
        self._distance = max(4.0, min(45.0, self._distance - delta * 1.5))
        self.update()
