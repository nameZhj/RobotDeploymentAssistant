"""
@file: src/ui/windows/main_studio_window.py
@brief: 编排演播主窗口，集成 2D/3D 画布、群组轨迹工作区、动作/轨迹库与双层时间轴
@exports: MainStudioWindow
"""
import logging
import time
from typing import Any, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QMainWindow, QMessageBox, QPushButton,
    QSplitter, QStackedLayout, QStackedWidget, QVBoxLayout, QWidget,
)
from src.application.services.virtual_show_player import VirtualShowPlayer
from src.application.stage_director.stage_map_controller import StageMapController
from src.application.stage_director.stage_preview_coordinator import StagePreviewCoordinator
from src.core.config_loader import config_loader
from src.infrastructure.storage.choreo_sqlite_store import ChoreoSqliteStore
from src.ui.choreo_page.choreo_toolbar import ChoreoToolbar
from src.ui.choreo_page.dual_layer_timeline_canvas import DualLayerTimelineCanvas
from src.ui.choreo_page.group_trajectory_workspace import GroupTrajectoryWorkspace
from src.ui.choreo_page.lib_panels_controller import LibPanelsController
from src.ui.choreo_page.stage_canvas_2d import StageCanvas2D
from src.ui.choreo_page.stage_dock_left_panel import StageDockLeftPanel
from src.ui.choreo_page.stage_overlay_controls import StageOverlayControls
from src.ui.choreo_page.timeline_left_toolbar import TimelineLeftToolbar
from src.ui.header.top_show_header import TopShowHeader
from src.ui.stage3d.stage_viewport_3d import StageViewport3D

logger = logging.getLogger("MainStudioWindow")


