# @file: src/api/routes.py
# @brief: Standard HTTP REST route dispatcher for lower computer ROS navigation, task chain, motion, and system ops.
# @exports: LowerComputerContext, dispatch_http_request

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from src.api.system_routes import dispatch_system_route
from src.commands.control_arbiter import ControlArbiter
from src.commands.lora_wifi_agent import LoraWifiAgent
from src.commands.motion_command_executor import MotionCommandExecutor
from src.commands.system_ops_service import SystemOpsService
from src.config.robot_config_reader import RobotConfigReader
from src.config.ros_env_config import ROS_COMPONENTS, ROS_LAUNCH_COMMANDS, ROS_SERVICES, ROS_TOPICS, RosEnvConfig
from src.ros_bridge.navctl_runner import NavctlRunner
from src.ros_bridge.ros_topic_service_bridge import RosTopicServiceBridge
from src.task_chain.task_chain_executor import TaskChainExecutor
from src.task_chain.webhook_dispatcher import WebhookDispatcher


class LowerComputerContext:
    """Dependency bundle wiring onboard config, ROS bridges, arbiter, motion executor, task chain, and system ops."""

    def __init__(
        self,
        cfg: Optional[RosEnvConfig] = None,
        navctl: Optional[NavctlRunner] = None,
        ros_bridge: Optional[RosTopicServiceBridge] = None,
        webhook: Optional[WebhookDispatcher] = None,
    ) -> None:
        self.cfg = cfg or RosEnvConfig()
        self.config_reader = RobotConfigReader(self.cfg)
        self.navctl = navctl or NavctlRunner(navctl_bin=self.cfg.navctl_bin)
        self.ros_bridge = ros_bridge or RosTopicServiceBridge(self.cfg)
        self.arbiter = ControlArbiter()
        self.motion_exec = MotionCommandExecutor(self.arbiter, self.config_reader, self.ros_bridge)
        self.webhook = webhook or WebhookDispatcher()
        self.task_chain = TaskChainExecutor(self.cfg, self.arbiter, self.ros_bridge, self.motion_exec, self.webhook)
        self.system_ops = SystemOpsService(self.cfg, self.config_reader)
        self.lora_wifi = LoraWifiAgent()


