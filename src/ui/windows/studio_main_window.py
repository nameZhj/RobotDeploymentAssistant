"""
@file: src/ui/windows/studio_main_window.py
@brief: 编排演播主窗口，集成 F-01~F-06 核心服务与顶底栏三工作台切换栈
@exports: StudioMainWindow
"""
import os
from typing import Optional, Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QVBoxLayout, QWidget
from src.application.services.swarm_monitor_service import SwarmMonitorService
from src.application.studio_controller import StudioController
from src.domain.kinematics.performance_sampler import StagePerformanceSampler
from src.domain.map.grid_and_calibration import MapGridProcessor
from src.domain.timeline.timeline_sequencer import TimelineSequencerEngine
from src.domain.trajectory.spline_builder import SplineTrajectoryBuilder
from src.domain.trajectory.ugc_guard_validator import UgcGuardValidator
from src.infrastructure.storage.studio_repository import StudioRepository
from src.ui.dialogs.view_tool_dialogs import open_view_tool_dialog
from src.ui.map_page.navigation_map_page import NavigationMapPage
from src.ui.monitor_page.monitor_page_view import MonitorPageView
from src.ui.shell.header_and_footer import StudioFooterBar, StudioHeaderBar
from src.ui.windows.main_studio_window import MainStudioWindow


class StudioMainWindow(QMainWindow):
    """全局主外壳窗口，聚合 SQLite 仓储、标定、样条、校验、时间轴、FK 及集群服务"""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        serial_manager: Optional[Any] = None,
        dance_updater: Optional[Any] = None,
        ssh_channel: Optional[Any] = None,
    ) -> None:
        super().__init__(parent)
        self.serial_manager = serial_manager
        self.dance_updater = dance_updater
        self.ssh_channel = ssh_channel
        self.repo = StudioRepository()
        self.grid_proc = MapGridProcessor()
        self.spline_builder = SplineTrajectoryBuilder()
        self.ugc_guard = UgcGuardValidator()
        self.timeline_engine = TimelineSequencerEngine()
        self.sampler = StagePerformanceSampler()
        self.swarm_service = SwarmMonitorService()
        self.controller = StudioController()

        self._init_window()
        self._build_layout()
        self._connect_signals()
        self._sync_initial_state()

    def _init_window(self) -> None:
        self.setWindowTitle("ChoreoNexus Studio - 机器人集群编排与演播控制台")
        self.resize(1440, 900)
        self.setMinimumSize(1200, 720)

    def _build_layout(self) -> None:
        root = QWidget(self)
        root.setObjectName("studioRoot")
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = StudioHeaderBar(self)
        layout.addWidget(self.header)

        self.stack = QStackedWidget(self)
        layout.addWidget(self.stack, 1)

        self.page_choreo = MainStudioWindow(self, controller=self.controller)
        self.stack.addWidget(self.page_choreo)

        self.page_monitor = MonitorPageView(self, controller=self.controller)
        self.stack.addWidget(self.page_monitor)

        self.page_map = NavigationMapPage(self, controller=self.controller)
        self.stack.addWidget(self.page_map)

        self.footer = StudioFooterBar(self)
        layout.addWidget(self.footer)

    def _connect_signals(self) -> None:
        self.header.page_changed.connect(self.stack.setCurrentIndex)
        self.header.scene_changed.connect(self._on_scene_changed)
        self.header.menu_action_triggered.connect(self._on_menu_action)
        self.header.settings_clicked.connect(lambda: open_view_tool_dialog(self, "系统设置"))
        self.footer.init_point_clicked.connect(self._on_init_point_clicked)
        self.footer.music_clicked.connect(self._on_music_clicked)

    def _sync_initial_state(self) -> None:
        scene = self.repo.get_scene("123")
        if scene:
            self.footer.set_scene_name(scene.get("name", "123"))
            self.footer.set_music_title(scene.get("music_title", "未配置音乐"))
        configs = self.repo.get_init_point_configs("123", cfg_id=1)
        if configs:
            self.footer.set_init_cfg(configs[0].get("cfg_name", "配置 1"))

    def _on_scene_changed(self, scene_id: str) -> None:
        scene = self.repo.get_scene(scene_id)
        name = scene["name"] if scene else scene_id
        self.footer.set_scene_name(name)
        if scene and scene.get("music_title"):
            self.footer.set_music_title(scene["music_title"])

    def _on_menu_action(self, action_name: str) -> None:
        open_view_tool_dialog(self, action_name)

    def _on_init_point_clicked(self) -> None:
        from src.ui.dialogs.functional_tool_dialogs import InitPointEditDialog
        dlg = InitPointEditDialog(parent=self)
        dlg.show() if os.environ.get("QT_QPA_PLATFORM") == "offscreen" else dlg.exec_()

    def _on_music_clicked(self) -> None:
        from src.ui.dialogs.functional_tool_dialogs import MusicSelectDialog
        dlg = MusicSelectDialog(parent=self)
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            dlg.show()
        elif dlg.exec_() and dlg.selected_path:
            title = os.path.basename(dlg.selected_path)
            self.repo.update_music("123", dlg.selected_path, title, 120.0)
            self.footer.set_music_title(title)
