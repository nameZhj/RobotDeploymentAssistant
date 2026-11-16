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

logger = logging.getLogger("G1WifiService")


class G1WifiService:
    """宇树 G1 无线网卡远端配置服务（复用现有 SSH 链路）"""

    def __init__(self, ssh_client: Optional[Any] = None) -> None:
        self._ssh = ssh_client

    def _get_ssh(self) -> Any:
        if self._ssh is not None:
            return self._ssh
        from backend.ssh_client import ssh_manager
        return ssh_manager

    def _require_ssh(self) -> Optional[Dict[str, Any]]:
        ssh = self._get_ssh()
        if not ssh.is_connected():
            return {"ok": False, "message": "未连接机器人 SSH（请先在上方或连机向导通过有线 192.168.123.164 建立 SSH 连接）"}
        return None

    def probe_network(self, ifname: str = DEFAULT_WIFI_IFNAME) -> Dict[str, Any]:
        err = self._require_ssh()
        if err:
            return err
        ssh = self._get_ssh()
        rc, out, err_s = ssh.execute_command(PROBE_SCRIPT, sudo=False, timeout=20.0)
        rc2, state_out, _ = ssh.execute_command(
            f"nmcli -f GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS device show {ifname} 2>&1",
            sudo=False, timeout=10.0,
        )
        state = parse_device_state(state_out if rc2 == 0 else "")
        return {
            "ok": rc == 0,
            "ifname": ifname,
            "state": state,
            "probe_log": (out or err_s or "").strip(),
            "message": "网卡探测完成" if rc == 0 else f"网卡探测返回状态码 {rc}: {err_s.strip()}",
        }

    def scan_wifi(self, ifname: str = DEFAULT_WIFI_IFNAME, rescan: str = "yes") -> Dict[str, Any]:
        err = self._require_ssh()
        if err:
            return err
        ssh = self._get_ssh()
        cmd = build_scan_cmd(ifname=ifname, rescan=rescan)
        rc, out, err_s = ssh.execute_command(cmd, sudo=True, timeout=25.0)
        if rc != 0 and rescan != "no":
            # 回退到非强制缓存扫描，避免无 sudo 权限时失败
            rc, out, err_s = ssh.execute_command(build_scan_cmd(ifname=ifname, rescan="auto"), sudo=False, timeout=15.0)
        if rc != 0:
            return {"ok": False, "ifname": ifname, "networks": [], "ap_count": 0, "message": f"Wi-Fi 扫描失败 ({rc}): {err_s.strip() or out.strip()}"}
        parsed = parse_scan_output(out, ifname=ifname)
        return {
            "ok": True,
            "ifname": ifname,
            **parsed,
            "message": f"扫描到 {len(parsed['networks'])} 个 Wi-Fi 网络 ({parsed['ap_count']} 个 AP)",
        }

    def connect_wifi(self, ssid: str, password: str = "", ifname: str = DEFAULT_WIFI_IFNAME) -> Dict[str, Any]:
        clean_ssid = (ssid or "").strip()
        if not clean_ssid or any(c in clean_ssid for c in "\r\n\x00"):
            return {"ok": False, "message": "SSID 不能为空且不能包含换行符"}
        if password and any(c in password for c in "\r\n\x00"):
            return {"ok": False, "message": "Wi-Fi 密码不能包含换行符"}
        err = self._require_ssh()
        if err:
            return err
        ssh = self._get_ssh()
        cmd = build_connect_cmd(clean_ssid, password=password, ifname=ifname)
        rc, out, err_s = ssh.execute_command(cmd, sudo=True, timeout=75.0)
        state = parse_device_state(out)
        if rc != 0:
            return {
                "ok": False,
                "ssid": clean_ssid,
                "ifname": ifname,
                "state": state,
                "raw_output": (out or err_s or "").strip(),
                "message": f"连接 Wi-Fi '{clean_ssid}' 失败 (code={rc}): {(err_s or out).strip().splitlines()[-1] if (err_s or out).strip() else '未知错误'}",
            }
        ip_tip = f"，已获取无线 IP: {state['ip_address']}" if state.get("ip_address") else ""
        return {
            "ok": True,
            "ssid": clean_ssid,
            "ifname": ifname,
            "state": state,
            "raw_output": out.strip(),
            "message": f"已连接 Wi-Fi '{clean_ssid}'{ip_tip}",
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
            return err
        ssh = self._get_ssh()
        cmd = build_ipv4_cmd(ifname=ifname, config=cfg)
        rc, out, err_s = ssh.execute_command(cmd, sudo=True, timeout=30.0)
        state = parse_device_state(out)
        if rc != 0:
            return {
                "ok": False,
                "ifname": ifname,
                "state": state,
                "raw_output": (out or err_s or "").strip(),
                "message": f"IPv4 配置失败 (code={rc}): {(err_s or out).strip()}",
            }
        return {
            "ok": True,
            "ifname": ifname,
            "method": cfg.method,
            "configured_address": cfg.address,
            "state": state,
            "message": f"Wi-Fi IPv4 已更新 ({cfg.method}: {state.get('ip_address') or cfg.address or 'DHCP'})",
        }


g1_wifi_service = G1WifiService()
