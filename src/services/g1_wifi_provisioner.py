# @file: src/services/g1_wifi_provisioner.py
# @brief: Clean adapter bridging backend.g1_wifi_service & SSH channel with TrackEntity wireless IP synchronization.
# @exports: G1WifiProvisioner

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.g1_wifi_service import G1WifiService
from src.core.event_bus import StudioEvent
from src.services.studio_state_service import StudioStateService


class G1WifiProvisioner:
    """Connects wired G1 SSH management port, provisions Wi-Fi/IPv4, and syncs track IPs."""

    def __init__(self, state: StudioStateService, wifi_service: Optional[G1WifiService] = None) -> None:
        self.state = state
        self._wifi = wifi_service or G1WifiService(ssh_client=state.ssh_channel)

    def connect_wired_ssh(
        self,
        host: str = "192.168.123.164",
        username: str = "unitree",
        password: str = "vsislab509",
        port: int = 22,
    ) -> Dict[str, Any]:
        ssh = self._wifi._get_ssh()
        if hasattr(ssh, "connect"):
            ok, msg = ssh.connect(host=host, port=port, username=username, password=password)
            return {"ok": bool(ok), "message": str(msg)}
        return {"ok": False, "message": "SSH 客户端不可用"}

    def probe_network(self, ifname: str = "wlan0") -> Dict[str, Any]:
        return self._wifi.probe_network(ifname=ifname)

    def scan_wifi(self, ifname: str = "wlan0", rescan: str = "yes") -> Dict[str, Any]:
        return self._wifi.scan_wifi(ifname=ifname, rescan=rescan)

    def connect_wifi(self, ssid: str, password: str = "", ifname: str = "wlan0") -> Dict[str, Any]:
        return self._wifi.connect_wifi(ssid=ssid, password=password, ifname=ifname)

    def configure_ipv4(
        self,
        ifname: str = "wlan0",
        method: str = "manual",
        address: str = "",
        netmask: str = "255.255.255.0",
        gateway: str = "",
        dns: str = "",
    ) -> Dict[str, Any]:
        return self._wifi.configure_ipv4(
            ifname=ifname, method=method, address=address, netmask=netmask, gateway=gateway, dns=dns
        )

    def sync_track_wireless_ip(self, target_id: str, new_ip: str) -> bool:
        """Persist provisioned wireless IP onto the matching robot TrackEntity."""
        clean_ip = (new_ip or "").split("/")[0].strip()
        if not clean_ip:
            return False
        updated = False
        for tr in self.state.tracks:
            if tr.target_id.upper() == target_id.strip().upper():
                tr.robot_ip = clean_ip
                self.state.scene_repo.upsert_track(tr)
                updated = True
        if updated:
            self.state.reload_all()
            self.state.bus.publish(StudioEvent.TRACKS_UPDATED, target_id)
            self.state.notify(f"已同步轨道 [{target_id}] 无线地址为 {clean_ip}", "ok")
        return updated

    def disconnect_ssh(self) -> None:
        ssh = self._wifi._get_ssh()
        if hasattr(ssh, "disconnect"):
            ssh.disconnect()
