# @file: src/ui/windows/main_studio_window.py
# @brief: Studio entrypoint window composing the UniUni v3 shell and assembling all 6 functional workspace pages.
# @exports: MainStudioWindow

from __future__ import annotations

from typing import Any, Optional
from PySide6.QtWidgets import QWidget

from src.ui.choreography import ChoreographyPage
from src.ui.formation import FormationPlanningPage
from src.ui.mapping import NavigationMapPage
from src.ui.modals import (
    BpmInfoModal,
    DeviceOverviewModal,
    InitPointModal,
    StageSizeModal,
)
from src.ui.monitoring import PerformanceMonitorPage, RadarMonitorPage
from src.ui.network import SystemNetworkPage
from src.ui.shell.app_shell_window import UniUniAppShell


class MainStudioWindow(UniUniAppShell):
    """Unified Studio desktop window preserved as the entry target for main.py."""

    def __init__(
        self,
        serial_manager: Optional[Any] = None,
        dance_updater: Optional[Any] = None,
        ssh_channel: Optional[Any] = None,
        initial_page: str = "choreography",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(
            serial_manager=serial_manager,
            dance_updater=dance_updater,
            ssh_channel=ssh_channel,
            initial_page=initial_page,
            parent=parent,
        )
        self.choreography_page = ChoreographyPage(self.state, self.playback, self)
        self.formation_page = FormationPlanningPage(self.state, self)
        self.mapping_page = NavigationMapPage(self.state, self)
        self.monitoring_page = PerformanceMonitorPage(self.state, self.playback, self)
        self.radar_page = RadarMonitorPage(self.state, self)
        self.network_page = SystemNetworkPage(self.state, self)

        self.set_page_widget("choreography", self.choreography_page)
        self.set_page_widget("formation", self.formation_page)
        self.set_page_widget("mapping", self.mapping_page)
        self.set_page_widget("monitoring", self.monitoring_page)
        self.set_page_widget("radar", self.radar_page)
        self.set_page_widget("network", self.network_page)

        self.register_modal_hook("device_overview", lambda: DeviceOverviewModal(self.state, self).exec())
        self.register_modal_hook("stage_size", lambda: StageSizeModal(self.state, self).exec())
        self.register_modal_hook("init_points", lambda: InitPointModal(self.state, self).exec())
        self.register_modal_hook("bpm_music", lambda: BpmInfoModal(self.state, self).exec())
        self.register_modal_hook("save_all", lambda: self.state.save_project_snapshot())
        if serial_manager is not None and getattr(serial_manager, "latest_dance_list_parsed", None):
            self.state.sync_actions_from_serial()
        self.switch_page(initial_page)
