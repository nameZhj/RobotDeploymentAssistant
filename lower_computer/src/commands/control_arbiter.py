# @file: src/commands/control_arbiter.py
# @brief: Enforces LRMP V1.0-R3 FREE/MANUAL/CHOREO authority mutual exclusion and timeout safety.
# @exports: ControlAuthority, ArbiterDecision, ControlArbiter

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
import time


class ControlAuthority(str, Enum):
    FREE = "FREE"
    MANUAL = "MANUAL"
    CHOREO = "CHOREO"


@dataclass(frozen=True)
class ArbiterDecision:
    allowed: bool
    authority: ControlAuthority
    reason: str


_MANUAL_CMDS = {
    "STAND", "GAIT", "PASSIVE", "FORWARD", "BACK", "BACKWARD",
    "MOVE_LEFT", "MOVE_RIGHT", "TURN_LEFT", "TURN_RIGHT", "MOVE", "DANCE",
    "BUTTON", "MASK",
}


class ControlArbiter:
    """Thread-safe LRMP V1.0-R3 onboard control authority state machine with hardware fault lockout."""

    def __init__(self, manual_lease_timeout_s: float = 3.0) -> None:
        self._lock = threading.Lock()
        self._state = ControlAuthority.FREE
        self._last_activity_ts = time.monotonic()
        self._lease_timeout_s = max(0.5, manual_lease_timeout_s)
        self._safety_locked = False
        self._safety_reason = ""

    @property
    def is_safety_locked(self) -> bool:
        with self._lock:
            return self._safety_locked

    @property
    def safety_lock_reason(self) -> str:
        with self._lock:
            return self._safety_reason

    def set_safety_lock(self, locked: bool, reason: str = "") -> None:
        with self._lock:
            self._safety_locked = bool(locked)
            self._safety_reason = reason if locked else ""

    @property
    def state(self) -> ControlAuthority:
        with self._lock:
            self._expire_manual_if_needed()
            return self._state

    def _expire_manual_if_needed(self) -> None:
        if self._state == ControlAuthority.MANUAL and (time.monotonic() - self._last_activity_ts) > self._lease_timeout_s:
            self._state = ControlAuthority.FREE

    def evaluate_and_apply(self, command: str) -> ArbiterDecision:
        cmd = (command or "").strip().upper()
        with self._lock:
            self._expire_manual_if_needed()
            if self._safety_locked and cmd not in ("STOP", "EMERGENCY", "PASSIVE", "RELEASE", "STATUS", "GETDANCELIST", "DISCOVER"):
                return ArbiterDecision(False, self._state, f"安全联锁生效，禁止执行 {cmd}: {self._safety_reason}")
            if cmd == "EMERGENCY":
                self._state = ControlAuthority.FREE
                self._last_activity_ts = time.monotonic()
                return ArbiterDecision(True, self._state, "EMERGENCY 急停立即接管并重置控制权为 FREE")

            if cmd == "PREP":
                if self._state == ControlAuthority.MANUAL:
                    return ArbiterDecision(False, self._state, "当前处于 MANUAL 控制态，拒绝抢占 CHOREO（请先 RELEASE）")
                self._state = ControlAuthority.CHOREO
                self._last_activity_ts = time.monotonic()
                return ArbiterDecision(True, self._state, "已申请 CHOREO 编排控制权")

            if cmd in ("PLAY", "BARRIER"):
                if self._state != ControlAuthority.CHOREO:
                    return ArbiterDecision(False, self._state, f"{cmd} 要求先通过 PREP 获取 CHOREO 控制权")
                self._last_activity_ts = time.monotonic()
                return ArbiterDecision(True, self._state, f"CHOREO 态允许执行 {cmd}")

            if cmd == "STOP":
                self._last_activity_ts = time.monotonic()
                if self._state == ControlAuthority.CHOREO:
                    self._state = ControlAuthority.FREE
                    return ArbiterDecision(True, self._state, "已安全中断 CHOREO 编排并释放控制权")
                return ArbiterDecision(True, self._state, f"在 {self._state.value} 态执行软停 STOP")

            if cmd == "RELEASE":
                if self._state == ControlAuthority.CHOREO:
                    return ArbiterDecision(False, self._state, "正在执行 CHOREO 编排，禁止用 RELEASE 强制释放")
                self._state = ControlAuthority.FREE
                self._last_activity_ts = time.monotonic()
                return ArbiterDecision(True, self._state, "已释放 MANUAL 控制权至 FREE")

            if cmd in _MANUAL_CMDS:
                if self._state == ControlAuthority.CHOREO:
                    return ArbiterDecision(False, self._state, f"CHOREO 编排执行中，禁止直接下发人工指令 {cmd}")
                self._state = ControlAuthority.MANUAL
                self._last_activity_ts = time.monotonic()
                return ArbiterDecision(True, self._state, f"MANUAL 态执行 {cmd}")

            if cmd in ("STATUS", "GETDANCELIST", "DISCOVER"):
                return ArbiterDecision(True, self._state, f"只读查询指令 {cmd}")

            return ArbiterDecision(False, self._state, f"未知或未授权指令: {cmd}")

    def release_choreo_on_finish(self) -> None:
        with self._lock:
            if self._state == ControlAuthority.CHOREO:
                self._state = ControlAuthority.FREE
                self._last_activity_ts = time.monotonic()
