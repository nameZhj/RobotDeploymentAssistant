# @file: src/api/routes.py
# @brief: Standard HTTP REST route dispatcher for lower computer ROS navigation, task chain, motion, safety, and system ops.
# @exports: LowerComputerContext, dispatch_http_request

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from src.api.slam_routes import dispatch_slam_route
from src.api.system_routes import dispatch_system_route
from src.commands.control_arbiter import ControlArbiter
from src.commands.g1_udp_motion_bridge import G1UdpMotionBridge
from src.commands.lora_wifi_agent import LoraWifiAgent
from src.commands.motion_command_executor import MotionCommandExecutor
from src.commands.system_ops_service import SystemOpsService
from src.config.robot_config_reader import RobotConfigReader
from src.config.ros_env_config import ROS_COMPONENTS, ROS_LAUNCH_COMMANDS, ROS_SERVICES, ROS_TOPICS, RosEnvConfig
from src.ros_bridge.navctl_runner import NavctlRunner
from src.ros_bridge.relocalize_helper import RosRelocalizer
from src.ros_bridge.ros_live_slam_tap import RosLiveSlamTap
from src.ros_bridge.ros_topic_service_bridge import RosTopicServiceBridge
from src.task_chain.safety_coordinator import SafetyCoordinator
from src.task_chain.task_chain_executor import TaskChainExecutor
from src.task_chain.webhook_dispatcher import WebhookDispatcher


class LowerComputerContext:
    """Dependency bundle wiring config, ROS, SLAM tap, relocalizer, safety coordinator, arbiter, motion, and task chain."""

    def __init__(
        self,
        cfg: Optional[RosEnvConfig] = None,
        navctl: Optional[NavctlRunner] = None,
        ros_bridge: Optional[RosTopicServiceBridge] = None,
        webhook: Optional[WebhookDispatcher] = None,
        motion_udp: Optional[G1UdpMotionBridge] = None,
    ) -> None:
        self.cfg = cfg or RosEnvConfig()
        self.config_reader = RobotConfigReader(self.cfg)
        self.navctl = navctl or NavctlRunner(navctl_bin=self.cfg.navctl_bin)
        self.ros_bridge = ros_bridge or RosTopicServiceBridge(self.cfg)
        self.discovery = self.ros_bridge.discovery
        self.slam_tap = RosLiveSlamTap(self.discovery)
        self.arbiter = ControlArbiter()
        self.motion_udp = motion_udp or (
            G1UdpMotionBridge(
                self.cfg.motion_udp_host, self.cfg.motion_udp_port,
                self.cfg.motion_udp_source_ip, self.cfg.motion_udp_source_port,
                self.cfg.motion_udp_probe_timeout_s, self.cfg.motion_udp_ack_timeout_s,
                self.cfg.motion_udp_dance_grace_s, self.cfg.motion_udp_default_dance_timeout_s,
            ) if self.cfg.motion_udp_enabled else None
        )
        self.motion_exec = MotionCommandExecutor(
            self.arbiter, self.config_reader, self.ros_bridge, motion_udp=self.motion_udp,
            transition_timeout_s=self.cfg.motion_udp_transition_timeout_s,
        )
        self.webhook = webhook or WebhookDispatcher()
        self.relocalizer = RosRelocalizer(self.ros_bridge, self.discovery, self.slam_tap, self.navctl)
        self.task_chain = TaskChainExecutor(self.cfg, self.arbiter, self.ros_bridge, self.motion_exec, self.webhook)
        self.safety = SafetyCoordinator(
            self.motion_exec, self.arbiter, self.ros_bridge, self.slam_tap,
            self.relocalizer, self.webhook, self.config_reader, self.task_chain,
        )
        self.task_chain.set_safety_coordinator(self.safety)
        if self.motion_udp is not None:
            self.motion_udp.set_event_callback(self.safety.on_udp_event)
        self.slam_tap.set_robot_state(self.safety.build_robot_state())
        self.system_ops = SystemOpsService(self.cfg, self.config_reader)
        self.lora_wifi = LoraWifiAgent()


