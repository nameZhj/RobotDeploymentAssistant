# @file: src/ui/network/__init__.py
# @brief: Public exports for G1 wireless setup wizard and System Network Settings page.
# @exports: SystemNetworkPage, WifiWizardPanel

from src.ui.network.system_network_page import SystemNetworkPage
from src.ui.network.wifi_wizard_panel import WifiWizardPanel

__all__ = ["SystemNetworkPage", "WifiWizardPanel"]
