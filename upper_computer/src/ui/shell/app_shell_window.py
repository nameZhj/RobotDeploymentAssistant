# @file: src/ui/shell/app_shell_window.py
# @brief: Master main window shell with 32px UTitlebar, 4-page QStackedWidget, 28px UStatusBar, and GUI-thread event bus bridge.
# @exports: StudioAppShell

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional, Tuple
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.event_bus import StudioEvent, Subscription
from src.core.settings import get_settings
from src.services import PlaybackCoordinator, StudioStateService
from src.ui.common.async_task import run_in_background
from src.ui.design_system.tokens import C_TEXT_2
from src.ui.design_system.ugc_v3_qss import build_ugc_v3_stylesheet
from src.ui.shell.shortcut_manager import ShortcutManager
from src.ui.shell.u_statusbar import UStatusBar
from src.ui.shell.u_titlebar import PAGE_DEFS, UTitlebar

logger = logging.getLogger(__name__)


class _EventBusBridge(QObject):
    """Marshals StudioEventBus.publish() calls made from worker threads onto the GUI thread."""

    _invoke = Signal(object)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._invoke.connect(self._run, Qt.ConnectionType.QueuedConnection)

    def submit(self, fn: Callable[[], None]) -> None:
        self._invoke.emit(fn)

    def _run(self, fn: Callable[[], None]) -> None:
        fn()


