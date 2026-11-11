import logging
import threading
from typing import Dict, Optional, Tuple
from src.core.config_loader import config_loader
from src.core.event_bus import event_bus
from src.infrastructure.serial.lora_serial_port import lora_port

logger = logging.getLogger("DirectMotionService")


class DirectMotionService:
    """
    Application service managing real-time jog, posture switching, and continuous MOVE.
    Enforces [-1.0, 1.0] velocity bounding and automatic zero-velocity safety reset.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._safety_timers: Dict[str, threading.Timer] = {}
        self._target_delim = config_loader.get_target_delimiter()
        self._param_delim = config_loader.get_param_delimiter()

    def send_basic_command(self, target: str, command_key: str) -> Tuple[bool, str]:
        """Send basic posture or gait command (STAND, GAIT, PASSIVE, STOP, RELEASE)."""
        meta = config_loader.find_command_meta(command_key)
        if not meta:
            return False, f"Unknown command: {command_key}"

        cmd_name = meta.get("cmd", command_key)
        raw_cmd = f"{target}{self._target_delim}{cmd_name}"

        # If sending STOP, immediately cancel active velocity watchdog timers
        if command_key.upper() == "STOP":
            self._cancel_safety_timer(target)

        ok = lora_port.send_raw(raw_cmd, src_id="CTRL", dst_id=target)
        msg = f"Dispatched {cmd_name} to [{target}]" if ok else f"Failed to send {cmd_name}"
        event_bus.publish("MOTION_COMMAND_SENT", {"target": target, "command": cmd_name, "success": ok})
        return ok, msg

    def send_discrete_step(self, target: str, direction: str, duration_s: float = 1.0) -> Tuple[bool, str]:
        """Send directional jog step (e.g. FORWARD, MOVE_LEFT, TURN_RIGHT)."""
        meta = config_loader.find_command_meta(direction)
        if not meta:
            return False, f"Unsupported discrete motion: {direction}"

        cmd_name = meta.get("cmd", direction)
        dur = max(0.1, min(duration_s, 5.0))
        raw_cmd = f"{target}{self._target_delim}{cmd_name}{self._param_delim}{dur:.1f}"

        ok = lora_port.send_raw(raw_cmd, src_id="CTRL", dst_id=target)
        return ok, f"Sent jog step {cmd_name} ({dur}s) to [{target}]"

    def send_continuous_move(
        self,
        target: str,
        forward: float,
        left: float,
        turn: float,
        duration_s: float = 0.5,
    ) -> Tuple[bool, str]:
        """
        Send omnidirectional velocity command: MOVE,forward,left,turn,duration_s.
        Strictly validates [-1.0, 1.0] bounds and arms an automatic zero-reset timer.
        """
        # Validate control limits within [-1.0, 1.0]
        if not (-1.0 <= forward <= 1.0 and -1.0 <= left <= 1.0 and -1.0 <= turn <= 1.0):
            err_msg = f"Velocity bounds exceeded: all values must be in [-1.0, 1.0], got ({forward}, {left}, {turn})"
            logger.warning(err_msg)
            return False, err_msg

        meta = config_loader.find_command_meta("MOVE")
        max_duration = float((meta or {}).get("max_duration_s", 15.0))
        valid_duration = max(0.05, min(duration_s, max_duration))

        cmd_name = (meta or {}).get("cmd", "MOVE")
        payload = (
            f"{cmd_name}{self._param_delim}{forward:.2f}"
            f"{self._param_delim}{left:.2f}"
            f"{self._param_delim}{turn:.2f}"
            f"{self._param_delim}{valid_duration:.2f}"
        )
        raw_cmd = f"{target}{self._target_delim}{payload}"

        ok = lora_port.send_raw(raw_cmd, src_id="CTRL", dst_id=target)
        if not ok:
            return False, f"Failed to transmit MOVE command to [{target}]"

        # Arm safety watchdog timer to automatically reset velocity to zero
        self._arm_zero_reset_watchdog(target, valid_duration)
        return True, f"Dispatched velocity MOVE to [{target}], auto-reset armed in {valid_duration:.2f}s"

    def execute_dance(self, target: str, action_name: str) -> Tuple[bool, str]:
        """Trigger motion clip action for target device."""
        meta = config_loader.find_command_meta("DANCE")
        cmd_name = (meta or {}).get("cmd", "DANCE")
        raw_cmd = f"{target}{self._target_delim}{cmd_name}{self._param_delim}{action_name.strip()}"
        ok = lora_port.send_raw(raw_cmd, src_id="CTRL", dst_id=target)
        return ok, f"Triggered dance action [{action_name}] on [{target}]"

    def _arm_zero_reset_watchdog(self, target: str, duration_s: float) -> None:
        """Arm a countdown timer to send zero-velocity reset after duration_s."""
        with self._lock:
            self._cancel_safety_timer(target)
            timer = threading.Timer(duration_s, self._trigger_zero_reset, args=(target,))
            timer.daemon = True
            self._safety_timers[target] = timer
            timer.start()

    def _cancel_safety_timer(self, target: str) -> None:
        """Cancel existing active watchdog timer for target."""
        if target in self._safety_timers:
            try:
                self._safety_timers[target].cancel()
            except Exception:
                pass
            del self._safety_timers[target]

    def _trigger_zero_reset(self, target: str) -> None:
        """Watchdog callback executing automatic zero-velocity reset."""
        with self._lock:
            self._safety_timers.pop(target, None)

        meta = config_loader.find_command_meta("MOVE")
        cmd_name = (meta or {}).get("cmd", "MOVE")
        zero_payload = f"{cmd_name}{self._param_delim}0.0{self._param_delim}0.0{self._param_delim}0.0{self._param_delim}0.0"
        raw_cmd = f"{target}{self._target_delim}{zero_payload}"
        logger.info(f"Watchdog auto-reset triggered for [{target}]: zero velocity dispatched")
        lora_port.send_raw(raw_cmd, src_id="CTRL", dst_id=target)
        event_bus.publish("MOTION_AUTO_RESET_TRIGGERED", {"target": target})


direct_motion_svc = DirectMotionService()
