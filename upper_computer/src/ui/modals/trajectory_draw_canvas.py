# @file: src/ui/modals/trajectory_draw_canvas.py
# @brief: Interactive 2D spline & freehand sketch canvas inside TrajectoryEditorModal with live Catmull-Rom preview.
# @exports: TrajectoryDrawCanvas

from __future__ import annotations

import math
from typing import List, Optional, Tuple
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen, QPolygonF, QWheelEvent
from PySide6.QtWidgets import QWidget

from src.domain.trajectory_entities import ControlPoint2D, TrajectoryEntity
from src.math.trajectory_sampler import sample_trajectory_50fps
from src.services.studio_state_service import StudioStateService
from src.ui.choreography.stage_painters import (
    paint_grid_and_stage,
    paint_occupancy_map,
    screen_to_world,
    world_to_screen,
)
from src.ui.design_system.tokens import C_ACCENT, C_OK, C_WARN


def _rdp_simplify(pts: List[Tuple[float, float]], eps: float = 0.22) -> List[Tuple[float, float]]:
    """Reduce freehand stroke samples into smooth sparse spline control points."""
    if len(pts) < 3:
        return pts
    ax, ay = pts[0]
    bx, by = pts[-1]
    dx, dy = bx - ax, by - ay
    denom = math.hypot(dx, dy)
    max_d, idx = -1.0, 0
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        d = math.hypot(px - ax, py - ay) if denom < 1e-6 else abs(dy * px - dx * py + bx * ay - by * ax) / denom
        if d > max_d:
            max_d, idx = d, i
    if max_d > eps:
        left = _rdp_simplify(pts[: idx + 1], eps)
        right = _rdp_simplify(pts[idx:], eps)
        return left[:-1] + right
    return [pts[0], pts[-1]]


