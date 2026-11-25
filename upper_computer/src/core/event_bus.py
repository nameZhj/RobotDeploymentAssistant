# @file: src/core/event_bus.py
# @brief: Thread-safe decoupled pub/sub event bus coordinating domain services and desktop v3 UI panels with cross-thread marshalling.
# @exports: StudioEvent, StudioEventBus, get_event_bus

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
import logging
import threading
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("Studio.EventBus")


class StudioEvent(str, Enum):
    """Canonical event topics decoupling L2-L7 engines from L8 UI views."""

    SCENE_CHANGED = "scene_changed"
    TASK_SWITCHED = "task_switched"
    TRACKS_UPDATED = "tracks_updated"
    TRAJECTORY_LIB_UPDATED = "trajectory_lib_updated"
    ACTION_LIB_UPDATED = "action_lib_updated"
    TIMELINE_UPDATED = "timeline_updated"
    BLOCK_SELECTED = "block_selected"
    PLAYHEAD_MOVED = "playhead_moved"
    PLAYBACK_STATE_CHANGED = "playback_state_changed"
    COLLISION_UPDATED = "collision_updated"
    INIT_POINTS_UPDATED = "init_points_updated"
    MAP_LOADED = "map_loaded"
    MAP_LIST_UPDATED = "map_list_updated"
    ROBOT_TELEMETRY_UPDATED = "robot_telemetry_updated"
    STATUS_NOTIFICATION = "status_notification"
    PAGE_NAVIGATION_REQUESTED = "page_navigation_requested"


CallbackFn = Callable[[Any], None]
DispatcherFn = Callable[[Callable[[], None]], None]


@dataclass
class Subscription:
    """Handle returned when registering a listener."""

    topic: StudioEvent
    callback: CallbackFn
    active: bool = field(default=True)


class StudioEventBus:
    """In-process thread-safe publish/subscribe bus with per-callback error isolation.

    When a UI dispatcher is registered (``set_dispatcher``), ``publish`` calls made from
    worker threads are marshalled onto the dispatcher's owning (GUI) thread so that Qt
    widgets are only ever touched from the thread that created them.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._listeners: Dict[StudioEvent, List[CallbackFn]] = defaultdict(list)
        self._dispatcher: Optional[DispatcherFn] = None
        self._dispatch_thread_id: Optional[int] = None

    def subscribe(self, topic: StudioEvent, callback: CallbackFn) -> Subscription:
        """Register callback for the given StudioEvent topic."""
        with self._lock:
            if callback not in self._listeners[topic]:
                self._listeners[topic].append(callback)
        return Subscription(topic=topic, callback=callback)

    def unsubscribe(self, topic: StudioEvent, callback: CallbackFn) -> None:
        """Remove a previously registered callback if present."""
        with self._lock:
            callbacks = self._listeners.get(topic, [])
            if callback in callbacks:
                callbacks.remove(callback)

    def set_dispatcher(self, dispatcher: DispatcherFn) -> None:
        """Register a callable that schedules a zero-arg function on the GUI thread.

        Must be called from the GUI thread itself so the owning thread id is captured.
        """
        self._dispatcher = dispatcher
        self._dispatch_thread_id = threading.get_ident()

    def clear_dispatcher(self) -> None:
        """Drop the registered dispatcher (e.g. when the owning window closes)."""
        self._dispatcher = None
        self._dispatch_thread_id = None

    @property
    def dispatcher_installed(self) -> bool:
        return self._dispatcher is not None

    def publish(self, topic: StudioEvent, payload: Any = None) -> int:
        """Notify all listeners subscribed to topic; return delivered count (0 when marshalled)."""
        if (
            self._dispatcher is not None
            and self._dispatch_thread_id is not None
            and threading.get_ident() != self._dispatch_thread_id
        ):
            dispatcher = self._dispatcher
            try:
                dispatcher(lambda: self._dispatch(topic, payload))
                return 0
            except RuntimeError as ex:
                # Dispatcher owner destroyed (window closing): fall back to direct delivery.
                logger.debug("事件总线跨线程投递失败，回退同线程直发: %s", ex)
                self.clear_dispatcher()
        return self._dispatch(topic, payload)

    def _dispatch(self, topic: StudioEvent, payload: Any) -> int:
        with self._lock:
            callbacks = list(self._listeners.get(topic, []))
        delivered = 0
        for cb in callbacks:
            try:
                cb(payload)
            except Exception:
                # R-8：逐回调错误隔离——单个回调异常仅记录不上抛，不中断其余监听者与发布方线程。
                logger.exception("事件总线回调异常 topic=%s callback=%r", topic, cb)
            else:
                delivered += 1
        return delivered

    def clear(self) -> None:
        """Clear all registered subscribers (primarily for unit tests)."""
        with self._lock:
            self._listeners.clear()


_GLOBAL_BUS: Optional[StudioEventBus] = None


def get_event_bus(reset: bool = False) -> StudioEventBus:
    """Return the global StudioEventBus singleton."""
    global _GLOBAL_BUS
    if _GLOBAL_BUS is None or reset:
        _GLOBAL_BUS = StudioEventBus()
    return _GLOBAL_BUS
