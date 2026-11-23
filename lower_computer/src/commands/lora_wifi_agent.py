# @file: src/commands/lora_wifi_agent.py
# @brief: Lower-computer LoRa serial Wi-Fi provisioning receiver executing authentic nmcli probe/scan/connect/IPv4 commands.
# @exports: LoraWifiAgent

from __future__ import annotations

import ipaddress
import shlex
import subprocess
from typing import Any, Callable, Dict, List, Optional, Tuple


ShellFn = Callable[[str, float], Tuple[int, str, str]]


def _default_shell(cmd: str, timeout_s: float) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout_s, check=False)
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"nmcli 命令超时 ({timeout_s:.1f}s)"
    except OSError as ex:
        return 127, "", f"nmcli 调用失败: {ex}"


class LoraWifiAgent:
    """Handles incoming LoRa wireless provisioning frames (`TARGET|WIFI_*`) on the robot via nmcli."""

    WIRED_SUBNET = ipaddress.IPv4Network("192.168.123.0/24")

    def __init__(self, shell_fn: Optional[ShellFn] = None) -> None:
        self._shell = shell_fn or _default_shell

    def handle_lora_wifi_command(self, command: str, params: List[str]) -> Dict[str, Any]:
        cmd = (command or "").strip().upper()
        if cmd == "WIFI_PROBE":
            ifname = params[0] if params else "wlan0"
            return self.probe(ifname)
        if cmd == "WIFI_SCAN":
            ifname = params[0] if params else "wlan0"
            return self.scan(ifname)
        if cmd == "WIFI_CONNECT":
            if not params:
                return {"ok": False, "message": "WIFI_CONNECT 缺少 SSID 参数"}
            ssid = params[0]
            pwd = params[1] if len(params) > 1 else ""
            ifname = params[2] if len(params) > 2 else "wlan0"
            return self.connect(ssid, pwd, ifname)
        if cmd == "WIFI_IPV4":
            method = params[0].lower() if params else "manual"
            address = params[1] if len(params) > 1 else ""
            netmask = params[2] if len(params) > 2 else "255.255.255.0"
            gateway = params[3] if len(params) > 3 else ""
            ifname = params[4] if len(params) > 4 else "wlan0"
            return self.configure_ipv4(ifname, method, address, netmask, gateway)
        return {"ok": False, "message": f"未知 LoRa 配网命令: {cmd}"}

    def probe(self, ifname: str = "wlan0") -> Dict[str, Any]:
        q_if = shlex.quote(ifname)
        rc, out, err_s = self._shell(
            f"nmcli -f GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS device show {q_if}",
            10.0,
        )
        return {
            "ok": rc == 0,
            "ifname": ifname,
            "raw_state": out,
            "ip_address": self._extract_ip(out),
            "message": "LoRa 网卡探测成功" if rc == 0 else (err_s or f"nmcli 退出码 {rc}"),
        }

    def scan(self, ifname: str = "wlan0") -> Dict[str, Any]:
        q_if = shlex.quote(ifname)
        cmd = (
            "export LC_ALL=C TERM=dumb PAGER= && "
            "nmcli --mode tabular --colors no --terse --escape yes "
            "--fields IN-USE,SSID,BSSID,CHAN,FREQ,SIGNAL,SECURITY "
            f"device wifi list ifname {q_if} --rescan yes"
        )
        rc, out, err_s = self._shell(cmd, 25.0)
        return {
            "ok": rc == 0,
            "ifname": ifname,
            "raw_scan": out,
            "message": "LoRa Wi-Fi 扫描完成" if rc == 0 else (err_s or f"nmcli scan 退出码 {rc}"),
        }

    def connect(self, ssid: str, password: str = "", ifname: str = "wlan0") -> Dict[str, Any]:
        q_if = shlex.quote(ifname)
        q_ssid = shlex.quote(ssid)
        pwd_arg = f" password {shlex.quote(password)}" if password else ""
        cmd = (
            f"nmcli --colors no --wait 60 device wifi connect {q_ssid}{pwd_arg} ifname {q_if} && "
            f"nmcli -f GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS device show {q_if}"
        )
        rc, out, err_s = self._shell(cmd, 65.0)
        return {
            "ok": rc == 0,
            "ssid": ssid,
            "ifname": ifname,
            "ip_address": self._extract_ip(out),
            "raw_output": out,
            "message": f"已连接 Wi-Fi {ssid}" if rc == 0 else (err_s or f"连接 {ssid} 失败"),
        }

    def configure_ipv4(
        self,
        ifname: str = "wlan0",
        method: str = "manual",
        address: str = "",
        netmask: str = "255.255.255.0",
        gateway: str = "",
    ) -> Dict[str, Any]:
        if method == "manual":
            cidr = address if "/" in address else f"{address}/{netmask}"
            iface = ipaddress.IPv4Interface(cidr)
            if iface.network.overlaps(self.WIRED_SUBNET):
                return {"ok": False, "message": "Wi-Fi 网段禁止与有线管理段 192.168.123.0/24 重叠"}
            addr_str = str(iface)
        else:
            addr_str = ""

        q_if = shlex.quote(ifname)
        cmd = (
            f'uuid=$(nmcli -t -f UUID,DEVICE connection show --active | awk -F: -v d={q_if} \'$2==d{{print $1}}\') && '
            f'nmcli connection modify uuid "$uuid" ipv4.method {shlex.quote(method)} '
            f'ipv4.addresses {shlex.quote(addr_str)} ipv4.gateway {shlex.quote(gateway)} && '
            f'nmcli connection up uuid "$uuid" ifname {q_if} && '
            f'nmcli -f GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS,IP4.GATEWAY device show {q_if}'
        )
        rc, out, err_s = self._shell(cmd, 30.0)
        return {
            "ok": rc == 0,
            "ifname": ifname,
            "method": method,
            "ip_address": self._extract_ip(out) or address.split("/")[0],
            "raw_output": out,
            "message": "LoRa Wi-Fi IPv4 配置完成" if rc == 0 else (err_s or f"IPv4 配置失败 ({rc})"),
        }

    @staticmethod
    def _extract_ip(stdout: str) -> str:
        for line in (stdout or "").splitlines():
            if "IP4.ADDRESS" in line and ":" in line:
                val = line.split(":", 1)[1].strip()
                return val.split("/", 1)[0]
        return ""
