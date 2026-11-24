"""
@file: backend/http_lower_bridge.py
@brief: Upper-computer Flask backend adapter routing all non-Wi-Fi-provisioning operations to lower computers over Wi-Fi LAN HTTP.
@exports: HttpLowerBridge, http_lower_bridge
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import socket
import time
from typing import Any, Dict, List, Optional

from src.protocol.robot_http_client import RobotHttpClient


class HttpLowerBridge:
    """Bridges Flask Web Console APIs exclusively to lower-computer HTTP REST services over Wi-Fi LAN."""

    def __init__(self, default_port: int = 8090, storage_file: Optional[Path] = None) -> None:
        self.client = RobotHttpClient(timeout_s=2.5)
        self.default_port = default_port
        self.robot_ip_map: Dict[str, str] = {}
        self.robot_port_map: Dict[str, int] = {}
        self.active_robot_ip: str = ""
        self._fleet_robots: List[Dict[str, Any]] = []
        self._fleet_selected: List[str] = []
        self._storage_file = storage_file or (Path(__file__).resolve().parents[1] / "cache" / "http_robot_fleet.json")
        self._load_fleet_from_disk()

    def _load_fleet_from_disk(self) -> None:
        if not self._storage_file.exists():
            return
        try:
            data = json.loads(self._storage_file.read_text(encoding="utf-8"))
            raw_robots = data.get("robots") or []
            norm: List[Dict[str, Any]] = []
            for item in raw_robots:
                if isinstance(item, dict) and item.get("id"):
                    rid = str(item["id"]).strip().upper()
                    ip = str(item.get("ip", "")).strip()
                    port = int(item.get("port") or self.default_port)
                    norm.append({"id": rid, "ip": ip, "port": port})
                    if ip:
                        self.robot_ip_map[rid] = ip
                        self.robot_port_map[rid] = port
                        self.active_robot_ip = ip
            self._fleet_robots = norm
            self._fleet_selected = [str(s).strip().upper() for s in (data.get("selected") or []) if str(s).strip()]
        except Exception:
            pass

    def get_fleet(self) -> Dict[str, Any]:
        return {
            "success": True,
            "robots": list(self._fleet_robots),
            "selected": list(self._fleet_selected),
            "default_port": self.default_port,
        }

    def save_fleet(self, robots: List[Any], selected: Optional[List[str]] = None) -> Dict[str, Any]:
        clean_robots: List[Dict[str, Any]] = []
        seen = set()
        for item in robots or []:
            if isinstance(item, dict):
                rid = str(item.get("id", "")).strip().upper()
                ip = str(item.get("ip", "")).strip()
                port = int(item.get("port") or self.default_port)
            else:
                rid = str(item).strip().upper()
                ip = self.robot_ip_map.get(rid, "")
                port = self.robot_port_map.get(rid, self.default_port)
            if not rid or rid == "ALL" or rid in seen:
                continue
            seen.add(rid)
            clean_robots.append({"id": rid, "ip": ip, "port": port})
            if ip:
                self.robot_ip_map[rid] = ip
                self.robot_port_map[rid] = port
                self.active_robot_ip = ip

        self._fleet_robots = clean_robots
        self._fleet_selected = [str(s).strip().upper() for s in (selected or []) if str(s).strip()]
        try:
            self._storage_file.parent.mkdir(parents=True, exist_ok=True)
            self._storage_file.write_text(
                json.dumps({"robots": self._fleet_robots, "selected": self._fleet_selected}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass
        return {"success": True, "robots": self._fleet_robots, "selected": self._fleet_selected}

    def set_robot_endpoint(self, target_id: str, robot_ip: str, port: Optional[int] = None) -> Dict[str, Any]:
        tgt = (target_id or "A").strip().upper()
        ip = (robot_ip or "").strip()
        use_port = int(port) if port else self.default_port
        if ip:
            self.robot_ip_map[tgt] = ip
            self.robot_port_map[tgt] = use_port
            self.active_robot_ip = ip
            existing = next((r for r in self._fleet_robots if r["id"] == tgt), None)
            if existing is not None:
                existing["ip"], existing["port"] = ip, use_port
            else:
                self._fleet_robots.append({"id": tgt, "ip": ip, "port": use_port})
            self.save_fleet(self._fleet_robots, self._fleet_selected)
        return {
            "ok": bool(ip), "target_id": tgt, "robot_ip": ip,
            "port": use_port, "map": dict(self.robot_ip_map),
        }

    def resolve_endpoint(self, target_id: str = "", explicit_ip: str = "", explicit_port: Optional[int] = None) -> tuple[str, int]:
        tgt = (target_id or "").strip().upper()
        ip = (explicit_ip or "").strip() or self.robot_ip_map.get(tgt, "") or self.active_robot_ip
        if explicit_port:
            port = int(explicit_port)
        elif tgt and tgt in self.robot_port_map:
            port = self.robot_port_map[tgt]
        else:
            matched = next((r.get("port") for r in self._fleet_robots if r.get("ip") == ip and r.get("port")), None)
            port = int(matched) if matched else self.default_port
        return ip, port

    def resolve_ip(self, target_id: str = "") -> str:
        ip, _ = self.resolve_endpoint(target_id)
        return ip

    def check_health(self, robot_ip: str, port: Optional[int] = None) -> Dict[str, Any]:
        ip = (robot_ip or "").strip()
        use_port = int(port or self.default_port)
        if not ip:
            return {"ok": False, "online": False, "ip": "", "port": use_port, "msg": "未配置无线 Wi-Fi IP"}
        fast = RobotHttpClient(timeout_s=1.2)
        t0 = time.monotonic()
        resp = fast.health(ip, port=use_port)
        ms = round((time.monotonic() - t0) * 1000.0, 1)
        return {
            "ok": resp.ok, "online": resp.ok, "ip": ip, "port": use_port, "latency_ms": ms,
            "robot_id": str(resp.data.get("robot_id", "")),
            "authority": str(resp.data.get("authority", "")),
            "motion_state": str(resp.data.get("motion_state", "")),
            "active_dance": str(resp.data.get("active_dance", "")),
            "ros_master_reachable": bool(resp.data.get("ros_master_reachable", False)),
            "msg": resp.message,
        }

    def check_fleet_health(self, robots: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        items = robots if robots is not None else self._fleet_robots
        if not items:
            return {"success": True, "online_count": 0, "total_count": 0, "robots": {}}

        def _probe(item: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
            rid = str(item.get("id", "")).strip().upper()
            ip, port = self.resolve_endpoint(rid, str(item.get("ip", "")), item.get("port"))
            return rid, self.check_health(ip, port)

        results: Dict[str, Dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(items)))) as pool:
            for rid, info in pool.map(_probe, items):
                results[rid] = info
        online = sum(1 for v in results.values() if v.get("online"))
        return {"success": True, "online_count": online, "total_count": len(items), "robots": results}

    def send_command(self, target: str, raw_command: str, robot_ip: str = "", port: Optional[int] = None) -> Dict[str, Any]:
        ip, use_port = self.resolve_endpoint(target, robot_ip, port)
        if not ip:
            return {"ok": False, "success": False, "http_used": True, "target": target, "msg": f"机器人 [{target}] 未配置 Wi-Fi 局域网 IP"}
        parts = [p.strip() for p in (raw_command or "").split(",") if p.strip()]
        cmd = parts[0] if parts else raw_command
        params = parts[1:] if len(parts) > 1 else []
        resp = self.client.send_command(ip, target, cmd, params, port=use_port)
        return {
            "ok": resp.ok, "success": resp.ok, "http_used": True, "status_code": resp.status_code,
            "endpoint": resp.endpoint, "target": target, "robot_ip": ip, "port": use_port,
            "command": raw_command, "msg": resp.message, "data": resp.data,
        }

    def send_command_multi(
        self,
        target_str: str,
        raw_command: str,
        robot_ip: str = "",
        port: Optional[int] = None,
        targets_map: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        targets = [t.strip().upper() for t in (target_str or "").split(",") if t.strip()]
        if not targets or targets == ["ALL"]:
            targets = [r["id"] for r in self._fleet_robots] or (["A"] if robot_ip or self.active_robot_ip else [])
        if not targets:
            return {"ok": False, "success": False, "http_used": True, "msg": "尚未添加或选择任何 Wi-Fi 局域网机器人"}

        tmap = targets_map or {}

        def _send_one(tgt: str) -> Dict[str, Any]:
            meta = tmap.get(tgt) or {}
            ip = str(meta.get("ip", "")).strip() if isinstance(meta, dict) else ""
            p = meta.get("port") if isinstance(meta, dict) else None
            return self.send_command(tgt, raw_command, robot_ip=ip or robot_ip, port=p or port)

        with ThreadPoolExecutor(max_workers=min(8, max(1, len(targets)))) as pool:
            receipts = list(pool.map(_send_one, targets))
        ok_cnt = sum(1 for r in receipts if r.get("ok"))
        summary = "; ".join(f"{r['target']}@{r.get('robot_ip') or '?'}:{r['msg']}" for r in receipts)
        return {
            "ok": ok_cnt > 0, "success": ok_cnt > 0, "all_ok": ok_cnt == len(receipts),
            "http_used": True, "target": ",".join(targets), "command": raw_command,
            "ok_count": ok_cnt, "total_count": len(receipts), "results": receipts, "msg": summary,
        }

    def fetch_dance_list(self, robot_ip: str = "", port: Optional[int] = None) -> Dict[str, Any]:
        ip, use_port = self.resolve_endpoint("", robot_ip, port)
        if not ip:
            return {"ok": False, "success": False, "http_used": True, "groups": [], "total_count": 0, "msg": "未配置机器人 Wi-Fi IP"}
        resp = self.client.fetch_actions(ip, port=use_port)
        groups = list(resp.data.get("groups") or [])
        total = int(resp.data.get("total_count", sum(len(g.get("items", [])) for g in groups)))
        return {
            "ok": resp.ok, "success": resp.ok, "http_used": True, "groups": groups,
            "total_count": total, "raw": str(resp.data.get("raw", "")), "msg": resp.message,
        }

    def fetch_dance_list_multi(
        self, target_str: str = "", robot_ip: str = "", targets_map: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        targets = [t.strip().upper() for t in (target_str or "").split(",") if t.strip() and t.strip().upper() != "ALL"]
        if not targets:
            return self.fetch_dance_list(robot_ip=robot_ip)
        tmap = targets_map or {}
        per_groups: Dict[str, List[Dict[str, Any]]] = {}
        per_counts: Dict[str, int] = {}
        errors: List[str] = []
        for tgt in targets:
            meta = tmap.get(tgt) or {}
            ip = str(meta.get("ip", "")).strip() if isinstance(meta, dict) else ""
            p = meta.get("port") if isinstance(meta, dict) else None
            use_ip, use_port = self.resolve_endpoint(tgt, ip or robot_ip, p)
            if not use_ip:
                errors.append(f"{tgt} 未配置 IP")
                continue
            res = self.fetch_dance_list(use_ip, port=use_port)
            if res.get("ok"):
                per_groups[tgt] = res["groups"]
                per_counts[tgt] = res["total_count"]
            else:
                errors.append(f"{tgt}@{use_ip}: {res.get('msg')}")
        if not per_groups:
            return {
                "ok": False, "success": False, "http_used": True, "groups": [],
                "total_count": 0, "per_robot_counts": per_counts,
                "msg": "; ".join(errors) or "未获取到任何在线机器人动作列表",
            }
        if len(per_groups) == 1:
            only_groups = next(iter(per_groups.values()))
            total = sum(len(g.get("items", [])) for g in only_groups)
            return {"ok": True, "success": True, "http_used": True, "groups": only_groups, "total_count": total, "per_robot_counts": per_counts, "msg": "Wi-Fi HTTP 同步成功"}

        alias_sets = [{it["alias"] for g in gs for it in g.get("items", []) if it.get("alias")} for gs in per_groups.values()]
        common_aliases = set.intersection(*alias_sets) if alias_sets else set()
        base_groups = next(iter(per_groups.values()))
        merged: List[Dict[str, Any]] = []
        for g in base_groups:
            items = [it for it in g.get("items", []) if it.get("alias") in common_aliases]
            if items:
                merged.append({**g, "items": items})
        total = sum(len(g["items"]) for g in merged)
        return {"ok": True, "success": True, "http_used": True, "groups": merged, "total_count": total, "per_robot_counts": per_counts, "msg": f"多机 HTTP 交集同步完成 ({total} 项)"}

    def scan_lan_http_robots(self, subnet: str = "", port: Optional[int] = None) -> Dict[str, Any]:
        use_port = int(port or self.default_port)
        prefix = (subnet or "").strip()
        if not prefix:
            prefix = self._detect_wifi_lan_prefix()
        if not prefix.endswith("."):
            prefix += "."
        candidates = [f"{prefix}{i}" for i in range(1, 255)]
        fast = RobotHttpClient(timeout_s=0.45)

        def _probe_ip(ip: str) -> Optional[Dict[str, Any]]:
            try:
                with socket.create_connection((ip, use_port), timeout=0.18):
                    pass
            except OSError:
                return None
            resp = fast.health(ip, port=use_port)
            if not resp.ok:
                return None
            return {
                "ip": ip, "port": use_port,
                "robot_id": str(resp.data.get("robot_id") or "A").upper(),
                "authority": str(resp.data.get("authority", "FREE")),
                "ros_master_reachable": bool(resp.data.get("ros_master_reachable", False)),
            }

        found: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=64) as pool:
            for hit in pool.map(_probe_ip, candidates):
                if hit is not None:
                    found.append(hit)
        return {"success": True, "subnet": prefix, "port": use_port, "devices": found, "count": len(found)}

    @staticmethod
    def _detect_wifi_lan_prefix() -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                parts = local_ip.split(".")
                if len(parts) == 4 and not local_ip.startswith("127."):
                    return f"{parts[0]}.{parts[1]}.{parts[2]}."
        except OSError:
            pass
        return "192.168.1."

    def deploy_dance_zip(self, zip_path: str, robot_ip: str = "") -> Dict[str, Any]:
        ip, use_port = self.resolve_endpoint("", robot_ip)
        if not ip:
            return {"ok": False, "http_used": False, "msg": "未配置无线 HTTP IP"}
        p = Path(zip_path)
        if not p.exists():
            return {"ok": False, "http_used": True, "msg": f"本地文件不存在: {zip_path}"}
        resp = self.client.deploy_dance_zip(ip, p.read_bytes(), port=use_port)
        return {"ok": resp.ok, "success": resp.ok, "http_used": True, "msg": resp.message, "data": resp.data}

    def precheck(self, robot_ip: str = "") -> Dict[str, Any]:
        ip, use_port = self.resolve_endpoint("", robot_ip)
        if not ip:
            return {"ok": False, "http_used": False}
        resp = self.client.system_precheck(ip, port=use_port)
        return {"ok": resp.ok, "success": resp.ok, "http_used": True, "data": resp.data, "msg": resp.message}

    def get_machine_id(self, robot_ip: str = "") -> Dict[str, Any]:
        ip, use_port = self.resolve_endpoint("", robot_ip)
        if not ip:
            return {"ok": False, "http_used": False}
        resp = self.client.fetch_machine_id(ip, port=use_port)
        return {"ok": resp.ok, "success": resp.ok, "http_used": True, "machine_id": resp.data.get("digest", ""), "data": resp.data, "msg": resp.message}

    def set_robot_id(self, robot_id: str, robot_ip: str = "") -> Dict[str, Any]:
        ip, use_port = self.resolve_endpoint("", robot_ip)
        if not ip:
            return {"ok": False, "http_used": False}
        resp = self.client.set_robot_id(ip, robot_id, port=use_port)
        return {"ok": resp.ok, "success": resp.ok, "http_used": True, "msg": resp.message, "data": resp.data}

    def get_control_state(self, target: str = "", robot_ip: str = "", port: Optional[int] = None) -> Dict[str, Any]:
        ip, use_port = self.resolve_endpoint(target, robot_ip, port)
        if not ip:
            return {"ok": False, "success": False, "http_used": True, "msg": "未配置机器人 Wi-Fi 局域网 IP"}
        resp = self.client.get_control_state(ip, port=use_port)
        return {"ok": resp.ok, "success": resp.ok, "http_used": True, "robot_ip": ip, "port": use_port, "data": resp.data, "msg": resp.message}

    def send_posture(self, target: str, posture: str, robot_ip: str = "", port: Optional[int] = None) -> Dict[str, Any]:
        ip, use_port = self.resolve_endpoint(target, robot_ip, port)
        if not ip:
            return {"ok": False, "success": False, "http_used": True, "msg": f"机器人 [{target or '?'}] 未配置 Wi-Fi 局域网 IP"}
        resp = self.client.send_posture(ip, posture, port=use_port)
        return {"ok": resp.ok, "success": resp.ok, "http_used": True, "status_code": resp.status_code, "data": resp.data, "msg": resp.message}

    def send_velocity(self, target: str, payload: Dict[str, Any], robot_ip: str = "", port: Optional[int] = None) -> Dict[str, Any]:
        ip, use_port = self.resolve_endpoint(target, robot_ip, port)
        if not ip:
            return {"ok": False, "success": False, "http_used": True, "msg": f"机器人 [{target or '?'}] 未配置 Wi-Fi 局域网 IP"}
        resp = self.client.send_velocity(ip, payload, port=use_port)
        return {"ok": resp.ok, "success": resp.ok, "http_used": True, "status_code": resp.status_code, "data": resp.data, "msg": resp.message}

    def send_dance(self, target: str, alias: str, robot_ip: str = "", port: Optional[int] = None) -> Dict[str, Any]:
        ip, use_port = self.resolve_endpoint(target, robot_ip, port)
        if not ip:
            return {"ok": False, "success": False, "http_used": True, "msg": f"机器人 [{target or '?'}] 未配置 Wi-Fi 局域网 IP"}
        resp = self.client.send_dance(ip, alias, port=use_port)
        return {"ok": resp.ok, "success": resp.ok, "http_used": True, "status_code": resp.status_code, "data": resp.data, "msg": resp.message}

    def send_stop(self, target: str = "", emergency: bool = False, robot_ip: str = "", port: Optional[int] = None) -> Dict[str, Any]:
        ip, use_port = self.resolve_endpoint(target, robot_ip, port)
        if not ip:
            return {"ok": False, "success": False, "http_used": True, "msg": f"机器人 [{target or '?'}] 未配置 Wi-Fi 局域网 IP"}
        resp = self.client.send_stop(ip, emergency=emergency, port=use_port)
        return {"ok": resp.ok, "success": resp.ok, "http_used": True, "status_code": resp.status_code, "data": resp.data, "msg": resp.message}

    def get_processes(self, robot_ip: str = "") -> Dict[str, Any]:
        ip, use_port = self.resolve_endpoint("", robot_ip)
        if not ip:
            return {"ok": False, "connected": False, "http_used": False}
        resp = self.client.get_processes(ip, port=use_port)
        procs = resp.data.get("processes", {})
        g1_on = bool(resp.data.get("g1_ctrl_running", procs.get("g1_ctrl_vsis", False)))
        lora_on = bool(resp.data.get("lora_recv_running", procs.get("lora_recv_group", False)))
        return {
            "ok": resp.ok, "success": resp.ok, "connected": resp.ok, "http_used": True,
            "processes": procs, "g1_ctrl_running": g1_on, "lora_recv_running": lora_on,
            "all_running": g1_on and lora_on, "data": resp.data,
        }

    def control_processes(self, action: str, robot_ip: str = "") -> Dict[str, Any]:
        ip, use_port = self.resolve_endpoint("", robot_ip)
        if not ip:
            return {"ok": False, "http_used": False}
        resp = self.client.control_processes(ip, action, port=use_port)
        return {"ok": resp.ok, "success": resp.ok, "http_used": True, "msg": resp.message, "data": resp.data}

    def get_docker_status(self, robot_ip: str = "") -> Dict[str, Any]:
        ip, use_port = self.resolve_endpoint("", robot_ip)
        if not ip:
            return {"ok": False, "http_used": False}
        resp = self.client.get_docker_status(ip, port=use_port)
        return {"ok": resp.ok, "success": resp.ok, "http_used": True, "data": resp.data, "msg": resp.message}

    def control_container(self, action: str, container_name: str = "vsis_g1", robot_ip: str = "") -> Dict[str, Any]:
        ip, use_port = self.resolve_endpoint("", robot_ip)
        if not ip:
            return {"ok": False, "http_used": False}
        resp = self.client.control_container(ip, action, container_name=container_name, port=use_port)
        return {"ok": resp.ok, "success": resp.ok, "http_used": True, "msg": resp.message, "data": resp.data}

    def startup_check(self, robot_ip: str = "") -> Dict[str, Any]:
        ip, use_port = self.resolve_endpoint("", robot_ip)
        if not ip:
            return {"ok": False, "connected": False, "http_used": False}
        health = self.check_health(ip, use_port)
        if not health.get("online"):
            return {"ok": False, "connected": False, "http_used": True, "host": ip, "port": use_port}
        lic = self.get_license_status(ip)
        proc = self.get_processes(ip)
        docker = self.get_docker_status(ip)
        has_lic = bool(lic.get("has_license"))
        ctrl_on = bool(proc.get("g1_ctrl_running"))
        lora_on = bool(proc.get("lora_recv_running"))
        cont_on = bool((docker.get("data") or {}).get("is_container_running", True))
        return {
            "ok": True, "connected": True, "transport": "WIFI_HTTP", "http_used": True,
            "host": ip, "port": use_port, "username": "http", "latency_ms": health.get("latency_ms", 0.0),
            "first_time": not (has_lic and cont_on),
            "has_license": has_lic, "license_valid": bool(lic.get("license_valid")),
            "license_data": lic.get("license_data", {}),
            "is_container_running": cont_on, "is_ctrl_running": ctrl_on, "is_lora_running": lora_on,
            "auto_detecting": False, "auto_status_msg": f"Wi-Fi HTTP 在线 ({ip}:{use_port})",
        }

    def get_license_status(self, robot_ip: str = "") -> Dict[str, Any]:
        ip, use_port = self.resolve_endpoint("", robot_ip)
        if not ip:
            return {"ok": False, "http_used": False}
        resp = self.client.fetch_license_status(ip, port=use_port)
        return {
            "ok": resp.ok, "success": resp.ok, "http_used": True, "connected": resp.status_code > 0,
            "has_license": bool(resp.data.get("present")), "license_valid": bool(resp.data.get("present")),
            "license_data": resp.data, "msg": resp.message,
        }

    def deploy_license(self, content: str | Dict[str, Any], robot_ip: str = "") -> Dict[str, Any]:
        ip, use_port = self.resolve_endpoint("", robot_ip)
        if not ip:
            return {"ok": False, "http_used": False}
        resp = self.client.deploy_license(ip, content, port=use_port)
        return {"ok": resp.ok, "success": resp.ok, "http_used": True, "msg": resp.message, "data": resp.data}

    def fetch_logs(self, log_type: str = "sec_run", lines: int = 200, container: str = "vsis_g1", robot_ip: str = "") -> Dict[str, Any]:
        ip, use_port = self.resolve_endpoint("", robot_ip)
        if not ip:
            return {"ok": False, "http_used": False}
        resp = self.client.fetch_logs(ip, log_type=log_type, lines=lines, container=container, port=use_port)
        log_lines = list(resp.data.get("lines") or [])
        raw_text = str(resp.data.get("raw_text") or "\n".join(log_lines))
        return {
            "ok": resp.ok, "success": resp.ok, "http_used": True,
            "lines": log_lines, "raw_text": raw_text,
            "target_container": str(resp.data.get("target_container") or container),
            "diagnostics": [], "msg": resp.message,
        }


http_lower_bridge = HttpLowerBridge()
