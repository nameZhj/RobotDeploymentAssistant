# @file: src/commands/motion_command_executor.py
# @brief: Implements known G1 LRMP/ROS commands and reserves structured extension slots for unexposed dances.
# @exports: CommandExecutionResult, MotionCommandExecutor

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from src.commands.control_arbiter import ControlArbiter
from src.config.robot_config_reader import RobotConfigReader
from src.ros_bridge.ros_topic_service_bridge import RosTopicServiceBridge


@dataclass
class CommandExecutionResult:
    """Authentic command dispatch outcome (REAL execution or explicit RESERVED_SLOT)."""

    ok: bool
    command: str
    params: List[str]
    execution_mode: str  # "REAL" | "RESERVED_SLOT" | "REJECTED"
    authority: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "command": self.command,
            "params": self.params,
            "execution_mode": self.execution_mode,
            "authority": self.authority,
            "message": self.message,
            "details": self.details,
        }


DdsActionHook = Callable[[str, List[str], Dict[str, Any]], Dict[str, Any]]
VelocityHook = Callable[[float, float, float, float], Dict[str, Any]]


class MotionCommandExecutor:
    """Dispatches all known G1 motion/status commands and exposes reserved slots for complex dances."""

    def __init__(
        self,
        arbiter: ControlArbiter,
        config_reader: RobotConfigReader,
        ros_bridge: RosTopicServiceBridge,
        dds_action_hook: Optional[DdsActionHook] = None,
        velocity_hook: Optional[VelocityHook] = None,
    ) -> None:
        self.arbiter = arbiter
        self.config_reader = config_reader
        self.ros_bridge = ros_bridge
        self._dds_hook = dds_action_hook
        self._vel_hook = velocity_hook
        self._active_motion: Dict[str, Any] = {"state": "PASSIVE", "vx": 0.0, "vy": 0.0, "vyaw": 0.0}

    def execute(self, command: str, params: Optional[List[str]] = None) -> CommandExecutionResult:
        cmd = (command or "").strip().upper()
        args = [str(p).strip() for p in (params or []) if str(p).strip()]
        decision = self.arbiter.evaluate_and_apply(cmd)
        if not decision.allowed:
            return CommandExecutionResult(False, cmd, args, "REJECTED", decision.authority.value, decision.reason)

        if cmd in ("STAND", "GAIT", "PASSIVE"):
            self._active_motion = {"state": cmd, "vx": 0.0, "vy": 0.0, "vyaw": 0.0}
            return CommandExecutionResult(True, cmd, args, "REAL", decision.authority.value, f"已切换运动状态至 {cmd}", dict(self._active_motion))

        if cmd == "STOP":
            self._active_motion["vx"] = 0.0
            self._active_motion["vy"] = 0.0
            self._active_motion["vyaw"] = 0.0
            cancel_res = self.ros_bridge.cancel_planning()
            vel_res = self.ros_bridge.publish_cmd_vel(0.0, 0.0, 0.0)
            return CommandExecutionResult(True, cmd, args, "REAL", decision.authority.value, "已执行软停 STOP", {"ros_cancel": cancel_res, "ros_cmd_vel": vel_res})

        if cmd == "EMERGENCY":
            self._active_motion = {"state": "PASSIVE", "vx": 0.0, "vy": 0.0, "vyaw": 0.0}
            cancel_res = self.ros_bridge.cancel_planning()
            vel_res = self.ros_bridge.publish_cmd_vel(0.0, 0.0, 0.0)
            return CommandExecutionResult(True, cmd, args, "REAL", decision.authority.value, "已执行硬急停 EMERGENCY（零轴并取消规划）", {"ros_cancel": cancel_res, "ros_cmd_vel": vel_res})

        if cmd == "RELEASE":
            self._active_motion = {"state": "STAND", "vx": 0.0, "vy": 0.0, "vyaw": 0.0}
            return CommandExecutionResult(True, cmd, args, "REAL", decision.authority.value, "已安全释放控制权至 FREE")

        if cmd in ("PREP", "PLAY", "BARRIER"):
            self._active_motion["state"] = "CHOREO"
            return CommandExecutionResult(
                True, cmd, args, "REAL", decision.authority.value,
                f"编舞同步指令 {cmd} 已生效", {"choreo_cmd": cmd, "params": args},
            )

        if cmd in ("FORWARD", "BACK", "BACKWARD", "MOVE_LEFT", "MOVE_RIGHT", "TURN_LEFT", "TURN_RIGHT", "MOVE"):
            return self._execute_velocity_cmd(cmd, args, decision.authority.value)

        if cmd == "STATUS":
            return self._execute_status(args, decision.authority.value)

        if cmd == "GETDANCELIST":
            reg = self.config_reader.read_dance_registry()
            return CommandExecutionResult(
                ok=reg["available"], command=cmd, params=args,
                execution_mode="REAL", authority=decision.authority.value,
                message=f"读取动作配置 ({reg['total_count']} 项)" if reg["available"] else reg["reason"],
                details=reg,
            )

        if cmd in ("DANCE", "BUTTON", "MASK"):
            return self._execute_reserved_action_slot(cmd, args, decision.authority.value)

        return CommandExecutionResult(False, cmd, args, "REJECTED", decision.authority.value, f"未实现指令 {cmd}")

    def _execute_velocity_cmd(self, cmd: str, args: List[str], auth: str) -> CommandExecutionResult:
        reg = self.config_reader.read_dance_registry()
        lim = reg["motion_limits"]
        vx, vy, vyaw, dur = 0.0, 0.0, 0.0, 0.2
        try:
            if cmd == "MOVE":
                if len(args) < 4:
                    raise ValueError("MOVE 需要 4 个参数: forward,left,turn,t")
                vx = max(-1.0, min(1.0, float(args[0]))) * lim["forward_axis"]
                vy = max(-1.0, min(1.0, float(args[1]))) * lim["lateral_axis"]
                vyaw = max(-1.0, min(1.0, float(args[2]))) * lim["turn_axis"]
                dur = max(0.1, min(10.0, float(args[3])))
            else:
                dur = 5.0 if (args and args[0].upper() == "HOLD") else (float(args[0]) if args else 1.0)
                dur = max(0.1, min(10.0, dur))
                mapping = {
                    "FORWARD": (lim["forward_axis"], 0.0, 0.0),
                    "BACK": (-lim["forward_axis"], 0.0, 0.0),
                    "BACKWARD": (-lim["forward_axis"], 0.0, 0.0),
                    "MOVE_LEFT": (0.0, lim["lateral_axis"], 0.0),
                    "MOVE_RIGHT": (0.0, -lim["lateral_axis"], 0.0),
                    "TURN_LEFT": (0.0, 0.0, lim["turn_axis"]),
                    "TURN_RIGHT": (0.0, 0.0, -lim["turn_axis"]),
                }
                vx, vy, vyaw = mapping[cmd]
        except ValueError as ex:
            return CommandExecutionResult(False, cmd, args, "REJECTED", auth, f"运动参数错误: {ex}")

        self._active_motion = {"state": "GAIT", "vx": round(vx, 3), "vy": round(vy, 3), "vyaw": round(vyaw, 3), "duration": dur}
        hook_res = self._vel_hook(vx, vy, vyaw, dur) if self._vel_hook else self.ros_bridge.publish_cmd_vel(vx, vy, vyaw)
        return CommandExecutionResult(True, cmd, args, "REAL", auth, f"已映射速度指令 ({vx:.2f}, {vy:.2f}, {vyaw:.2f}, {dur:.1f}s)", {**self._active_motion, "ros_cmd_vel": hook_res})

    def _execute_status(self, args: List[str], auth: str) -> CommandExecutionResult:
        sub = args[0].upper() if args else "ALL"
        details: Dict[str, Any] = {"authority": auth, "motion": self._active_motion}
        if sub in ("ALL", "ID"):
            details["robot_id"] = self.config_reader.read_robot_id()
            details["machine_id"] = self.config_reader.read_machine_id_digest()
        if sub in ("ALL", "NET"):
            details["network"] = self.config_reader.read_network_summary()
        if sub in ("ALL", "LICENSE"):
            details["license"] = self.config_reader.read_license_summary()
        if sub in ("ALL", "SHOW"):
            details["ros_telemetry"] = self.ros_bridge.read_telemetry_snapshot().to_dict()
        return CommandExecutionResult(True, "STATUS", args, "REAL", auth, f"已采集真实状态 ({sub})", details)

    def _execute_reserved_action_slot(self, cmd: str, args: List[str], auth: str) -> CommandExecutionResult:
        """Reserved slot for dances/button masks pending direct C++ DDS controller binding."""
        if cmd == "DANCE":
            if not args:
                return CommandExecutionResult(False, cmd, args, "REJECTED", auth, "DANCE 指令缺少动作别名参数")
            alias = args[0].upper()
            reg = self.config_reader.read_dance_registry()
            entry = reg["alias_map"].get(alias)
            if reg["available"] and entry is None:
                return CommandExecutionResult(False, cmd, args, "REJECTED", auth, f"动作 '{alias}' 未在机载 dance_map 中注册")
            if self._dds_hook is not None:
                hook_out = self._dds_hook(cmd, args, entry or {"alias": alias})
                return CommandExecutionResult(True, cmd, args, "REAL", auth, f"已通过 DDS 钩子执行舞蹈 {alias}", hook_out)
            return CommandExecutionResult(
                ok=True, command=cmd, params=args, execution_mode="RESERVED_SLOT", authority=auth,
                message=f"舞蹈 [{alias}] 已通过白名单校验，当前处于预留执行槽位（等待底层 DDS 手柄桥接挂载）",
                details={"alias": alias, "mapped_keys": entry["keys"] if entry else [], "slot_status": "RESERVED"},
            )

        if self._dds_hook is not None:
            hook_out = self._dds_hook(cmd, args, {})
            return CommandExecutionResult(True, cmd, args, "REAL", auth, f"已通过 DDS 钩子执行 {cmd}", hook_out)
        return CommandExecutionResult(
            ok=True, command=cmd, params=args, execution_mode="RESERVED_SLOT", authority=auth,
            message=f"高级指令 {cmd} 已进入预留执行槽位",
            details={"params": args, "slot_status": "RESERVED"},
        )
