"""
@file: src/ui/timeline_widget.py
@brief: 支持拖拽放置、双子层(动作/轨迹)、防重叠互斥与剪辑编辑的多机器人时间轴视口
@exports: TimelineWidget
"""
import copy
import json
import logging
import time
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QContextMenuEvent, QKeyEvent, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QMenu, QMessageBox, QWidget

logger = logging.getLogger("TimelineWidget")
CHOREO_MIME_TYPE = "application/x-robo-choreo-asset"


class TimelineWidget(QWidget):
    """支持多机器人与群组双子层、拖拽放置与微调的专业时间轴"""

    clipAdded = Signal(dict)
    clipSelected = Signal(dict)
    clipChanged = Signal(dict)
    clipDeleted = Signal(str)
    timeCursorChanged = Signal(float)

    HEADER_WIDTH = 110
    RULER_HEIGHT = 28
    TRACK_HEIGHT = 64
    SUB_LAYER_HEIGHT = 28

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True); self.setFocusPolicy(Qt.StrongFocus); self.setMouseTracking(True)
        self.setMinimumHeight(240)
        self.px_per_sec, self.playhead_time, self.scroll_x = 40.0, 0.0, 0.0
        self.tracks: List[Dict[str, Any]] = [
            {"id": "track_A", "name": "机器人 A", "is_group": False, "robot_id": "A"},
            {"id": "track_B", "name": "机器人 B", "is_group": False, "robot_id": "B"},
            {"id": "track_group_1", "name": "群组 1", "is_group": True, "robot_id": "group_1", "members": ["A", "B", "C", "D"]},
        ]
        self.clips: List[Dict[str, Any]] = []
        self._selected_clip_id: Optional[str] = None
        self._dragging_playhead = False
        self._drag_clip_id: Optional[str] = None
        self._drag_mode, self._drag_start_x, self._drag_orig_time, self._drag_orig_dur = "MOVE", 0.0, 0.0, 0.0

    def time_to_px(self, t: float) -> float:
        return self.HEADER_WIDTH + (t * self.px_per_sec) - self.scroll_x

    def px_to_time(self, px: float) -> float:
        return max(0.0, (px - self.HEADER_WIDTH + self.scroll_x) / self.px_per_sec)

    # --- 拖拽放置 (Drag & Drop) ---
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(CHOREO_MIME_TYPE): event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(CHOREO_MIME_TYPE): event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasFormat(CHOREO_MIME_TYPE): return
        try:
            asset = json.loads(event.mimeData().data(CHOREO_MIME_TYPE).data().decode("utf-8"))
        except Exception: return

        pos = event.position()
        if pos.x() < self.HEADER_WIDTH or pos.y() < self.RULER_HEIGHT: return
        t_idx = int((pos.y() - self.RULER_HEIGHT) // self.TRACK_HEIGHT)
        if t_idx < 0 or t_idx >= len(self.tracks): return

        track = self.tracks[t_idx]
        local_y = (pos.y() - self.RULER_HEIGHT) % self.TRACK_HEIGHT
        layer = "active" if local_y < self.SUB_LAYER_HEIGHT + 2 else "trajectory"
        cat = asset.get("category", "action")
        if cat == "trajectory": layer = "trajectory"
        elif cat in ("dance", "action"): layer = "active"

        start_t = self._resolve_overlap(track["id"], layer, round(self.px_to_time(pos.x()), 2), float(asset.get("duration", 3.0)))
        new_clip = {
            "clip_id": f"clip_{int(time.time() * 1000)}", "track_id": track["id"], "robot_id": track["robot_id"],
            "layer": layer, "asset_id": asset.get("asset_id", ""), "asset_type": cat,
            "name": asset.get("name", "未命名"), "cmd": asset.get("cmd", "STAND"),
            "start_time": start_t, "duration": float(asset.get("duration", 3.0)),
            "formation_id": asset.get("formation_id", ""), "color": asset.get("color", "#38bdf8"),
        }
        self.clips.append(new_clip)
        self._selected_clip_id = new_clip["clip_id"]
        self.clipAdded.emit(new_clip); self.clipSelected.emit(new_clip)
        self.update(); event.acceptProposedAction()

    def _resolve_overlap(self, track_id: str, layer: str, start_t: float, dur: float) -> float:
        for c in sorted([c for c in self.clips if c["track_id"] == track_id and c["layer"] == layer], key=lambda x: x["start_time"]):
            if not (start_t + dur <= c["start_time"] or start_t >= c["start_time"] + c["duration"]):
                start_t = round(c["start_time"] + c["duration"] + 0.1, 2)
        return start_t

    # --- 渲染逻辑 ---
    def paintEvent(self, event) -> None:
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.fillRect(self.rect(), QColor("#0b0f19"))
        # 1. 刻度尺
        p.fillRect(QRectF(0, 0, self.width(), self.RULER_HEIGHT), QColor("#111827"))
        p.setPen(QPen(QColor("#334155"), 1)); p.drawLine(0, self.RULER_HEIGHT, self.width(), self.RULER_HEIGHT)
        step = 1 if self.px_per_sec >= 30 else (2 if self.px_per_sec >= 15 else 5)
        for s in range(0, int((self.width() - self.HEADER_WIDTH + self.scroll_x) / self.px_per_sec) + 2, step):
            px = self.time_to_px(s)
            if px >= self.HEADER_WIDTH:
                p.setPen(QPen(QColor("#64748b"), 1)); p.drawLine(px, self.RULER_HEIGHT - 6, px, self.RULER_HEIGHT)
                p.drawText(px + 3, self.RULER_HEIGHT - 8, f"{s}s")
        # 2. 轨道与双子层
        for idx, track in enumerate(self.tracks):
            ty = self.RULER_HEIGHT + idx * self.TRACK_HEIGHT
            p.fillRect(QRectF(0, ty, self.HEADER_WIDTH, self.TRACK_HEIGHT), QColor("#131c2e"))
            p.setPen(QPen(QColor("#1e293b"), 1))
            p.drawLine(0, ty + self.TRACK_HEIGHT, self.width(), ty + self.TRACK_HEIGHT)
            p.drawLine(self.HEADER_WIDTH, ty, self.HEADER_WIDTH, ty + self.TRACK_HEIGHT)
            p.setPen(QPen(QColor("#38bdf8" if track["is_group"] else "#f8fafc"), 1))
            p.drawText(6, ty + 18, f"{'👥 ' if track['is_group'] else '🤖 '}{track['name']}")
            p.setPen(QPen(QColor("#64748b"), 1))
            p.drawText(6, ty + 36, "● 动作层"); p.drawText(6, ty + 56, "● 轨迹层")
            p.setPen(QPen(QColor("#1e293b"), 1, Qt.DotLine))
            p.drawLine(self.HEADER_WIDTH, ty + self.SUB_LAYER_HEIGHT + 2, self.width(), ty + self.SUB_LAYER_HEIGHT + 2)
        # 3. Clips
        for c in self.clips:
            t_idx = next((i for i, t in enumerate(self.tracks) if t["id"] == c["track_id"]), -1)
            if t_idx < 0: continue
            ty = self.RULER_HEIGHT + t_idx * self.TRACK_HEIGHT
            rect = QRectF(self.time_to_px(c["start_time"]), ty + (2 if c["layer"] == "active" else self.SUB_LAYER_HEIGHT + 4), max(12.0, c["duration"] * self.px_per_sec), self.SUB_LAYER_HEIGHT - 2)
            is_sel = (c["clip_id"] == self._selected_clip_id)
            p.setBrush(QBrush(QColor(c.get("color", "#38bdf8"))))
            p.setPen(QPen(QColor("#facc15") if is_sel else QColor("#ffffff"), 2 if is_sel else 1))
            p.drawRoundedRect(rect, 4, 4)
            p.setPen(QPen(QColor("#ffffff"), 1))
            p.drawText(rect.adjusted(6, 4, -4, -4), Qt.AlignLeft | Qt.AlignVCenter, f"{c.get('name', '')} ({c.get('duration', 0):.1f}s)")
        # 4. 播放头
        hx = self.time_to_px(self.playhead_time)
        if hx >= self.HEADER_WIDTH:
            p.setPen(QPen(QColor("#ef4444"), 2)); p.drawLine(hx, 0, hx, self.height())
            p.setBrush(QBrush(QColor("#ef4444"))); p.drawPolygon([QPointF(hx - 5, 0), QPointF(hx + 5, 0), QPointF(hx, 10)])

    # --- 交互事件 ---
    def mousePressEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        if pos.y() <= self.RULER_HEIGHT:
            self.playhead_time = self.px_to_time(pos.x()); self._dragging_playhead = True
            self.timeCursorChanged.emit(self.playhead_time); self.update(); return
        clicked = self._find_clip_at(pos.x(), pos.y())
        if clicked:
            self._selected_clip_id, self._drag_clip_id = clicked["clip_id"], clicked["clip_id"]
            self._drag_start_x, self._drag_orig_time, self._drag_orig_dur = pos.x(), clicked["start_time"], clicked["duration"]
            right_px = self.time_to_px(clicked["start_time"] + clicked["duration"])
            self._drag_mode = "RESIZE_RIGHT" if abs(pos.x() - right_px) <= 8 else "MOVE"
            self.clipSelected.emit(clicked); self.update()
        else:
            self._selected_clip_id = None; self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        if self._dragging_playhead:
            self.playhead_time = self.px_to_time(pos.x())
            self.timeCursorChanged.emit(self.playhead_time); self.update(); return
        if self._drag_clip_id:
            clip = next((c for c in self.clips if c["clip_id"] == self._drag_clip_id), None)
            if not clip: return
            delta = (pos.x() - self._drag_start_x) / self.px_per_sec
            if self._drag_mode == "MOVE": clip["start_time"] = max(0.0, round(self._drag_orig_time + delta, 2))
            elif self._drag_mode == "RESIZE_RIGHT": clip["duration"] = max(0.5, round(self._drag_orig_dur + delta, 2))
            self.clipChanged.emit(clip); self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._dragging_playhead, self._drag_clip_id = False, None

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else (1.0 / 1.15)
        self.px_per_sec = max(10.0, min(160.0, self.px_per_sec * factor)); self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Delete and self._selected_clip_id: self.delete_selected_clip()

    def _find_clip_at(self, px: float, py: float) -> Optional[Dict[str, Any]]:
        for c in reversed(self.clips):
            t_idx = next((i for i, t in enumerate(self.tracks) if t["id"] == c["track_id"]), -1)
            if t_idx < 0: continue
            ty = self.RULER_HEIGHT + t_idx * self.TRACK_HEIGHT
            sub_y = ty + (2 if c["layer"] == "active" else self.SUB_LAYER_HEIGHT + 4)
            rect = QRectF(self.time_to_px(c["start_time"]), sub_y, max(12.0, c["duration"] * self.px_per_sec), self.SUB_LAYER_HEIGHT - 2)
            if rect.contains(px, py): return c
        return None

    def delete_selected_clip(self) -> None:
        if not self._selected_clip_id: return
        cid = self._selected_clip_id
        self.clips = [c for c in self.clips if c["clip_id"] != cid]
        self._selected_clip_id = None
        self.clipDeleted.emit(cid); self.update()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        clip = self._find_clip_at(event.pos().x(), event.pos().y())
        menu = QMenu(self)
        if clip:
            menu.addAction("🗑️ 删除此片段").triggered.connect(lambda: self._delete_clip_by_id(clip["clip_id"]))
            if clip.get("asset_type") == "trajectory":
                menu.addAction("👥 绑定默认阵型").triggered.connect(lambda: self._bind_formation(clip))
        else:
            menu.addAction("➕ 添加单机轨道").triggered.connect(self._add_single_track)
        menu.exec(event.globalPos())

    def _delete_clip_by_id(self, cid: str) -> None:
        self.clips = [c for c in self.clips if c["clip_id"] != cid]
        self.clipDeleted.emit(cid); self.update()

    def _bind_formation(self, clip: Dict[str, Any]) -> None:
        clip["formation_id"] = "form_default"; self.clipChanged.emit(clip); self.update()

    def _add_single_track(self) -> None:
        seq = len(self.tracks) + 1
        rid = chr(ord('A') + seq - 1) if seq <= 26 else f"R{seq}"
        self.tracks.append({"id": f"track_{rid}", "name": f"机器人 {rid}", "is_group": False, "robot_id": rid})
        self.update()

    def get_all_clips(self) -> List[Dict[str, Any]]: return copy.deepcopy(self.clips)
    def set_clips(self, clips: List[Dict[str, Any]]) -> None: self.clips = copy.deepcopy(clips); self.update()
    def clear_clips(self) -> None: self.clips.clear(); self._selected_clip_id = None; self.update()
