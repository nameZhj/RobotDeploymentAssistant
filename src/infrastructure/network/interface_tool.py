import os
import subprocess
from typing import Dict, List, Optional, Tuple
import psutil

from src.core.logger import get_logger

logger = get_logger("InterfaceTool")


class InterfaceTool:
    """
    Windows network interface discovery and netsh static IP direct-link configuration.
    """

    @staticmethod
    def list_network_interfaces() -> List[Dict[str, str]]:
        interfaces = []
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()

        for name, net_stat in stats.items():
            ip_str = ""
            if name in addrs:
                for addr in addrs[name]:
                    if addr.family == psutil.AF_LINK or str(addr.family).endswith("AF_INET"):
                        if "." in addr.address:
                            ip_str = addr.address
                            break
            interfaces.append({
                "name": name,
                "is_up": str(net_stat.isup),
                "speed": str(net_stat.speed),
                "ip": ip_str,
            })
        return interfaces

    @staticmethod
    def set_static_ip(
        interface_name: str,
        ip: str = "192.168.123.200",
        netmask: str = "255.255.255.0",
        gateway: str = "192.168.123.1",
    ) -> Tuple[bool, str]:
        cmd = f'netsh interface ip set address name="{interface_name}" static {ip} {netmask} {gateway}'
        try:
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                logger.info(f"Static IP {ip} configured on {interface_name}")
                return True, "Static IP set successfully"
            logger.warning(f"netsh failed: {res.stderr or res.stdout}")
            return False, res.stderr or res.stdout
        except Exception as e:
            logger.error(f"Failed to execute netsh: {e}")
            return False, str(e)

    @staticmethod
    def set_dhcp(interface_name: str) -> Tuple[bool, str]:
        cmd = f'netsh interface ip set address name="{interface_name}" source=dhcp'
        try:
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                logger.info(f"DHCP enabled on {interface_name}")
                return True, "DHCP set successfully"
            return False, res.stderr or res.stdout
        except Exception as e:
            return False, str(e)


interface_tool = InterfaceTool()
