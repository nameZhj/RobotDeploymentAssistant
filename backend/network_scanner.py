import socket
import concurrent.futures
from typing import Any, Dict, List, Optional


class NetworkScanner:
    """局域网 IP 与端口探测扫描器"""

    @staticmethod
    def check_ip_port(ip: str, port: int = 22, timeout: float = 0.35) -> Optional[Dict[str, Any]]:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            if sock.connect_ex((ip, port)) == 0:
                is_unitree_default = ip in ("192.168.123.164", "192.168.123.161", "192.168.123.162")
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

    @classmethod
    def scan_subnet(cls, subnet_prefix: str = "192.168.123", port: int = 22, max_workers: int = 50, progress_cb=None) -> List[Dict[str, Any]]:
        results = []
        candidates = [f"{subnet_prefix}.{i}" for i in range(1, 255)]
        total = len(candidates)
        completed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ip = {executor.submit(cls.check_ip_port, ip, port, 0.4): ip for ip in candidates}
            for future in concurrent.futures.as_completed(future_to_ip):
                completed += 1
                if progress_cb:
                    progress_cb(int((completed / total) * 100))
                res = future.result()
                if res:
                    results.append(res)
        results.sort(key=lambda x: (not x.get("is_unitree", False), x["ip"]))
        return results


network_scanner = NetworkScanner()

