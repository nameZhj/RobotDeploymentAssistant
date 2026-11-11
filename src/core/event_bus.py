import inspect
import logging
import threading
from typing import Any, Callable, Dict, List

logger = logging.getLogger("EventBus")


class EventBus:
    """
    Lightweight, thread-safe in-process publish-subscribe event bus.
    Facilitates decoupling between transport frames (ACK/RSP/EVT) and domain listeners.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}

    def subscribe(self, topic: str, callback: Callable[[Any], None]) -> None:
        """Register a subscriber callback for a specific topic or '*' for all events."""
        with self._lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = []
            if callback not in self._subscribers[topic]:
                self._subscribers[topic].append(callback)

    def unsubscribe(self, topic: str, callback: Callable[[Any], None]) -> bool:
        """Remove a subscriber callback from a topic."""
        with self._lock:
            if topic in self._subscribers and callback in self._subscribers[topic]:
                self._subscribers[topic].remove(callback)
                if not self._subscribers[topic]:
                    del self._subscribers[topic]
                return True
            return False

    def publish(self, topic: str, payload: Any = None) -> int:
        """
        Synchronously dispatch an event payload to topic subscribers and wildcard subscribers.
        Returns the number of invoked listeners.
        """
        listeners: List[Callable[[Any], None]] = []
        with self._lock:
            if topic in self._subscribers:
                listeners.extend(self._subscribers[topic])
            if "*" in self._subscribers and topic != "*":
                listeners.extend(self._subscribers["*"])

        delivered = 0
        for handler in listeners:
            try:
                sig = inspect.signature(handler)
                if len(sig.parameters) == 0:
                    handler()  # type: ignore
                elif len(sig.parameters) == 1:
                    handler(payload)
                else:
                    handler(topic, payload)  # type: ignore
                delivered += 1
            except Exception as e:
                logger.error(f"EventBus handler failed on topic [{topic}]: {e}", exc_info=True)

        return delivered

    def publish_async(self, topic: str, payload: Any = None) -> threading.Thread:
        """Dispatch an event asynchronously on a daemon thread."""
        t = threading.Thread(target=self.publish, args=(topic, payload), daemon=True)
        t.start()
        return t

    def clear(self) -> None:
        """Remove all subscribers."""
        with self._lock:
            self._subscribers.clear()


event_bus = EventBus()

