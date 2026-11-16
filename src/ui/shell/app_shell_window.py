# @file: src/ui/shell/app_shell_window.py
# @brief: Master UniUni v3 main window shell with 32px UTitlebar, 6-page QStackedWidget, and 28px UStatusBar.
# @exports: UniUniAppShell

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.event_bus import StudioEvent
from src.core.settings import get_settings
from src.services import PlaybackCoordinator, StudioStateService
from src.ui.design_system.tokens import C_TEXT_2
from src.ui.design_system.ugc_v3_qss import build_ugc_v3_stylesheet
from src.ui.shell.shortcut_manager import ShortcutManager
from src.ui.shell.u_statusbar import UStatusBar
from src.ui.shell.u_titlebar import PAGE_DEFS, UTitlebar


class UniUniAppShell(QMainWindow):
    """Canonical UniUni v3 desktop application shell hosting all 6 studio pages."""

    def __init__(
        self,
        serial_manager: Optional[Any] = None,
        dance_updater: Optional[Any] = None,
        ssh_channel: Optional[Any] = None,
        initial_page: str = "choreography",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("UniUniAppShell")
        cfg = get_settings()
        self.setWindowTitle(cfg.app_title)
        self.resize(cfg.ui_layout.default_width, cfg.ui_layout.default_height)
        self.setMinimumSize(cfg.ui_layout.min_width, cfg.ui_layout.min_height)
        self.setStyleSheet(build_ugc_v3_stylesheet())

        self.state = StudioStateService(
            serial_manager=serial_manager,
            dance_updater=dance_updater,
            ssh_channel=ssh_channel,
        )
        self.playback = PlaybackCoordinator(self.state, self)
        self._page_widgets: Dict[str, QWidget] = {}
        self._modal_hooks: Dict[str, Callable[[], None]] = {}

        central = QWidget(self)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.titlebar = UTitlebar(central)
        self.stack = QStackedWidget(central)
        self.statusbar = UStatusBar(version=cfg.version, parent=central)

        root_layout.addWidget(self.titlebar)
        root_layout.addWidget(self.stack, 1)
        root_layout.addWidget(self.statusbar)
        self.setCentralWidget(central)

        self._init_default_pages()
        self._wire_signals()
        self._bind_shortcuts()
        self.switch_page(initial_page)
        self._refresh_statusbar()

    def _init_default_pages(self) -> None:
        for key, title in PAGE_DEFS:
            placeholder = QWidget(self.stack)
            l = QVBoxLayout(placeholder)
            lbl = QLabel(f"{title} ({key}) — Ready", placeholder)
            lbl.setStyleSheet(f"color: {C_TEXT_2}; font-size: 14px; padding: 24px;")
            l.addWidget(lbl)
            self._page_widgets[key] = placeholder
            self.stack.addWidget(placeholder)

    def set_page_widget(self, page_key: str, widget: QWidget) -> None:
        """Replace a stacked page slot cleanly without breaking outer shell references."""
        old = self._page_widgets.get(page_key)
        if old is not None:
            idx = self.stack.indexOf(old)
            self.stack.removeWidget(old)
            old.deleteLater()
            self.stack.insertWidget(max(0, idx), widget)
        else:
            self.stack.addWidget(widget)
        self._page_widgets[page_key] = widget
        if self.titlebar._tab_buttons.get(page_key) and self.titlebar._tab_buttons[page_key].isChecked():
            self.stack.setCurrentWidget(widget)

    def register_modal_hook(self, hook_name: str, callback: Callable[[], None]) -> None:
        self._modal_hooks[hook_name] = callback

    def switch_page(self, page_key: str) -> None:
        widget = self._page_widgets.get(page_key)
        if widget is not None:
            self.stack.setCurrentWidget(widget)
            self.titlebar.set_active_page(page_key)

    def _wire_signals(self) -> None:
        self.titlebar.pageSelected.connect(self.switch_page)
        self.titlebar.deviceOverviewClicked.connect(lambda: self._invoke_hook("device_overview"))
        self.titlebar.sceneMenuClicked.connect(lambda: self._invoke_hook("stage_size"))
        self.titlebar.helpMenuClicked.connect(self._show_help_dialog)
        self.statusbar.initPointsClicked.connect(lambda: self._invoke_hook("init_points"))
        self.statusbar.musicClicked.connect(lambda: self._invoke_hook("bpm_music"))

        self.playback.timeChanged.connect(
            lambda t: self.statusbar.set_timecode(t, self.state.total_duration())
        )
        self.state.bus.subscribe(StudioEvent.SCENE_CHANGED, lambda _p: self._refresh_statusbar())
        self.state.bus.subscribe(StudioEvent.TRACKS_UPDATED, lambda _p: self._refresh_statusbar())
        self.state.bus.subscribe(StudioEvent.TIMELINE_UPDATED, lambda _p: self._refresh_statusbar())
        self.state.bus.subscribe(StudioEvent.INIT_POINTS_UPDATED, lambda p: self._refresh_statusbar(p))
        self.state.bus.subscribe(StudioEvent.STATUS_NOTIFICATION, self._on_status_notice)
        self.state.bus.subscribe(
            StudioEvent.PAGE_NAVIGATION_REQUESTED,
            lambda k: self.switch_page(str(k)),
        )

    def _bind_shortcuts(self) -> None:
        sm = ShortcutManager(self)
        sm.register("Space", self.playback.toggle_play)
        sm.register("Ctrl+Z", lambda: self._run_undo(redo=False))
        sm.register("Ctrl+Y", lambda: self._run_undo(redo=True))
        sm.register("Ctrl+S", lambda: self._invoke_hook("save_all"))
        for idx, (key, _) in enumerate(PAGE_DEFS, 1):
            sm.register(f"Ctrl+{idx}", lambda k=key: self.switch_page(k))

    def _run_undo(self, redo: bool) -> None:
        desc = self.state.undo_stack.redo() if redo else self.state.undo_stack.undo()
        if desc:
            verb = "重做" if redo else "撤销"
            self.state.notify(f"已{verb}: {desc}", "ok")

    def _invoke_hook(self, name: str) -> None:
        fn = self._modal_hooks.get(name)
        if fn is not None:
            fn()

    def _refresh_statusbar(self, init_preset_name: object = None) -> None:
        music_name = os.path.basename(self.state.scene.audio_path) if self.state.scene.audio_path else ""
        init_txt = str(init_preset_name) if isinstance(init_preset_name, str) and init_preset_name else ""
        self.statusbar.set_scene_summary(self.state.scene.name, len(self.state.tracks), music_name, init_txt)
        self.statusbar.set_timecode(self.state.playhead_s, self.state.total_duration())

    def _on_status_notice(self, payload: object) -> None:
        if isinstance(payload, dict):
            self.statusbar.set_notification(str(payload.get("text", "")), str(payload.get("tone", "info")))

    def _show_help_dialog(self) -> None:
        QMessageBox.information(
            self,
            "UniSwarm Studio 快捷键与操作指南",
            "【通用快捷键】Space: 播放/暂停 | Ctrl+S: 保存工程 | Ctrl+Z/Y: 撤销/重做 | Ctrl+1..6: 切换工作区\n"
            "【主舞台轨迹绘制】点击『轨迹绘制』后左键落点、右键完成并保存、Alt+左键平移动画布、Ctrl+Z 撤回点。\n"
            "【时间轴编排】点击『+ 轨道』添加真实机器人，右键轨道头可编辑/静音/锁定/删除，Del 删选中块。",
        )
