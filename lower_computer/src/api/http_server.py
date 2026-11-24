# @file: src/api/http_server.py
# @brief: Standard HTTP/1.1 multi-threaded REST server hosting lower computer routes.
# @exports: LowerComputerHttpServer

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from typing import Dict, Optional
from urllib.parse import urlparse

from src.api.routes import LowerComputerContext, dispatch_http_request
from src.api.slam_routes import _sync_tap_from_cli_if_idle


class LowerComputerHttpServer:
    """Embeds a standard ThreadingHTTPServer exposing LowerComputerContext REST endpoints."""

    def __init__(self, ctx: LowerComputerContext, host: str = "0.0.0.0", port: int = 8090) -> None:
        self.ctx = ctx
        self.host = host
        self.port = port
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()

    @property
    def bound_port(self) -> int:
        return int(self._httpd.server_address[1]) if self._httpd else self.port

    def start(self, blocking: bool = False) -> int:
        ctx = self.ctx
        stop_flag = self._stop_flag
        stop_flag.clear()

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args) -> None:  # noqa: A002
                return

            def _handle(self, method: str) -> None:
                try:
                    length = int(self.headers.get("Content-Length", "0") or "0")
                except ValueError:
                    self._send(400, {"ok": False, "message": "无效的 Content-Length"}, "application/json")
                    return
                raw_body = self.rfile.read(max(0, length)) if length > 0 else b""
                clean_path = urlparse(self.path).path.rstrip("/")
                ctype_req = (self.headers.get("Content-Type") or "").lower()
                parsed_json = None
                if raw_body:
                    if clean_path == "/api/v1/slam/map/upload" and "json" not in ctype_req:
                        parsed_json = {"_raw_bytes": raw_body}
                    else:
                        try:
                            parsed_json = json.loads(raw_body.decode("utf-8"))
                        except Exception:
                            self._send(400, {"ok": False, "message": "无效的 JSON 请求体"}, "application/json")
                            return
                try:
                    code, payload, ctype = dispatch_http_request(ctx, method, self.path, parsed_json)
                    extra: Dict[str, str] = {}
                    if clean_path == "/api/v1/slam/live_cloud" and code == 200:
                        st = ctx.slam_tap.get_live_state()
                        extra["X-Cloud-Seq"] = str(st.get("cloud_seq", 0))
                        extra["X-Cloud-Count"] = str(st.get("point_count", 0))
                    self._send(code, payload, ctype, extra=extra)
                except Exception as ex:
                    self._send(500, {"ok": False, "message": f"服务器内部异常: {ex}"}, "application/json")

            def _send(self, code: int, payload: object, ctype: str, extra: Optional[Dict[str, str]] = None) -> None:
                body = payload if isinstance(payload, (bytes, bytearray)) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-LRMP-Target")
                self.send_header("Content-Type", f"{ctype}; charset=utf-8" if ctype == "application/json" else ctype)
                self.send_header("Content-Length", str(len(body)))
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def _serve_slam_sse_stream(self) -> None:
                self.close_connection = True
                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                _sync_tap_from_cli_if_idle(ctx)
                init_state = ctx.slam_tap.get_live_state()
                last_seq = int(init_state.get("state_seq", 0))
                try:
                    self.wfile.write(f"data: {json.dumps(init_state, ensure_ascii=False)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    while not stop_flag.is_set():
                        cur_seq, state = ctx.slam_tap.wait_for_update(last_seq, timeout_s=1.5)
                        if stop_flag.is_set():
                            break
                        if cur_seq > last_seq:
                            last_seq = cur_seq
                            self.wfile.write(f"data: {json.dumps(state, ensure_ascii=False)}\n\n".encode("utf-8"))
                        else:
                            if not ctx.slam_tap.is_streaming() and ctx.ros_bridge.is_ros_master_reachable():
                                _sync_tap_from_cli_if_idle(ctx)
                                state2 = ctx.slam_tap.get_live_state()
                                if int(state2.get("state_seq", 0)) > last_seq:
                                    last_seq = int(state2["state_seq"])
                                    self.wfile.write(f"data: {json.dumps(state2, ensure_ascii=False)}\n\n".encode("utf-8"))
                                    self.wfile.flush()
                                    continue
                            self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass

            def do_OPTIONS(self) -> None:  # noqa: N802
                self._send(204, b"", "text/plain")

            def do_GET(self) -> None:  # noqa: N802
                if urlparse(self.path).path.rstrip("/") == "/api/v1/slam/stream":
                    self._serve_slam_sse_stream()
                    return
                self._handle("GET")

            def do_POST(self) -> None:  # noqa: N802
                self._handle("POST")

            def do_PUT(self) -> None:  # noqa: N802
                self._send(405, {"ok": False, "message": "Method Not Allowed"}, "application/json")

            def do_DELETE(self) -> None:  # noqa: N802
                self._send(405, {"ok": False, "message": "Method Not Allowed"}, "application/json")

        self._httpd = ThreadingHTTPServer((self.host, self.port), _Handler)
        if blocking:
            self._httpd.serve_forever()
            return self.bound_port
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True, name="LowerComputerHTTP")
        self._thread.start()
        return self.bound_port

    def stop(self) -> None:
        self._stop_flag.set()
        self.ctx.slam_tap.stop()
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None
