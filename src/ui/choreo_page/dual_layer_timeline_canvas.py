"""
@file: src/ui/choreo_page/dual_layer_timeline_canvas.py
@brief: 双子层时间轴交互视口：单机与群组轨道、素材拖拽放置、时序移动/拉伸微调及持久化
@exports: DualLayerTimelineCanvas, TimelineBlock, BarrierMarker
"""
from dataclasses import dataclass, field
import json
import logging
from typing import Any, Dict, List, Optional, Sequence
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor, QDragEnterEvent, QDragMoveEvent, QDropEvent, QPainter,
)
from PySide6.QtWidgets import QWidget
from src.application.stage_director.timeline_choreo_controller import (
    TimelineChoreoController,
)
from src.domain.timeline.timeline_clip_asset import TimelineClipAsset, TrackLayerType
from src.ui.choreo_page.timeline_canvas_renderer import TimelineCanvasRenderer

logger = logging.getLogger("DualLayerTimelineCanvas")


@dataclass
class TimelineBlock:
    """时间轴呈现块，映射自持久化 TimelineClipAsset"""
    block_id: str
    track_id: str  # "1", "2", "GROUP"
    is_upper_action: bool
    name: str
    start_ms: int
    duration_ms: int
    is_group: bool = False
    allow_stretch: bool = True

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.duration_ms


@dataclass
class BarrierMarker:
    barrier_id: str
    time_ms: int
    participating_tracks: List[str] = field(default_factory=list)


