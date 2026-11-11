import threading
import time
from typing import Callable, List, Optional
import serial
import serial.tools.list_ports

from src.core.config_loader import config_loader
from src.core.logger import comm_logger, get_logger

logger = get_logger("LoraSerialPort")


class LoraSerialPort:
    """
    Low-level serial communication driver for the hardware wireless transceiver.
    Strictly records frame transmissions via comm_logger with SRC_ID.
    """

    def __init__(self) -> None:
        self._serial: Optional[serial.Serial] = None
        self._lock = threading.Lock()
        self._rx_thread: Optional[threading.Thread] = None
        self._running = False
        self._rx_callback: Optional[Callable[[str], None]] = None

        policy = config_loader.get_transport_policy()
        self._ack_timeout_s = policy.get("ack_timeout_ms", 800) / 1000.0

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    @property
    def port_name(self) -> str:
        return self._serial.port if self.is_open else ""

    def list_available_ports(self) -> List[str]:
        ports = serial.tools.list_ports.comports()
        return [p.device for p in ports]

    def open(self, port: str, baudrate: int = 9600) -> bool:
        with self._lock:
            if self.is_open:
                self.close()
            try:
                self._serial = serial.Serial(
                    port=port,
                    baudrate=baudrate,
                    timeout=0.1,
                    write_timeout=0.5,
                )
                self._running = True
                self._rx_thread = threading.Thread(target=self._read_loop, daemon=True)
                self._rx_thread.start()
                logger.info(f"Serial port {port} opened at {baudrate} baud.")
                return True
            except Exception as e:
                logger.error(f"Failed to open port {port}: {e}")
                self._serial = None
                return False

    def close(self) -> None:
        with self._lock:
            self._running = False
            if self._serial:
                try:
                    self._serial.close()
                except Exception as e:
                    logger.warning(f"Error closing serial: {e}")
                self._serial = None
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=0.5)

    def set_rx_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        self._rx_callback = callback

    def send_raw(self, data: bytes | str, src_id: str = "CTRL", dst_id: str = "ALL") -> bool:
        """Convenience method sending raw payload while recording audit log."""
        line = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)
        return self.send_raw_line(line, src_id, dst_id)

    def send_raw_line(self, line: str, src_id: str, dst_id: str) -> bool:
        with self._lock:
            if not self.is_open:
                logger.warning("Attempted to send frame while serial port is closed.")
                return False
            try:
                data = line.encode("ascii", errors="replace")
                if not data.endswith(b"\n"):
                    data += b"\n"
                self._serial.write(data)
                self._serial.flush()
                comm_logger.log_frame(
                    src_id=src_id,
                    dst_id=dst_id,
                    frame_type="RAW",
                    payload=line.strip(),
                    status="SENT",
                )
                return True
            except Exception as e:
                logger.error(f"Failed to write serial line: {e}")
                return False

    def _read_loop(self) -> None:
        buffer = bytearray()
        while self._running:
            try:
                if not self.is_open:
                    break
                data = self._serial.read(64)
                if data:
                    buffer.extend(data)
                    while b"\n" in buffer:
                        idx = buffer.index(b"\n")
                        raw_line = buffer[:idx].decode("ascii", errors="ignore").strip()
                        buffer = buffer[idx + 1 :]
                        if raw_line and self._rx_callback:
                            self._rx_callback(raw_line)
                else:
                    time.sleep(0.01)
            except Exception as e:
                if self._running:
                    logger.error(f"Serial read error: {e}")
                break


lora_port = LoraSerialPort()

