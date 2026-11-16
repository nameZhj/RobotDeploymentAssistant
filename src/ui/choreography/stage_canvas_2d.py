# @file: src/ui/choreography/stage_canvas_2d.py
# @brief: Interactive 2D metric stage canvas with inline trajectory drawing, sketch brush, robot drag, and PCD map overlay.
# @exports: StageCanvas2D

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import List, Optional, Tuple
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QImage, QKeyEvent, QMouseEvent, QPainter, QWheelEvent
from PySide6.QtWidgets import QWidget

from src.core.event_bus import StudioEvent
from src.core.settings import get_settings
from src.core.undo_stack import CallableUndoCommand
from src.domain.trajectory_entities import ControlPoint2D, TrajectoryEntity
from src.math.trajectory_sampler import sample_trajectory_50fps
from src.services.studio_state_service import StudioStateService
from src.ui.choreography.stage_painters import (
    paint_draft_trajectory,
    paint_empty_stage_hint,
    paint_grid_and_stage,
    paint_occupancy_map,
    paint_robots_and_collisions,
    paint_sketches,
    paint_trajectories,
    screen_to_world,
    world_to_screen,
)


class StageCanvas2D(QWidget):
    """Z-up metric top-down 2D stage canvas supporting inline UniUni trajectory drawing & sketch brush."""

    hoverCoordChanged = Signal(float, float)
    draftPointsChanged = Signal(int)
    trajectoryFinishRequested = Signal(list)  # List[ControlPoint2D]

    def __init__(self, state: StudioStateService, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self.ppm: float = 42.0
        self.pan_offset = QPointF(0.0, 0.0)
        self.show_trajectories: bool = True
        self.draw_mode: str = "view"  # "view" | "draw_traj" | "sketch"
        self.draft_points: List[ControlPoint2D] = []
        self._draft_samples = None
        self.sketch_strokes: List[List[Tuple[float, float]]] = []
        self._active_stroke: List[Tuple[float, float]] = []
        self._hover_world: Optional[Tuple[float, float]] = None

        self._grid_img: Optional[QImage] = None
        self._grid_meta = (0.0, 0.0, 0.05)
        self._last_mouse: Optional[QPointF] = None
        self._drag_draft_idx: Optional[int] = None
        self._drag_robot_idx: Optional[int] = None
        self._drag_robot_origin: Optional[Tuple[float, float]] = None
        self._panning: bool = False
        self.highlighted_track_id: Optional[int] = None

        self.setMinimumSize(240, 180)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        state.bus.subscribe(StudioEvent.PLAYHEAD_MOVED, lambda _t: self.update())
        state.bus.subscribe(StudioEvent.SCENE_CHANGED, lambda _p: self.update())
        state.bus.subscribe(StudioEvent.TIMELINE_UPDATED, lambda _p: self.update())
        state.bus.subscribe(StudioEvent.TRACKS_UPDATED, lambda _p: self.update())
        state.bus.subscribe(StudioEvent.TRAJECTORY_LIB_UPDATED, lambda _p: self.update())
        state.bus.subscribe(StudioEvent.MAP_LOADED, self._on_map_loaded)
        self._sync_active_map()

    def set_draw_mode(self, mode: str) -> None:
        self.draw_mode = mode if mode in ("view", "draw_traj", "sketch") else "view"
        self.setCursor(Qt.CursorShape.CrossCursor if self.draw_mode != "view" else Qt.CursorShape.ArrowCursor)
        self.update()

    def clear_sketches(self) -> None:
        self.sketch_strokes.clear()
        self._active_stroke.clear()
        self.update()

    def clear_draft(self) -> None:
        self.draft_points.clear()
        self._draft_samples = None
        self.draftPointsChanged.emit(0)
        self.update()

    def undo_draw_step(self) -> bool:
        if self.draw_mode == "draw_traj" and self.draft_points:
            self.draft_points.pop()
            self._rebuild_draft_preview()
            return True
        if self.draw_mode == "sketch" and self.sketch_strokes:
            self.sketch_strokes.pop()
            self.update()
            return True
        return False

    def _rebuild_draft_preview(self) -> None:
        if len(self.draft_points) >= 2:
            tmp = TrajectoryEntity(control_points=self.draft_points, duration=max(2.0, len(self.draft_points) * 1.5))
            arr, _ = sample_trajectory_50fps(tmp)
            self._draft_samples = arr
        else:
            self._draft_samples = None
        self.draftPointsChanged.emit(len(self.draft_points))
        self.update()

    def reset_view(self) -> None:
        self.pan_offset = QPointF(0.0, 0.0)
        span = max(float(self.state.scene.stage_width or 12.0), float(self.state.scene.stage_height or 8.0), 4.0)
        self.ppm = max(14.0, min(85.0, min(max(240, self.width()), max(180, self.height())) / (span + 2.5)))
        self.update()

    def set_occupancy_grid(self, png_path: str, ox: float, oy: float, res: float) -> None:
        p = Path(png_path)
        self._grid_img = QImage(str(p)) if png_path and p.exists() else None
        self._grid_meta = (ox, oy, max(0.005, res))
        self.update()

    def _sync_active_map(self) -> None:
        m = self.state.active_map
        if m and m.grid_png_path:
            self.set_occupancy_grid(m.grid_png_path, m.origin_x, m.origin_y, m.resolution)
        else:
            self._grid_img = None

    def _on_map_loaded(self, _payload) -> None:
        self._sync_active_map()
        self.update()

    def _origin_px(self) -> QPointF:
        return QPointF(self.width() * 0.5 + self.pan_offset.x(), self.height() * 0.5 + self.pan_offset.y())

    def paintEvent(self, _event) -> None:
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
        paint_trajectories(p, self.state, origin, self.ppm, self.show_trajectories)
        paint_sketches(p, origin, self.ppm, self.sketch_strokes, self._active_stroke)
        paint_robots_and_collisions(
            p, self.state, origin, self.ppm, get_settings().stage_defaults.safety_distance_m,
            highlight_track_id=self.highlighted_track_id,
        )
        paint_draft_trajectory(
            p, origin, self.ppm, self.draft_points, self._draft_samples,
            self._hover_world if self.draw_mode == "draw_traj" else None,
        )
        paint_empty_stage_hint(p, self.width(), self.height(), len(self.state.tracks))

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.matches(e.StandardKey.Undo) or (e.modifiers() & Qt.KeyboardModifier.ControlModifier and e.key() == Qt.Key.Key_Z):
            if self.undo_draw_step():
                return
        super().keyPressEvent(e)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        self._last_mouse = pos
        origin = self._origin_px()
        wx, wy = screen_to_world(pos.x(), pos.y(), origin, self.ppm)

        if event.button() == Qt.MouseButton.RightButton and self.draw_mode == "draw_traj":
            if len(self.draft_points) >= 2:
                self.trajectoryFinishRequested.emit(copy.deepcopy(self.draft_points))
            else:
                self.clear_draft()
            return
        if (
            event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton)
            or (event.modifiers() & Qt.KeyboardModifier.AltModifier)
        ):
            self._panning = True
            return
        if self.draw_mode == "draw_traj":
            for idx, cp in enumerate(self.draft_points):
                sc = world_to_screen(cp.x, cp.y, origin, self.ppm)
                if math.hypot(sc.x() - pos.x(), sc.y() - pos.y()) <= 11.0:
                    self._drag_draft_idx = idx
                    return
            yaw = math.atan2(wy - self.draft_points[-1].y, wx - self.draft_points[-1].x) if self.draft_points else 0.0
            self.draft_points.append(ControlPoint2D(round(wx, 3), round(wy, 3), round(yaw, 4)))
            self._rebuild_draft_preview()
            return
        if self.draw_mode == "sketch":
            self._active_stroke = [(round(wx, 3), round(wy, 3))]
            self.update()
            return

        hit_r = max(14.0, 0.35 * self.ppm)
        for idx, tr in enumerate(self.state.tracks):
            px, py, _ = self.state.evaluate_robot_pose(tr, self.state.playhead_s)
            sc = world_to_screen(px, py, origin, self.ppm)
            if math.hypot(sc.x() - pos.x(), sc.y() - pos.y()) <= hit_r:
                self._drag_robot_idx = idx
                self._drag_robot_origin = (tr.init_x, tr.init_y)
                return
        self._panning = True

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        wx, wy = screen_to_world(pos.x(), pos.y(), self._origin_px(), self.ppm)
        self._hover_world = (round(wx, 2), round(wy, 2))
        self.hoverCoordChanged.emit(wx, wy)

        if self._panning and self._last_mouse is not None:
            self.pan_offset += pos - self._last_mouse
            self._last_mouse = pos
            self.update()
            return
        if self._drag_draft_idx is not None:
            cp = self.draft_points[self._drag_draft_idx]
            cp.x, cp.y = round(wx, 3), round(wy, 3)
            self._rebuild_draft_preview()
            return
        if self.draw_mode == "sketch" and (event.buttons() & Qt.MouseButton.LeftButton):
            if not self._active_stroke or math.hypot(wx - self._active_stroke[-1][0], wy - self._active_stroke[-1][1]) >= 0.06:
                self._active_stroke.append((round(wx, 3), round(wy, 3)))
                self.update()
            return
        if self._drag_robot_idx is not None and 0 <= self._drag_robot_idx < len(self.state.tracks):
            tr = self.state.tracks[self._drag_robot_idx]
            tr.init_x, tr.init_y = round(wx, 2), round(wy, 2)
            self.update()
            return
        if self.draw_mode == "draw_traj" and self.draft_points:
            self.update()

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:
        self._panning = False
        self._drag_draft_idx = None
        if self._active_stroke and len(self._active_stroke) >= 2:
            self.sketch_strokes.append(list(self._active_stroke))
        self._active_stroke.clear()
        if self._drag_robot_idx is not None and 0 <= self._drag_robot_idx < len(self.state.tracks):
            tr = self.state.tracks[self._drag_robot_idx]
            old_xy = self._drag_robot_origin or (tr.init_x, tr.init_y)
            new_xy = (tr.init_x, tr.init_y)
            if old_xy != new_xy and tr.id is not None:
                tid = tr.id
                def _redo() -> None:
                    cur = next((t for t in self.state.tracks if t.id == tid), None)
                    if cur:
                        cur.init_x, cur.init_y = new_xy
                        self.state.scene_repo.upsert_track(cur)
                        self.state.reload_all()
                        self.state.bus.publish(StudioEvent.TRACKS_UPDATED, tid)
                def _undo() -> None:
                    cur = next((t for t in self.state.tracks if t.id == tid), None)
                    if cur:
                        cur.init_x, cur.init_y = old_xy
                        self.state.scene_repo.upsert_track(cur)
                        self.state.reload_all()
                        self.state.bus.publish(StudioEvent.TRACKS_UPDATED, tid)
                self.state.undo_stack.push(CallableUndoCommand(f"调整 {tr.name} 初始站位", _redo, _undo), execute_redo=True)
        self._drag_robot_idx = None
        self._drag_robot_origin = None
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        pos = event.position()
        wx, wy = screen_to_world(pos.x(), pos.y(), self._origin_px(), self.ppm)
        self.ppm = max(8.0, min(180.0, self.ppm * (1.12 if event.angleDelta().y() > 0 else 0.89)))
        new_sx = self.width() * 0.5 + self.pan_offset.x() + wx * self.ppm
        new_sy = self.height() * 0.5 + self.pan_offset.y() - wy * self.ppm
        self.pan_offset += QPointF(pos.x() - new_sx, pos.y() - new_sy)
        self.update()
