# @file: src/services/g1_wifi_provisioner.py
# @brief: Clean adapter bridging backend.g1_wifi_service & SSH channel with TrackEntity wireless IP synchronization.
# @exports: G1WifiProvisioner

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.g1_wifi_service import G1WifiService
from src.core.event_bus import StudioEvent
from src.services.studio_state_service import StudioStateService


class G1WifiProvisioner:
    """Connects LoRa wireless provisioning channel, provisions Wi-Fi/IPv4, and syncs track HTTP IPs."""

    def __init__(self, state: StudioStateService, wifi_service: Optional[G1WifiService] = None) -> None:
        self.state = state
        self._wifi = wifi_service or G1WifiService(ssh_client=state.ssh_channel)

    def bind_lora_port(self, lora_port: str, baudrate: int = 9600) -> Dict[str, Any]:
        """Bind dedicated LoRa serial port (CH340/CH341) for wireless provisioning."""
        res = self._wifi.configure_lora_channel(lora_port, baudrate)
        sm = self.state.serial_manager
        if sm is not None and hasattr(sm, "connect_port") and lora_port:
            try:
                conn_res = sm.connect_port(lora_port, baudrate=baudrate)
                res["serial_connected"] = bool(conn_res.get("success"))
                res["serial_msg"] = str(conn_res.get("msg", ""))
            except Exception as ex:
                res["serial_connected"] = False
                res["serial_msg"] = str(ex)
        return res

    def list_lora_ports(self) -> list[dict[str, Any]]:
        sm = self.state.serial_manager
        if sm is not None and hasattr(sm, "list_ports"):
            return list(sm.list_ports())
        return []

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
