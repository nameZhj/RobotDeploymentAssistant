# @file: src/task_chain/webhook_dispatcher.py
# @brief: Sends authentic HTTP POST JSON callbacks to upper computer without synthetic or fake success.
# @exports: CallbackReceipt, WebhookDispatcher

from __future__ import annotations

from dataclasses import dataclass, field
import json
import threading
import time
from typing import Any, Dict, List
from urllib import error as urlerror
from urllib import request as urlrequest


@dataclass(frozen=True)
class CallbackReceipt:
    """Authentic HTTP delivery record for a single callback event."""

    ok: bool
    status_code: int
    event: str
    url: str
    elapsed_ms: float
    error: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "status_code": self.status_code,
            "event": self.event,
            "url": self.url,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "error": self.error,
            "timestamp": self.timestamp,
        }


class WebhookDispatcher:
    """Dispatches real HTTP POST event callbacks to the upper computer listener."""

    def __init__(self, timeout_s: float = 3.0) -> None:
        self.timeout_s = max(0.5, timeout_s)
        self._lock = threading.Lock()
        self._opener = urlrequest.build_opener(urlrequest.ProxyHandler({}))
        self.history: List[CallbackReceipt] = []

    def emit(self, callback_url: str, event: str, payload: Dict[str, Any]) -> CallbackReceipt:
        url = (callback_url or "").strip()
        if not url:
            rec = CallbackReceipt(False, 0, event, "", 0.0, error="未配置 callback_url，未发送远程回调")
            self._record(rec)
            return rec

        body = json.dumps({"event": event, "timestamp": time.time(), **payload}, ensure_ascii=False).encode("utf-8")
        req = urlrequest.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "X-Robot-Event": event},
            method="POST",
        )
        t0 = time.monotonic()
        try:
            with self._opener.open(req, timeout=self.timeout_s) as resp:
                elapsed = (time.monotonic() - t0) * 1000.0
                rec = CallbackReceipt(200 <= resp.status < 300, int(resp.status), event, url, elapsed)
        except urlerror.HTTPError as ex:
            elapsed = (time.monotonic() - t0) * 1000.0
            rec = CallbackReceipt(False, int(ex.code), event, url, elapsed, error=str(ex))
        except Exception as ex:
            elapsed = (time.monotonic() - t0) * 1000.0
            rec = CallbackReceipt(False, 0, event, url, elapsed, error=str(ex))
        self._record(rec)
        return rec

    def _record(self, rec: CallbackReceipt) -> None:
        with self._lock:
            self.history.append(rec)
            if len(self.history) > 200:
                self.history = self.history[-100:]
