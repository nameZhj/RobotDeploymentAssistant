# @file: src/ui/mapping/navigation_map_page.py
# @brief: Clean 3-column UniUni Page 3 Mapping & Navigation workspace (PCD Manager | 3D/2D Viewer | Teleop SLAM).
# @exports: NavigationMapPage

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QWidget

from src.services.studio_state_service import StudioStateService
from src.ui.choreography.stage_canvas_2d import StageCanvas2D
from src.ui.design_system.u_buttons import UIconButton, USegmented
from src.ui.design_system.u_panels import UPanel
from src.ui.mapping.pcd_map_library_dock import PcdMapLibraryDock
from src.ui.mapping.teleop_mapping_dock import TeleopMappingDock
from src.viewport3d.stage_viewport_3d import StageViewport3D


class NavigationMapPage(QWidget):
    """3-column PCD map & teleop SLAM page guaranteeing zero cramped buttons."""

    def __init__(self, state: StudioStateService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        self.lib_dock = PcdMapLibraryDock(state, self)
        self.center_panel = UPanel(title="点云 / 2D 栅格地图视口", header_widgets=[], parent=self)
        self.mode_switch = USegmented(["3D 点云", "2D 栅格"], default="3D 点云", parent=self.center_panel)
        self.reset_b = UIconButton("home", tooltip="重置地图视角", size=24, parent=self.center_panel)
        hdr = self.center_panel.header_bar.layout()
        hdr.addWidget(self.reset_b)
        hdr.addWidget(self.mode_switch)

        self.stack = QStackedWidget(self.center_panel.body_widget)
        self.vp3d = StageViewport3D(state, self.stack)
        self.map2d = StageCanvas2D(state, self.stack)
        self.stack.addWidget(self.vp3d)
        self.stack.addWidget(self.map2d)
        self.center_panel.body_layout.addWidget(self.stack, 1)

        self.teleop_dock = TeleopMappingDock(state, self)

        lay.addWidget(self.lib_dock)
        lay.addWidget(self.center_panel, 1)
        lay.addWidget(self.teleop_dock)

        self.mode_switch.currentChanged.connect(lambda m: self.stack.setCurrentIndex(0 if "3D" in m else 1))
        self.reset_b.clicked.connect(
            lambda: self.vp3d.reset_view("iso") if self.stack.currentIndex() == 0 else self.map2d.reset_view()
        )
        self.lib_dock.cloudLoaded.connect(lambda _m, cloud: self.vp3d.set_point_cloud(cloud.points_xyz, cloud.colors_rgb))
        self.teleop_dock.slamCloudUpdated.connect(lambda pts, rgb: self.vp3d.set_point_cloud(pts, rgb))
