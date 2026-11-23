# @file: src/core/event_bus.py
# @brief: Thread-safe decoupled pub/sub event bus coordinating domain services and UniUni v3 UI panels.
# @exports: StudioEvent, StudioEventBus, get_event_bus

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
import threading
from typing import Any, Callable, Dict, List, Optional


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


@dataclass
class Subscription:
    """Handle returned when registering a listener."""

    topic: StudioEvent
    callback: CallbackFn
    active: bool = field(default=True)


class StudioEventBus:
    """In-process thread-safe publish/subscribe bus with weak error isolation."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._listeners: Dict[StudioEvent, List[CallbackFn]] = defaultdict(list)

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

    def publish(self, topic: StudioEvent, payload: Any = None) -> int:
        """Notify all listeners subscribed to topic; return delivered count."""
        with self._lock:
            callbacks = list(self._listeners.get(topic, []))
        delivered = 0
        for cb in callbacks:
            cb(payload)
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
