# @file: src/commands/lora_serial_daemon.py
# @brief: Onboard LoRa serial listener receiving TARGET|WIFI_* provisioning frames and replying with WIFI_ACK JSON.
# @exports: LoraSerialWifiDaemon

from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Optional

from src.commands.lora_wifi_agent import LoraWifiAgent
from src.config.robot_config_reader import RobotConfigReader


class LoraSerialWifiDaemon:
    """Listens on onboard LoRa serial device for pure-LoRa Wi-Fi provisioning commands before Wi-Fi is ready."""

    def __init__(
        self,
        wifi_agent: LoraWifiAgent,
        config_reader: RobotConfigReader,
        serial_port: str = "/dev/ttyCH341USB0",
        baudrate: int = 9600,
        serial_factory: Optional[Callable[[str, int], Any]] = None,
    ) -> None:
        self.wifi_agent = wifi_agent
        self.config_reader = config_reader
        self.serial_port = serial_port
        self.baudrate = baudrate
        self._serial_factory = serial_factory
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ser: Optional[Any] = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def process_frame_line(self, raw_line: str) -> Optional[str]:
        """Parse one `TARGET|WIFI_CMD,arg1,...` frame and return `WIFI_ACK|<id>|<json>` if addressed to us."""
        line = (raw_line or "").strip()
        if "|" not in line:
            return None
        target, body = line.split("|", 1)
        tgt = target.strip().upper()
        my_id = str(self.config_reader.read_robot_id().get("robot_id", "A")).upper()
        if tgt not in ("ALL", my_id):
            return None
        parts = [p.strip() for p in body.split(",") if p.strip()]
        if not parts or not parts[0].upper().startswith("WIFI_"):
            return None
        cmd, params = parts[0].upper(), parts[1:]
        res = self.wifi_agent.handle_lora_wifi_command(cmd, params)
        envelope = {"cmd": cmd, "target_id": my_id, **res}
        return f"WIFI_ACK|{my_id}|{json.dumps(envelope, ensure_ascii=False)}"

    def start(self) -> bool:
        if self.is_running:
            return True
        ser = self._open_serial()
        if ser is None:
            return False
        self._ser = ser
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="LoraWifiSerialDaemon")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None

    def _open_serial(self) -> Optional[Any]:
        if self._serial_factory is not None:
            try:
                return self._serial_factory(self.serial_port, self.baudrate)
            except Exception:
                return None
        try:
            import serial  # type: ignore[import-untyped]
            return serial.Serial(self.serial_port, self.baudrate, timeout=0.5)
        except Exception:
            return None

    def _loop(self) -> None:
        while not self._stop_event.is_set() and self._ser is not None:
            try:
                raw = self._ser.readline()
                if not raw:
                    continue
                text = raw.decode("utf-8", errors="ignore") if isinstance(raw, (bytes, bytearray)) else str(raw)
                ack = self.process_frame_line(text)
                if ack:
                    self._ser.write((ack + "\n").encode("utf-8"))
                    if hasattr(self._ser, "flush"):
                        self._ser.flush()
            except Exception:
                time.sleep(0.2)
