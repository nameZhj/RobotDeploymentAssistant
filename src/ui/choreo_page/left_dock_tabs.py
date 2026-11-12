"""
@file: src/ui/choreo_page/left_dock_tabs.py
@brief: 舞台编导左侧三Tab整合坞（地图管理、阵型设计与动作/轨迹素材库）
@exports: LeftDockTabs
"""
import glob
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)
from src.core.models import FormationMember, FormationModel
from src.core.storage_manager import storage_manager
from src.ui.asset_library import AssetLibraryPanel
from src.ui.choreo_page.stage_dock_left_panel import StageDockLeftPanel
from src.ui.formation_panel import FormationPanel
from src.ui.map_manager_panel import MapManagerPanel

logger = logging.getLogger("LeftDockTabs")


class LeftDockTabs(QWidget):
    """舞台编导左侧停靠区：集成地图管理、阵型设计与素材库三大工作台"""

    mapLoaded = Signal(dict, object)
    mapUnloaded = Signal()
    formationApplied = Signal(dict)
    robotSelected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None, controller: Optional[Any] = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(4)

        self.tabs = QTabWidget(self)
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #1e293b; background: #0f172a; border-radius: 4px; }
            QTabBar::tab { background: #1e293b; color: #94a3b8; padding: 6px 10px; font-size: 11px; font-weight: 600; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background: #0284c7; color: #ffffff; }
        """)

        # Tab 1: 地图管理面板
        map_ctrl = getattr(self.controller, "map_controller", None) if self.controller else None
        self.map_panel = MapManagerPanel(self, controller=map_ctrl)
        self.map_panel.sig_map_loaded.connect(self.mapLoaded.emit)
        self.map_panel.sig_map_unloaded.connect(self.mapUnloaded.emit)
        self.tab_map = self.map_panel
        self.tabs.addTab(self.tab_map, "🗺️ 地图")

        # Tab 2: 阵型设计
        self.formation_panel = FormationPanel(self)
        self.formation_panel.sig_formation_changed.connect(self.formationApplied.emit)
        self.tab_formation = self.formation_panel
        self.list_formations = self.formation_panel.list_saved
        self.tabs.addTab(self.tab_formation, "👥 阵型")

        # Tab 3: 动作/轨迹素材库
        self.asset_library = AssetLibraryPanel(self)
        self.lib_panels = self.asset_library
        self.tabs.addTab(self.asset_library, "💃 素材库")

        # 舞台机器人站位面板
        self.stage_dock = StageDockLeftPanel(self)
        self.stage_dock.robotSelected.connect(self.robotSelected.emit)
        self.tabs.addTab(self.stage_dock, "🤖 机器人")

        main_layout.addWidget(self.tabs)

    def refresh_formations(self) -> None:
        if hasattr(self, "formation_panel"):
            self.formation_panel.refresh_saved_list()