class MainStudioWindow(QMainWindow):
    """
    Primary Studio Orchestration Window for Robot Deployment Assistant.
    Unifies TopShowHeader, Left Dock, 2D/3D Stage Viewport with floating overlay,
    Right Telemetry Dock, Dual-Layer Timeline, and 60Hz VirtualShowPlayer.
    """

    def __init__(
        self, parent: Optional[QWidget] = None, controller: Optional[Any] = None,
        serial_manager: Optional[Any] = None, dance_updater: Optional[Any] = None,
        ssh_channel: Optional[Any] = None, **kwargs: Any,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.store = ChoreoSqliteStore()
        self.serial_manager = serial_manager
        self.dance_updater = dance_updater
        self.ssh_channel = ssh_channel
        self._app_info = config_loader.get_app_info()
        self._layout_cfg = config_loader.get_ui_layout()
        self._is_syncing_time = False
        self.map_controller = StageMapController()
        self._init_window()
        self._build_layout()
        self._init_choreo_studio()

    def _init_window(self) -> None:
        title = self._app_info.get("app_title", "ChoreoNexus Studio")
        self.setWindowTitle(f"{title} - 舞蹈编排")
        self.resize(int(self._layout_cfg.get("default_width", 1440)), int(self._layout_cfg.get("default_height", 900)))
        self.setMinimumSize(int(self._layout_cfg.get("min_width", 1200)), int(self._layout_cfg.get("min_height", 720)))
        self.setStyleSheet("QMainWindow { background-color: #0b0f19; } QSplitter::handle { background-color: #1e293b; } QSplitter::handle:hover { background-color: #0ea5e9; } QFrame.panel-container { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 6px; }")

    def _build_layout(self) -> None:
        root_widget = QWidget(self); self.setCentralWidget(root_widget)
        root_layout = QVBoxLayout(root_widget)
        root_layout.setContentsMargins(0, 0, 0, 0); root_layout.setSpacing(0)
        self.header = TopShowHeader(self); root_layout.addWidget(self.header)
        self.workspace_stack = QStackedWidget(root_widget); root_layout.addWidget(self.workspace_stack, 1)

        self.single_choreo_widget = QWidget(self.workspace_stack)
        single_layout = QVBoxLayout(self.single_choreo_widget)
        single_layout.setContentsMargins(0, 0, 0, 0); single_layout.setSpacing(0)
        self.toolbar = ChoreoToolbar(self.single_choreo_widget)
        single_layout.addWidget(self.toolbar)

        self.v_splitter = QSplitter(Qt.Vertical, self.single_choreo_widget)
        single_layout.addWidget(self.v_splitter, 1)
        self.workspace_stack.addWidget(self.single_choreo_widget)
        self.group_workspace = GroupTrajectoryWorkspace(self.workspace_stack, controller=self.controller)
        self.workspace_stack.addWidget(self.group_workspace)

        self.h_splitter = QSplitter(Qt.Horizontal, self)
        self.v_splitter.addWidget(self.h_splitter)

        self.left_dock_container = QFrame(self, objectName="leftDockContainer")
        self.left_dock_container.setProperty("class", "panel-container")
        self.left_dock_layout = QVBoxLayout(self.left_dock_container)
        self.left_dock_layout.setContentsMargins(6, 6, 6, 6); self.left_dock_layout.setSpacing(6)
        self.left_dock_container.setMinimumWidth(260)

        self.btn_group_trajectory = QPushButton("👥 群组轨迹", self.left_dock_container, objectName="btnGroupTrajectory")
        self.btn_group_trajectory.setFixedHeight(34); self.btn_group_trajectory.setCursor(Qt.PointingHandCursor)
        self.btn_group_trajectory.setStyleSheet("QPushButton#btnGroupTrajectory { background-color: #1e293b; color: #38bdf8; border: 1px solid #0284c7; border-radius: 4px; font-size: 12px; font-weight: 700; } QPushButton#btnGroupTrajectory:hover { background-color: #0369a1; color: #ffffff; border-color: #38bdf8; }")
        self.btn_group_trajectory.clicked.connect(self.enter_group_trajectory_workspace)
        self.left_dock_layout.addWidget(self.btn_group_trajectory)
        self.stage_dock = StageDockLeftPanel(self.left_dock_container)
        self.left_dock_layout.addWidget(self.stage_dock, 1)
        self.h_splitter.addWidget(self.left_dock_container)

        self.viewport_container = QFrame(self, objectName="stageViewportContainer")
        self.viewport_container.setProperty("class", "panel-container")
        self.viewport_layout = QVBoxLayout(self.viewport_container)
        self.viewport_layout.setContentsMargins(0, 0, 0, 0)
        self.h_splitter.addWidget(self.viewport_container)

        self.right_dock_container = QFrame(self, objectName="rightDockContainer")
        self.right_dock_container.setProperty("class", "panel-container")
        self.right_dock_layout = QVBoxLayout(self.right_dock_container)
        self.right_dock_layout.setContentsMargins(6, 6, 6, 6)
        self.right_dock_container.setMinimumWidth(320)
        self.lib_panels = LibPanelsController(self, controller=self.controller)
        self.right_dock_layout.addWidget(self.lib_panels)
        self.h_splitter.addWidget(self.right_dock_container)
        self.h_splitter.setSizes([280, 860, 360])

        self.timeline_container = QFrame(self, objectName="timelineCanvasContainer")
        self.timeline_container.setProperty("class", "panel-container")
        self.timeline_layout = QHBoxLayout(self.timeline_container)
        self.timeline_layout.setContentsMargins(0, 0, 0, 0); self.timeline_layout.setSpacing(0)
        self.timeline_container.setMinimumHeight(220)
        self.v_splitter.addWidget(self.timeline_container)
        self.v_splitter.setSizes([600, 280])

    def _init_choreo_studio(self) -> None:
        stage_host = QWidget(self.viewport_container)
        stage_stack_layout = QStackedLayout(stage_host)
        stage_stack_layout.setStackingMode(QStackedLayout.StackAll)

        self.stage_stack = QStackedWidget(stage_host)
        self.stage_2d = StageCanvas2D(self.stage_stack, controller=self.controller)
        self.stage_3d = StageViewport3D(self.stage_stack, controller=self.controller)
        self.stage_stack.addWidget(self.stage_2d); self.stage_stack.addWidget(self.stage_3d)

        self.overlay_controls = StageOverlayControls(stage_host)
        stage_stack_layout.addWidget(self.overlay_controls); stage_stack_layout.addWidget(self.stage_stack)
        self.viewport_layout.addWidget(stage_host)

        self.timeline_toolbar = TimelineLeftToolbar(self.timeline_container)
        self.timeline_canvas = DualLayerTimelineCanvas(self.timeline_container, controller=self.controller)
        self.timeline_layout.addWidget(self.timeline_toolbar); self.timeline_layout.addWidget(self.timeline_canvas, 1)

        self.show_player = VirtualShowPlayer(self)
        self.preview_coordinator = StagePreviewCoordinator(self)

        for sig, slot in [
            (self.overlay_controls.viewDimensionChanged, self._on_dimension_changed),
            (self.overlay_controls.animationToggled, self._on_play_toggled),
            (self.overlay_controls.gridToggled, self.stage_3d.set_grid_visible),
            (self.overlay_controls.resetOriginClicked, self.stage_3d.reset_camera),
            (self.overlay_controls.clearAllClicked, self.stage_2d.clear_all),
            (self.overlay_controls.modeChanged, self._on_draw_mode_changed),
            (self.timeline_toolbar.playToggled, self._on_play_toggled),
            (self.timeline_toolbar.saveClicked, self._on_save_button_clicked),
            (self.timeline_canvas.cursorMoved, self._on_timeline_cursor_moved),
            (self.show_player.tick, self._on_player_tick),
            (self.show_player.tick, self.preview_coordinator.on_player_tick),
            (self.show_player.playbackStateChanged, self._on_player_state_changed),
            (self.preview_coordinator.posesUpdated, self.stage_3d.update_robot_poses),
            (self.preview_coordinator.collisionDiagnosed, self.stage_3d.set_collision_diagnostics),
            (self.stage_dock.robotSelected, self.stage_2d.select_robot),
            (self.stage_2d.robotSelected, self.stage_dock.select_robot),
            (self.stage_2d.mapLoaded, self.stage_dock.update_scene_info),
            (self.stage_2d.trajectoryFinished, self._on_trajectory_finished),
            (self.stage_2d.trajectorySaved, self.lib_panels.refresh_trajectories),
            (self.stage_2d.trajectoryDeleted, self.lib_panels.refresh_trajectories),
            (self.lib_panels.trajectorySelected, self._on_lib_traj_selected),
            (self.group_workspace.groupSaved, lambda g: self.lib_panels.refresh_trajectories()),
            (self.group_workspace.groupDeleted, lambda gid: self.lib_panels.refresh_trajectories()),
            (self.toolbar.newRequested, self.header.newProjectRequested.emit),
            (self.toolbar.importRequested, self.header.importProjectRequested.emit),
            (self.toolbar.saveRequested, self._on_toolbar_save),
            (self.toolbar.loadMapRequested, self._open_map_manager),
            (self.toolbar.modeChanged, self.stage_2d.set_draw_mode),
            (self.toolbar.undoRequested, self.stage_2d.undo_waypoint),
            (self.toolbar.clearRequested, self.stage_2d.clear_active_trajectory),
            (self.toolbar.finishRequested, self.stage_2d.finish_trajectory),
            (self.toolbar.resetViewRequested, self.stage_2d.reset_view),
            (self.toolbar.emergencyStopRequested, self._on_emergency_brake),
            (self.group_workspace.backRequested, self.exit_group_trajectory_workspace),
        ]:
            sig.connect(slot)
        self.stage_dock.set_robots(self.stage_2d._robot_spawns)

    def _on_dimension_changed(self, dimension: str) -> None:
        target = self.stage_3d if dimension == "3D" else self.stage_2d
        if dimension == "3D":
            self._sync_preview_data()
        self.stage_stack.setCurrentWidget(target)

    def _sync_preview_data(self) -> None:
        from src.application.stage_director.stage_preview_engine import StagePreviewEngine
        p = StagePreviewEngine.build_preview_tracks(self.store)
        self.show_player.set_tracks(p["robot_tracks"])
        self.show_player.set_duration_ms(p["duration_ms"])
        self.preview_coordinator.set_robot_tracks(p["robot_tracks"])
        self.stage_3d.set_trajectories(p["trajectory_lines"])
        init_poses = self.preview_coordinator.sample_at_time(self.show_player.get_current_time_ms())
        self.stage_3d.update_robot_poses(init_poses)

    def _on_draw_mode_changed(self, mode: str) -> None:
        if self.controller:
            self.controller.draw_mode = mode
        self.stage_2d.set_draw_mode(mode)

    def _on_play_toggled(self, is_playing: bool) -> None:
        if is_playing and not self.show_player.is_playing():
            self._sync_preview_data()
        if self.controller and self.controller.is_playing != is_playing:
            self.controller.toggle_playback()
        if self.show_player.is_playing() != is_playing:
            self.show_player.toggle_play(is_playing)

    def _open_map_manager(self) -> None:
        from src.ui.dialogs.stage_map_dialog import StageMapDialog
        dlg = StageMapDialog(parent=self, controller=self.map_controller)
        dlg.mapLoadedToStage.connect(self._on_map_loaded)
        dlg.mapUnloadedFromStage.connect(self._on_map_unloaded)
        dlg.exec()

    def _on_map_loaded(self, img: Any, info: dict, meta: dict) -> None:
        self.stage_2d.set_grid_data(img, info, meta)
        path = meta.get("file_path", "")
        if path and os.path.exists(path):
            from src.infrastructure.map.pcd_io_engine import PcdMapLoader
            self.stage_3d.set_point_cloud(PcdMapLoader.load_pcd(path))

    def _on_map_unloaded(self) -> None:
        self.stage_2d.set_grid_data(None, None, None)
        self.stage_3d.clear_point_cloud()

    def _on_save_button_clicked(self) -> None:
        # 移除写死 8001 假成功反馈。真实持久化链路在后续阶段接入
        QMessageBox.warning(self, "保存提示", "时间轴编排计划已缓存至当前工作区。\n不可变演播计划编译导出功能正在收敛中，暂未执行持久化。")

    def _on_timeline_cursor_moved(self, time_ms: int) -> None:
        if not self._is_syncing_time:
            self._is_syncing_time = True
            self.show_player.seek(time_ms)
            if self.controller:
                self.controller.seek_time(time_ms / 1000.0)
            self._is_syncing_time = False

    def _on_player_tick(self, time_ms: int, poses: dict) -> None:
        self.stage_3d.update_robot_poses(poses)
        self._is_syncing_time = True
        self.timeline_canvas.set_current_time_ms(time_ms, notify=False)
        self._is_syncing_time = False

    def _on_player_state_changed(self, is_playing: bool) -> None:
        if self.timeline_toolbar.btn_play.isChecked() != is_playing:
            self.timeline_toolbar.btn_play.setChecked(is_playing)

    def _on_emergency_brake(self) -> None:
        logger.warning("PHYSICAL E-STOP ACTIVATED FROM CHOREO TOOLBAR - Not connected to real robot hardware")
        QMessageBox.warning(self, "硬件急停未连接", "当前处于虚拟演播与离线编排模式，未连接真机硬件。\n急停信号仅在真机联调模式下有效。")

    def _on_toolbar_save(self) -> None:
        if getattr(self.stage_2d, "_active_waypoints", None):
            self.stage_2d.finish_trajectory()
        if getattr(self.stage_2d, "_selected_trajectory_id", None):
            self.stage_2d.save_current_trajectory()
        self.lib_panels.refresh_trajectories()
        self.header.saveProjectRequested.emit()

    def _on_trajectory_finished(self, traj_data: dict) -> None:
        logger.info(f"Trajectory captured in Studio: {traj_data.get('name')}")
        self.stage_2d.save_current_trajectory(traj_data.get("id"))
        self.lib_panels.refresh_trajectories()

    def _on_lib_traj_selected(self, data: dict) -> None:
        tid = data.get("asset_id") or data.get("traj_id")
        if tid:
            self.stage_2d.select_trajectory(str(tid))

    def enter_group_trajectory_workspace(self) -> None:
        if hasattr(self, "show_player") and self.show_player.is_playing():
            self.show_player.pause()
        self.workspace_stack.setCurrentIndex(1)

    def exit_group_trajectory_workspace(self) -> None:
        if hasattr(self, "show_player") and self.show_player.is_playing():
            self.show_player.pause()
        self.workspace_stack.setCurrentIndex(0)

    def current_workspace_index(self) -> int:
        return self.workspace_stack.currentIndex()

    def hideEvent(self, event) -> None:
        if hasattr(self, "show_player") and self.show_player.is_playing():
            self.show_player.pause()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        if hasattr(self, "show_player"):
            self.show_player.cleanup()
        super().closeEvent(event)