def dispatch_http_request(
    ctx: LowerComputerContext,
    method: str,
    raw_path: str,
    body: Optional[Dict[str, Any]] = None,
) -> Tuple[int, Dict[str, Any] | bytes, str]:
    """Dispatch HTTP request and return (status_code, json_dict_or_bytes, content_type)."""
    parsed = urlparse(raw_path)
    path = parsed.path.rstrip("/") or "/"
    query = parse_qs(parsed.query)
    data = body or {}
    m = method.upper()

    sys_match = dispatch_system_route(ctx, m, path, query, data)
    if sys_match is not None:
        return sys_match

    if m == "GET" and path == "/api/v1/health":
        rid = ctx.config_reader.read_robot_id()
        return 200, {
            "ok": True,
            "robot_id": rid["robot_id"],
            "robot_id_configured": rid["configured"],
            "ros_master_reachable": ctx.ros_bridge.is_ros_master_reachable(),
            "navctl_available": ctx.navctl.is_available(),
            "authority": ctx.arbiter.state.value,
            "ros_components": ROS_COMPONENTS,
        }, "application/json"

    if m == "GET" and path == "/api/v1/status":
        q = (query.get("query", ["ALL"])[0] or "ALL").upper()
        st = ctx.motion_exec.execute("STATUS", [q])
        return 200, {
            "ok": True,
            "authority": ctx.arbiter.state.value,
            "task_chain": ctx.task_chain.state.to_dict(),
            "details": st.details,
            "ros_spec": {"launch": ROS_LAUNCH_COMMANDS, "topics": ROS_TOPICS, "services": ROS_SERVICES},
        }, "application/json"

    if m == "GET" and path == "/api/v1/actions/list":
        reg = ctx.config_reader.read_dance_registry()
        return (200 if reg["available"] else 404), {"ok": reg["available"], **reg}, "application/json"

    if m == "POST" and path in ("/api/v1/task_chain/upload", "/api/v1/lrmp/choreography/upload"):
        try:
            st = ctx.task_chain.upload_chain(data)
            return 200, {"ok": True, "message": "任务链已校验并保存", "state": st}, "application/json"
        except RuntimeError as ex:
            return 409, {"ok": False, "message": str(ex)}, "application/json"
        except Exception as ex:
            return 400, {"ok": False, "message": f"任务链格式错误: {ex}"}, "application/json"

    if m == "POST" and path == "/api/v1/task_chain/prep":
        res = ctx.task_chain.prep_chain(str(data.get("run_id", "9001")), str(data.get("callback_url", "")))
        return res["status_code"], res, "application/json"

    if m == "POST" and path == "/api/v1/task_chain/start":
        res = ctx.task_chain.start_chain(str(data.get("run_id", "9001")), str(data.get("callback_url", "")))
        return res["status_code"], res, "application/json"

    if m == "POST" and path == "/api/v1/task_chain/barrier":
        try:
            rel_ms = int(data.get("release_ms", 0))
        except (ValueError, TypeError):
            return 400, {"ok": False, "message": "release_ms 必须为整数"}, "application/json"
        res = ctx.task_chain.release_barrier(str(data.get("run_id", "")), str(data.get("barrier_id", "1")), rel_ms)
        return res["status_code"], res, "application/json"

    if m == "POST" and path == "/api/v1/task_chain/stop":
        res = ctx.task_chain.stop_and_return_origin(data.get("origin_pose"), str(data.get("callback_url", "")))
        return res["status_code"], res, "application/json"

    if m == "POST" and path == "/api/v1/control/command":
        cmd = str(data.get("command", "")).strip()
        if not cmd:
            return 400, {"ok": False, "message": "缺少 command 字段"}, "application/json"
        params = [str(p) for p in (data.get("params") or [])]
        cu = cmd.upper()
        if cu in ("STOP", "EMERGENCY"):
            ctx.task_chain.abort_running_chain(reason=cu)
        elif cu == "BARRIER" and params:
            b_id = params[1] if len(params) > 1 else "1"
            rel_ms = int(params[2]) if len(params) > 2 and params[2].isdigit() else 0
            ctx.task_chain.release_barrier(params[0], b_id, rel_ms)
        res = ctx.motion_exec.execute(cmd, params)
        code = 200 if res.ok else (409 if res.execution_mode == "REJECTED" else 400)
        return code, res.to_dict(), "application/json"

    if m == "POST" and path == "/api/v1/navigation/navctl":
        action = str(data.get("action", "status"))
        res = ctx.navctl.execute(action)
        code = 200 if res.ok else (503 if not res.available else 400)
        return code, res.to_dict(), "application/json"

    if m == "POST" and path == "/api/v1/navigation/goal":
        if "x" not in data or "y" not in data:
            return 400, {"ok": False, "message": "缺少目标点坐标 x, y"}, "application/json"
        try:
            gx, gy, gyaw = float(data["x"]), float(data["y"]), float(data.get("yaw", 0.0))
        except (ValueError, TypeError):
            return 400, {"ok": False, "message": "目标点坐标 x/y/yaw 必须为数值"}, "application/json"
        res = ctx.ros_bridge.publish_nav_goal(gx, gy, gyaw)
        return (202 if res["ok"] else 503), res, "application/json"

    if m == "POST" and path == "/api/v1/navigation/initialpose":
        if "x" not in data or "y" not in data:
            return 400, {"ok": False, "message": "缺少初始定位坐标 x, y"}, "application/json"
        try:
            ix, iy, iyaw = float(data["x"]), float(data["y"]), float(data.get("yaw", 0.0))
        except (ValueError, TypeError):
            return 400, {"ok": False, "message": "初始定位坐标 x/y/yaw 必须为数值"}, "application/json"
        res = ctx.ros_bridge.publish_initial_pose(ix, iy, iyaw)
        return (200 if res["ok"] else 503), res, "application/json"

    if m == "POST" and path == "/api/v1/navigation/cancel":
        res = ctx.ros_bridge.cancel_planning()
        return (200 if res["ok"] else 503), res, "application/json"

    if m == "GET" and path == "/api/v1/navigation/diagnostics":
        if not ctx.ros_bridge.is_ros_master_reachable():
            return 503, {"ok": False, "reason": "ROS Master 不可达"}, "application/json"
        diag = ctx.ros_bridge.diagnostics
        return 200, {
            "ok": True,
            "versions": diag.query_versions(),
            "graph": diag.inspect_graph(),
            "global_path": diag.read_global_path(),
        }, "application/json"

    if path == "/api/v1/navigation/teb_params":
        if not ctx.ros_bridge.is_ros_master_reachable():
            return 503, {"ok": False, "reason": "ROS Master 不可达"}, "application/json"
        res = (
            ctx.ros_bridge.diagnostics.get_teb_parameters()
            if m == "GET"
            else ctx.ros_bridge.diagnostics.set_teb_parameters(data.get("params") or {})
        )
        return (200 if res["ok"] else 400), res, "application/json"

    if m == "GET" and path == "/api/v1/slam/scan":
        if not ctx.ros_bridge.is_ros_master_reachable():
            return 503, {"ok": False, "reason": "ROS Master 不可达"}, "application/json"
        res = ctx.ros_bridge.diagnostics.read_cad_scan_summary()
        return (200 if res["ok"] else 503), res, "application/json"

    if m == "GET" and path == "/api/v1/slam/map.pcd":
        req_path = query.get("path", [""])[0]
        target = Path(req_path) if req_path else None
        if target is None or not target.exists():
            pcds = sorted(ctx.cfg.maps_dir.glob("*.pcd"), key=lambda p: p.stat().st_mtime, reverse=True) if ctx.cfg.maps_dir.exists() else []
            target = pcds[0] if pcds else None
        if target is None or not target.exists():
            return 404, {"ok": False, "message": f"未在 {ctx.cfg.maps_dir} 找到真实建图生成的 .pcd 文件"}, "application/json"
        return 200, target.read_bytes(), "application/octet-stream"

    return 404, {"ok": False, "message": f"未知接口路径: {m} {path}"}, "application/json"
