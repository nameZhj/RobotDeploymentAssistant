# @file: src/protocol/robot_http_system_mixin.py
# @brief: System, container, license, dance ZIP, and PCD transfer HTTP methods mixed into RobotHttpClient.
# @exports: RobotHttpResponse, RobotHttpSystemMixin

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Dict
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import quote


@dataclass(frozen=True)
class RobotHttpResponse:
    """Standardized HTTP response envelope from a lower computer endpoint."""

    ok: bool
    status_code: int
    endpoint: str
    data: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    raw_bytes: bytes = b""


class RobotHttpSystemMixin:
    """System ops, license, dance bundle, and PCD transfer methods for RobotHttpClient."""

    def system_precheck(self, robot_ip: str, port: int | None = None) -> RobotHttpResponse:
        return self._request_json("GET", robot_ip, "/api/v1/system/precheck", port=port)

    def fetch_machine_id(self, robot_ip: str, port: int | None = None) -> RobotHttpResponse:
        return self._request_json("GET", robot_ip, "/api/v1/system/machine_id", port=port)

    def get_processes(self, robot_ip: str, port: int | None = None) -> RobotHttpResponse:
        return self._request_json("GET", robot_ip, "/api/v1/system/processes", port=port)

    def control_processes(self, robot_ip: str, action: str, port: int | None = None) -> RobotHttpResponse:
        return self._request_json("POST", robot_ip, "/api/v1/system/processes", payload={"action": action}, port=port)

    def set_robot_id(self, robot_ip: str, robot_id: str, port: int | None = None) -> RobotHttpResponse:
        return self._request_json("POST", robot_ip, "/api/v1/system/robot_id", payload={"robot_id": robot_id}, port=port)

    def get_docker_status(self, robot_ip: str, port: int | None = None) -> RobotHttpResponse:
        return self._request_json("GET", robot_ip, "/api/v1/system/docker", port=port)

    def control_container(
        self, robot_ip: str, action: str, container_name: str = "vsis_g1", port: int | None = None,
    ) -> RobotHttpResponse:
        return self._request_json(
            "POST", robot_ip, "/api/v1/system/container",
            payload={"action": action, "container_name": container_name}, port=port,
        )

    def fetch_logs(
        self, robot_ip: str, log_type: str = "sec_run", lines: int = 200,
        container: str = "vsis_g1", port: int | None = None,
    ) -> RobotHttpResponse:
        return self._request_json(
            "GET", robot_ip, f"/api/v1/system/logs?type={log_type}&lines={lines}&container={container}", port=port,
        )

    def fetch_license_status(self, robot_ip: str, port: int | None = None) -> RobotHttpResponse:
        return self._request_json("GET", robot_ip, "/api/v1/license/status", port=port)

    def deploy_license(self, robot_ip: str, content: str | Dict[str, Any], port: int | None = None) -> RobotHttpResponse:
        return self._request_json("POST", robot_ip, "/api/v1/license/deploy", payload={"content": content}, port=port)

    def deploy_dance_zip(self, robot_ip: str, zip_bytes: bytes, port: int | None = None) -> RobotHttpResponse:
        b64 = base64.b64encode(zip_bytes).decode("ascii")
        return self._request_json("POST", robot_ip, "/api/v1/dance/deploy", payload={"zip_base64": b64}, port=port)

    def download_slam_pcd(
        self, robot_ip: str, save_path: Path, remote_path: str = "", port: int | None = None,
    ) -> RobotHttpResponse:
        qs = f"?path={quote(remote_path)}" if remote_path else ""
        url = f"{self._base(robot_ip, port)}/api/v1/slam/map.pcd{qs}"
        try:
            with self._opener.open(urlrequest.Request(url, method="GET"), timeout=max(5.0, self._timeout())) as resp:
                raw = resp.read()
                save_path.parent.mkdir(parents=True, exist_ok=True)
                save_path.write_bytes(raw)
                return RobotHttpResponse(True, int(resp.status), url, {"saved_path": str(save_path), "sha256": hashlib.sha256(raw).hexdigest()}, "PCD 下载成功", raw)
        except urlerror.HTTPError as ex:
            return RobotHttpResponse(False, int(ex.code), url, {}, f"HTTP {ex.code}: {ex.read().decode('utf-8', errors='ignore')}")
        except Exception as ex:
            return RobotHttpResponse(False, 0, url, {}, f"PCD 下载失败: {ex}")

    def upload_slam_pcd(
        self, robot_ip: str, pcd_path: Path, restart_localization: bool = False, port: int | None = None,
    ) -> RobotHttpResponse:
        if not pcd_path.exists():
            return RobotHttpResponse(False, 0, "", {}, f"本地 PCD 不存在: {pcd_path}")
        raw = pcd_path.read_bytes()
        url = f"{self._base(robot_ip, port)}/api/v1/slam/map/upload?filename={quote(pcd_path.name)}&restart_localization={'1' if restart_localization else '0'}"
        req = urlrequest.Request(url, data=raw, headers={"Content-Type": "application/octet-stream"}, method="POST")
        try:
            with self._opener.open(req, timeout=max(15.0, self._timeout() * 3.0)) as resp:
                parsed = json.loads(resp.read().decode("utf-8") or "{}")
                return RobotHttpResponse(200 <= resp.status < 300, int(resp.status), url, parsed, str(parsed.get("message") or "PCD 上传成功"))
        except urlerror.HTTPError as ex:
            return RobotHttpResponse(False, int(ex.code), url, {}, f"HTTP {ex.code}: {ex.read().decode('utf-8', errors='ignore')}")
        except Exception as ex:
            return RobotHttpResponse(False, 0, url, {}, f"PCD 上传失败: {ex}")
