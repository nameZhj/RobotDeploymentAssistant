# @file: src/api/http_server.py
# @brief: Standard HTTP/1.1 multi-threaded REST server hosting lower computer routes.
# @exports: LowerComputerHttpServer

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from typing import Optional

from src.api.routes import LowerComputerContext, dispatch_http_request


class LowerComputerHttpServer:
    """Embeds a standard ThreadingHTTPServer exposing LowerComputerContext REST endpoints."""

    def __init__(self, ctx: LowerComputerContext, host: str = "0.0.0.0", port: int = 8090) -> None:
        self.ctx = ctx
        self.host = host
        self.port = port
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def bound_port(self) -> int:
        return int(self._httpd.server_address[1]) if self._httpd else self.port

    def start(self, blocking: bool = False) -> int:
        ctx = self.ctx

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
                parsed_json = None
                if raw_body:
                    try:
                        parsed_json = json.loads(raw_body.decode("utf-8"))
                    except Exception:
                        self._send(400, {"ok": False, "message": "无效的 JSON 请求体"}, "application/json")
                        return
                try:
                    code, payload, ctype = dispatch_http_request(ctx, method, self.path, parsed_json)
                    self._send(code, payload, ctype)
                except Exception as ex:
                    self._send(500, {"ok": False, "message": f"服务器内部异常: {ex}"}, "application/json")

            def _send(self, code: int, payload: object, ctype: str) -> None:
                body = payload if isinstance(payload, (bytes, bytearray)) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-LRMP-Target")
                self.send_header("Content-Type", f"{ctype}; charset=utf-8" if ctype == "application/json" else ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_OPTIONS(self) -> None:  # noqa: N802
                self._send(204, b"", "text/plain")

            def do_GET(self) -> None:  # noqa: N802
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
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None
