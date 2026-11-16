# @file: src/services/playback_coordinator.py
# @brief: 50Hz multi-viewport playback clock driving 2D stage, 3D GL avatars, timeline playhead, and progress bar.
# @exports: PlaybackCoordinator

from __future__ import annotations

from typing import Optional
from PySide6.QtCore import QObject, QTimer, Signal

from src.core.event_bus import StudioEvent
from src.services.studio_state_service import StudioStateService


class PlaybackCoordinator(QObject):
    """Synchronized master show clock emitting smooth 50Hz timecode updates."""

    timeChanged = Signal(float)
    stateChanged = Signal(bool)

    def __init__(self, state: StudioStateService, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.state = state
        self.is_playing = False
        self.speed = 1.0
        self._dt_sec = 0.02
        self._timer = QTimer(self)
        self._timer.setInterval(20)
        self._timer.timeout.connect(self._on_tick)

    def toggle_play(self) -> bool:
        if self.is_playing:
            self.pause()
        else:
            self.play()
        return self.is_playing

    def play(self) -> None:
        total = self.state.total_duration()
        if self.state.playhead_s >= total - 0.02:
            self.state.playhead_s = 0.0
        self.is_playing = True
        self._timer.start()
        self.stateChanged.emit(True)
        self.state.bus.publish(StudioEvent.PLAYBACK_STATE_CHANGED, True)

    def pause(self) -> None:
        self.is_playing = False
        self._timer.stop()
        self.stateChanged.emit(False)
        self.state.bus.publish(StudioEvent.PLAYBACK_STATE_CHANGED, False)

    def replay(self) -> None:
        self.seek(0.0)
        self.play()

    def seek(self, t_sec: float) -> None:
        total = self.state.total_duration()
        clamped = max(0.0, min(float(t_sec), total))
        self.state.playhead_s = clamped
        self.timeChanged.emit(clamped)
        self.state.bus.publish(StudioEvent.PLAYHEAD_MOVED, clamped)

    def set_speed(self, speed_factor: float) -> None:
        self.speed = max(0.1, min(4.0, float(speed_factor)))

    def _on_tick(self) -> None:
        total = self.state.total_duration()
        nxt = self.state.playhead_s + self._dt_sec * self.speed
        if nxt >= total:
            self.state.playhead_s = total
            self.timeChanged.emit(total)
            self.state.bus.publish(StudioEvent.PLAYHEAD_MOVED, total)
            self.pause()
            return
        self.state.playhead_s = nxt
        self.timeChanged.emit(nxt)
        self.state.bus.publish(StudioEvent.PLAYHEAD_MOVED, nxt)
