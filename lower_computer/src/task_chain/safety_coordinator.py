# @file: src/task_chain/safety_coordinator.py
# @brief: Coordinates UDP fault/ESTOP circuit breakers, LOC_LOST auto-relocalization, SSE pushes, and Webhook alerts.
# @exports: SafetyCoordinator

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from src.commands.control_arbiter import ControlArbiter
from src.commands.motion_command_executor import MotionCommandExecutor
from src.config.robot_config_reader import RobotConfigReader
from src.ros_bridge.relocalize_helper import RosRelocalizer
from src.ros_bridge.ros_live_slam_tap import RosLiveSlamTap
from src.ros_bridge.ros_topic_service_bridge import RosTopicServiceBridge
from src.task_chain.webhook_dispatcher import WebhookDispatcher

if TYPE_CHECKING:
    from src.task_chain.task_chain_executor import TaskChainExecutor

_LOCKING_MODES = frozenset({"ESTOP", "FAULT", "MANUAL_OVERRIDE"})
_BLOCKING_LEVELS = frozenset({"ERROR", "FATAL"})


class SafetyCoordinator:
    """Bridges G1 UDP async events into safety locks, ROS cancellation, chain abort, auto-relocalize, and SSE/webhooks."""

    def __init__(
        self,
        motion_exec: MotionCommandExecutor,
        arbiter: ControlArbiter,
        ros_bridge: RosTopicServiceBridge,
        slam_tap: RosLiveSlamTap,
        relocalizer: RosRelocalizer,
        webhook: WebhookDispatcher,
        config_reader: RobotConfigReader,
        task_chain: Optional[TaskChainExecutor] = None,
    ) -> None:
        self.motion_exec = motion_exec
        self.arbiter = arbiter
        self.ros_bridge = ros_bridge
        self.slam_tap = slam_tap
        self.relocalizer = relocalizer
        self.webhook = webhook
        self.config_reader = config_reader
        self.task_chain = task_chain
        self._lock = threading.Lock()
        self._reloc_exec_lock = threading.Lock()
        self._callback_url: str = ""
        self._reloc_status: Dict[str, Any] = {"status": "IDLE", "strategy": "", "message": "", "confidence": None}
        self._last_auto_reloc_ts: float = 0.0
        self._reloc_running: bool = False
        self._was_safety_locked: bool = False

    def set_task_chain(self, task_chain: TaskChainExecutor) -> None:
        self.task_chain = task_chain

    def set_callback_url(self, url: str) -> None:
        clean = (url or "").strip()
        if clean:
            with self._lock:
                self._callback_url = clean

    def get_relocalize_status(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._reloc_status)

    def build_robot_state(self) -> Dict[str, Any]:
        rid = str(self.config_reader.read_robot_id().get("robot_id") or "A").strip().upper()
        st = self.motion_exec.get_state()
        motion = st["motion"]
        return {
            "target_id": rid,
            "authority": st["authority"],
            "motion_state": motion.get("state", ""),
            "active_dance": motion.get("active_dance", ""),
            "nav_input": motion.get("nav_input", ""),
            "nav_status": motion.get("nav_status", ""),
            "nav_reason": motion.get("nav_reason", ""),
            "active_faults": motion.get("active_faults", []),
            "safety_locked": bool(motion.get("safety_locked", False)),
            "lock_reason": motion.get("lock_reason", ""),
            "relocalize_status": self.get_relocalize_status(),
        }

    def _emit_webhook(self, event: str, payload: Dict[str, Any]) -> None:
        with self._lock:
            cb = self._callback_url
        if cb:
            self.webhook.emit(cb, event, payload)

    def _sync_sse_robot_state(self) -> Dict[str, Any]:
        rs = self.build_robot_state()
        self.slam_tap.set_robot_state(rs)
        return rs

    def trigger_relocalize(
        self,
        mode: str = "auto",
        pose: Optional[Tuple[float, float, float]] = None,
        fallback_pose: Optional[Tuple[float, float, float]] = None,
        min_confidence: float = 0.65,
        timeout_s: float = 6.0,
        allow_restart: bool = True,
        emit_webhook: bool = False,
    ) -> Dict[str, Any]:
        with self._reloc_exec_lock:
            with self._lock:
                self._reloc_running = True
                self._reloc_status = {"status": "RUNNING", "strategy": mode, "message": "正在执行重定位...", "confidence": None}
            rs = self._sync_sse_robot_state()
            if emit_webhook:
                self._emit_webhook("RELOCALIZE_STARTED", {"target_id": rs["target_id"], "mode": mode, "robot_state": rs})
            try:
                res = self.relocalizer.relocalize(
                    mode=mode, pose=pose, fallback_pose=fallback_pose,
                    min_confidence=min_confidence, timeout_s=timeout_s, allow_restart=allow_restart,
                )
                status = "SUCCEEDED" if res.get("ok") else "FAILED"
                with self._lock:
                    self._reloc_status = {
                        "status": status,
                        "strategy": res.get("strategy_used", ""),
                        "message": res.get("message", ""),
                        "confidence": res.get("confidence"),
                        "needs_manual": bool(res.get("needs_manual", False)),
                    }
                rs2 = self._sync_sse_robot_state()
                if emit_webhook:
                    self._emit_webhook(f"RELOCALIZE_{status}", {"target_id": rs2["target_id"], **res, "robot_state": rs2})
                return res
            finally:
                with self._lock:
                    self._reloc_running = False

    def _maybe_start_auto_reloc(self) -> None:
        now = time.monotonic()
        with self._lock:
            if self._reloc_running or (now - self._last_auto_reloc_ts) < 15.0:
                return
            self._last_auto_reloc_ts = now
        if self.arbiter.is_safety_locked or not self.ros_bridge.is_ros_master_reachable():
            return
        threading.Thread(
            target=self.trigger_relocalize,
            kwargs={"mode": "auto", "allow_restart": False, "emit_webhook": True},
            daemon=True,
            name="AutoRelocalize",
        ).start()

    def on_udp_event(self, event: str, payload: Dict[str, Any]) -> None:
        """Handle asynchronous G1 UDP events off the RX thread without blocking UDP ACK/PONG."""
        with self._lock:
            was_locked = self._was_safety_locked
        self.motion_exec.handle_udp_event(event, payload)
        now_locked = self.arbiter.is_safety_locked
        is_blocking_fault = event == "FAULT" and payload.get("level") in _BLOCKING_LEVELS
        is_locking_state = event == "STATE" and payload.get("state") in _LOCKING_MODES
        active_chain = self.task_chain is not None and self.task_chain.state.status in ("PREPARING", "READY", "RUNNING", "WAITING_BARRIER")
        if (is_blocking_fault or is_locking_state) and (not was_locked or active_chain):
            reason = payload.get("lock_reason") or payload.get("code") or payload.get("state") or "FAULT"
            self.ros_bridge.cancel_planning()
            self.ros_bridge.stop_cmd_vel()
            if self.task_chain is not None:
                self.task_chain.abort_running_chain(reason=f"安全熔断: {reason}")
        elif event == "NAV_STATUS" and payload.get("status") == "FAILED" and payload.get("reason") == "LOC_LOST":
            self.ros_bridge.cancel_planning()
            self.ros_bridge.stop_cmd_vel()
            self._maybe_start_auto_reloc()
        with self._lock:
            self._was_safety_locked = now_locked

        rs = self._sync_sse_robot_state()
        tgt = rs["target_id"]
        if event == "FAULT":
            wh = "ROBOT_FAULT_CLEARED" if payload.get("cleared") else "ROBOT_FAULT"
            self._emit_webhook(wh, {"target_id": tgt, **payload, "robot_state": rs})
        elif event == "STATE":
            self._emit_webhook("ROBOT_STATE_CHANGED", {"target_id": tgt, **payload, "robot_state": rs})
        elif event == "NAV_STATUS":
            self._emit_webhook("NAV_STATUS_CHANGED", {"target_id": tgt, **payload, "robot_state": rs})
        elif event == "DANCE_START":
            self._emit_webhook("DANCE_STARTED", {"target_id": tgt, **payload, "robot_state": rs})
        elif event == "DANCE_DONE":
            self._emit_webhook("DANCE_COMPLETED", {"target_id": tgt, **payload, "robot_state": rs})