class TrajectoryDrawCanvas(QWidget):
    """2D stage sketchpad supporting click-point placement, freehand brush, and waypoint drag."""

    pointsChanged = Signal()

    def __init__(self, state: StudioStateService, traj: TrajectoryEntity, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.traj = traj
        self.tool_mode: str = "click"  # "click" | "brush" | "move"
        self.ppm: float = 42.0
        self.pan_offset = QPointF(0.0, 0.0)
        self._drag_idx: Optional[int] = None
        self._pan_last: Optional[QPointF] = None
        self._stroke_pts: List[Tuple[float, float]] = []
        self._preview_pts = []
        self._grid_img: Optional[QImage] = None
        m = state.active_map
        if m and m.grid_png_path:
            self._grid_img = QImage(m.grid_png_path)
            self._grid_meta = (m.origin_x, m.origin_y, max(0.005, m.resolution))
        else:
            self._grid_meta = (0.0, 0.0, 0.05)

        self.setMinimumSize(420, 340)
        self.setMouseTracking(True)
        self.refresh_preview()

    def set_tool(self, mode: str) -> None:
        self.tool_mode = mode

    def clear_points(self) -> None:
        self.traj.control_points.clear()
        self.refresh_preview()
        self.pointsChanged.emit()

    def undo_point(self) -> None:
        if self.traj.control_points:
            self.traj.control_points.pop()
            self.refresh_preview()
            self.pointsChanged.emit()

    def refresh_preview(self) -> None:
        arr, _ = sample_trajectory_50fps(self.traj)
        self._preview_pts = arr
        self.update()

    def _origin_px(self) -> QPointF:
        return QPointF(self.width() * 0.5 + self.pan_offset.x(), self.height() * 0.5 + self.pan_offset.y())

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        origin = self._origin_px()
        paint_grid_and_stage(
            p, self.width(), self.height(), origin, self.ppm,
            float(self.state.scene.stage_width or 12.0),
            float(self.state.scene.stage_height or 8.0),
        )
        ox, oy, res = self._grid_meta
        paint_occupancy_map(p, self._grid_img, ox, oy, res, origin, self.ppm)

        # Sampled spline polyline
        if len(self._preview_pts) >= 2:
            p.setPen(QPen(QColor(C_ACCENT), 2.4))
            step = max(1, len(self._preview_pts) // 90)
            poly = QPolygonF([world_to_screen(float(r[1]), float(r[2]), origin, self.ppm) for r in self._preview_pts[::step]])
            poly.append(world_to_screen(float(self._preview_pts[-1, 1]), float(self._preview_pts[-1, 2]), origin, self.ppm))
            p.drawPolyline(poly)

        # Freehand preview stroke
        if len(self._stroke_pts) >= 2:
            p.setPen(QPen(QColor(C_WARN), 1.6, Qt.PenStyle.DashLine))
            p.drawPolyline(QPolygonF([world_to_screen(x, y, origin, self.ppm) for x, y in self._stroke_pts]))

        # Control points
        for idx, cp in enumerate(self.traj.control_points):
            sc = world_to_screen(cp.x, cp.y, origin, self.ppm)
            col = QColor(C_OK if idx == 0 else (C_WARN if idx == len(self.traj.control_points) - 1 else "#60a5fa"))
            p.setBrush(col)
            p.setPen(QPen(QColor("#ffffff"), 1.4))
            p.drawEllipse(sc, 6.0, 6.0)
            p.drawText(int(sc.x() + 8), int(sc.y() - 4), f"P{idx + 1}")

    def mousePressEvent(self, e: QMouseEvent) -> None:
        pos = e.position()
        if e.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            self._pan_last = pos
            return
        origin = self._origin_px()
        wx, wy = screen_to_world(pos.x(), pos.y(), origin, self.ppm)
        # Hit existing control point for drag adjustment
        for idx, cp in enumerate(self.traj.control_points):
            sc = world_to_screen(cp.x, cp.y, origin, self.ppm)
            if math.hypot(sc.x() - pos.x(), sc.y() - pos.y()) <= 10.0:
                self._drag_idx = idx
                return
        if self.tool_mode == "brush":
            self._stroke_pts = [(round(wx, 3), round(wy, 3))]
        elif self.tool_mode == "click":
            yaw = 0.0
            if self.traj.control_points:
                prev = self.traj.control_points[-1]
                yaw = math.atan2(wy - prev.y, wx - prev.x)
            self.traj.control_points.append(ControlPoint2D(round(wx, 3), round(wy, 3), round(yaw, 4)))
            self.refresh_preview()
            self.pointsChanged.emit()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        pos = e.position()
        if self._pan_last is not None:
            self.pan_offset += pos - self._pan_last
            self._pan_last = pos
            self.update()
            return
        wx, wy = screen_to_world(pos.x(), pos.y(), self._origin_px(), self.ppm)
        if self._drag_idx is not None:
            cp = self.traj.control_points[self._drag_idx]
            cp.x, cp.y = round(wx, 3), round(wy, 3)
            self.refresh_preview()
            self.pointsChanged.emit()
        elif self.tool_mode == "brush" and (e.buttons() & Qt.MouseButton.LeftButton):
            self._stroke_pts.append((round(wx, 3), round(wy, 3)))
            self.update()

    def mouseReleaseEvent(self, _e: QMouseEvent) -> None:
        self._drag_idx = None
        self._pan_last = None
        if self.tool_mode == "brush" and len(self._stroke_pts) >= 2:
            simplified = _rdp_simplify(self._stroke_pts, eps=0.25)
            self._stroke_pts.clear()
            self.traj.control_points = [ControlPoint2D(x, y, 0.0) for x, y in simplified]
            self.refresh_preview()
            self.pointsChanged.emit()

    def wheelEvent(self, e: QWheelEvent) -> None:
        factor = 1.12 if e.angleDelta().y() > 0 else 0.89
        self.ppm = max(10.0, min(160.0, self.ppm * factor))
        self.update()
