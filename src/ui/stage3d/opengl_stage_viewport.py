"""
自适应 3D 虚拟演示舞台视口
支持 3D 透视网格地面、蓝青色高程渐变点云、XYZ 空间坐标指示器与机器人 3D 走位跳舞渲染
"""
import math
from typing import Any, Dict, List, Optional, Tuple
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QPushButton, QWidget

from src.domain.map.grid_projection_service import GridProjectionService
from src.infrastructure.map.pcd_parser_engine import PcdParserEngine
from src.ui.stage3d.robot_avatar_3d_painter import RobotAvatar3DPainter


class OpenGLStageViewport(QWidget):
    """3D 虚拟舞台视口 (支持 Eco 办公本极速管线与 Pro 独显硬件渲染)"""

    animationToggled = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None, render_mode: str = "ECO") -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.yaw_deg, self.pitch_deg, self.distance = -45.0, -28.0, 16.0
        self.target_x, self.target_y, self.target_z = -5.0, 0.0, 0.6
        self._is_orbiting, self._is_panning = False, False
        self._last_mouse_pos = QPointF()

        self.painter_3d = RobotAvatar3DPainter(mode=render_mode)
        self.robot_states: Dict[str, Dict[str, Any]] = {
            "1": {"x": -2.0, "y": 0.0, "yaw": 0.0, "action": "POPPING1", "color": "#10b981"},
            "2": {"x": 2.0, "y": 0.0, "yaw": 3.14, "action": "芭蕾", "color": "#38bdf8"}
        }
        self.trajectories: Dict[str, List[Tuple[float, float]]] = {}
        self.is_animating = False

        # 加载与生成蓝青色高程点云切片
        raw_cloud = PcdParserEngine.generate_default_point_cloud(num_points=4000)
        # 降采样为 1200 个高亮特征点以保障 60FPS
        step = max(1, len(raw_cloud) // 1200)
        self.point_cloud = raw_cloud[::step]
        self.point_colors = GridProjectionService.compute_height_colors(self.point_cloud)

        self.btn_anim = QPushButton("▷ 展示动画", self)
        self.btn_anim.setStyleSheet(
            "background: #1e293b; color: #38bdf8; border: 1px solid #38bdf8; "
            "padding: 5px 12px; border-radius: 4px; font-weight: bold; font-size: 12px;"
        )
        self.btn_anim.move(14, 14)
        self.btn_anim.clicked.connect(self._toggle_animation)

    def set_render_mode(self, mode: str) -> None:
        self.painter_3d.set_render_mode(mode)
        self.update()

    def set_trajectories(self, trajs: Dict[str, List[Tuple[float, float]]]) -> None:
        self.trajectories = trajs
        self.update()

    def update_robot_states(self, states: Dict[str, Dict[str, Any]]) -> None:
        for rid, s in states.items():
            if rid in self.robot_states:
                self.robot_states[rid].update(s)
            else:
                self.robot_states[rid] = s
        self.update()

    def _toggle_animation(self) -> None:
        self.is_animating = not self.is_animating
        self.btn_anim.setText("❚❚ 暂停" if self.is_animating else "▷ 展示动画")
        self.animationToggled.emit(self.is_animating)

    def project(self, x: float, y: float, z: float) -> Optional[Tuple[float, float, float]]:
        """将 3D 世界坐标 (x, y, z) 透视投影为视口像素坐标 (sx, sy, depth)"""
        dx, dy, dz = x - self.target_x, y - self.target_y, z - self.target_z
        ryaw, rpitch = math.radians(self.yaw_deg), math.radians(self.pitch_deg)
        x1 = dx * math.cos(ryaw) - dy * math.sin(ryaw)
        y1 = dx * math.sin(ryaw) + dy * math.cos(ryaw)
        y2 = y1 * math.cos(rpitch) - dz * math.sin(rpitch)
        z2 = y1 * math.sin(rpitch) + dz * math.cos(rpitch)
        depth = self.distance + y2
        if depth <= 0.6:
            return None
        scale = (self.height() * 1.05) / depth
        sx = self.width() * 0.5 + x1 * scale
        sy = self.height() * 0.55 - z2 * scale
        return sx, sy, depth

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("#080c14"))

        self._draw_ground_grid(p)
        self._draw_point_cloud(p)
        self._draw_trajectories(p)
        self._draw_robots(p)
        self._draw_axes_indicator(p, w, h)

    def _draw_ground_grid(self, p: QPainter) -> None:
        p.setPen(QPen(QColor(30, 41, 59, 130), 1))
        # 沿 X 轴与 Y 轴绘制地面网格
        for gx in range(-15, 6, 2):
            p0 = self.project(float(gx), -6.0, 0.0)
            p1 = self.project(float(gx), 4.0, 0.0)
            if p0 and p1:
                p.drawLine(int(p0[0]), int(p0[1]), int(p1[0]), int(p1[1]))
        for gy in range(-6, 5, 2):
            p0 = self.project(-15.0, float(gy), 0.0)
            p1 = self.project(5.0, float(gy), 0.0)
            if p0 and p1:
                p.drawLine(int(p0[0]), int(p0[1]), int(p1[0]), int(p1[1]))

    def _draw_point_cloud(self, p: QPainter) -> None:
        if self.point_cloud is None or len(self.point_cloud) == 0:
            return
        for i, pt in enumerate(self.point_cloud):
            proj = self.project(pt[0], pt[1], pt[2])
            if proj is not None:
                rgba = self.point_colors[i]
                c = QColor(int(rgba[0] * 255), int(rgba[1] * 255), int(rgba[2] * 255), 180)
                p.setPen(QPen(c, 2))
                p.drawPoint(int(proj[0]), int(proj[1]))

    def _draw_trajectories(self, p: QPainter) -> None:
        colors = ["#10b981", "#38bdf8", "#fbbf24"]
        for idx, (rid, wps) in enumerate(self.trajectories.items()):
            col = QColor(colors[idx % len(colors)])
            p.setPen(QPen(col, 2, Qt.DashLine))
            for i in range(len(wps) - 1):
                p0 = self.project(wps[i][0], wps[i][1], 0.02)
                p1 = self.project(wps[i + 1][0], wps[i + 1][1], 0.02)
                if p0 and p1:
                    p.drawLine(int(p0[0]), int(p0[1]), int(p1[0]), int(p1[1]))
            # 绘制航点
            p.setBrush(QBrush(col))
            p.setPen(QPen(Qt.white, 1))
            for wp in wps:
                pw = self.project(wp[0], wp[1], 0.02)
                if pw:
                    p.drawEllipse(QPointF(pw[0], pw[1]), 3, 3)

    def _draw_robots(self, p: QPainter) -> None:
        t_sec = 0.0
        for rid, s in sorted(self.robot_states.items(), key=lambda x: -x[1].get("y", 0.0)):
            x = float(s.get("x", 0.0))
            y = float(s.get("y", 0.0))
            yaw = float(s.get("yaw", 0.0))
            action = str(s.get("action", "POPPING1"))
            col = str(s.get("color", "#38bdf8"))
            is_walk = action == "WALK_GAIT" or "WALK" in action.upper()
            self.painter_3d.render_robot(
                p, self.project, (x, y, 0.72, yaw), action, t_sec,
                color_hex=col, robot_id=rid, is_walking=is_walk
            )

    def _draw_axes_indicator(self, p: QPainter, w: int, h: int) -> None:
        """右下角 XYZ 三色坐标指示器"""
        cx, cy = w - 55, h - 55
        p.fillRect(cx - 35, cy - 35, 70, 70, QColor(15, 23, 42, 180))
        ryaw, rpitch = math.radians(self.yaw_deg), math.radians(self.pitch_deg)

        def proj_axis(ax, ay, az):
            x1 = ax * math.cos(ryaw) - ay * math.sin(ryaw)
            y1 = ax * math.sin(ryaw) + ay * math.cos(ryaw)
            z2 = y1 * math.sin(rpitch) + az * math.cos(rpitch)
            return cx + x1 * 26.0, cy - z2 * 26.0

        for col, vec, label in [(QColor("#ef4444"), (1, 0, 0), "X"),
                               (QColor("#22c55e"), (0, 1, 0), "Y"),
                               (QColor("#38bdf8"), (0, 0, 1), "Z")]:
            ex, ey = proj_axis(*vec)
            p.setPen(QPen(col, 2))
            p.drawLine(cx, cy, int(ex), int(ey))
            p.drawText(int(ex + 2), int(ey + 4), label)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._is_orbiting, self._last_mouse_pos = True, event.pos()
        elif event.button() == Qt.RightButton:
            self._is_panning, self._last_mouse_pos = True, event.pos()

    def mouseMoveEvent(self, event) -> None:
        delta = event.pos() - self._last_mouse_pos
        self._last_mouse_pos = event.pos()
        if self._is_orbiting:
            self.yaw_deg += delta.x() * 0.4
            self.pitch_deg = max(-85.0, min(10.0, self.pitch_deg + delta.y() * 0.4))
            self.update()
        elif self._is_panning:
            factor = self.distance * 0.003
            self.target_x -= delta.x() * factor
            self.target_y += delta.y() * factor
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        self._is_orbiting = False
        self._is_panning = False

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = 0.9 if event.angleDelta().y() > 0 else 1.1
        self.distance = max(4.0, min(80.0, self.distance * factor))
        self.update()

