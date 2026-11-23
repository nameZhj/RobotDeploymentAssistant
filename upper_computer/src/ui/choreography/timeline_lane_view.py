# @file: src/ui/choreography/timeline_lane_view.py
# @brief: Interactive multi-robot timeline canvas with drag-drop, undo/redo, lock/mute, track CRUD context menu, and scrub.
# @exports: TimelineLaneView

from __future__ import annotations

import copy
import json
from typing import Optional, Set, Tuple
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeyEvent, QMouseEvent, QPainter, QWheelEvent
from PySide6.QtWidgets import QWidget

from src.core.event_bus import StudioEvent
from src.domain.timeline_entities import TimelineBlockEntity
from src.services.playback_coordinator import PlaybackCoordinator
from src.services.studio_state_service import StudioStateService
from src.ui.choreography.timeline_block_painter import (
    LANE_H, RULER_H, compute_chain_block_width, paint_empty_timeline_hint, paint_lane_blocks, paint_ruler, paint_track_sidebar,
)
from src.ui.choreography.timeline_context_menus import show_block_context_menu, show_track_context_menu, split_block_at_time
from src.ui.choreography.timeline_collision_clamp import clamp_move_start, clamp_resize_duration
from src.ui.choreography.track_lib_panel import BLOCK_MIME_TYPE
from src.ui.design_system.tokens import W_TRACK_HEAD


