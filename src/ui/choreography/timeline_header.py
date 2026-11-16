# @file: src/ui/choreography/timeline_header.py
# @brief: 38px UniUni timeline top control bar with task management, quick dialogs, BPM, and HTTP cluster deploy.
# @exports: TimelineHeader

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from src.core.event_bus import StudioEvent
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.tokens import C_CARD, C_TEXT_2, FONT_MONO, H_BTN_XS, LINE
from src.ui.design_system.u_buttons import UBadge, UButton


class TimelineHeader(QFrame):
    """Top toolbar above timeline lanes housing task, track, fragment, check, and deploy controls."""

    addTrackClicked = Signal()
    playToggleClicked = Signal()
    saveClicked = Signal()
    switchTaskClicked = Signal()
    saveFragmentClicked = Signal()
    rangeIoClicked = Signal()
    bpmClicked = Signal()
    preCheckClicked = Signal()
    jsonViewClicked = Signal()
    httpDeployClicked = Signal()
    initPointsClicked = Signal()

    def __init__(self, state: StudioStateService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.setFixedHeight(38)
        self.setStyleSheet(f"TimelineHeader {{ background: {C_CARD}; border-bottom: 1px solid {LINE}; }}")

        hl = QHBoxLayout(self)
        hl.setContentsMargins(8, 0, 8, 0)
        hl.setSpacing(5)

        specs = (
            ("播放", "default", "play", self.playToggleClicked),
            ("保存", "default", "save", self.saveClicked),
            ("轨道", "primary", "plus", self.addTrackClicked),
            ("任务", "default", "folder", self.switchTaskClicked),
            ("站位", "default", "target", self.initPointsClicked),
            ("片段", "default", "bookmark", self.saveFragmentClicked),
            ("区间I/O", "default", "sliders", self.rangeIoClicked),
            ("节拍", "default", "music", self.bpmClicked),
            ("预检", "default", "check", self.preCheckClicked),
            ("JSON", "default", "file", self.jsonViewClicked),
            ("下发", "default", "upload", self.httpDeployClicked),
        )
        self._play_btn: UButton | None = None
        for text, var, icon, sig in specs:
            b = UButton(text, variant=var, size="xs", icon_name=icon, parent=self)
            b.setFixedHeight(H_BTN_XS)
            b.clicked.connect(sig.emit)
            if text == "播放":
                self._play_btn = b
            hl.addWidget(b)

        hl.addStretch(1)
        self.task_lbl = QLabel("", self)
        self.task_lbl.setStyleSheet(f"color: {C_TEXT_2}; font-size: 11px;")
        self.task_lbl.setMaximumWidth(120)
        hl.addWidget(self.task_lbl)

        self.bpm_badge = UBadge("120 BPM", tone="accent", parent=self)
        self.dur_badge = UBadge("00:30", tone="neutral", parent=self)
        self.dur_badge.setStyleSheet(f"font-family: {FONT_MONO}; font-size: 11px;")
        hl.addWidget(self.bpm_badge)
        hl.addWidget(self.dur_badge)

        state.bus.subscribe(StudioEvent.SCENE_CHANGED, lambda _p: self.refresh())
        state.bus.subscribe(StudioEvent.TASK_SWITCHED, lambda _p: self.refresh())
        state.bus.subscribe(StudioEvent.TIMELINE_UPDATED, lambda _p: self.refresh())
        state.bus.subscribe(StudioEvent.PLAYBACK_STATE_CHANGED, self._on_play_state)
        self.refresh()

    def _on_play_state(self, playing: object) -> None:
        if self._play_btn is not None:
            self._play_btn.setText("暂停" if playing else "播放")

    def refresh(self) -> None:
        self.task_lbl.setText(f"当前: {self.state.task.name}")
        self.bpm_badge.setText(f"{self.state.scene.bpm:.0f} BPM")
        self.dur_badge.setText(f"{self.state.total_duration():.1f}s")
