"""
@file: backend/http_lower_bridge.py
@brief: Upper-computer Flask backend adapter routing non-Wi-Fi-provisioning operations to lower computer over Wi-Fi HTTP.
@exports: HttpLowerBridge, http_lower_bridge
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.protocol.robot_http_client import RobotHttpClient


class HttpLowerBridge:
    """Bridges Flask Web Console APIs to the lower computer HTTP REST service (port 8090)."""

    def __init__(self, default_port: int = 8090) -> None:
        self.client = RobotHttpClient(timeout_s=3.0)
        self.default_port = default_port
        self.robot_ip_map: Dict[str, str] = {}
        self.active_robot_ip: str = ""

    def set_robot_endpoint(self, target_id: str, robot_ip: str, port: Optional[int] = None) -> Dict[str, Any]:
        tgt = (target_id or "A").strip().upper()
        ip = (robot_ip or "").strip()
        if port:
            self.default_port = int(port)
        if ip:
            self.robot_ip_map[tgt] = ip
            self.active_robot_ip = ip
        return {
            "ok": bool(ip),
            "target_id": tgt,
            "robot_ip": ip,
            "port": self.default_port,
            "map": dict(self.robot_ip_map),
        }

    def resolve_ip(self, target_id: str = "") -> str:
        tgt = (target_id or "").strip().upper()
        if tgt and tgt in self.robot_ip_map:
            return self.robot_ip_map[tgt]
        if self.active_robot_ip:
            return self.active_robot_ip
        try:
            from backend.ssh_client import ssh_manager
            if ssh_manager.is_connected() and ssh_manager.host:
                return ssh_manager.host
        except Exception:
            pass
        return ""

    def send_command(self, target: str, raw_command: str, robot_ip: str = "") -> Dict[str, Any]:
        ip = (robot_ip or "").strip() or self.resolve_ip(target)
        if not ip:
            return {"ok": False, "http_used": False, "msg": "未配置无线 Wi-Fi HTTP 目标 IP"}
        parts = [p.strip() for p in (raw_command or "").split(",") if p.strip()]
        cmd = parts[0] if parts else raw_command
        params = parts[1:] if len(parts) > 1 else []
        resp = self.client.send_command(ip, target, cmd, params, port=self.default_port)
        return {
            "ok": resp.ok,
            "success": resp.ok,
            "http_used": True,
            "status_code": resp.status_code,
            "endpoint": resp.endpoint,
            "target": target,
            "command": raw_command,
            "msg": resp.message,
            "data": resp.data,
        }

    def fetch_dance_list(self, robot_ip: str = "") -> Dict[str, Any]:
        ip = (robot_ip or "").strip() or self.resolve_ip()
        if not ip:
            return {"ok": False, "http_used": False, "groups": [], "total_count": 0}
        resp = self.client.fetch_actions(ip, port=self.default_port)
        groups = list(resp.data.get("groups") or [])
        return {
            "ok": resp.ok,
            "success": resp.ok,
            "http_used": True,
            "groups": groups,
            "total_count": int(resp.data.get("total_count", len(groups))),
            "raw": str(resp.data.get("raw", "")),
            "msg": resp.message,
        }

    def deploy_dance_zip(self, zip_path: str, robot_ip: str = "") -> Dict[str, Any]:
        ip = (robot_ip or "").strip() or self.resolve_ip()
        if not ip:
            return {"ok": False, "http_used": False, "msg": "未配置无线 HTTP IP"}
        p = Path(zip_path)
        if not p.exists():
            return {"ok": False, "http_used": True, "msg": f"本地文件不存在: {zip_path}"}
        resp = self.client.deploy_dance_zip(ip, p.read_bytes(), port=self.default_port)
        return {"ok": resp.ok, "success": resp.ok, "http_used": True, "msg": resp.message, "data": resp.data}

    def precheck(self, robot_ip: str = "") -> Dict[str, Any]:
        ip = (robot_ip or "").strip() or self.resolve_ip()
        if not ip:
            return {"ok": False, "http_used": False}
        resp = self.client.system_precheck(ip, port=self.default_port)
        return {"ok": resp.ok, "success": resp.ok, "http_used": True, "data": resp.data, "msg": resp.message}

    def get_machine_id(self, robot_ip: str = "") -> Dict[str, Any]:
        ip = (robot_ip or "").strip() or self.resolve_ip()
        if not ip:
            return {"ok": False, "http_used": False}
        resp = self.client.fetch_machine_id(ip, port=self.default_port)
        return {"ok": resp.ok, "success": resp.ok, "http_used": True, "machine_id": resp.data.get("digest", ""), "data": resp.data, "msg": resp.message}

    def set_robot_id(self, robot_id: str, robot_ip: str = "") -> Dict[str, Any]:
        ip = (robot_ip or "").strip() or self.resolve_ip()
        if not ip:
            return {"ok": False, "http_used": False}
        resp = self.client.set_robot_id(ip, robot_id, port=self.default_port)
        return {"ok": resp.ok, "success": resp.ok, "http_used": True, "msg": resp.message, "data": resp.data}

    def get_processes(self, robot_ip: str = "") -> Dict[str, Any]:
        ip = (robot_ip or "").strip() or self.resolve_ip()
        if not ip:
            return {"ok": False, "http_used": False}
        resp = self.client.get_processes(ip, port=self.default_port)
        return {"ok": resp.ok, "success": resp.ok, "http_used": True, "processes": resp.data.get("processes", {}), "data": resp.data}

    def control_processes(self, action: str, robot_ip: str = "") -> Dict[str, Any]:
        ip = (robot_ip or "").strip() or self.resolve_ip()
        if not ip:
            return {"ok": False, "http_used": False}
        resp = self.client.control_processes(ip, action, port=self.default_port)
        return {"ok": resp.ok, "success": resp.ok, "http_used": True, "msg": resp.message, "data": resp.data}

    def get_license_status(self, robot_ip: str = "") -> Dict[str, Any]:
        ip = (robot_ip or "").strip() or self.resolve_ip()
        if not ip:
            return {"ok": False, "http_used": False}
        resp = self.client.fetch_license_status(ip, port=self.default_port)
        return {
            "ok": resp.ok, "success": resp.ok, "http_used": True, "connected": resp.status_code > 0,
            "has_license": bool(resp.data.get("present")), "license_valid": bool(resp.data.get("present")),
            "license_data": resp.data, "msg": resp.message,
        }

    def deploy_license(self, content: str | Dict[str, Any], robot_ip: str = "") -> Dict[str, Any]:
        ip = (robot_ip or "").strip() or self.resolve_ip()
        if not ip:
            return {"ok": False, "http_used": False}
        resp = self.client.deploy_license(ip, content, port=self.default_port)
        return {"ok": resp.ok, "success": resp.ok, "http_used": True, "msg": resp.message, "data": resp.data}

    def fetch_logs(self, log_type: str = "sec_run", lines: int = 200, robot_ip: str = "") -> Dict[str, Any]:
        ip = (robot_ip or "").strip() or self.resolve_ip()
        if not ip:
            return {"ok": False, "http_used": False}
        resp = self.client.fetch_logs(ip, log_type=log_type, lines=lines, port=self.default_port)
        return {"ok": resp.ok, "success": resp.ok, "http_used": True, "lines": resp.data.get("lines", []), "msg": resp.message}


http_lower_bridge = HttpLowerBridge()