class TimelineLaneView(QWidget):
    """Multi-track unified lane canvas supporting drops, move, trim, undo/redo, and track CRUD."""

    rulerDoubleClicked = Signal(float)
    blockSelected = Signal(object)

    def __init__(self, state: StudioStateService, playback: PlaybackCoordinator, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.playback = playback
        self.pps: float = 34.0
        self.scroll_x: int = 0
        self.snap_enabled: bool = True
        self.selected_block_id: Optional[int] = None
        self.selected_track_id: Optional[int] = None
        self._drag_mode: str = ""
        self._drag_block: Optional[TimelineBlockEntity] = None
        self._drag_before: Optional[TimelineBlockEntity] = None
        self._drag_origin_t: float = 0.0
        self._drag_origin_dur: float = 0.0
        self._drag_start_x: float = 0.0
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(180)
        for ev in (StudioEvent.PLAYHEAD_MOVED, StudioEvent.TIMELINE_UPDATED):
            state.bus.subscribe(ev, lambda _p: self.update())
        for ev in (StudioEvent.TRACKS_UPDATED, StudioEvent.SCENE_CHANGED, StudioEvent.TASK_SWITCHED):
            state.bus.subscribe(ev, lambda _p: self._sync_height())
        self._sync_height()

    def _sync_height(self) -> None:
        self.setMinimumHeight(RULER_H + max(3, len(self.state.tracks)) * LANE_H + 24)
        self.update()

    def zoom(self, factor: float) -> None:
        self.pps = max(10.0, min(120.0, self.pps * factor))
        self.update()

    def _overlap_block_ids(self) -> Set[int]:
        bad: Set[int] = set()
        blks = self.state.blocks
        for i in range(len(blks)):
            for j in range(i + 1, len(blks)):
                if not blks[i].is_ignored and not blks[j].is_ignored and blks[i].overlaps(blks[j]):
                    if blks[i].id is not None:
                        bad.add(blks[i].id)
                    if blks[j].id is not None:
                        bad.add(blks[j].id)
        return bad

    def _snap(self, val: float) -> float:
        return round(max(0.0, val) * 10.0) / 10.0 if self.snap_enabled else max(0.0, val)

    def _is_track_locked(self, track_id: int) -> bool:
        tr = next((t for t in self.state.tracks if t.id == track_id), None)
        return bool(tr and tr.locked)

    def _track_at_y(self, y: float):
        if y < RULER_H:
            return None
        ridx = int((y - RULER_H) // LANE_H)
        return self.state.tracks[ridx] if 0 <= ridx < len(self.state.tracks) else None

    def _hit_block(self, x: float, y: float) -> Tuple[Optional[TimelineBlockEntity], bool]:
        tr = self._track_at_y(y) if x >= W_TRACK_HEAD else None
        if tr is None:
            return (None, False)
        matches = sorted(
            (b for b in self.state.blocks if b.track_id == tr.id),
            key=lambda b: (round(b.start_time, 4), b.id or 0),
        )
        prev_right: Optional[float] = None
        hit: Optional[Tuple[TimelineBlockEntity, bool]] = None
        for blk in matches:
            bx0 = W_TRACK_HEAD + blk.start_time * self.pps - self.scroll_x
            bw = compute_chain_block_width(blk.title, blk.duration, self.pps)
            if prev_right is not None and bx0 < prev_right + 10.0:
                bx0 = prev_right + 10.0
            bx1 = bx0 + bw
            prev_right = bx1
            if bx0 <= x <= bx1:
                hit = (blk, x >= bx1 - 8.0)
        return hit or (None, False)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = max(1, self.width())
        lane_w = max(1, w - W_TRACK_HEAD)
        paint_track_sidebar(p, W_TRACK_HEAD, self.state.tracks, RULER_H, self.selected_track_id)
        paint_ruler(p, W_TRACK_HEAD, lane_w, self.pps, self.scroll_x, self.state.playhead_s)
        paint_lane_blocks(
            p, W_TRACK_HEAD, lane_w, RULER_H, self.state.tracks,
            self.state.blocks, self._overlap_block_ids(),
            self.pps, self.scroll_x, self.selected_block_id, self.state.playhead_s,
        )
        paint_empty_timeline_hint(p, W_TRACK_HEAD, lane_w, RULER_H, self.state.tracks)

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        if e.mimeData().hasFormat(BLOCK_MIME_TYPE):
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent) -> None:
        if not e.mimeData().hasFormat(BLOCK_MIME_TYPE) or not self.state.tracks:
            return
        pos = e.position()
        ridx = max(0, min(len(self.state.tracks) - 1, int((pos.y() - RULER_H) // LANE_H)))
        target_track = self.state.tracks[ridx]
        if target_track.locked:
            self.state.notify(f"轨道 {target_track.name} 已锁定，禁止拖入编辑", "warn")
            return
        t_start = round(max((b.end_time for b in self.state.blocks if b.track_id == (target_track.id or 1) and not b.is_ignored), default=0.0), 2)
        data = json.loads(bytes(e.mimeData().data(BLOCK_MIME_TYPE)).decode("utf-8"))
        blk_type = str(data.get("block_type", "trajectory"))
        blk_dur = max(0.5, float(data.get("duration", 5.0)))
        blk = TimelineBlockEntity(
            task_id=self.state.task.id or 1,
            track_id=target_track.id or 1,
            block_type=blk_type,
            ref_id=int(data.get("ref_id", 0)),
            code_no=str(data.get("code_no", "")),
            title=str(data.get("title", "任务节点")),
            start_time=t_start,
            duration=blk_dur,
        )
        saved = self.state.commit_block_change(None, blk, f"追加任务节点 {blk.title}")
        self.selected_block_id = saved.id if saved else None
        e.acceptProposedAction()

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.selected_block_id is not None:
            self.delete_selected_block()
            return
        super().keyPressEvent(e)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        pos = e.position()
        self._drag_start_x = pos.x()
        if e.button() == Qt.MouseButton.RightButton:
            if pos.x() < W_TRACK_HEAD:
                self._show_track_menu(self._track_at_y(pos.y()), e.globalPosition().toPoint())
                return
            blk, _ = self._hit_block(pos.x(), pos.y())
            if blk is not None:
                self.selected_block_id = blk.id
                self._show_block_menu(blk, e.globalPosition().toPoint())
                return
        if e.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self._drag_mode, self._drag_origin_t = "pan", float(self.scroll_x)
            return
        if pos.x() < W_TRACK_HEAD:
            tr = self._track_at_y(pos.y())
            if tr is not None:
                self.selected_track_id = tr.id
                self.update()
            return
        if pos.y() < RULER_H:
            self._drag_mode = "scrub"
            self.playback.seek(max(0.0, (pos.x() - W_TRACK_HEAD + self.scroll_x) / self.pps))
            return

        blk, is_resize = self._hit_block(pos.x(), pos.y())
        if blk is not None:
            self.selected_block_id = blk.id
            self.selected_track_id = blk.track_id
            self.blockSelected.emit(blk)
            if not self._is_track_locked(blk.track_id):
                self._drag_block = blk
                self._drag_before = copy.deepcopy(blk)
                self._drag_origin_t, self._drag_origin_dur = blk.start_time, blk.duration
                self._drag_mode = "resize" if is_resize else "move"
        else:
            self.selected_block_id = None
            self.playback.seek(max(0.0, (pos.x() - W_TRACK_HEAD + self.scroll_x) / self.pps))
        self.update()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        pos = e.position()
        dx = pos.x() - self._drag_start_x
        if self._drag_mode == "pan":
            self.scroll_x = max(0, int(self._drag_origin_t - dx))
            self.update()
        elif self._drag_mode == "scrub":
            self.playback.seek(max(0.0, (pos.x() - W_TRACK_HEAD + self.scroll_x) / self.pps))
        elif self._drag_mode == "move" and self._drag_block is not None:
            raw_t = self._snap(self._drag_origin_t + dx / self.pps)
            sibs = [b for b in self.state.blocks if b.track_id == self._drag_block.track_id and not b.is_ignored and b.id != self._drag_block.id]
            self._drag_block.start_time = clamp_move_start(raw_t, self._drag_block.duration, self._drag_block.start_time, sibs)
            self.update()
        elif self._drag_mode == "resize" and self._drag_block is not None:
            raw_dur = max(0.5, self._snap(self._drag_origin_dur + dx / self.pps))
            sibs = [b for b in self.state.blocks if b.track_id == self._drag_block.track_id and not b.is_ignored and b.id != self._drag_block.id]
            self._drag_block.duration = clamp_resize_duration(self._drag_block.start_time, raw_dur, sibs)
            self.update()

    def mouseReleaseEvent(self, _e: QMouseEvent) -> None:
        if self._drag_mode in ("move", "resize") and self._drag_block is not None and self._drag_before is not None:
            if (self._drag_block.start_time, self._drag_block.duration) != (self._drag_before.start_time, self._drag_before.duration):
                self.state.commit_block_change(self._drag_before, copy.deepcopy(self._drag_block), f"调整 {self._drag_block.title}")
        self._drag_mode, self._drag_block, self._drag_before = "", None, None

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:
        if e.position().x() < W_TRACK_HEAD:
            tr = self._track_at_y(e.position().y())
            if tr is not None:
                from src.ui.modals.add_track_dialog import AddTrackDialog
                AddTrackDialog(self.state, self, track=tr).exec()
            return
        if e.position().y() <= RULER_H and e.position().x() >= W_TRACK_HEAD:
            self.rulerDoubleClicked.emit(max(0.0, (e.position().x() - W_TRACK_HEAD + self.scroll_x) / self.pps))

    def wheelEvent(self, e: QWheelEvent) -> None:
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1.12 if e.angleDelta().y() > 0 else 0.89)
        else:
            self.scroll_x = max(0, self.scroll_x - int(e.angleDelta().y() * 0.4))
            self.update()

    def _show_track_menu(self, tr, global_pt) -> None:
        self.selected_track_id = show_track_context_menu(self, self.state, tr, global_pt)

    def _show_block_menu(self, blk: TimelineBlockEntity, global_pt) -> None:
        show_block_context_menu(self, blk, global_pt)

    def delete_selected_track(self) -> None:
        if self.selected_track_id is not None:
            name = self.state.delete_track_with_undo(self.selected_track_id)
            if name:
                self.selected_track_id = None
                self.state.notify(f"已删除轨道 {name} (支持 Ctrl+Z 撤销)", "info")

    def delete_selected_block(self) -> None:
        blk = next((b for b in self.state.blocks if b.id == self.selected_block_id), None)
        if blk is None or self._is_track_locked(blk.track_id):
            return
        self.state.commit_block_change(blk, None, f"删除块 {blk.title}")
        self.selected_block_id = None

    def toggle_ignore_selected_block(self) -> None:
        blk = next((b for b in self.state.blocks if b.id == self.selected_block_id), None)
        if blk is None:
            return
        after = copy.deepcopy(blk)
        after.is_ignored = not blk.is_ignored
        self.state.commit_block_change(blk, after, ("恢复" if blk.is_ignored else "忽略") + f" {blk.title}")

    def split_selected_or_at_playhead(self) -> None:
        t = self.state.playhead_s
        cand = next(
            (b for b in self.state.blocks if b.id == self.selected_block_id and b.start_time + 0.3 < t < b.end_time - 0.3),
            None,
        ) or next((b for b in self.state.blocks if b.start_time + 0.3 < t < b.end_time - 0.3), None)
        if cand is not None and not self._is_track_locked(cand.track_id):
            split_block_at_time(self.state, cand, t)

    def duplicate_selected_block(self) -> None:
        blk = next((b for b in self.state.blocks if b.id == self.selected_block_id), None)
        if blk is None or self._is_track_locked(blk.track_id):
            return
        dup = copy.deepcopy(blk)
        dup.id = None
        dup.start_time = self.state.next_track_end_time(blk.track_id)
        saved = self.state.commit_block_change(None, dup, f"复制 {blk.title}")
        if saved:
            self.selected_block_id = saved.id
