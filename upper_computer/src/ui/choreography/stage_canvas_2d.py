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
from src.ui.choreography.stage_live_nav_painter import LiveNavOverlayState, paint_live_nav_overlay
from src.ui.choreography.stage_painters import (
    paint_draft_trajectory, paint_empty_stage_hint, paint_grid_and_stage,
    paint_occupancy_map, paint_robots_and_collisions, paint_sketches,
    paint_trajectories, screen_to_world, world_to_screen,
)


class StageCanvas2D(QWidget):
    """Z-up metric top-down 2D stage canvas supporting inline UniUni trajectory drawing & sketch brush."""

    hoverCoordChanged = Signal(float, float)
    draftPointsChanged = Signal(int)
    trajectoryFinishRequested = Signal(list)  # List[ControlPoint2D]
    robotSelected = Signal(int)
    initialPoseRequested = Signal(float, float, float)
    navGoalRequested = Signal(float, float, float)

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
        self._drag_robot_offset: Tuple[float, float] = (0.0, 0.0)
        self._panning: bool = False
        self.highlighted_track_id: Optional[int] = None
        self._live_nav = LiveNavOverlayState()

        self.setMinimumSize(240, 180)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        for ev in (
            StudioEvent.PLAYHEAD_MOVED, StudioEvent.SCENE_CHANGED,
            StudioEvent.TIMELINE_UPDATED, StudioEvent.TRACKS_UPDATED,
            StudioEvent.TRAJECTORY_LIB_UPDATED,
        ):
            state.bus.subscribe(ev, lambda _p: self.update())
        state.bus.subscribe(StudioEvent.MAP_LOADED, self._on_map_loaded)
        self._sync_active_map()

    def set_draw_mode(self, mode: str) -> None:
        valid = ("view", "draw_traj", "sketch", "set_initialpose", "set_nav_goal")
        self.draw_mode = mode if mode in valid else "view"
        self.setCursor(Qt.CursorShape.CrossCursor if self.draw_mode != "view" else Qt.CursorShape.ArrowCursor)
        self.update()

    def set_live_nav_overlay(self, pose=None, global_path=None, scan_xy=None, active_goal=None) -> None:
        self._live_nav.pose = pose
        if global_path is not None:
            self._live_nav.global_path = [(float(pt[0]), float(pt[1])) for pt in global_path if len(pt) >= 2]
        if scan_xy is not None:
            self._live_nav.scan_xy = [(float(pt[0]), float(pt[1])) for pt in scan_xy if len(pt) >= 2]
        if active_goal is not None:
            self._live_nav.active_goal = active_goal
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
            arr, _ = sample_trajectory_50fps(TrajectoryEntity(control_points=self.draft_points, duration=max(2.0, len(self.draft_points) * 1.5)))
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
        paint_grid_and_stage(p, self.width(), self.height(), origin, self.ppm, float(self.state.scene.stage_width or 12.0), float(self.state.scene.stage_height or 8.0))
        paint_occupancy_map(p, self._grid_img, *self._grid_meta, origin, self.ppm)
        paint_trajectories(p, self.state, origin, self.ppm, self.show_trajectories)
        paint_sketches(p, origin, self.ppm, self.sketch_strokes, self._active_stroke)
        paint_robots_and_collisions(p, self.state, origin, self.ppm, get_settings().stage_defaults.safety_distance_m, highlight_track_id=self.highlighted_track_id)
        paint_draft_trajectory(p, origin, self.ppm, self.draft_points, self._draft_samples, self._hover_world if self.draw_mode == "draw_traj" else None)
        paint_live_nav_overlay(p, self._live_nav, origin, self.ppm)
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
        if self.draw_mode in ("set_initialpose", "set_nav_goal"):
            self._live_nav.drag_kind = self.draw_mode
            self._live_nav.drag_start = (round(wx, 3), round(wy, 3))
            self._live_nav.drag_end = (round(wx, 3), round(wy, 3))
            self.update()
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
                self.highlighted_track_id = tr.id
                self._drag_robot_idx = idx
                self._drag_robot_origin = (tr.init_x, tr.init_y)
                self._drag_robot_offset = (tr.init_x - wx, tr.init_y - wy)
                self.robotSelected.emit(tr.id or 0)
                self.state.notify(f"选中 [{tr.name}] 初始坐标 ({tr.init_x:.2f}, {tr.init_y:.2f}) — 拖动可调整", "info")
                self.update()
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
        if self._live_nav.drag_start is not None:
            self._live_nav.drag_end = (round(wx, 3), round(wy, 3))
            self.update()
            return
        if self.draw_mode == "sketch" and (event.buttons() & Qt.MouseButton.LeftButton):
            if not self._active_stroke or math.hypot(wx - self._active_stroke[-1][0], wy - self._active_stroke[-1][1]) >= 0.06:
                self._active_stroke.append((round(wx, 3), round(wy, 3)))
                self.update()
            return
        if self._drag_robot_idx is not None and 0 <= self._drag_robot_idx < len(self.state.tracks):
            tr = self.state.tracks[self._drag_robot_idx]
            ox, oy = self._drag_robot_offset
            tr.init_x, tr.init_y = self.state.clamp_robot_drag_xy(tr, wx + ox, wy + oy)
            self.update()
            return
        if self.draw_mode == "draw_traj" and self.draft_points:
            self.update()

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:
        self._panning = False
        self._drag_draft_idx = None
        if self._live_nav.drag_start is not None and self._live_nav.drag_end is not None:
            x0, y0 = self._live_nav.drag_start
            x1, y1 = self._live_nav.drag_end
            yaw = round(math.atan2(y1 - y0, x1 - x0), 4) if math.hypot(x1 - x0, y1 - y0) > 0.05 else 0.0
            kind = self._live_nav.drag_kind
            self._live_nav.drag_start = self._live_nav.drag_end = None
            if kind == "set_initialpose":
                self.initialPoseRequested.emit(x0, y0, yaw)
            elif kind == "set_nav_goal":
                self._live_nav.active_goal = (x0, y0, yaw)
                self.navGoalRequested.emit(x0, y0, yaw)
        if self._active_stroke and len(self._active_stroke) >= 2:
            self.sketch_strokes.append(list(self._active_stroke))
        self._active_stroke.clear()
        if self._drag_robot_idx is not None and 0 <= self._drag_robot_idx < len(self.state.tracks):
            tr = self.state.tracks[self._drag_robot_idx]
            old_xy, new_xy = self._drag_robot_origin or (tr.init_x, tr.init_y), (tr.init_x, tr.init_y)
            if old_xy != new_xy and tr.id is not None:
                tid = tr.id
                def _apply(xy: Tuple[float, float]) -> None:
                    cur = next((t for t in self.state.tracks if t.id == tid), None)
                    if cur:
                        cur.init_x, cur.init_y = xy
                        self.state.scene_repo.upsert_track(cur)
                        self.state.reload_all()
                        self.state.bus.publish(StudioEvent.TRACKS_UPDATED, tid)
                self.state.undo_stack.push(CallableUndoCommand(f"调整 {tr.name} 初始站位", lambda: _apply(new_xy), lambda: _apply(old_xy)), execute_redo=True)
        self._drag_robot_idx = self._drag_robot_origin = None
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        pos = event.position()
        wx, wy = screen_to_world(pos.x(), pos.y(), self._origin_px(), self.ppm)
        self.ppm = max(8.0, min(180.0, self.ppm * (1.12 if event.angleDelta().y() > 0 else 0.89)))
        new_sx = self.width() * 0.5 + self.pan_offset.x() + wx * self.ppm
        new_sy = self.height() * 0.5 + self.pan_offset.y() - wy * self.ppm
        self.pan_offset += QPointF(pos.x() - new_sx, pos.y() - new_sy)
        self.update()
