# @file: src/commands/g1_udp_protocol.py
# @brief: Wire packet builder, 8-type G1 UDP reply parser, and thread-safe G1 robot state/fault/nav tracker.
# @exports: FaultRecord, ParsedUdpReply, G1RobotStateTracker, build_motion_udp_packet, parse_udp_reply_line

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
import threading
import time
from typing import Any, Dict, List, Optional

_TARGET_RE = re.compile(r"[A-Z0-9_-]+(?:,[A-Z0-9_-]+)*")
_LOCKING_MODES = frozenset({"ESTOP", "FAULT", "MANUAL_OVERRIDE"})
_BLOCKING_LEVELS = frozenset({"ERROR", "FATAL"})


def build_motion_udp_packet(target: str, command: str) -> bytes:
    """Pack TARGET|COMMAND\\n matching the exact G1 motion receiver constraints."""
    tgt = (target or "").strip().upper()
    cmd = (command or "").strip().upper()
    if not _TARGET_RE.fullmatch(tgt):
        raise ValueError("Target must be A, A,B or ALL")
    if not cmd or any(ord(ch) < 32 or ord(ch) > 126 or ch == "|" for ch in cmd):
        raise ValueError("Command must be one printable ASCII line without |")
    if cmd.split(",", 1)[0] == "GETDANCELIST":
        raise ValueError("GETDANCELIST radio replies are not supported by UDP motion bridge")
    pkt = f"{tgt}|{cmd}\n".encode("ascii")
    if len(pkt) > 192:
        raise ValueError("Packet exceeds 192 bytes including newline")
    return pkt


@dataclass(frozen=True)
class FaultRecord:
    """Active G1 onboard fault entry reported by TARGET|FAULT."""

    level: str
    code: str
    detail: str = ""
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ParsedUdpReply:
    """Normalized representation of any single line received from the G1 UDP receiver."""

    target: str
    kind: str
    raw_payload: str
    command: str = ""
    detail: str = ""
    reason: str = ""
    mode: str = ""
    active_dance: str = ""
    nav_input: str = ""
    has_nav_input: bool = False
    alias: str = ""
    result: str = ""
    nav_status: str = ""
    level: str = ""
    code: str = ""


def parse_udp_reply_line(line: str) -> Optional[ParsedUdpReply]:
    """Parse TARGET|PAYLOAD reply frames including 3-field STATE, DANCE_*, NAV_STATUS, and FAULT."""
    clean = (line or "").strip()
    if "|" not in clean:
        return None
    tgt, payload = [p.strip().upper() for p in clean.split("|", 1)]
    if not tgt or not payload:
        return None
    if payload == "PONG":
        return ParsedUdpReply(target=tgt, kind="PONG", raw_payload=payload)
    parts = [p.strip() for p in payload.split(",")]
    head = parts[0]
    if head == "ACK" and len(parts) >= 2:
        return ParsedUdpReply(
            target=tgt, kind="ACK", raw_payload=payload,
            command=parts[1], detail=",".join(parts[2:]) if len(parts) > 2 else "",
        )
    if head == "ERR" and len(parts) >= 2:
        return ParsedUdpReply(
            target=tgt, kind="ERR", raw_payload=payload,
            command=parts[1], reason=",".join(parts[2:]) if len(parts) > 2 else payload,
        )
    if head == "STATE" and len(parts) >= 2:
        dance = parts[2] if len(parts) > 2 else ""
        nav_in = parts[3] if len(parts) > 3 else ""
        return ParsedUdpReply(
            target=tgt, kind="STATE", raw_payload=payload,
            mode=parts[1], active_dance="" if dance in ("", "NONE") else dance,
            nav_input=nav_in, has_nav_input=bool(nav_in),
        )
    if head == "DANCE_START" and len(parts) >= 2:
        return ParsedUdpReply(target=tgt, kind="DANCE_START", raw_payload=payload, alias=parts[1])
    if head == "DANCE_DONE" and len(parts) >= 2:
        res = parts[2] if len(parts) > 2 else "OK"
        rsn = ",".join(parts[3:]) if len(parts) > 3 else ""
        return ParsedUdpReply(target=tgt, kind="DANCE_DONE", raw_payload=payload, alias=parts[1], result=res, reason=rsn)
    if head == "NAV_STATUS" and len(parts) >= 2:
        rsn = ",".join(parts[2:]) if len(parts) > 2 else ""
        return ParsedUdpReply(target=tgt, kind="NAV_STATUS", raw_payload=payload, nav_status=parts[1], reason=rsn)
    if head == "FAULT" and len(parts) >= 3:
        raw_lvl = parts[1]
        if raw_lvl == "CLEAR":
            # Support both live `FAULT,CLEAR,CLEAR,<CODE>` and compact `FAULT,CLEAR,<CODE>`
            if len(parts) >= 4 and parts[2] == "CLEAR":
                code, detail = parts[3], ",".join(parts[4:]) if len(parts) > 4 else ""
            else:
                code, detail = parts[2], ",".join(parts[3:]) if len(parts) > 3 else ""
            return ParsedUdpReply(target=tgt, kind="FAULT", raw_payload=payload, level="CLEAR", code=code, detail=detail)
        detail = ",".join(parts[3:]) if len(parts) > 3 else ""
        return ParsedUdpReply(target=tgt, kind="FAULT", raw_payload=payload, level=raw_lvl, code=parts[2], detail=detail)
    return None


