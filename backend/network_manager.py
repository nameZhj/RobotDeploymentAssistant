import os
import sys
import socket
import subprocess
import threading
import concurrent.futures
import time
import logging
from typing import List, Dict, Any, Optional

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger("NetworkManager")


class NetworkManager:
    """局域网扫描与 Windows 本机网卡直连配置管理"""

    def __init__(self):
        self.scanning = False
        self.scan_progress = 0
        self.scan_results: List[Dict[str, Any]] = []

    def get_local_interfaces(self) -> List[Dict[str, Any]]:
        """获取 Windows 本地网卡列表与当前 IP"""
        interfaces = []
        if psutil is None:
            return interfaces

        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()

        for nic_name, nic_addrs in addrs.items():
            stat = stats.get(nic_name)
            is_up = stat.isup if stat else False
            speed = stat.speed if stat else 0

            ipv4 = ""
            netmask = ""
            mac = ""
            for addr in nic_addrs:
                if addr.family == socket.AF_INET:
                    ipv4 = addr.address
                    netmask = addr.netmask
                elif getattr(addr, 'family', None) == getattr(psutil, 'AF_LINK', -1) or "link" in str(addr.family).lower():
                    mac = addr.address

            # 排除虚拟网卡/Loopback（如需全部显示也可）
            is_loopback = ipv4.startswith("127.") or "loopback" in nic_name.lower()
            interfaces.append({
                "name": nic_name,
                "ip": ipv4,
                "netmask": netmask,
                "mac": mac,
                "is_up": is_up,
                "speed_mbps": speed,
                "is_unitree_subnet": ipv4.startswith("192.168.123."),
                "is_loopback": is_loopback
            })

        return interfaces

    def configure_nic_static(self, nic_name: str, ip: str = "192.168.123.200", netmask: str = "255.255.255.0", gateway: str = "192.168.123.1") -> Dict[str, Any]:
        """
        Windows: 调用 netsh 命令将指定网卡设为同网段静态 IP
        """
        if sys.platform != "win32":
            return {"success": False, "msg": "网卡配置功能仅支持 Windows 系统"}

        try:
            # netsh interface ip set address name="以太网" static 192.168.123.200 255.255.255.0 192.168.123.1
            cmd = f'netsh interface ip set address name="{nic_name}" static {ip} {netmask} {gateway}'
            logger.info(f"正在配置网卡静态IP: {cmd}")
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            if res.returncode == 0 or "确定" in res.stdout or not res.stderr.strip():
                return {
                    "success": True,
                    "msg": f"网卡 [{nic_name}] 已成功配置为静态 IP: {ip} (子网掩码: {netmask})",
                    "cmd": cmd
                }
            else:
                return {
                    "success": False,
                    "msg": f"配置网卡需要管理员权限或网卡名称不正确: {res.stderr or res.stdout}",
                    "cmd": cmd
                }
        except Exception as e:
            return {"success": False, "msg": f"配置失败: {str(e)}"}

    def configure_nic_dhcp(self, nic_name: str) -> Dict[str, Any]:
        """
        Windows: 调用 netsh 命令恢复为 DHCP 自动获取
        """
        if sys.platform != "win32":
            return {"success": False, "msg": "网卡配置功能仅支持 Windows 系统"}

        try:
            cmd1 = f'netsh interface ip set address name="{nic_name}" dhcp'
            cmd2 = f'netsh interface ip set dns name="{nic_name}" dhcp'
            logger.info(f"正在恢复网卡为DHCP: {cmd1}")
            res1 = subprocess.run(cmd1, shell=True, capture_output=True, text=True, timeout=10)
            res2 = subprocess.run(cmd2, shell=True, capture_output=True, text=True, timeout=10)
            return {
                "success": True,
                "msg": f"网卡 [{nic_name}] 已恢复为自动获取 IP (DHCP)"
            }
        except Exception as e:
            return {"success": False, "msg": f"恢复 DHCP 失败: {str(e)}"}

    def _check_ip_port(self, ip: str, port: int = 22, timeout: float = 0.4) -> Optional[Dict[str, Any]]:
        """探测单个 IP 的 22 端口并尝试识别特征"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            if result == 0:
                # 尝试读取 SSH banner
                banner = ""
                try:
                    sock.settimeout(0.5)
                    banner_bytes = sock.recv(1024)
                    banner = banner_bytes.decode('utf-8', errors='ignore').strip()
                except Exception:
                    pass
                sock.close()

                # 判断特征
                is_unitree_default = (ip == "192.168.123.164" or ip == "192.168.123.161" or ip == "192.168.123.162")
                device_type = "Unitree G1/Go2 Robot" if is_unitree_default or "Ubuntu" in banner or "SSH" in banner else "SSH Device"

                return {
                    "ip": ip,
                    "port": port,
                    "status": "online",
                    "banner": banner,
                    "is_unitree": is_unitree_default or ("SSH" in banner),
                    "device_type": device_type,
                    "default_hint": "宇树默认IP (G1/Go2)" if is_unitree_default else "局域网活跃SSH主机"
                }
            sock.close()
        except Exception:
            pass
        return None

    def scan_network(self, target_subnet: str = "192.168.123.", port: int = 22) -> List[Dict[str, Any]]:
        """
        多线程并发扫描局域网网段 (默认 192.168.123.1 - 254)
        """
        self.scanning = True
        self.scan_progress = 0
        self.scan_results = []

        # 优先把宇树常用 IP 排在前面先扫
        priority_ips = [
            f"{target_subnet}164", # G1 运控 / 宿主机常用
            f"{target_subnet}161",
            f"{target_subnet}162",
            f"{target_subnet}163",
            f"{target_subnet}10",
            f"{target_subnet}1",
        ]

        all_ips = list(priority_ips)
        for i in range(1, 255):
            ip = f"{target_subnet}{i}"
            if ip not in all_ips:
                all_ips.append(ip)

        found_devices = []
        total = len(all_ips)
        completed = 0

        # 并发 60 线程快速扫描
        with concurrent.futures.ThreadPoolExecutor(max_workers=60) as executor:
            future_to_ip = {executor.submit(self._check_ip_port, ip, port): ip for ip in all_ips}
            for future in concurrent.futures.as_completed(future_to_ip):
                completed += 1
                self.scan_progress = int((completed / total) * 100)
                try:
                    res = future.result()
                    if res:
                        found_devices.append(res)
                except Exception:
                    pass

        # 排序：宇树默认 IP 优先
        found_devices.sort(key=lambda x: (not x.get("is_unitree", False), x.get("ip") != "192.168.123.164", x.get("ip")))
        self.scan_results = found_devices
        self.scanning = False
        self.scan_progress = 100
        return found_devices


network_manager = NetworkManager()
