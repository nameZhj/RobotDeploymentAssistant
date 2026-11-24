# @file: src/ui/formation/formation_planner_canvas.py
# @brief: Interactive 2D swarm formation visualizer displaying sources, draggable target slots, and collision-free paths.
# @exports: FormationPlannerCanvas

from __future__ import annotations

import math
from pathlib import Path
from typing import List, Optional, Tuple
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen, QPolygonF, QWheelEvent
from PySide6.QtWidgets import QWidget

from src.core.event_bus import StudioEvent
from src.domain.track_entities import pick_track_color
from src.services.studio_state_service import StudioStateService
from src.ui.choreography.stage_painters import paint_grid_and_stage, paint_occupancy_map, screen_to_world, world_to_screen
from src.ui.design_system.tokens import C_ACCENT, C_OK, C_WARN

Point2D = Tuple[float, float]


class FormationPlannerCanvas(QWidget):
    """2D formation CAD viewport supporting interactive target dragging & simulated path playback."""

    targetsEdited = Signal()

    def __init__(self, state: StudioStateService, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.ppm: float = 42.0
        self.pan_offset = QPointF(0.0, 0.0)
        self.sources: List[Point2D] = []
        self.targets: List[Point2D] = []
        self.assignment: List[int] = []
        self.knots: List[List[Point2D]] = []
        self.sim_progress: float = 1.0
        self._drag_target_idx: Optional[int] = None
        self._pan_last: Optional[QPointF] = None
        self._grid_img: Optional[QImage] = None
        self._grid_meta = (0.0, 0.0, 0.05)
        self.setMinimumSize(360, 280)
        state.bus.subscribe(StudioEvent.MAP_LOADED, lambda _p: (self._sync_active_map(), self.update()))
        self._sync_active_map()

    def _sync_active_map(self) -> None:
        m = self.state.active_map
        p = Path(m.grid_png_path) if m and m.grid_png_path else None
        self._grid_img = QImage(str(p)) if p and p.exists() else None
        self._grid_meta = (m.origin_x, m.origin_y, max(0.005, m.resolution)) if m else (0.0, 0.0, 0.05)

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
        paint_occupancy_map(p, self._grid_img, *self._grid_meta, origin, self.ppm)

        # Draw planned splines or straight pairing lines
        if self.knots:
            for idx, pts in enumerate(self.knots):
                if len(pts) < 2:
                    continue
                col = QColor(pick_track_color(idx + 1))
                p.setPen(QPen(col, 2.2))
                limit = max(2, int(len(pts) * self.sim_progress))
                p.drawPolyline(QPolygonF([world_to_screen(x, y, origin, self.ppm) for x, y in pts[:limit]]))
        elif self.sources and self.targets and self.assignment:
            p.setPen(QPen(QColor("#64748b"), 1.3, Qt.PenStyle.DashLine))
            for i, sx_sy in enumerate(self.sources):
                if i < len(self.assignment) and 0 <= self.assignment[i] < len(self.targets):
                    tx, ty = self.targets[self.assignment[i]]
                    p.drawLine(
                        world_to_screen(sx_sy[0], sx_sy[1], origin, self.ppm),
                        world_to_screen(tx, ty, origin, self.ppm),
                    )

        # Draw source robots (green circles)
        for i, (sx, sy) in enumerate(self.sources):
            sc = world_to_screen(sx, sy, origin, self.ppm)
            p.setBrush(QColor(C_OK))
            p.setPen(QPen(QColor("#ffffff"), 1.3))
            p.drawEllipse(sc, 7.0, 7.0)
            p.drawText(int(sc.x() + 9), int(sc.y() - 4), f"S{i + 1}")

        # Draw target slots (accent diamonds, draggable)
        for j, (tx, ty) in enumerate(self.targets):
            sc = world_to_screen(tx, ty, origin, self.ppm)
            p.setBrush(QColor(C_ACCENT if j != self._drag_target_idx else C_WARN))
            p.setPen(QPen(QColor("#ffffff"), 1.3))
            poly = QPolygonF(
                [QPointF(sc.x(), sc.y() - 7), QPointF(sc.x() + 7, sc.y()), QPointF(sc.x(), sc.y() + 7), QPointF(sc.x() - 7, sc.y())]
            )
            p.drawPolygon(poly)
            p.drawText(int(sc.x() + 9), int(sc.y() + 10), f"T{j + 1}")

    def mousePressEvent(self, e: QMouseEvent) -> None:
        pos = e.position()
        if e.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            self._pan_last = pos
            return
        origin = self._origin_px()
        for j, (tx, ty) in enumerate(self.targets):
            sc = world_to_screen(tx, ty, origin, self.ppm)
            if math.hypot(sc.x() - pos.x(), sc.y() - pos.y()) <= 11.0:
                self._drag_target_idx = j
                return

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        pos = e.position()
        if self._pan_last is not None:
            self.pan_offset += pos - self._pan_last
            self._pan_last = pos
            self.update()
            return
        if self._drag_target_idx is not None:
            wx, wy = screen_to_world(pos.x(), pos.y(), self._origin_px(), self.ppm)
            self.targets[self._drag_target_idx] = (round(wx, 3), round(wy, 3))
            self.update()
            self.targetsEdited.emit()

    def mouseReleaseEvent(self, _e: QMouseEvent) -> None:
        self._drag_target_idx = None
        self._pan_last = None

    def wheelEvent(self, e: QWheelEvent) -> None:
        self.ppm = max(12.0, min(140.0, self.ppm * (1.12 if e.angleDelta().y() > 0 else 0.89)))
        self.update()