class G1RobotStateTracker:
    """Thread-safe onboard mirror of G1 mode, active dance, nav input/status, and active faults."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.mode: str = ""
        self.active_dance: str = ""
        self.nav_input: str = ""
        self.has_nav_input: bool = False
        self.nav_status: str = ""
        self.nav_reason: str = ""
        self.nav_seq: int = 0
        self.state_seq: int = 0
        self.active_faults: Dict[str, FaultRecord] = {}
        self.last_dance_result: str = ""
        self.last_ack: str = ""
        self.last_error: str = ""
        self.reachable: Optional[bool] = None
        self.last_pong_target: str = ""
        self.last_rx_ts: float = 0.0

    def _compute_lock_unlocked(self) -> tuple[bool, str]:
        blocking = [f for f in self.active_faults.values() if f.level in _BLOCKING_LEVELS]
        reasons: List[str] = []
        if self.mode in _LOCKING_MODES:
            reasons.append(f"G1 处于 {self.mode} 模式")
        if blocking:
            codes = ",".join(f"{f.level}:{f.code}" for f in blocking)
            reasons.append(f"阻断故障 {codes}")
        return bool(reasons), "；".join(reasons)

    @property
    def is_safety_locked(self) -> bool:
        with self._lock:
            locked, _ = self._compute_lock_unlocked()
            return locked

    def safety_lock_reason(self) -> str:
        with self._lock:
            _, reason = self._compute_lock_unlocked()
            return reason

    def is_nav_ready(self) -> bool:
        with self._lock:
            locked, _ = self._compute_lock_unlocked()
            if locked or self.mode != "GAIT":
                return False
            return (not self.has_nav_input) or (self.nav_input in ("READY", "ACTIVE"))

    def set_error(self, msg: str) -> None:
        with self._lock:
            self.last_error = msg

    def get_error(self) -> str:
        with self._lock:
            return self.last_error

    def set_reachable(self, val: bool) -> None:
        with self._lock:
            self.reachable = val

    def clear_pong_target(self) -> None:
        with self._lock:
            self.last_pong_target = ""

    def get_pong_target(self) -> str:
        with self._lock:
            return self.last_pong_target

    def get_seqs(self) -> tuple[int, int]:
        with self._lock:
            return self.state_seq, self.nav_seq

    def get_nav_state(self) -> tuple[int, str, str]:
        with self._lock:
            return self.nav_seq, self.nav_status, self.nav_reason

    def get_mode_summary(self) -> tuple[str, str]:
        with self._lock:
            return self.mode, self.nav_input

    def apply(self, rep: ParsedUdpReply) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Update tracker state from a parsed UDP frame and return optional event payload for listeners."""
        now = time.time()
        with self._lock:
            self.last_rx_ts = now
            if rep.kind == "PONG":
                self.last_pong_target, self.reachable = rep.target, True
                return None, None
            if rep.kind == "ACK":
                self.last_ack = rep.raw_payload
                return None, None
            if rep.kind == "ERR":
                self.last_error = f"{rep.command}: {rep.reason}" if rep.command else rep.raw_payload
                return "ERR", {"command": rep.command, "reason": rep.reason}
            if rep.kind == "STATE":
                self.mode = rep.mode
                self.active_dance = rep.active_dance
                if rep.has_nav_input:
                    self.nav_input = rep.nav_input
                    self.has_nav_input = True
                self.state_seq += 1
                locked, lock_reason = self._compute_lock_unlocked()
                return "STATE", {
                    "state": self.mode, "active_dance": self.active_dance,
                    "nav_input": self.nav_input, "safety_locked": locked, "lock_reason": lock_reason,
                }
            if rep.kind == "DANCE_START":
                self.active_dance = rep.alias
                if self.mode not in _LOCKING_MODES:
                    self.mode = "DANCING"
                self.state_seq += 1
                return "DANCE_START", {"alias": rep.alias, "state": self.mode}
            if rep.kind == "DANCE_DONE":
                self.active_dance = ""
                self.last_dance_result = f"{rep.alias}:{rep.result}" + (f":{rep.reason}" if rep.reason else "")
                if rep.result == "OK" and self.mode in ("DANCE", "DANCING"):
                    self.mode = "STAND"
                self.state_seq += 1
                ok = rep.result == "OK"
                return "DANCE_DONE", {
                    "alias": rep.alias, "result": rep.result, "reason": rep.reason,
                    "ok": ok, "state": self.mode,
                }
            if rep.kind == "NAV_STATUS":
                self.nav_status = rep.nav_status
                self.nav_reason = rep.reason
                self.nav_seq += 1
                return "NAV_STATUS", {"status": rep.nav_status, "reason": rep.reason, "nav_seq": self.nav_seq}
            if rep.kind == "FAULT":
                if rep.level == "CLEAR":
                    if rep.code in ("", "ALL"):
                        self.active_faults.clear()
                    else:
                        self.active_faults.pop(rep.code, None)
                else:
                    self.active_faults[rep.code] = FaultRecord(rep.level, rep.code, rep.detail, now)
                locked, lock_reason = self._compute_lock_unlocked()
                return "FAULT", {
                    "level": rep.level, "code": rep.code, "detail": rep.detail,
                    "cleared": rep.level == "CLEAR", "safety_locked": locked, "lock_reason": lock_reason,
                    "active_faults": [f.to_dict() for f in self.active_faults.values()],
                }
        return None, None

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            locked, lock_reason = self._compute_lock_unlocked()
            return {
                "reachable": self.reachable,
                "last_ack": self.last_ack,
                "last_error": self.last_error,
                "remote_state": self.mode,
                "remote_dance": self.active_dance,
                "nav_input": self.nav_input,
                "has_nav_input": self.has_nav_input,
                "nav_status": self.nav_status,
                "nav_reason": self.nav_reason,
                "nav_seq": self.nav_seq,
                "state_seq": self.state_seq,
                "active_faults": [f.to_dict() for f in self.active_faults.values()],
                "safety_locked": locked,
                "lock_reason": lock_reason,
                "last_dance_result": self.last_dance_result,
            }
