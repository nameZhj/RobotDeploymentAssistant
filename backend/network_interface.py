import socket
import subprocess
from typing import Any, Dict, List, Tuple

try:
    import psutil
except ImportError:
    psutil = None


def _safe_decode(data: bytes) -> str:
    if not data:
        return ""
    for enc in ("utf-8", "gbk", "cp936", "ansi", "oem"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode("utf-8", errors="replace")


def _run_win_cmd(cmd: str, timeout: float = 10.0) -> Tuple[int, str]:
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, timeout=timeout)
        out = _safe_decode(res.stdout).strip()
        err = _safe_decode(res.stderr).strip()
        combined = f"{out}\n{err}".strip() if err else out
        return res.returncode, combined
    except Exception as e:
        return -1, str(e)


class NetworkInterfaceHelper:
    """Windows 网卡发现与 netsh 直连操作"""

    @staticmethod
    def get_local_interfaces() -> List[Dict[str, Any]]:
        interfaces = []
        if psutil is None:
            return interfaces
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        for nic_name, nic_addrs in addrs.items():
            stat = stats.get(nic_name)
            is_up = stat.isup if stat else False
            speed = stat.speed if stat else 0
            ipv4, netmask, mac = "", "", ""
            for addr in nic_addrs:
                if addr.family == socket.AF_INET:
                    ipv4 = addr.address
                    netmask = addr.netmask
                elif addr.family == psutil.AF_LINK:
                    mac = addr.address
            name_lower = nic_name.lower()
            is_loopback = ("loopback" in name_lower or "回环" in name_lower)
            is_unitree = (ipv4.startswith("192.168.123."))
            interfaces.append({
                "name": nic_name, "ip": ipv4, "netmask": netmask, "mac": mac,
                "is_up": is_up, "speed_mbps": speed, "is_loopback": is_loopback, "is_unitree_subnet": is_unitree
            })
        interfaces.sort(key=lambda x: (not x["is_unitree_subnet"], not x["is_up"], x["is_loopback"], x["name"]))
        return interfaces

    @staticmethod
    def configure_nic_static(nic_name: str, ip: str = "192.168.123.200", mask: str = "255.255.255.0", gateway: str = "192.168.123.1") -> Dict[str, Any]:
        cmd = f'netsh interface ip set address name="{nic_name}" static {ip} {mask} {gateway}'
        code, out = _run_win_cmd(cmd)
        if code == 0:
            return {"success": True, "msg": f"网卡 [{nic_name}] 静态 IP ({ip}) 配置成功"}
        return {"success": False, "msg": f"配置失败: {out}"}

    @staticmethod
    def restore_nic_dhcp(nic_name: str) -> Dict[str, Any]:
        code, out = _run_win_cmd(f'netsh interface ip set address name="{nic_name}" dhcp')
        _run_win_cmd(f'netsh interface ip set dns name="{nic_name}" dhcp')
        if code == 0:
            return {"success": True, "msg": f"网卡 [{nic_name}] 已成功恢复为自动获取 IP (DHCP)"}
        return {"success": False, "msg": f"恢复 DHCP 失败: {out}"}


network_interface_helper = NetworkInterfaceHelper()

