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
    """局域网扫描与 Windows 本机网卡直连配置、断网自动检测自愈连接管理"""

    def __init__(self):
        self.scanning = False
        self.scan_progress = 0
        self.scan_results: List[Dict[str, Any]] = []

        # 断网自动检测重连控制
        self.auto_connect_enabled = True
        self.auto_detecting = False
        self.last_auto_check_time = 0.0
        self.last_auto_status_msg = "初始化中"
        self._daemon_thread: Optional[threading.Thread] = None
        self._stop_daemon_event = threading.Event()
        self._manual_disconnect_pause_until = 0.0

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

    def auto_heal_nic(self, target_ip: str = "192.168.123.200") -> Dict[str, Any]:
        """
        自愈网卡配置：
        检查本机是否有网卡已配置在 192.168.123.x 网段；
        若无，自动寻找已连通物理网卡（如以太网直连），将其配置为 192.168.123.200。
        """
        nics = self.get_local_interfaces()
        # 1. 已处于 192.168.123.x 的网卡
        for nic in nics:
            if nic.get("is_unitree_subnet") and nic.get("is_up"):
                return {
                    "healed": False,
                    "already_ready": True,
                    "nic_name": nic["name"],
                    "ip": nic["ip"],
                    "msg": f"网卡 [{nic['name']}] 处于 192.168.123.x 网段 ({nic['ip']})，无需调整"
                }

        # 2. 寻找物理以太网卡 / 活跃网卡
        candidate = None
        for nic in nics:
            name_lower = nic["name"].lower()
            # 排除虚拟和回环
            if nic.get("is_loopback") or "vethernet" in name_lower or "wsl" in name_lower or "tun" in name_lower:
                continue
            if ("以太网" in nic["name"] or "ethernet" in name_lower) and nic.get("is_up"):
                candidate = nic
                break

        # 如果没有已连通以太网，找任意非虚拟非无线网卡
        if not candidate:
            for nic in nics:
                name_lower = nic["name"].lower()
                if nic.get("is_loopback") or "vethernet" in name_lower or "wsl" in name_lower or "tun" in name_lower or "wlan" in name_lower or "wi-fi" in name_lower:
                    continue
                if "以太网" in nic["name"] or "ethernet" in name_lower:
                    candidate = nic
                    break

        if candidate:
            nic_name = candidate["name"]
            res = self.configure_nic_static(nic_name, ip=target_ip)
            return {
                "healed": res.get("success", False),
                "already_ready": False,
                "nic_name": nic_name,
                "ip": target_ip,
                "msg": res.get("msg", "")
            }

        return {
            "healed": False,
            "already_ready": False,
            "nic_name": "",
            "ip": "",
            "msg": "未发现可配置的物理以太网卡"
        }

    def _check_ip_port(self, ip: str, port: int = 22, timeout: float = 0.35) -> Optional[Dict[str, Any]]:
        """探测单个 IP 的 22 端口连通性"""
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            if result == 0:
                is_unitree_default = (ip == "192.168.123.164" or ip == "192.168.123.161" or ip == "192.168.123.162")
                return {
                    "ip": ip,
                    "port": port,
                    "status": "online",
                    "banner": "",
                    "is_unitree": is_unitree_default,
                    "device_type": "Unitree G1/Go2 Robot" if is_unitree_default else "SSH Device",
                    "default_hint": "宇树默认IP (G1/Go2)" if is_unitree_default else "局域网活跃SSH主机"
                }
        except Exception:
            pass
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
        return None

    def auto_detect_and_connect(self, force_configure_nic: bool = False, timeout: float = 2.0) -> Dict[str, Any]:
        """
        全自动化断网/直连网络探测与连接：
        1. 若已连接且健康，直接返回；
        2. 若未处于 192.168.123.x 网段且 force_configure_nic 为 True，自愈配置网卡；
        3. 并发高速探测候选机器人 IP；
        4. 命中后自动握手建立 SSH 连接。
        """
        from .ssh_client import ssh_manager

        if ssh_manager.is_connected():
            lat = ssh_manager.test_latency()
            if lat >= 0:
                return {
                    "success": True,
                    "connected": True,
                    "target_ip": ssh_manager.host,
                    "msg": f"机器人已处于连接状态 ({ssh_manager.host}:{ssh_manager.port})，延迟: {lat:.1f}ms"
                }

        # 0. 优先检测本机物理以太网卡是否已插入网线并就绪
        if sys.platform == "win32":
            nics = self.get_local_interfaces()
            has_physical_eth = any(
                n.get("is_up") and ("以太网" in n["name"] or "ethernet" in n["name"].lower())
                and not n.get("is_loopback") and "vethernet" not in n["name"].lower() and "wsl" not in n["name"].lower()
                for n in nics
            )
            if not has_physical_eth:
                self.auto_detecting = False
                self.last_auto_status_msg = "网线未连接"
                return {
                    "success": False,
                    "connected": False,
                    "msg": "物理以太网卡未连接网线，请先连接机器人直连网线"
                }

        self.auto_detecting = True
        self.last_auto_check_time = time.time()
        self.last_auto_status_msg = "正在探测机器人..."

        # 1. 检查或自愈网卡
        if force_configure_nic:
            heal_res = self.auto_heal_nic()
            if heal_res.get("healed"):
                time.sleep(0.8)

        # 2. 候选常用 IP 列表 (优先精准探测当前配置的 IP 或 164)
        priority_ips = [ssh_manager.host or "192.168.123.164"]
        for extra in ["192.168.123.161", "192.168.123.162", "192.168.123.10", "192.168.123.14"]:
            if extra not in priority_ips:
                priority_ips.append(extra)

        found_ip = None
        for ip in priority_ips:
            res = self._check_ip_port(ip, 22, 0.3)
            if res and res.get("status") == "online":
                found_ip = ip
                break

        # 3. 若候选 IP 命中，立即握手连接
        if found_ip:
            self.last_auto_status_msg = f"正在连接 {found_ip}..."
            ssh_manager.set_credentials(host=found_ip, port=22, username="unitree", password="123")
            ok, msg = ssh_manager.connect(timeout=timeout)
            self.auto_detecting = False
            if ok:
                self.last_auto_status_msg = f"已连接 ({found_ip})"
                return {
                    "success": True,
                    "connected": True,
                    "target_ip": found_ip,
                    "msg": f"自动探测成功！已连接至机器人 [{found_ip}]"
                }
            else:
                self.last_auto_status_msg = f"{found_ip} 未就绪"
                return {
                    "success": False,
                    "connected": False,
                    "target_ip": found_ip,
                    "msg": f"探测到主机 {found_ip}，但 SSH 握手未通过"
                }

        self.auto_detecting = False
        self.last_auto_status_msg = "等待机器人上线"
        return {
            "success": False,
            "connected": False,
            "msg": "未在 192.168.123.x 网段探测到在线机器人，请确认网线已插好或机器人已开机"
        }

    def scan_network(self, target_subnet: str = "192.168.123.", port: int = 22) -> List[Dict[str, Any]]:
        """
        多线程并发扫描局域网网段 (默认 192.168.123.1 - 254)
        """
        self.scanning = True
        self.scan_progress = 0
        self.scan_results = []

        priority_ips = [
            f"{target_subnet}164",
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

        found_devices.sort(key=lambda x: (not x.get("is_unitree", False), x.get("ip") != "192.168.123.164", x.get("ip")))
        self.scan_results = found_devices
        self.scanning = False
        self.scan_progress = 100
        return found_devices

    def pause_auto_reconnect(self, seconds: float = 12.0):
        """用户主动断开时，暂停后台自动重连指定的秒数"""
        self._manual_disconnect_pause_until = time.time() + seconds

    def start_background_daemon(self):
        """启动断网自动探测与自愈重连常驻守护线程"""
        if self._daemon_thread and self._daemon_thread.is_alive():
            return

        self._stop_daemon_event.clear()

        def _worker():
            from .ssh_client import ssh_manager
            logger.info("后台断网自动检测与重连守护进程已启动")
            while not self._stop_daemon_event.is_set():
                try:
                    now = time.time()
                    if self.auto_connect_enabled and now > self._manual_disconnect_pause_until:
                        # 若未连接，执行快速探测重连 (使用充裕超时确保 SSH banner 握手成功)
                        if not ssh_manager.is_connected():
                            self.auto_detect_and_connect(force_configure_nic=False, timeout=5.0)
                        else:
                            # 已连接状态下做轻量存活探测
                            lat = ssh_manager.test_latency()
                            if lat < 0:
                                logger.warning("检测到机器人网络链路中断，准备自动探测重连...")
                                ssh_manager.disconnect()
                except Exception as e:
                    logger.debug(f"Auto detector loop exception: {e}")

                time.sleep(5.0)

        self._daemon_thread = threading.Thread(target=_worker, daemon=True, name="AutoNetworkDetector")
        self._daemon_thread.start()

    def stop_background_daemon(self):
        self._stop_daemon_event.set()


network_manager = NetworkManager()
network_manager.start_background_daemon()
