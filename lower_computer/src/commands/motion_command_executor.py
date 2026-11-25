# @file: src/commands/motion_command_executor.py
# @brief: Dispatches G1 LRMP/ROS/UDP commands, enforces transition convergence, and executes sequential chain actions.
# @exports: CommandExecutionResult, MotionCommandExecutor

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.commands.control_arbiter import ControlArbiter
from src.commands.g1_udp_motion_bridge import G1UdpMotionBridge, UdpSendResult
from src.commands.motion_action_helpers import dispatch_reserved_slot, parse_velocity_args
from src.config.robot_config_reader import RobotConfigReader
from src.ros_bridge.ros_topic_service_bridge import RosTopicServiceBridge


@dataclass
class CommandExecutionResult:
    """Authentic command dispatch outcome (REAL, RESERVED_SLOT, REJECTED, or UNAVAILABLE)."""

    ok: bool
    command: str
    params: List[str]
    execution_mode: str  # "REAL" | "RESERVED_SLOT" | "REJECTED" | "UNAVAILABLE"
    authority: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


DdsActionHook = Callable[[str, List[str], Dict[str, Any]], Dict[str, Any]]
VelocityHook = Callable[[float, float, float, float], Dict[str, Any]]


class MotionCommandExecutor:
    """Dispatches all known G1 motion/status commands and exposes reserved slots for complex dances."""

    def __init__(
        self, arbiter: ControlArbiter, config_reader: RobotConfigReader, ros_bridge: RosTopicServiceBridge,
        dds_action_hook: Optional[DdsActionHook] = None, velocity_hook: Optional[VelocityHook] = None,
        motion_udp: Optional[G1UdpMotionBridge] = None, transition_timeout_s: float = 6.0,
    ) -> None:
        self.arbiter, self.config_reader, self.ros_bridge = arbiter, config_reader, ros_bridge
        self._dds_hook, self._vel_hook, self.motion_udp = dds_action_hook, velocity_hook, motion_udp
        self._transition_timeout_s = max(0.5, float(transition_timeout_s))
        self._active_motion: Dict[str, Any] = {"state": "PASSIVE", "vx": 0.0, "vy": 0.0, "vyaw": 0.0, "active_dance": ""}

    def _robot_id(self) -> str:
        return str(self.config_reader.read_robot_id().get("robot_id") or "A").strip().upper() or "A"

    def _send_udp(self, cmd_line: str) -> Optional[UdpSendResult]:
        return self.motion_udp.send_command(self._robot_id(), cmd_line) if self.motion_udp is not None else None

    @staticmethod
    def _udp_fail_mode(udp_res: UdpSendResult) -> str:
        return "UNAVAILABLE" if udp_res.error_code in ("ACK_TIMEOUT", "SOCKET_CLOSED", "SEND_FAILED") else "REJECTED"

    def handle_udp_event(self, event: str, payload: Dict[str, Any]) -> None:
        """Synchronize local motion state and arbiter safety lock from G1 UDP replies."""
        if self.motion_udp is not None:
            tr = self.motion_udp.tracker
            self.arbiter.set_safety_lock(tr.is_safety_locked, tr.safety_lock_reason())
        if event == "DANCE_START":
            self._active_motion["active_dance"] = str(payload.get("alias", ""))
            if payload.get("state"):
                self._active_motion["state"] = str(payload["state"])
        elif event == "DANCE_DONE":
            self._active_motion["active_dance"] = ""
            if payload.get("state"):
                self._active_motion["state"] = str(payload["state"])
            elif payload.get("ok"):
                self._active_motion["state"] = "STAND"
            self._active_motion["last_dance_result"] = f"{payload.get('alias', '')}:{payload.get('result', '')}"
        elif event == "STATE":
            if payload.get("state"):
                self._active_motion["state"] = str(payload["state"])
            self._active_motion["active_dance"] = str(payload.get("active_dance", ""))

    def _merged_motion_state(self) -> Dict[str, Any]:
        motion = dict(self._active_motion)
        if self.motion_udp is not None:
            snap = self.motion_udp.tracker.snapshot()
            if snap["remote_state"]:
                motion["state"], motion["active_dance"] = snap["remote_state"], snap["remote_dance"]
            for k in ("nav_input", "nav_status", "nav_reason", "active_faults", "safety_locked", "lock_reason"):
                motion[k] = snap[k]
            motion["last_dance_result"] = snap["last_dance_result"] or motion.get("last_dance_result", "")
        else:
            motion.update({
                "nav_input": "", "nav_status": "", "nav_reason": "", "active_faults": [],
                "safety_locked": self.arbiter.is_safety_locked, "lock_reason": self.arbiter.safety_lock_reason,
            })
        return motion

    def _wait_posture_settled(self, target_posture: str, stop_event: Optional[threading.Event] = None) -> Tuple[bool, str]:
        if self.motion_udp is None or not self.motion_udp.tracker.has_nav_input:
            return True, ""
        if target_posture == "STAND":
            return self.motion_udp.wait_for_state(lambda t: t.mode in ("STAND", "GAIT"), self._transition_timeout_s, stop_event)
        if target_posture == "GAIT":
            return self.motion_udp.wait_for_state(lambda t: t.is_nav_ready(), self._transition_timeout_s, stop_event)
        if target_posture == "PASSIVE":
            return self.motion_udp.wait_for_state(lambda t: t.mode == "PASSIVE", self._transition_timeout_s, stop_event, abort_on_lock=False)
        return True, ""

    def ensure_gait_for_nav(self, stop_event: Optional[threading.Event] = None, allow_stand_from_passive: bool = True) -> Tuple[bool, str]:
        """Ensure G1 receiver is in GAIT/READY mode before ROS navigation sends goal/cmd_vel."""
        if self.motion_udp is None:
            return True, ""
        tr = self.motion_udp.tracker
        if tr.is_safety_locked:
            return False, tr.safety_lock_reason()
        cur_mode = tr.mode or str(self._active_motion.get("state") or "PASSIVE")
        cur_dance = tr.active_dance or str(self._active_motion.get("active_dance") or "")
        if cur_dance or cur_mode in ("DANCE", "DANCING"):
            return False, f"机器人正在执行舞蹈 ({cur_dance or cur_mode})，禁止下发导航"
        if tr.is_nav_ready() or (not tr.mode and self._active_motion.get("state") == "GAIT"):
            return True, ""
        auth = self.arbiter.state.value
        if cur_mode == "PASSIVE":
            if not allow_stand_from_passive:
                return False, "机器人处于 PASSIVE 卸力态，请先执行站立 (STAND)"
            res_st = self._dispatch_posture_or_stop("STAND", [], auth)
            if not res_st.ok:
                return False, res_st.message
            ok_s, err_s = self._wait_posture_settled("STAND", stop_event)
            if not ok_s:
                return False, err_s
        elif cur_mode == "STANDING":
            ok_s, err_s = self._wait_posture_settled("STAND", stop_event)
            if not ok_s:
                return False, err_s
        res_g = self._dispatch_posture_or_stop("GAIT", [], auth)
        return (self._wait_posture_settled("GAIT", stop_event) if res_g.ok else (False, res_g.message))

    def get_state(self) -> Dict[str, Any]:
        return {"authority": self.arbiter.state.value, "motion": self._merged_motion_state()}

    def execute_posture(self, posture: str, wait_ready: bool = False) -> CommandExecutionResult:
        p = (posture or "").strip().upper()
        if p not in ("STAND", "GAIT", "PASSIVE", "RELEASE"):
            return CommandExecutionResult(False, p, [], "REJECTED", self.arbiter.state.value, f"不支持的姿态模式: {posture}")
        res = self.execute(p)
        if res.ok and wait_ready and p in ("STAND", "GAIT", "PASSIVE"):
            ok_w, err_w = self._wait_posture_settled(p)
            if not ok_w:
                return CommandExecutionResult(False, p, [], "UNAVAILABLE" if "超时" in err_w else "REJECTED", res.authority, err_w, {**res.details, "motion": self._merged_motion_state()})
            res.details["motion"] = self._merged_motion_state()
        return res

    def execute_velocity(
        self, direction: str = "", duration: float = 1.0,
        vx: Optional[float] = None, vy: Optional[float] = None, vyaw: Optional[float] = None,
    ) -> CommandExecutionResult:
        if direction:
            return self.execute(direction.strip().upper(), [str(duration)])
        lim = self.config_reader.read_dance_registry()["motion_limits"]
        rx = max(-1.0, min(1.0, (vx or 0.0) / max(0.05, lim["forward_axis"])))
        ry = max(-1.0, min(1.0, (vy or 0.0) / max(0.05, lim["lateral_axis"])))
        rz = max(-1.0, min(1.0, (vyaw or 0.0) / max(0.05, lim["turn_axis"])))
        return self.execute("MOVE", [str(rx), str(ry), str(rz), str(duration)])

    def execute_dance(self, alias: str) -> CommandExecutionResult:
        return self.execute("DANCE", [alias])

    def execute_stop(self, emergency: bool = False) -> CommandExecutionResult:
        return self.execute("EMERGENCY" if emergency else "STOP")

    def execute(self, command: str, params: Optional[List[str]] = None) -> CommandExecutionResult:
        raw_cmd = (command or "").strip()
        args = [str(p).strip() for p in (params or []) if str(p).strip()]
        if "," in raw_cmd and not args:
            parts = [p.strip() for p in raw_cmd.split(",") if p.strip()]
            raw_cmd, args = (parts[0] if parts else ""), parts[1:]
        cmd = raw_cmd.upper()
        decision = self.arbiter.evaluate_and_apply(cmd)
        if not decision.allowed:
            return CommandExecutionResult(False, cmd, args, "REJECTED", decision.authority.value, decision.reason)
        auth = decision.authority.value
        if cmd in ("STAND", "GAIT", "PASSIVE", "STOP", "EMERGENCY"):
            return self._dispatch_posture_or_stop(cmd, args, auth)
        if cmd == "RELEASE":
            self._active_motion = {"state": "STAND", "vx": 0.0, "vy": 0.0, "vyaw": 0.0, "active_dance": ""}
            return CommandExecutionResult(True, cmd, args, "REAL", auth, "已安全释放控制权至 FREE")
        if cmd in ("PREP", "PLAY", "BARRIER"):
            self._active_motion["state"] = "CHOREO"
            return CommandExecutionResult(True, cmd, args, "REAL", auth, f"编舞同步指令 {cmd} 已生效", {"choreo_cmd": cmd, "params": args})
        if cmd in ("FORWARD", "BACK", "BACKWARD", "MOVE_LEFT", "MOVE_RIGHT", "TURN_LEFT", "TURN_RIGHT", "MOVE"):
            return self._execute_velocity_cmd(cmd, args, auth)
        if cmd == "STATUS":
            return self._execute_status(args, auth)
        if cmd == "DISCOVER":
            info = {"robot_id": self.config_reader.read_robot_id(), "network": self.config_reader.read_network_summary(), "motion": self._merged_motion_state()}
            return CommandExecutionResult(True, cmd, args, "REAL", auth, "设备在线发现响应", info)
        if cmd == "GETDANCELIST":
            reg = self.config_reader.read_dance_registry()
            return CommandExecutionResult(reg["available"], cmd, args, "REAL", auth, f"读取动作配置 ({reg['total_count']} 项)" if reg["available"] else reg["reason"], reg)
        if cmd in ("DANCE", "BUTTON", "MASK"):
            return dispatch_reserved_slot(cmd, args, auth, self.config_reader.read_dance_registry(), self._active_motion, self._dds_hook, self.motion_udp, self.ros_bridge, self._send_udp, self._udp_fail_mode, CommandExecutionResult)
        return CommandExecutionResult(False, cmd, args, "REJECTED", auth, f"未实现指令 {cmd}")

    def _execute_velocity_cmd(self, cmd: str, args: List[str], auth: str) -> CommandExecutionResult:
        lim = self.config_reader.read_dance_registry()["motion_limits"]
        try:
            vx, vy, vyaw, dur, udp_line = parse_velocity_args(cmd, args, lim)
        except ValueError as ex:
            return CommandExecutionResult(False, cmd, args, "REJECTED", auth, f"运动参数错误: {ex}")
        vel_state = {"state": "GAIT", "vx": round(vx, 3), "vy": round(vy, 3), "vyaw": round(vyaw, 3), "duration": dur, "active_dance": ""}
        if self._vel_hook:
            self._active_motion = vel_state
            return CommandExecutionResult(True, cmd, args, "REAL", auth, f"已映射速度指令 ({vx:.2f}, {vy:.2f}, {vyaw:.2f}, {dur:.1f}s)", {**vel_state, "ros_cmd_vel": self._vel_hook(vx, vy, vyaw, dur)})
        if self.motion_udp is not None:
            udp_res = self._send_udp(udp_line)
            if udp_res.ok:
                self._active_motion = vel_state
            return CommandExecutionResult(udp_res.ok, cmd, args, "REAL" if udp_res.ok else self._udp_fail_mode(udp_res), auth, f"已下发 UDP 运动指令 {udp_line}" if udp_res.ok else udp_res.message, {**(vel_state if udp_res.ok else self._active_motion), "udp": udp_res.to_dict()})
        self._active_motion = vel_state
        return CommandExecutionResult(True, cmd, args, "REAL", auth, f"已映射速度指令 ({vx:.2f}, {vy:.2f}, {vyaw:.2f}, {dur:.1f}s)", {**vel_state, "ros_cmd_vel": self.ros_bridge.publish_cmd_vel(vx, vy, vyaw, duration_s=dur)})

    def _execute_status(self, args: List[str], auth: str) -> CommandExecutionResult:
        sub = args[0].upper() if args else "ALL"
        details: Dict[str, Any] = {"authority": auth, "motion": self._merged_motion_state()}
        if sub in ("ALL", "ID"):
            details["robot_id"], details["machine_id"] = self.config_reader.read_robot_id(), self.config_reader.read_machine_id_digest()
        if sub in ("ALL", "NET"):
            details["network"] = self.config_reader.read_network_summary()
        if sub in ("ALL", "LICENSE"):
            details["license"] = self.config_reader.read_license_summary()
        if sub in ("ALL", "SHOW"):
            details["ros_telemetry"] = self.ros_bridge.read_telemetry_snapshot().to_dict()
        return CommandExecutionResult(True, "STATUS", args, "REAL", auth, f"已采集真实状态 ({sub})", details)

    def _dispatch_posture_or_stop(self, cmd: str, args: List[str], auth: str) -> CommandExecutionResult:
        if cmd in ("STOP", "EMERGENCY"):
            self._active_motion = {"state": "STOP", "vx": 0.0, "vy": 0.0, "vyaw": 0.0, "active_dance": ""}
            extra: Dict[str, Any] = {"ros_cancel": self.ros_bridge.cancel_planning(), "ros_cmd_vel": self.ros_bridge.stop_cmd_vel()}
            udp_res = self._send_udp("STOP")
            if udp_res is not None:
                extra["udp"] = udp_res.to_dict()
            ok = True if udp_res is None else udp_res.ok
            msg = ("已执行急停 STOP" if cmd == "EMERGENCY" else "已执行软停 STOP") if ok else udp_res.message
            return CommandExecutionResult(ok, cmd, args, "REAL" if ok else self._udp_fail_mode(udp_res), auth, msg, extra)
        udp_res = self._send_udp(cmd)
        if udp_res is not None and not udp_res.ok:
            return CommandExecutionResult(False, cmd, args, self._udp_fail_mode(udp_res), auth, udp_res.message, {"udp": udp_res.to_dict()})
        self._active_motion = {"state": cmd, "vx": 0.0, "vy": 0.0, "vyaw": 0.0, "active_dance": ""}
        extra = dict(self._active_motion)
        if self._dds_hook is not None:
            extra["dds"] = self._dds_hook(cmd, args, {})
        if udp_res is not None:
            extra["udp"] = udp_res.to_dict()
        return CommandExecutionResult(True, cmd, args, "REAL", auth, f"已切换运动状态至 {cmd}", extra)

    def execute_chain_action(self, node: Dict[str, Any], stop_event: threading.Event) -> Tuple[bool, str]:
        """Execute a sequential task-chain action node and await convergence / DANCE_DONE."""
        raw = str(node.get("lrmp_code") or node.get("lrmpCode") or node.get("code_no") or node.get("title") or "").strip().upper()
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        cmd, args = (parts[0], parts[1:]) if parts else (raw, [])
        auth = self.arbiter.state.value
        try:
            dur = float(node.get("duration", node.get("time", 0.0)) or 0.0)
        except (TypeError, ValueError):
            dur = 0.0
        if self.arbiter.is_safety_locked and cmd not in ("STOP", "PASSIVE"):
            return False, f"安全联锁生效，禁止执行 {cmd}: {self.arbiter.safety_lock_reason}"
        if cmd in ("STAND", "GAIT", "PASSIVE", "STOP"):
            res = self._dispatch_posture_or_stop(cmd, args, auth)
            return self._wait_posture_settled(cmd, stop_event) if res.ok else (False, res.message)
        if cmd in ("FORWARD", "BACK", "BACKWARD", "MOVE_LEFT", "MOVE_RIGHT", "TURN_LEFT", "TURN_RIGHT", "MOVE"):
            if cmd != "MOVE" and not args and dur > 0.0:
                args = [str(dur)]
            res = self._execute_velocity_cmd(cmd, args, auth)
            if not res.ok:
                return False, res.message
            deadline = time.monotonic() + min(10.0, max(0.0, float(res.details.get("duration", dur))))
            while time.monotonic() < deadline:
                if stop_event.is_set() or self.arbiter.is_safety_locked:
                    return False, self.arbiter.safety_lock_reason or "任务已中止"
                time.sleep(0.05)
            return True, res.message
        res = dispatch_reserved_slot("DANCE", [cmd], auth, self.config_reader.read_dance_registry(), self._active_motion, self._dds_hook, self.motion_udp, self.ros_bridge, self._send_udp, self._udp_fail_mode, CommandExecutionResult)
        if not res.ok:
            return False, res.message
        if self.motion_udp is not None:
            return self.motion_udp.wait_dance_completion(res.params[0] if res.params else cmd, dur, stop_event)
        return True, res.message
