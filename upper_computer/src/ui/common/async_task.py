# @file: src/ui/common/async_task.py
# @brief: Qt-friendly background runner executing blocking network/SSH/PCD work on QThreadPool with GUI-thread result delivery.
# @exports: BackgroundTaskRunner, TaskHandle, get_task_runner, run_in_background, wait_for_all_tasks, reset_task_runner

from __future__ import annotations

import logging
import time
import traceback
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

from PySide6.QtCore import QCoreApplication, QEventLoop, QObject, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import QWidget

logger = logging.getLogger("Studio.BackgroundTasks")

TaskFn = Callable[[], Any]
CallbackFn = Callable[[Any], None]


class TaskHandle:
    """Lightweight completion handle returned by BackgroundTaskRunner.run()."""

    __slots__ = ("task_id", "done", "result", "error")

    def __init__(self, task_id: int) -> None:
        self.task_id = task_id
        self.done = False
        self.result: Any = None
        self.error: Optional[str] = None

    def wait(self, timeout_s: float = 15.0) -> bool:
        """Process Qt events until the task completes (tests / synchronous callers only)."""
        app = QCoreApplication.instance()
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        while not self.done:
            if app is not None:
                app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
            else:
                time.sleep(0.005)
            if time.monotonic() > deadline:
                return False
        return True


class _Runnable(QRunnable):
    """QRunnable executing ``fn`` off the GUI thread and reporting through a queued signal."""

    def __init__(self, task_id: int, fn: TaskFn, completed: Signal) -> None:
        super().__init__()
        self._task_id = task_id
        self._fn = fn
        self._completed = completed
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: D401 - QRunnable API
        try:
            result = self._fn()
        except Exception as ex:  # noqa: BLE001 - propagate every worker failure to the GUI thread
            self._completed.emit(self._task_id, False, f"{ex}\n{traceback.format_exc()}")
        else:
            self._completed.emit(self._task_id, True, result)


class BackgroundTaskRunner(QObject):
    """Runs blocking callables on the global QThreadPool and delivers results on the GUI thread.

    * ``fn`` runs on a worker thread (never touches Qt widgets).
    * ``on_done(result)`` / ``on_error(text)`` run on the GUI thread via a queued signal.
    * Widgets passed in ``busy_widgets`` are disabled while the task runs and restored afterwards.
    """

    _completed = Signal(int, bool, object)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._completed.connect(self._on_completed)
        self._pool = QThreadPool.globalInstance()
        self._handles: Dict[int, TaskHandle] = {}
        self._callbacks: Dict[int, Tuple[Optional[CallbackFn], Optional[CallbackFn], Tuple[Tuple[QWidget, bool], ...]]] = {}
        self._next_id = 0
        self._pending = 0

    @property
    def pending(self) -> int:
        return self._pending

    def run(
        self,
        fn: TaskFn,
        on_done: Optional[CallbackFn] = None,
        on_error: Optional[CallbackFn] = None,
        busy_widgets: Iterable[Optional[QWidget]] = (),
        busy_text: Optional[str] = None,
        notifier: Optional[Callable[[str, str], None]] = None,
    ) -> TaskHandle:
        """Schedule ``fn`` in the background; returns a TaskHandle immediately."""
        task_id = self._next_id
        self._next_id += 1
        widgets: Tuple[Tuple[QWidget, bool], ...] = tuple(
            (w, w.isEnabled()) for w in busy_widgets if isinstance(w, QWidget)
        )
        for w, _ in widgets:
            w.setEnabled(False)
        if busy_text and notifier is not None:
            try:
                notifier(busy_text, "info")
            except RuntimeError as ex:
                logger.debug("后台任务 %s 的 busy 提示目标已销毁: %s", task_id, ex)
        handle = TaskHandle(task_id)
        self._handles[task_id] = handle
        self._callbacks[task_id] = (on_done, on_error, widgets)
        self._pending += 1
        self._pool.start(_Runnable(task_id, fn, self._completed))
        return handle

    def _on_completed(self, task_id: int, ok: bool, payload: Any) -> None:
        self._pending = max(0, self._pending - 1)
        handle = self._handles.pop(task_id, None)
        on_done, on_error, widgets = self._callbacks.pop(task_id, (None, None, ()))
        for w, was_enabled in widgets:
            try:
                w.setEnabled(was_enabled)
            except RuntimeError as ex:
                logger.debug("后台任务 %s 恢复控件状态时控件已销毁: %s", task_id, ex)
        if handle is not None:
            handle.done = True
            if ok:
                handle.result = payload
            else:
                handle.error = str(payload)
        if not ok:
            logger.error("后台任务 %s 失败:\n%s", task_id, payload)
        callback = on_done if ok else on_error
        if callback is None:
            return
        try:
            callback(payload)
        except RuntimeError as ex:
            # Target widget was destroyed while the task was running (dialog closed, page removed).
            logger.debug("后台任务 %s 回调目标已销毁: %s", task_id, ex)
        except Exception:  # noqa: BLE001 - never let a result handler crash the GUI thread
            logger.exception("后台任务 %s 回调异常", task_id)


_RUNNER: Optional[BackgroundTaskRunner] = None


def get_task_runner() -> BackgroundTaskRunner:
    """Return the process-wide runner (created lazily on the GUI thread)."""
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = BackgroundTaskRunner()
    return _RUNNER


def reset_task_runner() -> None:
    """Drop the runner reference (tests / application teardown)."""
    global _RUNNER
    _RUNNER = None


def wait_for_all_tasks(timeout_s: float = 30.0) -> bool:
    """Process Qt events until every pending background task has settled (tests / synchronous flows).

    Chained tasks (an ``on_done`` scheduling another background task) are covered by requiring
    two consecutive idle passes before declaring the runner settled.
    """
    runner = get_task_runner()
    app = QCoreApplication.instance()
    deadline = time.monotonic() + max(0.0, float(timeout_s))
    idle_rounds = 0
    while time.monotonic() < deadline:
        if runner.pending > 0:
            idle_rounds = 0
        else:
            idle_rounds += 1
            if idle_rounds >= 2:
                return True
        if app is not None:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        else:
            time.sleep(0.005)
    return runner.pending == 0


def run_in_background(
    fn: TaskFn,
    on_done: Optional[CallbackFn] = None,
    on_error: Optional[CallbackFn] = None,
    busy_widgets: Iterable[Optional[QWidget]] = (),
    busy_text: Optional[str] = None,
    notifier: Optional[Callable[[str, str], None]] = None,
) -> TaskHandle:
    """Convenience wrapper around ``get_task_runner().run(...)``."""
    return get_task_runner().run(fn, on_done, on_error, busy_widgets, busy_text, notifier)
