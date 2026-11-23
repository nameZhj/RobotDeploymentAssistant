# @file: src/ui/choreography/timeline_collision_clamp.py
# @brief: Rigid-body collision clamp preventing same-type timeline blocks from overlapping on the same track.
# @exports: same_type_siblings, clamp_move_start, clamp_resize_duration, resolve_non_overlapping_slot

from __future__ import annotations

from typing import Iterable, List, Optional

from src.domain.timeline_entities import TimelineBlockEntity


def same_type_siblings(
    blocks: Iterable[TimelineBlockEntity],
    track_id: int,
    block_type: str,
    exclude_id: Optional[int] = None,
) -> List[TimelineBlockEntity]:
    """Return active sibling blocks of the same block_type on track_id sorted by start_time."""
    sibs = [
        b
        for b in blocks
        if b.track_id == track_id
        and b.block_type == block_type
        and not b.is_ignored
        and (exclude_id is None or b.id != exclude_id)
    ]
    sibs.sort(key=lambda b: (b.start_time, b.end_time))
    return sibs


def _is_free(start: float, dur: float, siblings: List[TimelineBlockEntity], tol: float = 1e-4) -> bool:
    end = start + dur
    for s in siblings:
        if start < s.end_time - tol and s.start_time < end - tol:
            return False
    return True


def clamp_move_start(
    target_start: float,
    duration: float,
    origin_start: float,
    siblings: List[TimelineBlockEntity],
) -> float:
    """Resolve non-overlapping start time when dragging a block horizontally, acting like solid collision."""
    t = max(0.0, float(target_start))
    dur = max(0.5, float(duration))
    if _is_free(t, dur, siblings):
        return round(t, 2)

    # If dragged from outside a sibling into it, push firmly against the approach wall first
    moving_right = t >= origin_start
    blocking = [s for s in siblings if t < s.end_time - 1e-4 and s.start_time < t + dur - 1e-4]
    if blocking:
        s = blocking[0] if moving_right else blocking[-1]
        wall = round(s.start_time - dur, 2) if moving_right else round(s.end_time, 2)
        if wall >= 0.0 and _is_free(wall, dur, siblings):
            return max(0.0, wall)

    candidates: List[float] = []
    for s in siblings:
        left_edge = round(s.start_time - dur, 2)
        if left_edge >= 0.0 and _is_free(left_edge, dur, siblings):
            candidates.append(left_edge)
        right_edge = round(s.end_time, 2)
        if _is_free(right_edge, dur, siblings):
            candidates.append(right_edge)

    if not candidates:
        return round(origin_start, 2)
    best = min(candidates, key=lambda c: abs(c - t))
    return max(0.0, best)


def clamp_resize_duration(
    start_time: float,
    target_duration: float,
    siblings: List[TimelineBlockEntity],
    min_dur: float = 0.5,
) -> float:
    """Clamp resized block duration so its right edge stops cleanly at the next same-type block."""
    dur = max(min_dur, float(target_duration))
    later = [s.start_time for s in siblings if s.start_time >= start_time - 1e-4]
    if later:
        limit = max(min_dur, min(later) - start_time)
        dur = min(dur, limit)
    return round(dur, 2)


def resolve_non_overlapping_slot(
    target_start: float,
    duration: float,
    siblings: List[TimelineBlockEntity],
) -> float:
    """Place a dropped/inserted block at target_start or slide to nearest collision-free interval."""
    t = max(0.0, float(target_start))
    dur = max(0.5, float(duration))
    if _is_free(t, dur, siblings):
        return round(t, 2)
    candidates: List[float] = [s.end_time for s in siblings if _is_free(s.end_time, dur, siblings)]
    for s in siblings:
        left_s = s.start_time - dur
        if left_s >= 0.0 and _is_free(left_s, dur, siblings):
            candidates.append(left_s)
    if not candidates:
        return round(max((s.end_time for s in siblings), default=0.0), 2)
    # Prefer nearest forward boundary first when dropping inside an existing block
    forward = [c for c in candidates if c >= t - 1e-4]
    chosen = min(forward, key=lambda c: abs(c - t)) if forward else min(candidates, key=lambda c: abs(c - t))
    return round(max(0.0, chosen), 2)
