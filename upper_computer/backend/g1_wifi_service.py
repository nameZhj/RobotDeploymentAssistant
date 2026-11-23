"""
@file: backend/g1_wifi_service.py
@brief: 基于 SSH 通道执行 G1 机器人网卡探测、Wi-Fi 扫描、热点连接及静态/DHCP IPv4 配置的服务封装
@exports: G1WifiService, g1_wifi_service
"""
import logging
from typing import Any, Dict, List, Optional

from backend.g1_wifi_parser import (
    DEFAULT_WIFI_IFNAME,
    IPv4Config,
    PROBE_SCRIPT,
    build_connect_cmd,
    build_ipv4_cmd,
    build_scan_cmd,
    parse_device_state,
    parse_scan_output,
    parse_static_ipv4,
)
from backend.lora_wifi_tunnel import LoraWifiTunnel, lora_wifi_tunnel

logger = logging.getLogger("G1WifiService")


class G1WifiService:
    """宇树 G1 无线网卡远端配置服务（专用 LoRa 配网通道：CH340/CH341 LoRa 串口 + SSH Proxy）"""

    def __init__(
        self,
        ssh_client: Optional[Any] = None,
        lora_port: str = "COM13",
        lora_baud: int = 9600,
        tunnel: Optional[LoraWifiTunnel] = None,
    ) -> None:
        self._ssh = ssh_client
        self.lora_port = lora_port
        self.lora_baud = lora_baud
        self.transport_channel = "LoRa"
        self.tunnel = tunnel or lora_wifi_tunnel
        self.tunnel.configure(serial_port=lora_port, baudrate=lora_baud)

    def configure_lora_channel(self, lora_port: str, lora_baud: int = 9600, target_id: str = "A") -> Dict[str, Any]:
        self.lora_port = (lora_port or "").strip() or self.lora_port
        self.lora_baud = int(lora_baud or 9600)
        self.tunnel.configure(serial_port=self.lora_port, baudrate=self.lora_baud, target_id=target_id)
        return {
            "ok": True,
            "transport": self.transport_channel,
            "lora_port": self.lora_port,
            "lora_baud": self.lora_baud,
            "target_id": self.tunnel.target_id,
            "proxy_command": self.tunnel.build_proxy_command(),
            "message": f"无线配网通道已绑定 LoRa 串口 [{self.lora_port} @ {self.lora_baud}]",
        }

    def _get_ssh(self) -> Any:
        if self._ssh is not None:
            return self._ssh
        from backend.ssh_client import ssh_manager
        return ssh_manager

    def _require_ssh(self) -> Optional[Dict[str, Any]]:
        ssh = self._get_ssh()
        if not ssh.is_connected():
            return {"ok": False, "message": "LoRa 配网通道未连接（请先绑定并连接 LoRa 串口或建立 LoRa SSH 隧道）"}
        return None

    def probe_network(self, ifname: str = DEFAULT_WIFI_IFNAME) -> Dict[str, Any]:
        err = self._require_ssh()
        if err:
            ack = self.tunnel.emit_and_wait_lora_ack("WIFI_PROBE", ifname)
            if ack.get("ack_received"):
                ad = ack["ack_data"]
                return {
                    "ok": bool(ad.get("ok")), "transport": "LoRa", "lora_frame": ack["frame"],
                    "ifname": ifname, "state": parse_device_state(ad.get("raw_state", "")),
                    "probe_log": ad.get("raw_state", ""), "message": ad.get("message", "LoRa 探测完成"),
                }
            return {**err, "transport": "LoRa", "lora_frame": ack["frame"]}
        lora_tx = self.tunnel.emit_lora_wifi_frame("WIFI_PROBE", ifname)
        ssh = self._get_ssh()
        rc, out, err_s = ssh.execute_command(PROBE_SCRIPT, sudo=False, timeout=20.0)
        rc2, state_out, _ = ssh.execute_command(
            f"nmcli -f GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS device show {ifname} 2>&1",
            sudo=False, timeout=10.0,
        )
        state = parse_device_state(state_out if rc2 == 0 else "")
        return {
            "ok": rc == 0,
            "transport": "LoRa",
            "lora_frame": lora_tx["frame"],
            "ifname": ifname,
            "state": state,
            "probe_log": (out or err_s or "").strip(),
            "message": "LoRa 网卡探测完成" if rc == 0 else f"网卡探测返回状态码 {rc}: {err_s.strip()}",
        }

    def scan_wifi(self, ifname: str = DEFAULT_WIFI_IFNAME, rescan: str = "yes") -> Dict[str, Any]:
        err = self._require_ssh()
        if err:
            ack = self.tunnel.emit_and_wait_lora_ack("WIFI_SCAN", ifname)
            if ack.get("ack_received"):
                ad = ack["ack_data"]
                parsed = parse_scan_output(ad.get("raw_scan", ""), ifname=ifname)
                return {
                    "ok": bool(ad.get("ok")), "transport": "LoRa", "lora_frame": ack["frame"],
                    "ifname": ifname, **parsed, "message": ad.get("message", "LoRa Wi-Fi 扫描完成"),
                }
            return {**err, "transport": "LoRa", "lora_frame": ack["frame"]}
        lora_tx = self.tunnel.emit_lora_wifi_frame("WIFI_SCAN", ifname)
        ssh = self._get_ssh()
        cmd = build_scan_cmd(ifname=ifname, rescan=rescan)
        rc, out, err_s = ssh.execute_command(cmd, sudo=True, timeout=25.0)
        if rc != 0 and rescan != "no":
            rc, out, err_s = ssh.execute_command(build_scan_cmd(ifname=ifname, rescan="auto"), sudo=False, timeout=15.0)
        if rc != 0:
            return {
                "ok": False, "transport": "LoRa", "lora_frame": lora_tx["frame"],
                "ifname": ifname, "networks": [], "ap_count": 0,
                "message": f"Wi-Fi 扫描失败 ({rc}): {err_s.strip() or out.strip()}",
            }
        parsed = parse_scan_output(out, ifname=ifname)
        return {
            "ok": True,
            "transport": "LoRa",
            "lora_frame": lora_tx["frame"],
            "ifname": ifname,
            **parsed,
            "message": f"通过 LoRa 扫描到 {len(parsed['networks'])} 个 Wi-Fi 网络 ({parsed['ap_count']} 个 AP)",
        }

    def connect_wifi(self, ssid: str, password: str = "", ifname: str = DEFAULT_WIFI_IFNAME) -> Dict[str, Any]:
        clean_ssid = (ssid or "").strip()
        if not clean_ssid or any(c in clean_ssid for c in "\r\n\x00"):
            return {"ok": False, "message": "SSID 不能为空且不能包含换行符"}
        if password and any(c in password for c in "\r\n\x00"):
            return {"ok": False, "message": "Wi-Fi 密码不能包含换行符"}
        err = self._require_ssh()
        if err:
            ack = self.tunnel.emit_and_wait_lora_ack("WIFI_CONNECT", clean_ssid, password, ifname, timeout_s=15.0)
            if ack.get("ack_received"):
                ad = ack["ack_data"]
                state = parse_device_state(ad.get("raw_output", ""))
                if ad.get("ip_address") and not state.get("ip_address"):
                    state["ip_address"] = ad["ip_address"]
                return {
                    "ok": bool(ad.get("ok")), "transport": "LoRa", "lora_frame": ack["frame"],
                    "ssid": clean_ssid, "ifname": ifname, "state": state,
                    "raw_output": ad.get("raw_output", ""), "message": ad.get("message", ""),
                }
            return {**err, "transport": "LoRa", "lora_frame": ack["frame"]}
        lora_tx = self.tunnel.emit_lora_wifi_frame("WIFI_CONNECT", clean_ssid, password, ifname)
        ssh = self._get_ssh()
        cmd = build_connect_cmd(clean_ssid, password=password, ifname=ifname)
        rc, out, err_s = ssh.execute_command(cmd, sudo=True, timeout=75.0)
        state = parse_device_state(out)
        if rc != 0:
            return {
                "ok": False,
                "transport": "LoRa",
                "lora_frame": lora_tx["frame"],
                "ssid": clean_ssid,
                "ifname": ifname,
                "state": state,
                "raw_output": (out or err_s or "").strip(),
                "message": f"连接 Wi-Fi '{clean_ssid}' 失败 (code={rc}): {(err_s or out).strip().splitlines()[-1] if (err_s or out).strip() else '未知错误'}",
            }
        ip_tip = f"，已获取无线 IP: {state['ip_address']}" if state.get("ip_address") else ""
        return {
            "ok": True,
            "transport": "LoRa",
            "lora_frame": lora_tx["frame"],
            "ssid": clean_ssid,
            "ifname": ifname,
            "state": state,
            "raw_output": out.strip(),
            "message": f"已通过 LoRa 配网连接 Wi-Fi '{clean_ssid}'{ip_tip}",
        }

    def configure_ipv4(
        self,
        ifname: str = DEFAULT_WIFI_IFNAME,
        method: str = "manual",
        address: str = "",
        netmask: str = "",
        gateway: str = "",
        dns: str = "",
    ) -> Dict[str, Any]:
        m = (method or "manual").strip().lower()
        if m not in ("manual", "auto"):
            return {"ok": False, "message": "ipv4 method 仅支持 manual 或 auto (DHCP)"}
        try:
            if m == "manual":
                dns_tokens: List[str] = [p.strip() for p in (dns or "").replace(";", ",").split(",") if p.strip()]
                cfg = parse_static_ipv4(address, netmask=netmask, gateway=gateway, dns=dns_tokens)
            else:
                cfg = IPv4Config("auto")
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}

        err = self._require_ssh()
        if err:
            ack = self.tunnel.emit_and_wait_lora_ack("WIFI_IPV4", m, address, netmask, gateway, ifname, timeout_s=12.0)
            if ack.get("ack_received"):
                ad = ack["ack_data"]
                state = parse_device_state(ad.get("raw_output", ""))
                if ad.get("ip_address") and not state.get("ip_address"):
                    state["ip_address"] = ad["ip_address"]
                return {
                    "ok": bool(ad.get("ok")), "transport": "LoRa", "lora_frame": ack["frame"],
                    "ifname": ifname, "method": cfg.method, "configured_address": cfg.address,
                    "state": state, "message": ad.get("message", ""),
                }
            return {**err, "transport": "LoRa", "lora_frame": ack["frame"]}
        lora_tx = self.tunnel.emit_lora_wifi_frame("WIFI_IPV4", m, address, netmask, gateway, ifname)
        ssh = self._get_ssh()
        cmd = build_ipv4_cmd(ifname=ifname, config=cfg)
        rc, out, err_s = ssh.execute_command(cmd, sudo=True, timeout=30.0)
        state = parse_device_state(out)
        if rc != 0:
            return {
                "ok": False,
                "transport": "LoRa",
                "lora_frame": lora_tx["frame"],
                "ifname": ifname,
                "state": state,
                "raw_output": (out or err_s or "").strip(),
                "message": f"IPv4 配置失败 (code={rc}): {(err_s or out).strip()}",
            }
        return {
            "ok": True,
            "transport": "LoRa",
            "lora_frame": lora_tx["frame"],
            "ifname": ifname,
            "method": cfg.method,
            "configured_address": cfg.address,
            "state": state,
            "message": f"Wi-Fi IPv4 已通过 LoRa 配网更新 ({cfg.method}: {state.get('ip_address') or cfg.address or 'DHCP'})",
        }


g1_wifi_service = G1WifiService()
