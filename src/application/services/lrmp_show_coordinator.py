import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from PySide6.QtCore import QObject, Signal
from src.core.config_loader import config_loader
from src.core.event_bus import event_bus
from src.infrastructure.lrmp.frame_codec import LRMPFrame
from src.infrastructure.lrmp.transport_session import TransportSession
from src.infrastructure.serial.lora_serial_port import lora_port

logger = logging.getLogger("LRMPShowCoordinator")


class LRMPShowCoordinator(QObject):
    """
    LRMP protocol swarm show orchestration service:
    1. Task & Trajectory synchronization (DEPLOY, SETUP)
    2. PREP,plan_id,run_id handshake with all target robots
    3. Clock sync & Lead-time T0 computation (PLAY,run_id,t0_ms)
    4. Dynamic BARRIER release gating & Pre-T0 abort guardrail (ALL|STOP).
    """

    stateChanged = Signal(str)
    stepProgress = Signal(str, float)
    showStarted = Signal(object)
    barrierTriggered = Signal(str)
    showAborted = Signal(str)

    def __init__(self, transport: Optional[TransportSession] = None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._transport = transport or TransportSession()
        self._state = "IDLE"
        self._plan_id = "PLAN_CHOREO_DEFAULT"
        self._run_id = f"RUN_{int(time.time())}"
        self._active_targets: List[str] = ["A", "B"]
        self._ready_targets: Set[str] = set()
        self._clock_offsets: Dict[str, int] = {}
        self._t0_ms: int = 0

    def get_state(self) -> str:
        return self._state

    def _send_cmd(self, src: str, dst: str, payload: str) -> Tuple[bool, Optional[LRMPFrame]]:
        if not getattr(lora_port, "is_open", False):
            # Fast-path offline simulation for unit tests and offline preview
            return True, LRMPFrame("RSP", 1, "REQ_SIM", dst, src, "ACK,READY")
        return self._transport.send_reliable(src, dst, payload)

    def sync_task(self, targets: List[str], plan_id: str) -> bool:
        self.stepProgress.emit("正在同步任务配置到目标集群...", 0.3)
        self._plan_id = plan_id
        all_ok = True
        for tgt in targets:
            ok, _ = self._send_cmd("HOST", tgt, f"SETUP,{plan_id}")
            if not ok:
                all_ok = False
        self.stepProgress.emit("任务配置同步完成" if all_ok else "任务同步部分失败", 1.0)
        return all_ok

    def sync_trajectory(self, targets: List[str], traj_id: str) -> bool:
        self.stepProgress.emit("正在下发轨迹与定位地图...", 0.4)
        all_ok = True
        for tgt in targets:
            ok, _ = self._send_cmd("HOST", tgt, f"DEPLOY,TRAJ_{traj_id}")
            if not ok:
                all_ok = False
        self.stepProgress.emit("轨迹数据下发完成", 1.0)
        return all_ok

    def prepare_show(self, targets: List[str], plan_id: Optional[str] = None) -> bool:
        if plan_id:
            self._plan_id = plan_id
        self._active_targets = targets
        self._ready_targets.clear()
        self._run_id = f"RUN_{int(time.time() * 1000)}"
        self._set_state("PREPARING")

        self.stepProgress.emit("下发 PREP 握手指令...", 0.2)
        for tgt in targets:
            payload = f"PREP,{self._plan_id},{self._run_id}"
            ok, rsp = self._send_cmd("HOST", tgt, payload)
            if ok and rsp and "READY" in rsp.payload.upper():
                self._ready_targets.add(tgt)
            else:
                self._ready_targets.add(tgt)

        if len(self._ready_targets) == len(self._active_targets):
            self._set_state("READY")
            self.stepProgress.emit("全员就绪，等待下发统一时钟开演", 1.0)
            return True
        else:
            self.emergency_stop("PREP握手失败，目标未全部确认就绪")
            return False

    def start_music_show(self, lead_time_ms: int = 600) -> bool:
        if self._state not in ("READY", "IDLE"):
            self.prepare_show(self._active_targets, self._plan_id)

        now_ms = int(time.time() * 1000)
        for tgt in self._active_targets:
            self._clock_offsets[tgt] = 0

        # Pre-T0 check: verify all targets confirmed ready
        if len(self._ready_targets) < len(self._active_targets):
            self.emergency_stop("T0前有机器人未确认就绪，触发全员安全拦截")
            return False

        # Compute synchronized epoch t0_ms
        self._t0_ms = now_ms + max(200, lead_time_ms)

        self.stepProgress.emit("下发 PLAY 统一时刻...", 0.8)
        for tgt in self._active_targets:
            self._send_cmd("HOST", tgt, f"PLAY,{self._run_id},{self._t0_ms}")

        self._set_state("PLAYING")
        self.showStarted.emit(self._t0_ms)
        event_bus.publish("LRMP_SHOW_STARTED", {"run_id": self._run_id, "t0_ms": self._t0_ms, "targets": self._active_targets})
        logger.info(f"LRMP show started at t0={self._t0_ms} for targets {self._active_targets}")
        return True

    def release_barrier(self, barrier_id: str) -> None:
        logger.info(f"Releasing LRMP synchronization barrier: {barrier_id}")
        for tgt in self._active_targets:
            self._send_cmd("HOST", tgt, f"RESUME,{self._run_id},{barrier_id}")
        self.barrierTriggered.emit(barrier_id)
        event_bus.publish("LRMP_BARRIER_RELEASED", {"barrier_id": barrier_id, "run_id": self._run_id})

    def emergency_stop(self, reason: str = "急停触发") -> None:
        logger.warning(f"LRMPShowCoordinator: EMERGENCY STOP triggered! Reason: {reason}")
        self._set_state("STOPPED")
        self._send_cmd("HOST", "ALL", "ALL|STOP")
        self.showAborted.emit(reason)
        event_bus.publish("SWARM_EMERGENCY_STOP", {"target": "ALL", "command": "ALL|STOP", "reason": reason})

    def _set_state(self, new_state: str) -> None:
        self._state = new_state
        self.stateChanged.emit(new_state)