class DualLayerTimelineCanvas(QWidget):
    """支持多机/群组双子层时间轴画布：支持拖拽放置素材、位移/时长拉伸、撤销删除及持久化"""

    cursorMoved = Signal(int)
    blockSelected = Signal(dict)
    clipChanged = Signal(dict)
    barrierAdded = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None, controller: Optional[Any] = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.choreo_controller = TimelineChoreoController()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAcceptDrops(True)

        self._px_per_sec = 80.0
        self._current_time_ms = 0
        self._track_height = 56
        self._ruler_height = 28
        self._tracks: List[Dict[str, Any]] = []
        self._blocks: List[TimelineBlock] = []
        self._barriers: List[BarrierMarker] = []
        self._is_dragging_cursor = False
        self._dragged_block: Optional[TimelineBlock] = None
        self._resizing_block: Optional[TimelineBlock] = None
        self._selected_block: Optional[TimelineBlock] = None
        self._drag_start_x: float = 0.0
        self._drag_start_ms: int = 0
        self._drag_start_dur_ms: int = 0
        self._snap_ms = 100

        self.load_from_store()
        if self.controller and hasattr(self.controller, "playhead_updated"):
            self.controller.playhead_updated.connect(lambda t, p: self.set_current_time_ms(int(t * 1000.0), notify=False))

    def load_from_store(self) -> None:
        """从 SQLite 存储恢复时间轴所有已编排 Clip"""
        clips = self.choreo_controller.list_clips()
        self._blocks.clear()
        for c in clips:
            self._blocks.append(TimelineBlock(
                block_id=c.clip_id,
                track_id=c.robot_id,
                is_upper_action=(c.track_layer == TrackLayerType.ACTION),
                name=c.name or f"Clip-{c.ref_id}",
                start_ms=c.start_ms,
                duration_ms=c.duration_ms,
                is_group=c.is_group,
                allow_stretch=c.allow_stretch,
            ))
        self.update()

    def set_zoom_scale(self, percent: int) -> None:
        self._px_per_sec = 80.0 * (max(50, min(300, percent)) / 100.0)
        self.update()

    def set_tracks(self, tracks: Sequence[Dict[str, Any]]) -> None:
        self._tracks = [dict(t) for t in tracks]
        self.update()

    def set_barriers(self, barriers: Sequence[BarrierMarker]) -> None:
        self._barriers = list(barriers)
        self.update()

    # --- 拖放接收机制 (Drag & Drop) ---
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasFormat("application/x-choreo-asset") or event.mimeData().hasFormat("application/x-robo-choreo-asset") or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        asset_dict: Dict[str, Any] = {}
        for m_type in ("application/x-robo-choreo-asset", "application/x-choreo-asset"):
            if event.mimeData().hasFormat(m_type):
                try:
                    raw = bytes(event.mimeData().data(m_type))
                    asset_dict = json.loads(raw.decode("utf-8"))
                    break
                except Exception:
                    pass
        if not asset_dict and event.mimeData().hasText():
            txt = event.mimeData().text()
            parts = txt.split(":")
            if len(parts) >= 3:
                asset_dict = {"asset_type": parts[0], "asset_id": parts[1], "name": parts[2]}

        if not asset_dict:
            event.ignore(); return

        pos = event.pos()
        track_idx = int((pos.y() - self._ruler_height) // self._track_height)
        if not (0 <= track_idx < len(self._tracks)):
            event.ignore(); return
        target_track_id = self._tracks[track_idx]["id"]
        sub_y = (pos.y() - self._ruler_height) % self._track_height
        target_sub_layer = TrackLayerType.ACTION if sub_y < (self._track_height // 2) else TrackLayerType.TRAJECTORY

        exact_s = max(0.0, pos.x() / self._px_per_sec)
        start_ms = int(round((exact_s * 1000.0) / self._snap_ms) * self._snap_ms)

        ok, msg, clip = self.choreo_controller.create_clip_from_dropped_asset(
            asset_dict, target_track_id, target_sub_layer, start_ms
        )
        if ok and clip:
            event.acceptProposedAction()
            self._blocks.append(TimelineBlock(
                clip.clip_id, clip.robot_id, clip.track_layer == TrackLayerType.ACTION,
                clip.name, clip.start_ms, clip.duration_ms, clip.is_group, clip.allow_stretch
            ))
            self.clipChanged.emit(clip.to_dict())
            self.update()
        else:
            logger.warning(f"拒绝拖放编排: {msg}")
            event.ignore()

    # --- 视口绘制与渲染 ---
    def paintEvent(self, event) -> None:
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, Qt.black)
        TimelineCanvasRenderer.draw_grid_and_tracks(p, self._tracks, self._ruler_height, self._track_height, w)
        TimelineCanvasRenderer.draw_blocks(p, self._blocks, self._tracks, self._ruler_height, self._track_height, self._px_per_sec, self._selected_block)
        TimelineCanvasRenderer.draw_barriers(p, self._barriers, self._ruler_height, self._px_per_sec, h)
        TimelineCanvasRenderer.draw_ruler(p, self._ruler_height, self._px_per_sec, w)
        TimelineCanvasRenderer.draw_cursor(p, self._current_time_ms, self._px_per_sec, h)
        if not self._tracks:
            p.save(); p.setPen(QColor("#475569"))
            f = p.font(); f.setPointSize(11); f.setBold(True); p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter, "暂无编排轨道 (等待载入工程或添加机器人)")
            p.restore()

    # --- 鼠标与键盘交互 (选择 / 移动 / 时长拉伸 / 删除 / 撤销) ---
    def mousePressEvent(self, event) -> None:
        self.setFocus()
        pos = event.pos()
        if event.button() == Qt.LeftButton:
            if pos.y() <= self._ruler_height:
                self._is_dragging_cursor = True
                self._update_cursor_from_mouse(pos.x())
            else:
                clicked = None
                is_resize_mode = False
                track_map = {trk["id"]: i for i, trk in enumerate(self._tracks)}
                for b in reversed(self._blocks):
                    t_idx = track_map.get(b.track_id, 0)
                    x = (b.start_ms / 1000.0) * self._px_per_sec
                    bw = max(8.0, (b.duration_ms / 1000.0) * self._px_per_sec)
                    top = self._ruler_height + t_idx * self._track_height
                    sub_h = self._track_height // 2 - 2
                    y = top + 2 if b.is_upper_action else top + self._track_height // 2 + 1
                    rect = QRectF(x, y, bw, sub_h)
                    if rect.contains(pos):
                        clicked = b
                        if b.allow_stretch and abs(pos.x() - rect.right()) <= 8:
                            is_resize_mode = True
                        break

                if clicked:
                    self._selected_block = clicked
                    self._drag_start_x = pos.x()
                    self._drag_start_ms = clicked.start_ms
                    self._drag_start_dur_ms = clicked.duration_ms
                    if is_resize_mode:
                        self._resizing_block = clicked
                    else:
                        self._dragged_block = clicked
                    self.blockSelected.emit({"id": clicked.block_id, "name": clicked.name, "start_ms": clicked.start_ms, "duration_ms": clicked.duration_ms})
                else:
                    self._selected_block = None
                    self._is_dragging_cursor = True
                    self._update_cursor_from_mouse(pos.x())
            self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        pos = event.pos()
        if self._is_dragging_cursor:
            self._update_cursor_from_mouse(pos.x())
        elif self._dragged_block:
            delta_x = pos.x() - self._drag_start_x
            delta_ms = int((delta_x / self._px_per_sec) * 1000.0)
            self._dragged_block.start_ms = max(0, self._drag_start_ms + delta_ms)
            self.update()
        elif self._resizing_block:
            delta_x = pos.x() - self._drag_start_x
            delta_ms = int((delta_x / self._px_per_sec) * 1000.0)
            self._resizing_block.duration_ms = max(200, self._drag_start_dur_ms + delta_ms)
            self.update()
        else:
            self.setCursor(Qt.ArrowCursor)
            if self._selected_block and self._selected_block.allow_stretch:
                track_map = {trk["id"]: i for i, trk in enumerate(self._tracks)}
                t_idx = track_map.get(self._selected_block.track_id, 0)
                right_x = ((self._selected_block.start_ms + self._selected_block.duration_ms) / 1000.0) * self._px_per_sec
                top = self._ruler_height + t_idx * self._track_height
                if top <= pos.y() <= top + self._track_height and abs(pos.x() - right_x) <= 8:
                    self.setCursor(Qt.SizeHorCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragged_block:
            self.choreo_controller.move_clip(self._dragged_block.block_id, self._dragged_block.start_ms)
            self.clipChanged.emit({"id": self._dragged_block.block_id, "start_ms": self._dragged_block.start_ms})
            self._dragged_block = None
        elif self._resizing_block:
            self.choreo_controller.resize_clip(self._resizing_block.block_id, self._resizing_block.duration_ms)
            self.clipChanged.emit({"id": self._resizing_block.block_id, "duration_ms": self._resizing_block.duration_ms})
            self._resizing_block = None
        self._is_dragging_cursor = False
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self._selected_block:
            cid = self._selected_block.block_id
            self.choreo_controller.delete_clip(cid)
            self._blocks = [b for b in self._blocks if b.block_id != cid]
            self._selected_block = None
            self.update()
        elif event.key() == Qt.Key_Z and event.modifiers() & Qt.ControlModifier:
            if self.choreo_controller.undo():
                self.load_from_store()
        elif event.key() == Qt.Key_Y and event.modifiers() & Qt.ControlModifier:
            if self.choreo_controller.redo():
                self.load_from_store()
        super().keyPressEvent(event)

    def _update_cursor_from_mouse(self, mouse_x: float) -> None:
        exact_s = max(0.0, mouse_x / self._px_per_sec)
        if self.controller and hasattr(self.controller, "seek_time"):
            self.controller.seek_time(exact_s)
        time_ms = int(exact_s * 1000.0)
        snapped_ms = int(round(time_ms / self._snap_ms) * self._snap_ms)
        self.set_current_time_ms(snapped_ms, notify=True)
