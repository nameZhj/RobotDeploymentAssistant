# @file: tests/test_background_tasks.py
# @brief: Verification of GUI-thread event bus marshalling, background task runner semantics, and non-blocking SSE stream stop.
# @exports: test_event_bus_marshals_worker_publish_to_dispatcher_thread, test_background_task_runner_delivers_result_and_restores_widgets, test_fleet_health_refresh_never_blocks_gui, test_nav_stream_stop_is_non_blocking

from __future__ import annotations

import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QPushButton

from src.core.event_bus import StudioEvent, StudioEventBus
from src.persistence import StudioDatabase
from src.persistence.seed_builtin_data import ensure_seeded
from src.services.playback_coordinator import PlaybackCoordinator
from src.services.studio_state_service import StudioStateService
from src.ui.common.async_task import get_task_runner, run_in_background, wait_for_all_tasks
from src.ui.mapping.nav_live_poller import NavLiveStreamWorker
from src.ui.monitoring import PerformanceMonitorPage


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class _Bridge(QObject):
    """Test dispatcher mirroring the app shell's cross-thread event bus bridge."""

    _invoke = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._invoke.connect(self._run, Qt.ConnectionType.QueuedConnection)
        self.calls = []
        self.threads = []

    def submit(self, fn) -> None:
        self._invoke.emit(fn)

    def _run(self, fn) -> None:
        self.threads.append(threading.get_ident())
        self.calls.append(fn())


def test_event_bus_marshals_worker_publish_to_dispatcher_thread() -> None:
    app = _app()
    bus = StudioEventBus()
    bridge = _Bridge()
    bus.set_dispatcher(bridge.submit)
    seen = []
    bus.subscribe(StudioEvent.STATUS_NOTIFICATION, lambda p: seen.append((p, threading.get_ident())))

    worker = threading.Thread(target=lambda: bus.publish(StudioEvent.STATUS_NOTIFICATION, {"text": "hi"}))
    worker.start()
    worker.join()

    deadline = time.monotonic() + 3.0
    while not seen and time.monotonic() < deadline:
        app.processEvents()
    assert seen, "marshalled publish was never delivered to the GUI thread"
    assert seen[0][0] == {"text": "hi"}
    assert seen[0][1] == threading.get_ident()
    assert bridge.threads and bridge.threads[0] == threading.get_ident()
    bus.clear_dispatcher()


def test_background_task_runner_delivers_result_and_restores_widgets() -> None:
    _app()
    btn = QPushButton()
    results = []

    h = run_in_background(lambda: (time.sleep(0.15) or 42), on_done=results.append, busy_widgets=[btn])
    assert h is not None
    assert not btn.isEnabled()  # disabled while the blocking task runs
    assert h.wait(timeout_s=5.0)
    assert results == [42]
    assert btn.isEnabled()
    assert get_task_runner().pending == 0

    def _boom():
        raise RuntimeError("kaput")

    h2 = run_in_background(_boom, on_error=lambda err: results.append(err.splitlines()[0]))
    assert h2.wait(timeout_s=5.0)
    assert h2.done and h2.result is None and "kaput" in (h2.error or "")
    assert results[-1] == "kaput"
    wait_for_all_tasks(timeout_s=5.0)


def test_fleet_health_refresh_never_blocks_gui(tmp_path) -> None:
    _app()
    db = StudioDatabase(tmp_path / "bg_health.db")
    ensure_seeded(db)
    state = StudioStateService(db=db)
    state.load_demo_swarm_preset()
    pb = PlaybackCoordinator(state)
    perf = PerformanceMonitorPage(state, pb)

    def _slow_health(timeout_s: float = 1.2):
        time.sleep(0.4)
        return {}

    state.fleet_health = _slow_health  # simulate an unreachable fleet without real sockets
    t0 = time.monotonic()
    h = perf.refresh_fleet_health()
    elapsed = time.monotonic() - t0
    assert h is not None
    assert elapsed < 0.2, f"refresh_fleet_health blocked the GUI thread for {elapsed:.2f}s"
    assert h.wait(timeout_s=5.0)
    assert "[HEALTH]" in perf.log_box.toPlainText()
    wait_for_all_tasks(timeout_s=5.0)
    perf.deleteLater()


def test_nav_stream_stop_is_non_blocking() -> None:
    _app()
    worker = NavLiveStreamWorker()
    worker.start_stream("10.255.255.1")  # unroutable address: worker blocks in connect, GUI must not
    time.sleep(0.3)
    t0 = time.monotonic()
    worker.stop_stream()
    elapsed = time.monotonic() - t0
    assert elapsed < 0.25, f"stop_stream blocked the GUI thread for {elapsed:.2f}s"

    # Restarting immediately must not resurrect the invalidated generation
    worker.start_stream("127.0.0.1")
    time.sleep(0.2)
    t1 = time.monotonic()
    worker.stop_stream()
    assert (time.monotonic() - t1) < 0.25
    _app().processEvents()
