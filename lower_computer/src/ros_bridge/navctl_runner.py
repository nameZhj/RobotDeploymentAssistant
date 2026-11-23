# @file: src/ros_bridge/navctl_runner.py
# @brief: Executes real /opt/vsis_nav/navctl commands and parses authentic process output.
# @exports: NavctlResult, NavctlRunner

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any, Callable, Dict, List, Optional

from src.config.ros_env_config import NAVCTL_ACTIONS, NAVCTL_BIN


@dataclass(frozen=True)
class NavctlResult:
    """Authentic execution outcome from /opt/vsis_nav/navctl."""

    ok: bool
    available: bool
    action: str
    command: str
    returncode: int
    stdout: str
    stderr: str
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "available": self.available,
            "action": self.action,
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "reason": self.reason,
        }


CmdRunner = Callable[[List[str], float], subprocess.CompletedProcess]


def _default_cmd_runner(argv: List[str], timeout_s: float) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s, check=False)


class NavctlRunner:
    """Runs authentic G1 navigation manager commands defined in 下位机ros信息."""

    def __init__(
        self,
        navctl_bin: str = NAVCTL_BIN,
        use_sudo: bool = True,
        cmd_runner: Optional[CmdRunner] = None,
        exists_checker: Optional[Callable[[str], bool]] = None,
    ) -> None:
        self.navctl_bin = navctl_bin
        self.use_sudo = use_sudo
        self._run = cmd_runner or _default_cmd_runner
        self._exists = exists_checker or (lambda p: Path(p).exists())

    def is_available(self) -> bool:
        return bool(self._exists(self.navctl_bin))

    def execute(self, action: str, timeout_s: float = 20.0) -> NavctlResult:
        norm = " ".join((action or "").strip().lower().split())
        if norm not in NAVCTL_ACTIONS:
            return NavctlResult(
                ok=False, available=self.is_available(), action=norm, command="",
                returncode=-1, stdout="", stderr="",
                reason=f"不支持的 navctl 指令: '{action}'，允许集合: {', '.join(NAVCTL_ACTIONS)}",
            )

        argv: List[str] = ["sudo", "-n", self.navctl_bin, *norm.split()] if self.use_sudo else [self.navctl_bin, *norm.split()]
        cmd_str = " ".join(argv)
        if not self.is_available():
            return NavctlResult(
                ok=False, available=False, action=norm, command=cmd_str,
                returncode=127, stdout="", stderr="",
                reason=f"未检测到 {self.navctl_bin}（当前主机未部署 G1 导航容器管理程序）",
            )
        try:
            proc = self._run(argv, timeout_s)
            return NavctlResult(
                ok=proc.returncode == 0,
                available=True,
                action=norm,
                command=cmd_str,
                returncode=proc.returncode,
                stdout=(proc.stdout or "").strip(),
                stderr=(proc.stderr or "").strip(),
                reason="" if proc.returncode == 0 else f"navctl 退出码 {proc.returncode}",
            )
        except Exception as ex:
            return NavctlResult(
                ok=False, available=True, action=norm, command=cmd_str,
                returncode=-1, stdout="", stderr=str(ex), reason=f"执行异常: {ex}",
            )
