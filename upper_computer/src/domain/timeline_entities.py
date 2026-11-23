# @file: src/domain/timeline_entities.py
# @brief: Domain entities for unified timeline lane blocks (trajectory or action) and numbered quick fragments.
# @exports: TimelineBlockEntity, TimelineFragmentEntity

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class TimelineBlockEntity:
    """A draggable, resizable block placed on a robot timeline lane."""

    id: Optional[int] = None
    task_id: int = 1
    track_id: int = 1
    block_type: str = "trajectory"  # "trajectory" | "action"
    ref_id: int = 0
    code_no: str = ""
    title: str = ""
    start_time: float = 0.0
    duration: float = 5.0
    is_ignored: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def end_time(self) -> float:
        """Return exclusive end timestamp in seconds."""
        return round(self.start_time + self.duration, 4)

    def overlaps(self, other: "TimelineBlockEntity", tol: float = 1e-4) -> bool:
        """Check whether two active same-type blocks overlap on the same track (action + trajectory may run together)."""
        if self.track_id != other.track_id or self is other:
            return False
        if self.block_type != other.block_type:
            return False
        if self.id is not None and other.id is not None and self.id == other.id:
            return False
        return (self.start_time < other.end_time - tol) and (other.start_time < self.end_time - tol)


@dataclass
class TimelineFragmentEntity:
    """Saved numbered choreography fragment snapshot (slots 1..99)."""

    id: Optional[int] = None
    scene_id: int = 1
    slot_no: int = 1
    name: str = "片段 1"
    duration: float = 5.0
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_str)
