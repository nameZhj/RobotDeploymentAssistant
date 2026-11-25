# @file: src/task_chain/webhook_dispatcher.py
# @brief: Sends authentic HTTP POST JSON callbacks to upper computer without synthetic or fake success.
# @exports: CallbackReceipt, WebhookDispatcher

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import json
import threading
import time
from typing import Any, Deque, Dict, List, Optional, Tuple
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
    """Dispatches real HTTP POST event callbacks to the upper computer listener.

    High-frequency progress callbacks must never block the navigation polling loop or the
    emergency-stop HTTP handler: ``emit_async`` hands them to a bounded background queue with
    retry/backoff, while one-shot lifecycle events keep using the synchronous ``emit``.
    """

    def __init__(
        self,
        timeout_s: float = 3.0,
        async_queue_cap: int = 128,
        async_max_attempts: int = 2,
        async_backoff_s: float = 0.5,
    ) -> None:
        self.timeout_s = max(0.5, timeout_s)
        self._lock = threading.Lock()
        self._opener = urlrequest.build_opener(urlrequest.ProxyHandler({}))
        self.history: List[CallbackReceipt] = []
        self._async_cap = max(1, async_queue_cap)
        self._async_attempts = max(1, async_max_attempts)
        self._async_backoff_s = max(0.0, async_backoff_s)
        self._pending: Deque[Tuple[str, str, Dict[str, Any], bool]] = deque()
        self._pending_cond = threading.Condition()
        self._async_worker: Optional[threading.Thread] = None

    def emit(self, callback_url: str, event: str, payload: Dict[str, Any]) -> CallbackReceipt:
        url = (callback_url or "").strip()
        if not url:
            rec = CallbackReceipt(False, 0, event, "", 0.0, error="未配置 callback_url，未发送远程回调")
            self._record(rec)
            return rec
        if event in ("STEP_COMPLETED", "TASK_ERROR", "CHAIN_COMPLETED", "CHAIN_ABORTED", "STOPPED_RETURNING_ORIGIN"):
            self.drop_pending_progress(url)

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

    def _drop_progress_unlocked(self, url: str) -> int:
        before = len(self._pending)
        if not url:
            kept = [it for it in self._pending if it[1] != "STEP_PROGRESS"]
        else:
            kept = [it for it in self._pending if not (it[1] == "STEP_PROGRESS" and it[0] == url)]
        if len(kept) != before:
            self._pending = deque(kept)
        return before - len(self._pending)

    def drop_pending_progress(self, callback_url: str = "") -> int:
        """Remove queued STEP_PROGRESS callbacks so terminal states cannot be overwritten by stale progress."""
        url = (callback_url or "").strip()
        with self._pending_cond:
            return self._drop_progress_unlocked(url)

    def emit_async(self, callback_url: str, event: str, payload: Dict[str, Any], urgent: bool = False) -> CallbackReceipt:
        """Queue a webhook for background delivery and return an enqueue acknowledgement immediately."""
        url = (callback_url or "").strip()
        if not url:
            rec = CallbackReceipt(False, 0, event, "", 0.0, error="未配置 callback_url，未发送远程回调")
            self._record(rec)
            return rec
        item: Tuple[str, str, Dict[str, Any], bool] = (url, event, dict(payload), urgent)
        self._ensure_async_worker()
        with self._pending_cond:
            if urgent:
                self._drop_progress_unlocked(url)
                if len(self._pending) >= self._async_cap:
                    self._pending.pop()
                self._pending.appendleft(item)
            elif len(self._pending) >= self._async_cap:
                rec = CallbackReceipt(False, 0, event, url, 0.0, error="异步回调队列已满，本次事件未入队（已记录）")
                self._record(rec)
                return rec
            else:
                self._pending.append(item)
            self._pending_cond.notify_all()
        return CallbackReceipt(True, 0, event, url, 0.0, error="queued")

    def _ensure_async_worker(self) -> None:
        with self._pending_cond:
            if self._async_worker is not None and self._async_worker.is_alive():
                return
            self._async_worker = threading.Thread(target=self._async_worker_loop, daemon=True, name="WebhookAsyncSender")
            self._async_worker.start()

    def _async_worker_loop(self) -> None:
        while True:
            with self._pending_cond:
                while not self._pending:
                    self._pending_cond.wait()
                url, event, payload, urgent = self._pending.popleft()
            attempts = self._async_attempts + (1 if urgent else 0)
            for attempt in range(1, attempts + 1):
                rec = self.emit(url, event, payload)
                if rec.ok or attempt >= attempts:
                    break
                if self._async_backoff_s > 0:
                    time.sleep(self._async_backoff_s * attempt)

    def _record(self, rec: CallbackReceipt) -> None:
        with self._lock:
            self.history.append(rec)
            if len(self.history) > 200:
                self.history = self.history[-100:]
