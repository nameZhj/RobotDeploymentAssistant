import collections
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
from src.core.config_loader import config_loader
from src.core.event_bus import event_bus
from src.infrastructure.lrmp.frame_codec import LRMPFrame, frame_codec
from src.infrastructure.serial.lora_serial_port import lora_port

logger = logging.getLogger("TransportSession")


class TransportSession:
    """
    Manages transport-layer session reliability: ACK tracking, exponential backoff retries,
    anti-replay idempotency window, and strictly logging real device SRC_ID to runtime/logs.
    Handles immediate returns for short commands and two-stage ACCEPTED/EVT tracking for long tasks.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        policy = config_loader.get_transport_policy()
        self._ack_timeout_s = float(policy.get("ack_timeout_ms", 800)) / 1000.0
        self._max_retries = int(policy.get("max_retries", 3))

        self._seen_seq_window = collections.deque(maxlen=1000)
        self._seen_set = set()

        self._pending_acks: Dict[str, threading.Event] = {}
        self._pending_responses: Dict[str, Optional[LRMPFrame]] = {}
        self._async_tasks: Dict[str, Dict[str, Any]] = {}

        paths = config_loader.get_paths()
        logs_dir = Path(paths.get("logs_dir", "runtime/logs"))
        logs_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = logs_dir / "comm_transceiver.log"

    def log_frame(self, direction: str, frame: LRMPFrame) -> None:
        """Mandatory audit logging of raw frames with actual device SRC_ID."""
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_line = (
            f"[{ts}] [{direction.upper()}] TYPE={frame.frame_type} SEQ={frame.seq} "
            f"REQ_ID={frame.request_id} SRC={frame.src_id} DST={frame.dst_id} "
            f"PAYLOAD='{frame.payload}' CRC={frame.checksum}\n"
        )
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(log_line)
        except Exception as e:
            logger.error(f"Failed to append comm log: {e}")

    def send_reliable(self, src_id: str, dst_id: str, payload: str) -> Tuple[bool, Optional[LRMPFrame]]:
        """Send REQ frame and wait for ACK/RSP with retries."""
        frame = frame_codec.build_request(src_id, dst_id, payload)
        wire_str = frame_codec.encode(frame)
        ack_event = threading.Event()

        with self._lock:
            self._pending_acks[frame.request_id] = ack_event
            self._pending_responses[frame.request_id] = None

        success = False
        response_frame: Optional[LRMPFrame] = None

        for attempt in range(1, self._max_retries + 1):
            self.log_frame("TX", frame)
            lora_port.send_raw(wire_str, src_id=src_id, dst_id=dst_id)

            if ack_event.wait(timeout=self._ack_timeout_s):
                success = True
                with self._lock:
                    response_frame = self._pending_responses.get(frame.request_id)
                break
            logger.warning(
                f"Timeout waiting ACK for REQ={frame.request_id} to [{dst_id}], attempt {attempt}/{self._max_retries}"
            )

        with self._lock:
            self._pending_acks.pop(frame.request_id, None)
            self._pending_responses.pop(frame.request_id, None)

        # Handle long task tracking (SETUP / DEPLOY / PREP)
        if success and response_frame:
            self._track_if_long_task(dst_id, payload, response_frame)

        return success, response_frame

    def _track_if_long_task(self, target: str, payload: str, rsp: LRMPFrame) -> None:
        cmd_token = payload.split(",")[0].strip().upper()
        meta = config_loader.find_command_meta(cmd_token) or {}
        if meta.get("is_long_task", False):
            is_accepted = "ACCEPTED" in rsp.payload.upper()
            with self._lock:
                self._async_tasks[rsp.request_id] = {
                    "target": target,
                    "command": cmd_token,
                    "request_id": rsp.request_id,
                    "state": "ACCEPTED" if is_accepted else "REJECTED",
                    "updated_at": time.time(),
                }
            event_bus.publish("ASYNC_TASK_ACCEPTED", self._async_tasks[rsp.request_id])

    def handle_incoming_wire_line(self, line: str) -> Optional[LRMPFrame]:
        """Decode incoming line, filter replays, audit log, and dispatch events."""
        frame = frame_codec.decode(line)
        if not frame:
            return None

        self.log_frame("RX", frame)

        key = (frame.src_id, frame.seq, frame.request_id)
        with self._lock:
            if key in self._seen_set:
                logger.info(f"Ignored duplicate frame: {key}")
                return None
            self._seen_set.add(key)
            self._seen_seq_window.append(key)
            if len(self._seen_seq_window) == self._seen_seq_window.maxlen:
                old = self._seen_seq_window.popleft()
                self._seen_set.discard(old)

        with self._lock:
            if frame.request_id in self._pending_acks:
                self._pending_responses[frame.request_id] = frame
                self._pending_acks[frame.request_id].set()

            # Async EVT / STATUS resolution for long tasks
            if frame.request_id in self._async_tasks or frame.frame_type in ("EVT", "RSP"):
                for req_id, task in list(self._async_tasks.items()):
                    if task["target"] == frame.src_id and ("READY" in frame.payload or "DONE" in frame.payload):
                        task["state"] = "COMPLETED"
                        task["payload"] = frame.payload
                        event_bus.publish("ASYNC_TASK_COMPLETED", task)

        event_bus.publish("LRMP_FRAME_RECEIVED", {
            "type": frame.frame_type,
            "src_id": frame.src_id,
            "dst_id": frame.dst_id,
            "seq": frame.seq,
            "request_id": frame.request_id,
            "payload": frame.payload,
        })
        return frame

    def get_async_task_status(self, request_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._async_tasks.get(request_id)


transport_session = TransportSession()