class StudioAppShell(QMainWindow):
    """Canonical desktop application shell hosting all 4 studio pages."""

    def __init__(
        self,
        serial_manager: Optional[Any] = None,
        dance_updater: Optional[Any] = None,
        ssh_channel: Optional[Any] = None,
        initial_page: str = "choreography",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("StudioAppShell")
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
        self._bus_callback_pairs: Tuple[Tuple[StudioEvent, Callable[[Any], None]], ...] = ()
        self._bus_subscriptions: List[Subscription] = []

        # Worker threads (HTTP callbacks, background tasks) publish through this bridge so that
        # every Qt widget is only ever touched from the GUI thread that owns it.
        self._bus_bridge = _EventBusBridge(self)
        self.state.bus.set_dispatcher(self._bus_bridge.submit)

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
        if widget is None:
            page_key = "choreography"
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

        from src.services.task_chain_normalizer import active_chain_node_label
        self.playback.timeChanged.connect(
            lambda t: self.statusbar.set_timecode(
                t, self.state.effective_playback_duration() or self.state.total_duration(),
                active_chain_node_label(self.state.blocks, t, is_playing=self.playback.is_playing),
            )
        )
        # 急停回原点：services 层仅复位，HTTP 指令由 UI 层在后台线程下发（分层单向依赖）
        self.playback.stoppedToOrigin.connect(self._dispatch_stop_to_origin_http)
        self._subscribe_bus_events()

    def _subscribe_bus_events(self) -> None:
        """(Re)register the six shell-level bus listeners, keeping Subscription handles for closeEvent (R-8)."""
        if not self._bus_callback_pairs:
            self._bus_callback_pairs = (
                (StudioEvent.SCENE_CHANGED, lambda _p: self._refresh_statusbar()),
                (StudioEvent.TRACKS_UPDATED, lambda _p: self._refresh_statusbar()),
                (StudioEvent.TIMELINE_UPDATED, lambda _p: self._refresh_statusbar()),
                (StudioEvent.INIT_POINTS_UPDATED, lambda p: self._refresh_statusbar(p)),
                (StudioEvent.STATUS_NOTIFICATION, self._on_status_notice),
                (StudioEvent.PAGE_NAVIGATION_REQUESTED, lambda k: self.switch_page(str(k))),
            )
        self._bus_subscriptions = [
            self.state.bus.subscribe(topic, cb) for topic, cb in self._bus_callback_pairs
        ]

    def rearm_event_flow(self) -> None:
        """Re-arm the GUI-thread dispatcher, shell subscriptions and telemetry listener for window reuse (R-1).

        Must be invoked on the GUI thread (set_dispatcher captures the owning thread id); main.py's
        reuse path calls it from the Qt-queued _handle_show, which satisfies that constraint.
        """
        self._subscribe_bus_events()
        self.state.bus.set_dispatcher(self._bus_bridge.submit)
        if not self.state.callback_listener.is_running:
            try:
                self.state.callback_listener.start()
            except Exception as ex:
                logger.error(f"遥测回调监听器重启失败: {ex}", exc_info=True)

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

    def _dispatch_stop_to_origin_http(self) -> None:
        """Wi-Fi HTTP 停止并回原点指令的 UI 层后台下发（订阅 playback.stoppedToOrigin）。"""
        if not self.state.tracks:
            return
        run_in_background(
            self.state.stop_all_robots_and_return_origin_http,
            on_done=self._on_stop_http_done,
            on_error=lambda err: self.state.notify(f"回原点指令下发异常: {err.splitlines()[0]}", "warn"),
            busy_text="正在后台向全队下发停止并回原点指令 (Wi-Fi HTTP)...",
            notifier=self.state.notify,
        )

    def _on_stop_http_done(self, results: object) -> None:
        rows = results if isinstance(results, list) else []
        ok_cnt = sum(1 for r in rows if isinstance(r, dict) and r.get("ok"))
        if rows:
            self.state.notify(f"回原点指令下发完成：{ok_cnt}/{len(rows)} 台响应", "ok" if ok_cnt == len(rows) else "warn")

    def _invoke_hook(self, name: str) -> None:
        fn = self._modal_hooks.get(name)
        if fn is not None:
            fn()

    def _refresh_statusbar(self, init_preset_name: object = None) -> None:
        from src.services.task_chain_normalizer import active_chain_node_label
        music_name = os.path.basename(self.state.scene.audio_path) if self.state.scene.audio_path else ""
        init_txt = str(init_preset_name) if isinstance(init_preset_name, str) and init_preset_name else ""
        self.statusbar.set_scene_summary(self.state.scene.name, len(self.state.tracks), music_name, init_txt)
        self.statusbar.set_timecode(
            self.state.playhead_s,
            self.state.effective_playback_duration() or self.state.total_duration(),
            active_chain_node_label(self.state.blocks, self.state.playhead_s, is_playing=self.playback.is_playing),
        )

    def _on_status_notice(self, payload: object) -> None:
        if isinstance(payload, dict):
            self.statusbar.set_notification(str(payload.get("text", "")), str(payload.get("tone", "info")))

    def _show_help_dialog(self) -> None:
        QMessageBox.information(
            self,
            "舞台编导工作台快捷键与操作指南",
            "【通用快捷键】Space: 本地预览播放/暂停 | Ctrl+S: 保存工程 | Ctrl+Z/Y: 撤销/重做 | Ctrl+1..4: 切换 4 大工作区\n"
            "【主舞台轨迹绘制】点击『轨迹绘制』后左键落点、右键完成并保存、Esc 退出恢复『选择/移动』拖拽机器人起点。\n"
            "【真机任务链演出】在『舞蹈编排/队形规划』编排节点，在『表演监测』点击 PREP/PLAY/STOP 回原点（纯 Wi-Fi HTTP，后台执行不卡界面）。\n"
            "【网络与配网】机器人 Wi-Fi 配网、网卡与 License 管理统一在主页『网络管理』中完成。",
        )

    def closeEvent(self, event) -> None:
        self.playback.pause()
        # R-8：退订壳层全局总线订阅，避免窗口销毁后旧死回调残留中断其余监听者（复用路径由 rearm_event_flow 重挂）
        for sub in self._bus_subscriptions:
            self.state.bus.unsubscribe(sub.topic, sub.callback)
        self._bus_subscriptions = []
        self.state.bus.clear_dispatcher()
        self.state.callback_listener.stop()
        super().closeEvent(event)
