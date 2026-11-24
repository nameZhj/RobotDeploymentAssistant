# @file: src/ui/choreography/timeline_header.py
# @brief: 38px UniUni task-chain top control bar with local preview controls, track/task dialogs, and HTTP deploy.
# @exports: TimelineHeader

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QWidget

from src.core.event_bus import StudioEvent
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.tokens import C_CARD, C_TEXT_2, FONT_MONO, H_BTN_XS, LINE
from src.ui.design_system.u_buttons import UBadge, UButton


class TimelineHeader(QFrame):
    """Top toolbar above task-chain lanes housing core play/stop-to-origin/track/deploy controls with zero overlap."""

    addTrackClicked = Signal()
    playToggleClicked = Signal()
    stopClicked = Signal()
    saveClicked = Signal()
    switchTaskClicked = Signal()
    saveFragmentClicked = Signal()
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
        hl.setSpacing(6)

        specs = (
            ("播放", "default", "play", "播放 / 暂停本地任务链预览", self.playToggleClicked),
            ("复位", "default", "stop", "停止本地预览并重置游标（不触发真机移动）", self.stopClicked),
            ("保存", "default", "save", "保存当前工程", self.saveClicked),
            ("轨道", "primary", "plus", "添加真实机器人轨道", self.addTrackClicked),
            ("任务", "default", "folder", "切换或新建编排任务", self.switchTaskClicked),
            ("站位", "default", "target", "配置机器人初始原点站位", self.initPointsClicked),
            ("预检", "default", "check", "演出前安全与在线设备预检", self.preCheckClicked),
            ("下发", "default", "upload", "通过 Wi-Fi HTTP 下发任务链", self.httpDeployClicked),
        )
        self._play_btn: UButton | None = None
        for text, var, icon, tip, sig in specs:
            b = UButton(text, variant=var, size="xs", icon_name=icon, tooltip=tip, parent=self)
            b.setFixedHeight(H_BTN_XS)
            b.clicked.connect(sig.emit)
            if text == "播放":
                self._play_btn = b
            hl.addWidget(b)

        more_btn = UButton("更多", variant="ghost", size="xs", tooltip="任务片段与工程 JSON 工具", parent=self)
        more_btn.setFixedHeight(H_BTN_XS)
        more_menu = QMenu(more_btn)
        more_menu.addAction("任务片段管理", self.saveFragmentClicked.emit)
        more_menu.addAction("查看 / 导出 JSON", self.jsonViewClicked.emit)
        more_btn.setMenu(more_menu)
        hl.addWidget(more_btn)

        hl.addStretch(1)
        self.task_lbl = QLabel("", self)
        self.task_lbl.setStyleSheet(f"color: {C_TEXT_2}; font-size: 11px;")
        self.task_lbl.setMaximumWidth(140)
        hl.addWidget(self.task_lbl)

        self.dur_badge = UBadge("任务链 0 项", tone="neutral", parent=self)
        self.dur_badge.setStyleSheet(f"font-family: {FONT_MONO}; font-size: 11px;")
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
        active_cnt = sum(1 for b in self.state.blocks if not b.is_ignored)
        self.dur_badge.setText(f"任务链 {active_cnt} 项")
