# @file: src/ui/mapping/nav_relocalize_helper.py
# @brief: Helper utilities for relocalization seed lookup and compact G1 robot_state telemetry/alert formatting.
# @exports: extract_track_fallback_pose, format_robot_state_tags, evaluate_nav_alert, format_nav_telemetry_line

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Tuple


def extract_track_fallback_pose(tracks: Iterable[Any], robot_ip: str) -> Optional[Dict[str, float]]:
    """Return initial pose dict of the track matching robot_ip for relocalization prior fallback."""
    ip = (robot_ip or "").strip()
    for tr in tracks:
        if (getattr(tr, "robot_ip", "") or "").strip() == ip:
            return {"x": float(tr.init_x), "y": float(tr.init_y), "yaw": float(tr.init_yaw)}
    return None


def format_robot_state_tags(robot_state: Dict[str, Any]) -> str:
    """Format compact mode, nav_input, active_dance, fault codes, and relocalize status for telemetry label."""
    if not isinstance(robot_state, dict) or not robot_state:
        return ""
    parts: List[str] = []
    mode = str(robot_state.get("motion_state") or "")
    nav_in = str(robot_state.get("nav_input") or "")
    if mode:
        parts.append(f"运控:{mode}" + (f"({nav_in})" if nav_in else ""))
    dance = str(robot_state.get("active_dance") or "")
    if dance:
        parts.append(f"舞蹈:{dance}")
    nav_st = str(robot_state.get("nav_status") or "")
    nav_rsn = str(robot_state.get("nav_reason") or "")
    if nav_st:
        parts.append(f"导航:{nav_st}" + (f"/{nav_rsn}" if nav_rsn else ""))
    reloc = robot_state.get("relocalize_status") if isinstance(robot_state.get("relocalize_status"), dict) else {}
    if reloc.get("status") in ("RUNNING", "FAILED"):
        parts.append(f"重定位:{reloc['status']}")
    faults = robot_state.get("active_faults") or []
    if faults:
        codes = ",".join(f"{f.get('level', '')}:{f.get('code', '')}" for f in faults if isinstance(f, dict))
        if codes:
            parts.append(f"故障:{codes}")
    return " | ".join(parts)


def evaluate_nav_alert(robot_state: Dict[str, Any]) -> Tuple[str, str, bool, str]:
    """Return (tone, badge_text, clear_goal, alert_message) for live navigation UI guards."""
    if not isinstance(robot_state, dict) or not robot_state:
        return "", "", False, ""
    if robot_state.get("safety_locked"):
        reason = str(robot_state.get("lock_reason") or robot_state.get("motion_state") or "ESTOP")
        return "danger", f"安全锁: {robot_state.get('motion_state') or 'FAULT'}", True, f"机器人触发安全联锁: {reason}"
    nav_st = str(robot_state.get("nav_status") or "")
    nav_rsn = str(robot_state.get("nav_reason") or "")
    if nav_st == "FAILED":
        if nav_rsn == "LOC_LOST":
            return "danger", "定位丢失", True, "定位丢失 (LOC_LOST)，下位机已触发自动重定位或请点击重定位"
        return "danger", f"导航失败:{nav_rsn or 'ERR'}", True, f"G1 导航失败: {nav_rsn or 'FAILED'}"
    reloc = robot_state.get("relocalize_status") if isinstance(robot_state.get("relocalize_status"), dict) else {}
    if reloc.get("status") == "FAILED" and reloc.get("needs_manual"):
        return "warn", "需手动重定位", True, "自动重定位未收敛，请在 2D 地图点击「设初始位姿」拖拽重定位"
    faults = [f for f in (robot_state.get("active_faults") or []) if isinstance(f, dict)]
    if faults:
        codes = ",".join(str(f.get("code", "")) for f in faults)
        return "warn", f"告警:{codes}", False, f"机器人告警: {codes}"
    return "", "", False, ""


def format_nav_telemetry_line(
    state: Dict[str, Any], pose_tuple: Optional[Tuple[float, float, float]], rs: Dict[str, Any],
) -> str:
    """Format telemetry summary label text for NavigationMapPage."""
    conf = state.get("localization_confidence")
    delay = state.get("localization_delay_ms")
    nav_st = state.get("local_nav_status") or "-"
    pts = int(state.get("point_count", 0) or 0)
    pose_s = f"({pose_tuple[0]:.2f},{pose_tuple[1]:.2f},{math.degrees(pose_tuple[2]):.0f}°)" if pose_tuple else "(--)"
    conf_s = f"{conf:.2f}" if isinstance(conf, (int, float)) else "-"
    delay_s = f"{delay:.1f}ms" if isinstance(delay, (int, float)) else "-"
    rs_s = format_robot_state_tags(rs)
    return f"位姿:{pose_s} | 置信度:{conf_s} | 延迟:{delay_s} | 状态:{nav_st} | 点云:{pts:,}" + (f" | {rs_s}" if rs_s else "")
