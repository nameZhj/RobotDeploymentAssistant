# @file: src/protocol/http_callback_listener.py
# @brief: Upper computer HTTP webhook listener receiving authentic lower computer task-chain and telemetry callbacks.
# @exports: HttpCallbackListener

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading
from typing import Any, Dict, List, Optional

from src.core.event_bus import StudioEvent, StudioEventBus


def _resolve_local_ip_for(peer_ip: str) -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((peer_ip, 8090))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


class HttpCallbackListener:
    """Receives lower-computer HTTP callbacks and publishes live events onto StudioEventBus."""

    def __init__(self, bus: Optional[StudioEventBus] = None, host: str = "0.0.0.0", port: int = 0) -> None:
        self.bus = bus
        self.host = host
        self.port = port
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.events: List[Dict[str, Any]] = []
        self.latest_by_target: Dict[str, Dict[str, Any]] = {}

    @property
    def is_running(self) -> bool:
        return self._httpd is not None

    @property
    def bound_port(self) -> int:
        return int(self._httpd.server_address[1]) if self._httpd else self.port

    def callback_url_for(self, robot_ip: str) -> str:
        if not self.is_running:
            self.start()
        local_ip = "127.0.0.1" if robot_ip in ("127.0.0.1", "localhost") else _resolve_local_ip_for(robot_ip)
        return f"http://{local_ip}:{self.bound_port}/api/v1/callbacks/robot"

    def start(self) -> int:
        if self._httpd is not None:
            return self.bound_port
        owner = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args) -> None:  # noqa: A002
                return

            def do_POST(self) -> None:  # noqa: N802
                ln = int(self.headers.get("Content-Length", "0") or "0")
                raw = self.rfile.read(ln) if ln > 0 else b"{}"
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except Exception:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b'{"ok":false}')
                    return
                owner._handle_event(payload)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

        self._httpd = ThreadingHTTPServer((self.host, self.port), _Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True, name="UpperCallbackHTTP")
        self._thread.start()
        return self.bound_port

    def _handle_event(self, payload: Dict[str, Any]) -> None:
        state_obj = payload.get("state") if isinstance(payload.get("state"), dict) else {}
        tgt = str(payload.get("target_id") or state_obj.get("target_id") or "A").upper()
        with self._lock:
            self.events.append(payload)
            if len(self.events) > 300:
                self.events = self.events[-150:]
            merged = dict(self.latest_by_target.get(tgt, {}))
            merged.update(state_obj)
            merged["last_event"] = payload.get("event", "")
            if "pose" in payload:
                merged["pose"] = payload["pose"]
            if "title" in payload:
                merged["current_node_title"] = payload["title"]
            self.latest_by_target[tgt] = merged
        if self.bus is not None:
            self.bus.publish(StudioEvent.ROBOT_TELEMETRY_UPDATED, {"target_id": tgt, "payload": payload})

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None
