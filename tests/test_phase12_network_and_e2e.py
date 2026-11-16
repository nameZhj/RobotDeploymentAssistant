# @file: tests/test_phase12_network_and_e2e.py
# @brief: End-to-end verification of G1 Wi-Fi provisioner, all 6 UniUni pages, and multi-page Studio workflow.
# @exports: test_g1_wifi_provisioner_syncs_track_ip, test_full_six_page_main_studio_window

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from backend.g1_wifi_service import G1WifiService
from src.services.g1_wifi_provisioner import G1WifiProvisioner
from src.ui.windows.main_studio_window import MainStudioWindow


class _FakeSsh:
    def __init__(self) -> None:
        self.connected = False

    def connect(self, host, port, username, password):
        self.connected = True
        return True, f"connected {host}"

    def is_connected(self) -> bool:
        return self.connected

    def execute_command(self, cmd: str, sudo: bool = False, timeout: float = 15.0):
        if "device wifi list" in cmd:
            return (0, "*:UniLab_5G:AA\\:BB\\:CC\\:DD\\:EE\\:01:36:5180 MHz:92:WPA2\n", "")
        if "device show" in cmd:
            return (0, "GENERAL.STATE:100 (connected)\nGENERAL.CONNECTION:UniLab_5G\nIP4.ADDRESS[1]:192.168.50.101/24\n", "")
        return (0, "ok\n", "")


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_g1_wifi_provisioner_syncs_track_ip(tmp_path, monkeypatch) -> None:
    _app()
    monkeypatch.setenv("RDA_WORKSPACE_ROOT", str(tmp_path))
    from src.core.paths import get_paths
    get_paths(reset=True)
    win = MainStudioWindow(initial_page="network")
    win.state.load_demo_swarm_preset()
    fake_ssh = _FakeSsh()
    prov = G1WifiProvisioner(win.state, wifi_service=G1WifiService(ssh_client=fake_ssh))
    assert prov.connect_wired_ssh()["ok"]
    scan = prov.scan_wifi("wlan0")
    assert scan["ok"] and len(scan["networks"]) == 1
    assert scan["networks"][0]["ssid"] == "UniLab_5G"

    res = prov.configure_ipv4("wlan0", "manual", "192.168.50.188", "255.255.255.0", "192.168.50.1")
    assert res["ok"]
    assert prov.sync_track_wireless_ip("A", "192.168.50.188")
    tr_a = next(t for t in win.state.tracks if t.target_id == "A")
    assert tr_a.robot_ip == "192.168.50.188"
    win.close()
    monkeypatch.undo()
    get_paths(reset=True)


def test_full_six_page_main_studio_window(tmp_path, monkeypatch) -> None:
    _app()
    monkeypatch.setenv("RDA_WORKSPACE_ROOT", str(tmp_path))
    from src.core.paths import get_paths
    get_paths(reset=True)
    win = MainStudioWindow(initial_page="choreography")
    win.resize(1440, 860)
    win.show()
    for page_key in ("choreography", "formation", "mapping", "monitoring", "radar", "network"):
        win.switch_page(page_key)
        assert win.stack.currentWidget() is win._page_widgets[page_key]
    win.close()
    monkeypatch.undo()
    get_paths(reset=True)
