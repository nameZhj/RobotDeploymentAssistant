# @file: src/protocol/authority_state_machine.py
# @brief: Enforces LRMP V1.0-R3 FREE/MANUAL/CHOREO mutual exclusion and EMERGENCY preemption per robot.
# @exports: AuthorityTransitionResult, AuthorityStateMachine

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Dict, Iterable

from src.protocol.lrmp_constants import ControlAuthority, MANUAL_MOTION_COMMANDS


@dataclass(frozen=True)
class AuthorityTransitionResult:
    """Result returned by command gate checks."""

    allowed: bool
    authority: ControlAuthority
    reason: str = ""


class AuthorityStateMachine:
    """Tracks per-robot FREE / MANUAL / CHOREO leases preventing cross-mode conflicts."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._states: Dict[str, ControlAuthority] = {}

    def get_state(self, target: str) -> ControlAuthority:
        key = target.strip().upper()
        with self._lock:
            return self._states.get(key, ControlAuthority.FREE)

    def can_execute(self, target: str, command: str) -> AuthorityTransitionResult:
        """Check whether target is permitted to execute command under current lease."""
        key = target.strip().upper()
        cmd = command.strip().upper()
        with self._lock:
            cur = self._states.get(key, ControlAuthority.FREE)
            if cmd == "EMERGENCY":
                return AuthorityTransitionResult(True, cur, "EMERGENCY 最高优先级抢占放行")
            if cmd in ("DISCOVER", "STATUS", "BIND", "SETUP", "DEPLOY"):
                return AuthorityTransitionResult(True, cur, "管理指令允许")
            if cmd == "PREP":
                if cur == ControlAuthority.MANUAL:
                    return AuthorityTransitionResult(
                        False, cur, f"机器人 {key} 当前处于 MANUAL 手动控制态，请先执行 STOP + RELEASE 释放"
                    )
                return AuthorityTransitionResult(True, ControlAuthority.CHOREO, "允许申请 CHOREO 控制权")
            if cmd in ("PLAY", "BARRIER"):
                if cur != ControlAuthority.CHOREO:
                    return AuthorityTransitionResult(
                        False, cur, f"机器人 {key} 未完成 PREP 进入 CHOREO 就绪态（当前: {cur.value}）"
                    )
                return AuthorityTransitionResult(True, cur, "CHOREO 就绪")
            if cmd in MANUAL_MOTION_COMMANDS:
                if cur == ControlAuthority.CHOREO:
                    return AuthorityTransitionResult(
                        False, cur, f"机器人 {key} 正在执行 CHOREO 编排，禁止发送手动 {cmd}"
                    )
                return AuthorityTransitionResult(True, ControlAuthority.MANUAL, "允许获取 MANUAL 控制权")
            if cmd == "RELEASE":
                if cur == ControlAuthority.CHOREO:
                    return AuthorityTransitionResult(
                        False, cur, f"机器人 {key} 处于 CHOREO 态，请使用 STOP 中断编排"
                    )
                return AuthorityTransitionResult(True, ControlAuthority.FREE, "释放 MANUAL 控制权")
            if cmd == "STOP":
                return AuthorityTransitionResult(True, cur, "允许安全停止")
            return AuthorityTransitionResult(True, cur, "放行")

    def apply_command(self, target: str, command: str) -> AuthorityTransitionResult:
        """Validate and transition target's lease state atomically."""
        key = target.strip().upper()
        cmd = command.strip().upper()
        with self._lock:
            check = self.can_execute(key, cmd)
            if not check.allowed:
                return check
            if cmd == "EMERGENCY":
                self._states[key] = ControlAuthority.FREE
            elif cmd == "PREP":
                self._states[key] = ControlAuthority.CHOREO
            elif cmd in MANUAL_MOTION_COMMANDS:
                self._states[key] = ControlAuthority.MANUAL
            elif cmd == "RELEASE":
                self._states[key] = ControlAuthority.FREE
            elif cmd == "STOP" and self._states.get(key) == ControlAuthority.CHOREO:
                self._states[key] = ControlAuthority.FREE
            return AuthorityTransitionResult(True, self._states.get(key, ControlAuthority.FREE), check.reason)

    def acquire_manual(self, target: str) -> AuthorityTransitionResult:
        return self.apply_command(target, "STAND")

    def release_all(self, targets: Iterable[str]) -> None:
        with self._lock:
            for t in targets:
                self._states[t.strip().upper()] = ControlAuthority.FREE
