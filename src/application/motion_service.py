from typing import Any, List, Optional, Tuple
from src.core.constants import ControlAuthority
from src.core.logger import get_logger
from src.domain.arbitration.control_arbiter import control_arbiter
from src.domain.protocol.frame_builder import frame_builder
from src.infrastructure.serial.lora_serial_port import lora_port

logger = get_logger("MotionService")
LOCAL_SRC_ID = "HOST_CONTROLLER"


class MotionService:
    """
    Coordinates direct motion commands, authority lease acquisition, and serial frame dispatch.
    """

    def send_motion_command(
        self,
        targets: List[str],
        command: str,
        params: Optional[List[Any]] = None,
        auto_acquire_manual: bool = True,
    ) -> Tuple[bool, str]:
        if not lora_port.is_open:
            return False, "Serial port not connected"

        if command == "STOP":
            for tgt in targets:
                control_arbiter.handle_stop(tgt)

        elif auto_acquire_manual:
            for tgt in targets:
                if tgt.upper() != "ALL":
                    ok, msg = control_arbiter.request_authority(tgt, ControlAuthority.MANUAL, LOCAL_SRC_ID)
                    if not ok:
                        return False, f"Failed to acquire authority for {tgt}: {msg}"

        frames = frame_builder.build_expanded_frames(targets, command, params)
        success_count = 0
        for frame in frames:
            parts = frame.split("|", 1)
            dst_id = parts[0] if len(parts) > 1 else "UNKNOWN"
            if lora_port.send_raw_line(frame, src_id=LOCAL_SRC_ID, dst_id=dst_id):
                success_count += 1

        all_ok = success_count == len(frames)
        return all_ok, f"Sent {success_count}/{len(frames)} frames successfully"

    def release_control(self, targets: List[str]) -> Tuple[bool, str]:
        if not lora_port.is_open:
            return False, "Serial port not connected"

        released = 0
        for tgt in targets:
            if tgt.upper() != "ALL":
                ok, _ = control_arbiter.release_manual(tgt)
                if ok:
                    released += 1

        frames = frame_builder.build_expanded_frames(targets, "RELEASE")
        for f in frames:
            lora_port.send_raw_line(f, src_id=LOCAL_SRC_ID, dst_id=f.split("|")[0])

        return True, f"Released manual authority for {released} nodes"


motion_service = MotionService()
