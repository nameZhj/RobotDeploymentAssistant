# @file: src/ui/mapping/nav_live_poller.py
# @brief: Persistent HTTP/1.1 SSE client with non-blocking cloud fetch, generation-guarded non-blocking stop, and UI frame coalescing.
# @exports: NavLiveStreamWorker

from __future__ import annotations

import json
import socket
import threading
from typing import Any, Dict, Optional
from urllib.parse import urlparse
import numpy as np
from PySide6.QtCore import QObject, Signal

from src.protocol.robot_http_client import RobotHttpClient


class NavLiveStreamWorker(QObject):
    """Connects to lower_computer GET /api/v1/slam/stream (SSE) with coalesced latest-frame UI delivery.

    Threading contract
    ------------------
    * ``start_stream`` / ``stop_stream`` are called from the GUI thread and never block: stopping
      only flips a generation counter + stop event and closes the active socket; daemon threads
      notice the generation change and exit on their own (no ``join`` on the GUI thread).
    * Worker threads never touch widgets; they only emit Qt signals (queued to the GUI thread).
    """

    liveStateReceived = Signal(dict)
    liveCloudReceived = Signal(object, int)  # (np.ndarray [N,3], cloud_seq)
    streamStatusChanged = Signal(bool, str)
    _wakeDrain = Signal()

    def __init__(self, http_client: Optional[RobotHttpClient] = None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._http = http_client or RobotHttpClient(timeout_s=2.5)
        self._stop_ev = threading.Event()
        self._cloud_wake = threading.Event()
        self._sse_thread: Optional[threading.Thread] = None
        self._cloud_thread: Optional[threading.Thread] = None
        self._active_sock: Optional[socket.socket] = None
        self._robot_ip: str = ""
        self._gen: int = 0
        self._last_cloud_seq: int = 0
        self._target_cloud_seq: int = 0

        # Coalescing mailbox so 20-30Hz ROS bursts never flood the Qt event queue or leak memory
        self._mail_lock = threading.Lock()
        self._pending_state: Optional[Dict[str, Any]] = None
        self._pending_cloud: Optional[tuple[np.ndarray, int]] = None
        self._drain_scheduled: bool = False
        self._wakeDrain.connect(self._flush_to_ui)

    @property
    def robot_ip(self) -> str:
        return self._robot_ip

    def _is_current(self, gen: int) -> bool:
        return gen == self._gen and not self._stop_ev.is_set()

    def start_stream(self, robot_ip: str) -> None:
        ip = (robot_ip or "").strip()
        if ip == self._robot_ip and self._sse_thread is not None and self._sse_thread.is_alive():
            return
        self.stop_stream()
        self._robot_ip = ip
        self._last_cloud_seq = self._target_cloud_seq = 0
        if not ip:
            self.streamStatusChanged.emit(False, "未绑定机器人 Wi-Fi IP")
            return
        self._gen += 1
        gen = self._gen
        self._stop_ev.clear()
        self._cloud_wake.clear()
        self._sse_thread = threading.Thread(target=self._run_sse_loop, args=(gen,), daemon=True, name=f"NavSSE-{ip}")
        self._cloud_thread = threading.Thread(target=self._run_cloud_loop, args=(gen,), daemon=True, name=f"NavCloud-{ip}")
        self._sse_thread.start()
        self._cloud_thread.start()

    def stop_stream(self) -> None:
        """Signal worker loops to exit and close the socket immediately; never blocks the caller."""
        self._gen += 1  # invalidate any running loop regardless of the shared stop event
        self._stop_ev.set()
        self._cloud_wake.set()
        sock = self._active_sock
        self._active_sock = None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        self._sse_thread = self._cloud_thread = None
        with self._mail_lock:
            self._pending_state = None
            self._pending_cloud = None
            self._drain_scheduled = False

    def _enqueue_ui(self, state: Optional[Dict[str, Any]] = None, cloud: Optional[tuple[np.ndarray, int]] = None) -> None:
        trigger = False
        with self._mail_lock:
            if state is not None:
                self._pending_state = state
            if cloud is not None:
                self._pending_cloud = cloud
            if not self._drain_scheduled:
                self._drain_scheduled = True
                trigger = True
        if trigger:
            self._wakeDrain.emit()

    def _flush_to_ui(self) -> None:
        with self._mail_lock:
            st, cl = self._pending_state, self._pending_cloud
            self._pending_state = self._pending_cloud = None
            self._drain_scheduled = False
        if st is not None:
            self.liveStateReceived.emit(st)
        if cl is not None:
            self.liveCloudReceived.emit(cl[0], cl[1])

    def _run_sse_loop(self, gen: int) -> None:
        ip = self._robot_ip
        while self._is_current(gen) and ip:
            parsed = urlparse(self._http.slam_stream_url(ip))
            host, port = parsed.hostname or ip, parsed.port or 8090
            sock: Optional[socket.socket] = None
            try:
                sock = socket.create_connection((host, port), timeout=6.0)
                if not self._is_current(gen):
                    break
                self._active_sock = sock
                req = (
                    f"GET {parsed.path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
                    "Accept: text/event-stream\r\nConnection: close\r\n\r\n"
                ).encode("ascii")
                sock.sendall(req)
                buf = b""
                while b"\r\n\r\n" not in buf and self._is_current(gen):
                    chunk = sock.recv(4096)
                    if not chunk:
                        raise ConnectionError("SSE 握手断开")
                    buf += chunk
                if not self._is_current(gen):
                    break
                hdr_bytes, rest = buf.split(b"\r\n\r\n", 1)
                status_line = hdr_bytes.split(b"\r\n", 1)[0].decode("ascii", errors="ignore")
                if " 200 " not in status_line:
                    raise RuntimeError(status_line)
                self.streamStatusChanged.emit(True, f"HTTP 长连接已建立 ({ip})")
                buf = rest
                while self._is_current(gen):
                    while b"\n" in buf and self._is_current(gen):
                        raw_line, buf = buf.split(b"\n", 1)
                        line = raw_line.decode("utf-8", errors="ignore").strip()
                        if not line.startswith("data:"):
                            continue
                        try:
                            state = json.loads(line[5:].strip())
                        except ValueError:
                            continue
                        self._enqueue_ui(state=state)
                        cseq = int(state.get("cloud_seq", 0) or 0)
                        if cseq > self._last_cloud_seq and cseq > self._target_cloud_seq:
                            self._target_cloud_seq = cseq
                            self._cloud_wake.set()
                    if not self._is_current(gen):
                        break
                    chunk = sock.recv(8192)
                    if not chunk:
                        break
                    buf += chunk
            except Exception as ex:
                if not self._is_current(gen):
                    break
                self.streamStatusChanged.emit(False, f"等待下位机 HTTP ({ip}): {ex}")
                self._stop_ev.wait(1.2)
            finally:
                if self._active_sock is sock:
                    self._active_sock = None
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass

    def _run_cloud_loop(self, gen: int) -> None:
        while self._is_current(gen):
            self._cloud_wake.wait(timeout=1.0)
            self._cloud_wake.clear()
            if not self._is_current(gen) or not self._robot_ip:
                break
            if self._target_cloud_seq <= self._last_cloud_seq:
                continue
            resp = self._http.fetch_slam_live_cloud(self._robot_ip, since_seq=self._last_cloud_seq)
            if resp.status_code == 200 and resp.raw_bytes and len(resp.raw_bytes) >= 12:
                usable = len(resp.raw_bytes) - (len(resp.raw_bytes) % 12)
                pts = np.frombuffer(resp.raw_bytes[:usable], dtype=np.float32).reshape(-1, 3).copy()
                seq = int(resp.data.get("cloud_seq", self._target_cloud_seq))
                self._last_cloud_seq = seq
                self._enqueue_ui(cloud=(pts, seq))
