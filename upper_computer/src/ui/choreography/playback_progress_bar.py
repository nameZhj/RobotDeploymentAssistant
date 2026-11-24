# @file: src/ui/choreography/playback_progress_bar.py
# @brief: Floating UniUni playback bar with scrubbed seek track, stop-to-origin button, collision markers, and active chain label.
# @exports: PlaybackProgressBar

from __future__ import annotations

from typing import List, Tuple
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from src.core.event_bus import StudioEvent
from src.services.playback_coordinator import PlaybackCoordinator
from src.services.studio_state_service import StudioStateService
from src.services.task_chain_normalizer import active_chain_node_label
from src.ui.design_system.tokens import C_ACCENT, C_DANGER, C_FLOAT, C_FLOAT_EDGE, C_TEXT_1, C_TEXT_2, FONT_MONO
from src.ui.design_system.u_buttons import UBadge, UIconButton, UButton


class _ScrubRail(QWidget):
    """Custom painted scrubber bar highlighting active progress and red collision intervals."""

    seekRequested = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._progress: float = 0.0
        self._duration: float = 10.0
        self._collisions: List[Tuple[float, float]] = []
        self.setFixedHeight(20)
        self.setMinimumWidth(140)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_data(self, t: float, total: float, intervals: List[Tuple[float, float]]) -> None:
        self._duration = max(0.5, total)
        self._progress = max(0.0, min(1.0, t / self._duration))
        self._collisions = intervals
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, cy = max(1, self.width()), self.height() // 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#262b34"))
        p.drawRoundedRect(0, cy - 3, w, 6, 3, 3)

        p.setBrush(QColor(C_DANGER))
        for s0, s1 in self._collisions:
            x0 = int((s0 / self._duration) * w)
            x1 = max(x0 + 3, int((s1 / self._duration) * w))
            p.drawRoundedRect(x0, cy - 3, x1 - x0, 6, 2, 2)

        px = int(self._progress * w)
        p.setBrush(QColor(C_ACCENT))
        p.drawRoundedRect(0, cy - 3, px, 6, 3, 3)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(max(4, min(w - 5, px)) - 4, cy - 4, 9, 9)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        self._emit_seek(e.position().x())

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._emit_seek(e.position().x())

    def _emit_seek(self, px: float) -> None:
        ratio = max(0.0, min(1.0, px / max(1, self.width())))
        self.seekRequested.emit(ratio * self._duration)


class PlaybackProgressBar(QWidget):
    """Floating bottom translucent playback transport bar with stop-to-origin and task-chain indicator."""

    def __init__(self, state: StudioStateService, playback: PlaybackCoordinator, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.playback = playback
        self.setFixedHeight(36)
        self.setStyleSheet(
            f"PlaybackProgressBar {{ background: {C_FLOAT}; border: 1px solid {C_FLOAT_EDGE}; border-radius: 8px; }}"
        )
        hl = QHBoxLayout(self)
        hl.setContentsMargins(8, 0, 8, 0)
        hl.setSpacing(6)

        self.play_btn = UIconButton("play", tooltip="播放 / 暂停", size=24, color=C_TEXT_1, parent=self)
        self.play_btn.clicked.connect(playback.toggle_play)
        hl.addWidget(self.play_btn)

        self.stop_btn = UButton("复位", variant="default", size="xs", icon_name="stop", tooltip="停止本地预览并复位游标（不触发真机移动）", parent=self)
        self.stop_btn.clicked.connect(playback.reset_preview)
        hl.addWidget(self.stop_btn)

        self.replay_btn = UIconButton("replay", tooltip="从原点重播", size=24, color=C_TEXT_2, parent=self)
        self.replay_btn.clicked.connect(playback.replay)
        hl.addWidget(self.replay_btn)

        self.rail = _ScrubRail(self)
        self.rail.seekRequested.connect(playback.seek)
        hl.addWidget(self.rail, 1)

        self.time_lbl = QLabel("原点待命", self)
        self.time_lbl.setStyleSheet(f"font-family: {FONT_MONO}; font-size: 11px; color: {C_TEXT_1}; background: transparent;")
        hl.addWidget(self.time_lbl)

        self.speed_idx = 1
        self._speeds = [0.5, 1.0, 2.0]
        self.speed_btn = UButton("1.0x", variant="ghost", size="xs", parent=self)
        self.speed_btn.clicked.connect(self._cycle_speed)
        hl.addWidget(self.speed_btn)

        self.coll_badge = UBadge("0 碰撞", tone="ok", parent=self)
        hl.addWidget(self.coll_badge)

        playback.timeChanged.connect(lambda _t: self._refresh())
        playback.stateChanged.connect(self._on_play_state)
        state.bus.subscribe(StudioEvent.COLLISION_UPDATED, lambda _c: self._refresh())
        state.bus.subscribe(StudioEvent.TIMELINE_UPDATED, lambda _p: self._refresh())
        self._refresh()

    def _cycle_speed(self) -> None:
        self.speed_idx = (self.speed_idx + 1) % len(self._speeds)
        sp = self._speeds[self.speed_idx]
        self.playback.set_speed(sp)
        self.speed_btn.setText(f"{sp:.1f}x")

    def _on_play_state(self, playing: bool) -> None:
        from src.ui.design_system.svg_icons import render_svg_icon
        self.play_btn.setIcon(render_svg_icon("pause" if playing else "play", color=C_TEXT_1, size=13))

    def _refresh(self) -> None:
        t = self.state.playhead_s
        tot = self.state.total_duration()
        intervals = [(c.start_time, c.end_time) for c in self.state.collisions]
        self.rail.set_data(t, tot, intervals)
        self.time_lbl.setText(active_chain_node_label(self.state.blocks, t, is_playing=self.playback.is_playing))
        n = len(self.state.collisions)
        self.coll_badge.setText(f"{n} 碰撞")
        self.coll_badge.set_tone("danger" if n > 0 else "ok")
