# @file: src/commands/motion_action_helpers.py
# @brief: Pure velocity normalization and reserved dance/action dispatch helpers for MotionCommandExecutor.
# @exports: parse_velocity_args, dispatch_reserved_slot

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple


def parse_velocity_args(cmd: str, args: List[str], lim: Dict[str, float]) -> Tuple[float, float, float, float, str]:
    """Parse velocity or directional MOVE arguments into (vx, vy, vyaw, duration, udp_line)."""
    if cmd == "MOVE":
        if len(args) < 4:
            raise ValueError("MOVE 需要 4 个参数: forward,left,turn,t")
        rx, ry, rz = (max(-1.0, min(1.0, float(args[i]))) for i in range(3))
        dur = max(0.1, min(10.0, float(args[3])))
        return rx * lim["forward_axis"], ry * lim["lateral_axis"], rz * lim["turn_axis"], dur, f"MOVE,{rx:.3f},{ry:.3f},{rz:.3f},{dur:.2f}"
    dur = max(0.1, min(10.0, 5.0 if (args and args[0].upper() == "HOLD") else (float(args[0]) if args else 1.0)))
    mapping = {
        "FORWARD": (lim["forward_axis"], 0.0, 0.0), "BACK": (-lim["forward_axis"], 0.0, 0.0),
        "BACKWARD": (-lim["forward_axis"], 0.0, 0.0), "MOVE_LEFT": (0.0, lim["lateral_axis"], 0.0),
        "MOVE_RIGHT": (0.0, -lim["lateral_axis"], 0.0), "TURN_LEFT": (0.0, 0.0, lim["turn_axis"]),
        "TURN_RIGHT": (0.0, 0.0, -lim["turn_axis"]),
    }
    vx, vy, vyaw = mapping[cmd]
    return vx, vy, vyaw, dur, f"{'BACKWARD' if cmd == 'BACK' else cmd},{dur:.2f}"


def dispatch_reserved_slot(
    cmd: str, args: List[str], auth: str, reg: Dict[str, Any], active_motion: Dict[str, Any],
    dds_hook: Optional[Callable[[str, List[str], Dict[str, Any]], Dict[str, Any]]],
    motion_udp: Any, ros_bridge: Any, send_udp: Callable[[str], Any], fail_mode: Callable[[Any], str],
    result_cls: Any,
) -> Any:
    """Resolve dance alias against onboard registry and dispatch to DDS hook, UDP bridge, or reserved slot."""
    if cmd == "DANCE":
        if not args:
            return result_cls(False, cmd, args, "REJECTED", auth, "DANCE 指令缺少动作别名参数")
        req_alias = args[0].strip()
        alias_map = reg["alias_map"]
        entry = alias_map.get(req_alias) or {k.upper(): v for k, v in alias_map.items()}.get(req_alias.upper())
        canonical = entry["alias"] if entry else req_alias.upper()
        if reg["available"] and entry is None:
            return result_cls(False, cmd, args, "REJECTED", auth, f"动作 '{req_alias}' 未在机载 dance_map 中注册")
        if dds_hook is not None:
            active_motion["active_dance"] = canonical
            return result_cls(True, cmd, [canonical], "REAL", auth, f"已通过 DDS 钩子执行舞蹈 {canonical}", dds_hook(cmd, [canonical, *args[1:]], entry or {"alias": canonical}))
        if motion_udp is not None:
            ros_bridge.cancel_planning()
            ros_bridge.stop_cmd_vel()
            udp_res = send_udp(f"DANCE,{canonical}")
            mode = "REAL" if udp_res.ok else fail_mode(udp_res)
            if udp_res.ok:
                active_motion["state"] = "DANCE"
                active_motion["active_dance"] = canonical
            return result_cls(udp_res.ok, cmd, [canonical], mode, auth, f"已通过 UDP 下发舞蹈 {canonical}" if udp_res.ok else udp_res.message, {"alias": canonical, "mapped_keys": entry["keys"] if entry else [], "udp": udp_res.to_dict()})
        active_motion["active_dance"] = canonical
        return result_cls(True, cmd, [canonical], "RESERVED_SLOT", auth, f"舞蹈 [{canonical}] 已通过白名单校验（等待运控挂载）", {"alias": canonical, "mapped_keys": entry["keys"] if entry else [], "slot_status": "RESERVED"})
    if dds_hook is not None:
        return result_cls(True, cmd, args, "REAL", auth, f"已通过 DDS 钩子执行 {cmd}", dds_hook(cmd, args, {}))
    return result_cls(True, cmd, args, "RESERVED_SLOT", auth, f"高级指令 {cmd} 已进入预留执行槽位", {"params": args, "slot_status": "RESERVED"})