def _ctrl_http_code(res: Any) -> int:
    if res.ok:
        return 200
    if res.execution_mode == "UNAVAILABLE":
        return 503
    return 409 if res.execution_mode == "REJECTED" else 400


def dispatch_http_request(
    ctx: LowerComputerContext, method: str, raw_path: str, body: Optional[Dict[str, Any]] = None,
) -> Tuple[int, Dict[str, Any] | bytes, str]:
    """Dispatch HTTP request and return (status_code, json_dict_or_bytes, content_type)."""
    parsed = urlparse(raw_path)
    path, query, data, m = parsed.path.rstrip("/") or "/", parse_qs(parsed.query), (body or {}), method.upper()
    for match in (dispatch_system_route(ctx, m, path, query, data), dispatch_slam_route(ctx, m, path, query, data)):
        if match is not None:
            return match

    if m == "GET" and path == "/api/v1/health":
        rid = ctx.config_reader.read_robot_id()
        ctrl = ctx.motion_exec.get_state()
        mon = ctrl["motion"]
        return 200, {
            "ok": True, "robot_id": rid["robot_id"], "robot_id_configured": rid["configured"],
            "ros_master_reachable": ctx.ros_bridge.is_ros_master_reachable(),
            "navctl_available": ctx.navctl.is_available(), "authority": ctrl["authority"],
            "motion_state": mon["state"], "active_dance": mon.get("active_dance", ""),
            "nav_input": mon.get("nav_input", ""), "nav_status": mon.get("nav_status", ""),
            "nav_reason": mon.get("nav_reason", ""), "active_faults": mon.get("active_faults", []),
            "safety_locked": mon.get("safety_locked", False), "lock_reason": mon.get("lock_reason", ""),
            "relocalize_status": ctx.safety.get_relocalize_status(),
            "motion_udp_enabled": ctx.motion_udp is not None,
            "motion_udp": ctx.motion_udp.status_summary() if ctx.motion_udp else {"enabled": False, "reachable": False},
            "ros_components": ROS_COMPONENTS,
        }, "application/json"

    if m == "GET" and path == "/api/v1/status":
        q = (query.get("query", ["ALL"])[0] or "ALL").upper()
        st = ctx.motion_exec.execute("STATUS", [q])
        return 200, {
            "ok": True, "authority": ctx.arbiter.state.value, "task_chain": ctx.task_chain.state.to_dict(),
            "details": st.details, "ros_spec": {"launch": ROS_LAUNCH_COMMANDS, "topics": ROS_TOPICS, "services": ROS_SERVICES},
        }, "application/json"

    if m == "GET" and path == "/api/v1/actions/list":
        reg = ctx.config_reader.read_dance_registry()
        return (200 if reg["available"] else 404), {"ok": reg["available"], **reg}, "application/json"

    if m == "POST" and path in ("/api/v1/task_chain/upload", "/api/v1/lrmp/choreography/upload"):
        try:
            return 200, {"ok": True, "message": "任务链已校验并保存", "state": ctx.task_chain.upload_chain(data)}, "application/json"
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

    if m == "POST" and path == "/api/v1/control/callback":
        cb_url = str(data.get("callback_url", "")).strip()
        if not cb_url:
            return 400, {"ok": False, "message": "缺少 callback_url"}, "application/json"
        ctx.safety.set_callback_url(cb_url)
        return 200, {"ok": True, "callback_url": cb_url}, "application/json"

    if m == "GET" and path == "/api/v1/control/state":
        rid = ctx.config_reader.read_robot_id()
        if query.get("sync", ["0"])[0].lower() in ("1", "true", "yes") and ctx.motion_udp is not None:
            ctx.motion_udp.sync_state(rid["robot_id"])
            ctx.safety.on_udp_event("SYNC", {})
        return 200, {
            "ok": True, "robot_id": rid["robot_id"], **ctx.motion_exec.get_state(),
            "relocalize_status": ctx.safety.get_relocalize_status(),
            "motion_udp": ctx.motion_udp.status_summary() if ctx.motion_udp else {"enabled": False, "reachable": False},
            "task_chain": ctx.task_chain.state.to_dict(),
        }, "application/json"

    if path == "/api/v1/control/probe" and m in ("GET", "POST"):
        if ctx.motion_udp is None:
            return 503, {"ok": False, "reachable": False, "message": "本机 UDP 运控桥未启用"}, "application/json"
        tgt = str(data.get("target_id") or query.get("target_id", [""])[0] or ctx.config_reader.read_robot_id()["robot_id"])
        res = ctx.motion_udp.probe(tgt)
        if res["ok"]:
            ctx.safety.on_udp_event("SYNC", {})
        return (200 if res["ok"] else 503), res, "application/json"

    if m == "POST" and path == "/api/v1/control/posture":
        res = ctx.motion_exec.execute_posture(str(data.get("posture", "")), wait_ready=bool(data.get("wait_ready", False)))
        ctx.slam_tap.set_robot_state(ctx.safety.build_robot_state())
        return _ctrl_http_code(res), res.to_dict(), "application/json"

    if m == "POST" and path == "/api/v1/control/velocity":
        try:
            dur = float(data.get("duration", 1.0))
            vx, vy, vyaw = (float(data[k]) if k in data else None for k in ("vx", "vy", "vyaw"))
        except (ValueError, TypeError):
            return 400, {"ok": False, "message": "速度参数 vx/vy/vyaw/duration 必须为数值"}, "application/json"
        res = ctx.motion_exec.execute_velocity(str(data.get("direction", "")), dur, vx, vy, vyaw)
        ctx.slam_tap.set_robot_state(ctx.safety.build_robot_state())
        return _ctrl_http_code(res), res.to_dict(), "application/json"

    if m == "POST" and path == "/api/v1/control/dance":
        alias = str(data.get("alias", "") or data.get("dance", "")).strip()
        res = ctx.motion_exec.execute_dance(alias)
        ctx.slam_tap.set_robot_state(ctx.safety.build_robot_state())
        return _ctrl_http_code(res), res.to_dict(), "application/json"

    if m == "POST" and path == "/api/v1/control/stop":
        emergency = bool(data.get("emergency", False))
        ctx.task_chain.abort_running_chain(reason="EMERGENCY" if emergency else "STOP")
        res = ctx.motion_exec.execute_stop(emergency=emergency)
        ctx.slam_tap.set_robot_state(ctx.safety.build_robot_state())
        return _ctrl_http_code(res), res.to_dict(), "application/json"

    if m == "POST" and path == "/api/v1/control/command":
        cmd = str(data.get("command", "")).strip()
        if not cmd:
            return 400, {"ok": False, "message": "缺少 command 字段"}, "application/json"
        params = [str(p) for p in (data.get("params") or [])]
        if "," in cmd and not params:
            parts = [p.strip() for p in cmd.split(",") if p.strip()]
            cmd, params = (parts[0] if parts else ""), parts[1:]
        cu = cmd.upper()
        if cu in ("STOP", "EMERGENCY"):
            ctx.task_chain.abort_running_chain(reason=cu)
        elif cu == "BARRIER" and params:
            b_id = params[1] if len(params) > 1 else "1"
            rel_ms = int(params[2]) if len(params) > 2 and params[2].isdigit() else 0
            ctx.task_chain.release_barrier(params[0], b_id, rel_ms)
        res = ctx.motion_exec.execute(cmd, params)
        ctx.slam_tap.set_robot_state(ctx.safety.build_robot_state())
        out = res.to_dict()
        out["local_robot_id"] = ctx.config_reader.read_robot_id()["robot_id"]
        return _ctrl_http_code(res), out, "application/json"

    if m == "POST" and path == "/api/v1/navigation/navctl":
        action = str(data.get("action", "status"))
        res = ctx.navctl.execute(action)
        if res.ok:
            low = action.lower()
            if "stop" in low or "finish" in low:
                ctx.slam_tap.stop()
            elif "start" in low or "restart" in low:
                ctx.discovery.discover_topics(force=True)
                ctx.slam_tap.start()
        return (200 if res.ok else (503 if not res.available else 400)), res.to_dict(), "application/json"

    if m == "POST" and path == "/api/v1/navigation/goal":
        if "x" not in data or "y" not in data:
            return 400, {"ok": False, "message": "缺少目标点坐标 x, y"}, "application/json"
        try:
            gx, gy, gyaw = float(data["x"]), float(data["y"]), float(data.get("yaw", 0.0))
        except (ValueError, TypeError):
            return 400, {"ok": False, "message": "目标点坐标 x/y/yaw 必须为数值"}, "application/json"
        if not ctx.ros_bridge.is_ros_master_reachable():
            return 503, {"ok": False, "ros_available": False, "reason": f"ROS Master ({ctx.cfg.ros_master_uri}) 不可达"}, "application/json"
        if ctx.arbiter.is_safety_locked:
            return 409, {"ok": False, "ros_available": True, "reason": ctx.arbiter.safety_lock_reason, "message": ctx.arbiter.safety_lock_reason}, "application/json"
        if ctx.arbiter.state.value == "CHOREO":
            msg = "CHOREO 任务链执行中，禁止直接下发地图导航目标"
            return 409, {"ok": False, "ros_available": True, "reason": msg, "message": msg}, "application/json"
        if ctx.motion_udp is not None:
            ok_g, err_g = ctx.motion_exec.ensure_gait_for_nav(allow_stand_from_passive=False)
            if not ok_g:
                code = 503 if ("超时" in err_g or "未回复" in err_g or "socket" in err_g.lower()) else 409
                return code, {"ok": False, "ros_available": True, "reason": err_g, "message": err_g}, "application/json"
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
        res["cmd_vel_stop"] = ctx.ros_bridge.stop_cmd_vel()
        if ctx.motion_udp is not None:
            res["udp_stop"] = ctx.motion_exec.execute("STOP").to_dict()
        return (200 if res["ok"] else 503), res, "application/json"

    if m == "GET" and path == "/api/v1/navigation/diagnostics":
        if not ctx.ros_bridge.is_ros_master_reachable():
            return 503, {"ok": False, "ros_available": False, "reason": "ROS Master 不可达"}, "application/json"
        diag = ctx.ros_bridge.diagnostics
        return 200, {"ok": True, "versions": diag.query_versions(), "graph": diag.inspect_graph(), "global_path": diag.read_global_path()}, "application/json"

    if path == "/api/v1/navigation/teb_params":
        if not ctx.ros_bridge.is_ros_master_reachable():
            return 503, {"ok": False, "ros_available": False, "reason": "ROS Master 不可达"}, "application/json"
        res = ctx.ros_bridge.diagnostics.get_teb_parameters() if m == "GET" else ctx.ros_bridge.diagnostics.set_teb_parameters(data.get("params") or {})
        return (200 if res["ok"] else 400), res, "application/json"

    if m == "GET" and path == "/api/v1/slam/scan":
        if not ctx.ros_bridge.is_ros_master_reachable():
            return 503, {"ok": False, "ros_available": False, "reason": "ROS Master 不可达"}, "application/json"
        res = ctx.ros_bridge.diagnostics.read_cad_scan_summary()
        return (200 if res["ok"] else 503), res, "application/json"

    return 404, {"ok": False, "message": f"未知接口路径: {m} {path}"}, "application/json"
