# @file: src/protocol/robot_http_client.py
# @brief: Standard Wi-Fi HTTP client covering all lower-computer endpoints (actions, task chain, motion, ROS relocalize, system).
# @exports: RobotHttpResponse, RobotHttpClient

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib import error as urlerror
from urllib import request as urlrequest

from src.core.settings import get_settings
from src.protocol.robot_http_system_mixin import RobotHttpResponse, RobotHttpSystemMixin


class RobotHttpClient(RobotHttpSystemMixin):
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
        self, method: str, robot_ip: str, path: str, payload: Optional[Dict[str, Any]] = None,
        port: Optional[int] = None, extra_headers: Optional[Dict[str, str]] = None,
        timeout_override: Optional[float] = None,
    ) -> RobotHttpResponse:
        url = f"{self._base(robot_ip, port)}{path}"
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        req = urlrequest.Request(url, data=raw, headers=headers, method=method.upper())
        try:
            with self._opener.open(req, timeout=timeout_override or self._timeout()) as resp:
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
        self, robot_ip: str, alias: str, select_key: str, action_key: str,
        comment: str = "", port: Optional[int] = None,
    ) -> RobotHttpResponse:
        return self._request_json(
            "POST", robot_ip, "/api/v1/actions/register",
            payload={"alias": alias, "select_key": select_key, "action_key": action_key, "comment": comment}, port=port,
        )

    def upload_task_chain(
        self, robot_ip: str, target_id: str, payload: Dict[str, Any], port: Optional[int] = None,
    ) -> RobotHttpResponse:
        return self._request_json(
            "POST", robot_ip, "/api/v1/task_chain/upload", payload=payload, port=port,
            extra_headers={"X-LRMP-Target": target_id},
        )

    def prep_task_chain(
        self, robot_ip: str, run_id: str, callback_url: str = "", port: Optional[int] = None,
    ) -> RobotHttpResponse:
        return self._request_json("POST", robot_ip, "/api/v1/task_chain/prep", payload={"run_id": run_id, "callback_url": callback_url}, port=port)

    def start_task_chain(
        self, robot_ip: str, run_id: str, callback_url: str = "", port: Optional[int] = None,
    ) -> RobotHttpResponse:
        return self._request_json("POST", robot_ip, "/api/v1/task_chain/start", payload={"run_id": run_id, "callback_url": callback_url}, port=port)

    def barrier_task_chain(
        self, robot_ip: str, run_id: str, barrier_id: str = "1", release_ms: int = 0, port: Optional[int] = None,
    ) -> RobotHttpResponse:
        return self._request_json(
            "POST", robot_ip, "/api/v1/task_chain/barrier",
            payload={"run_id": run_id, "barrier_id": barrier_id, "release_ms": release_ms}, port=port,
        )

    def stop_and_return_origin(
        self, robot_ip: str, origin_pose: Dict[str, float], callback_url: str = "", port: Optional[int] = None,
    ) -> RobotHttpResponse:
        return self._request_json(
            "POST", robot_ip, "/api/v1/task_chain/stop",
            payload={"return_to_origin": True, "origin_pose": origin_pose, "callback_url": callback_url}, port=port,
        )

    def register_callback_url(self, robot_ip: str, callback_url: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("POST", robot_ip, "/api/v1/control/callback", payload={"callback_url": callback_url}, port=port)

    def send_command(
        self, robot_ip: str, target_id: str, command: str, params: Optional[List[str]] = None, port: Optional[int] = None,
    ) -> RobotHttpResponse:
        return self._request_json(
            "POST", robot_ip, "/api/v1/control/command",
            payload={"target_id": target_id, "command": command, "params": params or []}, port=port,
        )

    def get_control_state(self, robot_ip: str, sync: bool = False, port: Optional[int] = None) -> RobotHttpResponse:
        path = "/api/v1/control/state?sync=1" if sync else "/api/v1/control/state"
        return self._request_json("GET", robot_ip, path, port=port)

    def probe_motion(self, robot_ip: str, target_id: str = "", port: Optional[int] = None) -> RobotHttpResponse:
        qs = f"?target_id={target_id}" if target_id else ""
        return self._request_json("GET", robot_ip, f"/api/v1/control/probe{qs}", port=port)

    def send_posture(
        self, robot_ip: str, posture: str, wait_ready: bool = False, port: Optional[int] = None,
    ) -> RobotHttpResponse:
        timeout = max(self._timeout(), 7.5) if wait_ready else None
        return self._request_json(
            "POST", robot_ip, "/api/v1/control/posture",
            payload={"posture": posture, "wait_ready": bool(wait_ready)}, port=port, timeout_override=timeout,
        )

    def send_velocity(self, robot_ip: str, payload: Dict[str, Any], port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("POST", robot_ip, "/api/v1/control/velocity", payload=payload, port=port)

    def send_dance(self, robot_ip: str, alias: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("POST", robot_ip, "/api/v1/control/dance", payload={"alias": alias}, port=port)

    def send_stop(self, robot_ip: str, emergency: bool = False, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("POST", robot_ip, "/api/v1/control/stop", payload={"emergency": emergency}, port=port)

    def navctl(self, robot_ip: str, action: str, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("POST", robot_ip, "/api/v1/navigation/navctl", payload={"action": action}, port=port)

    def send_nav_goal(self, robot_ip: str, x: float, y: float, yaw: float = 0.0, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json(
            "POST", robot_ip, "/api/v1/navigation/goal",
            payload={"x": x, "y": y, "yaw": yaw, "frame_id": "map"}, port=port, timeout_override=max(self._timeout(), 8.0),
        )

    def set_initial_pose(self, robot_ip: str, x: float, y: float, yaw: float = 0.0, port: Optional[int] = None) -> RobotHttpResponse:
        return self._request_json("POST", robot_ip, "/api/v1/navigation/initialpose", payload={"x": x, "y": y, "yaw": yaw, "frame_id": "map"}, port=port)

    def relocalize(
        self, robot_ip: str, mode: str = "auto", x: Optional[float] = None, y: Optional[float] = None, yaw: float = 0.0,
        fallback_pose: Optional[Dict[str, float]] = None, min_confidence: float = 0.65,
        timeout_s: float = 6.0, allow_restart: bool = True, port: Optional[int] = None,
    ) -> RobotHttpResponse:
        payload: Dict[str, Any] = {
            "mode": mode, "min_confidence": float(min_confidence),
            "timeout_s": float(timeout_s), "allow_restart": bool(allow_restart),
        }
        if x is not None and y is not None:
            payload.update({"x": float(x), "y": float(y), "yaw": float(yaw)})
        if fallback_pose is not None:
            payload["fallback_pose"] = fallback_pose
        return self._request_json(
            "POST", robot_ip, "/api/v1/navigation/relocalize",
            payload=payload, port=port, timeout_override=max(self._timeout(), float(timeout_s) + 8.0),
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
        self, robot_ip: str, since_seq: int = 0, max_points: int = 30000, port: Optional[int] = None,
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
