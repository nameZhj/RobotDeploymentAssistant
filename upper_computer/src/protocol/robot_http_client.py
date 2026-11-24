# @file: src/protocol/robot_http_client.py
# @brief: Standard Wi-Fi HTTP client covering all 22 lower-computer endpoints (actions, task chain, ROS, system, license).
# @exports: RobotHttpResponse, RobotHttpClient

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import error as urlerror
from urllib import request as urlrequest

from src.core.settings import get_settings


@dataclass(frozen=True)
class RobotHttpResponse:
    """Standardized HTTP response envelope from a lower computer endpoint."""

    ok: bool
    status_code: int
    endpoint: str
    data: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    raw_bytes: bytes = b""


class RobotHttpClient:
    """Performs all non-provisioning robot communications over wireless Wi-Fi HTTP."""

    def __init__(self, timeout_s: Optional[float] = None) -> None:
        self._timeout_override = timeout_s
        self._opener = urlrequest.build_opener(urlrequest.ProxyHandler({}))

    def _base(self, robot_ip: str, port: Optional[int] = None) -> str:
        cfg = get_settings().virtual_interfaces
        use_port = port or cfg.http_default_port
        return f"http://{robot_ip.strip()}:{use_port}"

    def _timeout(self) -> float:
        if self._timeout_override is not None:
            return self._timeout_override
        return float(get_settings().virtual_interfaces.http_upload_timeout_s)

    def _request_json(
        self,
        method: str,
        robot_ip: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        port: Optional[int] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> RobotHttpResponse:
        url = f"{self._base(robot_ip, port)}{path}"
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        req = urlrequest.Request(url, data=raw, headers=headers, method=method.upper())
        try:
            with self._opener.open(req, timeout=self._timeout()) as resp:
                body = resp.read()
                parsed = json.loads(body.decode("utf-8")) if body else {}
                msg = str(parsed.get("message") or f"HTTP {resp.status}")
                return RobotHttpResponse(200 <= resp.status < 300, int(resp.status), url, parsed, msg)
        except urlerror.HTTPError as ex:
            body = ex.read()
            try:
                parsed = json.loads(body.decode("utf-8")) if body else {}
            except Exception:
                parsed = {"raw": body.decode("utf-8", errors="ignore")}
            msg = str(parsed.get("message") or parsed.get("reason") or f"HTTP {ex.code}")
            return RobotHttpResponse(False, int(ex.code), url, parsed, msg)
        except Exception as ex:
            return RobotHttpResponse(False, 0, url, {}, f"HTTP 连接失败 ({url}): {ex}")

    def health(self, robot_ip: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("GET", robot_ip, "/api/v1/health", port=port)

    def fetch_status(self, robot_ip: str, query: str = "ALL", port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("GET", robot_ip, f"/api/v1/status?query={query}", port=port)

    def fetch_actions(self, robot_ip: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("GET", robot_ip, "/api/v1/actions/list", port=port)

    def register_dance_alias(
        self, robot_ip: str, alias: str, select_key: str, action_key: str, comment: str = "", port: Optional[int] = None
    ) -> RobotHttpResponse:
        return self._request_json(
            "POST", robot_ip, "/api/v1/actions/register",
            payload={"alias": alias, "select_key": select_key, "action_key": action_key, "comment": comment},
            port=port,
        )

    def upload_task_chain(
        self, robot_ip: str, target_id: str, payload: Dict[str, Any], port: Optional[int] = None
    ) -> RobotHttpResponse:
        return self._request_json(
            "POST", robot_ip, "/api/v1/task_chain/upload", payload=payload, port=port,
            extra_headers={"X-LRMP-Target": target_id},
        )

    def prep_task_chain(
        self, robot_ip: str, run_id: str, callback_url: str = "", port: Optional[int] = None
    ) -> RobotHttpResponse:
        return self._request_json(
            "POST", robot_ip, "/api/v1/task_chain/prep",
            payload={"run_id": run_id, "callback_url": callback_url}, port=port,
        )

    def start_task_chain(
        self, robot_ip: str, run_id: str, callback_url: str = "", port: Optional[int] = None
    ) -> RobotHttpResponse:
        return self._request_json(
            "POST", robot_ip, "/api/v1/task_chain/start",
            payload={"run_id": run_id, "callback_url": callback_url}, port=port,
        )

    def barrier_task_chain(
        self, robot_ip: str, run_id: str, barrier_id: str = "1", release_ms: int = 0, port: Optional[int] = None
    ) -> RobotHttpResponse:
        return self._request_json(
            "POST", robot_ip, "/api/v1/task_chain/barrier",
            payload={"run_id": run_id, "barrier_id": barrier_id, "release_ms": release_ms}, port=port,
        )

    def stop_and_return_origin(
        self, robot_ip: str, origin_pose: Dict[str, float], callback_url: str = "", port: Optional[int] = None
    ) -> RobotHttpResponse:
        return self._request_json(
            "POST", robot_ip, "/api/v1/task_chain/stop",
            payload={"return_to_origin": True, "origin_pose": origin_pose, "callback_url": callback_url},
            port=port,
        )

    def send_command(
        self, robot_ip: str, target_id: str, command: str, params: Optional[List[str]] = None, port: Optional[int] = None
    ) -> RobotHttpResponse:
        return self._request_json(
            "POST", robot_ip, "/api/v1/control/command",
            payload={"target_id": target_id, "command": command, "params": params or []}, port=port,
        )

    def get_control_state(self, robot_ip: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("GET", robot_ip, "/api/v1/control/state", port=port)

    def send_posture(self, robot_ip: str, posture: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("POST", robot_ip, "/api/v1/control/posture", payload={"posture": posture}, port=port)

    def send_velocity(
        self, robot_ip: str, payload: Dict[str, Any], port: Optional[int] = None
    ) -> RobotHttpResponse:
        return self._request_json("POST", robot_ip, "/api/v1/control/velocity", payload=payload, port=port)

    def send_dance(self, robot_ip: str, alias: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("POST", robot_ip, "/api/v1/control/dance", payload={"alias": alias}, port=port)

    def send_stop(self, robot_ip: str, emergency: bool = False, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("POST", robot_ip, "/api/v1/control/stop", payload={"emergency": emergency}, port=port)

    def navctl(self, robot_ip: str, action: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("POST", robot_ip, "/api/v1/navigation/navctl", payload={"action": action}, port=port)

    def send_nav_goal(
        self, robot_ip: str, x: float, y: float, yaw: float = 0.0, port: Optional[int] = None
    ) -> RobotHttpResponse:
        return self._request_json(
            "POST", robot_ip, "/api/v1/navigation/goal",
            payload={"x": x, "y": y, "yaw": yaw, "frame_id": "map"}, port=port,
        )

    def set_initial_pose(
        self, robot_ip: str, x: float, y: float, yaw: float = 0.0, port: Optional[int] = None
    ) -> RobotHttpResponse:
        return self._request_json(
            "POST", robot_ip, "/api/v1/navigation/initialpose",
            payload={"x": x, "y": y, "yaw": yaw, "frame_id": "map"}, port=port,
        )

    def cancel_navigation(self, robot_ip: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("POST", robot_ip, "/api/v1/navigation/cancel", payload={}, port=port)

    def fetch_ros_diagnostics(self, robot_ip: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("GET", robot_ip, "/api/v1/navigation/diagnostics", port=port)

    def get_teb_params(self, robot_ip: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("GET", robot_ip, "/api/v1/navigation/teb_params", port=port)

    def set_teb_params(self, robot_ip: str, params: Dict[str, Any], port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("POST", robot_ip, "/api/v1/navigation/teb_params", payload={"params": params}, port=port)

    def fetch_cad_scan(self, robot_ip: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("GET", robot_ip, "/api/v1/slam/scan", port=port)

    def fetch_nav_discovery(self, robot_ip: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("GET", robot_ip, "/api/v1/navigation/discovery", port=port)

    def fetch_slam_live_state(self, robot_ip: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("GET", robot_ip, "/api/v1/slam/live_state", port=port)

    def slam_stream_url(self, robot_ip: str, port: Optional[int] = None) -> str:
        return f"{self._base(robot_ip, port)}/api/v1/slam/stream"

    def list_remote_maps(self, robot_ip: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("GET", robot_ip, "/api/v1/slam/maps", port=port)

    def fetch_slam_live_cloud(
        self, robot_ip: str, since_seq: int = 0, max_points: int = 30000, port: Optional[int] = None
    ) -> RobotHttpResponse:
        url = f"{self._base(robot_ip, port)}/api/v1/slam/live_cloud?since_seq={since_seq}&max_points={max_points}"
        try:
            with self._opener.open(urlrequest.Request(url, method="GET"), timeout=self._timeout()) as resp:
                raw = resp.read()
                seq = int(resp.headers.get("X-Cloud-Seq", str(since_seq)) or 0)
                cnt = int(resp.headers.get("X-Cloud-Count", str(len(raw) // 12)) or 0)
                return RobotHttpResponse(int(resp.status) == 200, int(resp.status), url, {"cloud_seq": seq, "point_count": cnt}, "OK" if resp.status == 200 else "UNCHANGED", raw)
        except Exception as ex:
            return RobotHttpResponse(False, 0, url, {}, f"点云拉取失败: {ex}")

    def system_precheck(self, robot_ip: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("GET", robot_ip, "/api/v1/system/precheck", port=port)

    def fetch_machine_id(self, robot_ip: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("GET", robot_ip, "/api/v1/system/machine_id", port=port)

    def get_processes(self, robot_ip: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("GET", robot_ip, "/api/v1/system/processes", port=port)

    def control_processes(self, robot_ip: str, action: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("POST", robot_ip, "/api/v1/system/processes", payload={"action": action}, port=port)

    def set_robot_id(self, robot_ip: str, robot_id: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("POST", robot_ip, "/api/v1/system/robot_id", payload={"robot_id": robot_id}, port=port)

    def get_docker_status(self, robot_ip: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("GET", robot_ip, "/api/v1/system/docker", port=port)

    def control_container(
        self, robot_ip: str, action: str, container_name: str = "vsis_g1", port: Optional[int] = None
    ) -> RobotHttpResponse:
        return self._request_json(
            "POST", robot_ip, "/api/v1/system/container",
            payload={"action": action, "container_name": container_name}, port=port,
        )

    def fetch_logs(
        self, robot_ip: str, log_type: str = "sec_run", lines: int = 200, container: str = "vsis_g1", port: Optional[int] = None
    ) -> RobotHttpResponse:
        return self._request_json(
            "GET", robot_ip, f"/api/v1/system/logs?type={log_type}&lines={lines}&container={container}", port=port
        )

    def fetch_license_status(self, robot_ip: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("GET", robot_ip, "/api/v1/license/status", port=port)

    def deploy_license(self, robot_ip: str, content: str | Dict[str, Any], port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("POST", robot_ip, "/api/v1/license/deploy", payload={"content": content}, port=port)

    def deploy_dance_zip(self, robot_ip: str, zip_bytes: bytes, port: Optional[int] = None) -> RobotHttpResponse:
        b64 = base64.b64encode(zip_bytes).decode("ascii")
        return self._request_json("POST", robot_ip, "/api/v1/dance/deploy", payload={"zip_base64": b64}, port=port)

    def download_slam_pcd(
        self, robot_ip: str, save_path: Path, remote_path: str = "", port: Optional[int] = None
    ) -> RobotHttpResponse:
        from urllib.parse import quote
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
        self, robot_ip: str, pcd_path: Path, restart_localization: bool = False, port: Optional[int] = None
    ) -> RobotHttpResponse:
        from urllib.parse import quote
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
