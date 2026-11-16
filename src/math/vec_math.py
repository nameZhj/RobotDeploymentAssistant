# @file: src/math/vec_math.py
# @brief: Pure 2D angle normalization/interpolation, segment intersection, and polyline length utilities.
# @exports: clamp, normalize_angle, interpolate_angle, segments_intersect, compute_polyline_length

from __future__ import annotations

import math
from typing import Sequence, Tuple


def clamp(value: float, low: float, high: float) -> float:
    """Clamp numeric scalar to [low, high]."""
    return min(max(value, low), high)


def normalize_angle(angle: float) -> float:
    """Wrap angle in radians into (-pi, pi]."""
    val = float(angle)
    while val > math.pi:
        val -= 2.0 * math.pi
    while val <= -math.pi:
        val += 2.0 * math.pi
    return val


def interpolate_angle(start: float, end: float, alpha: float) -> float:
    """Shortest-arc circular angle interpolation in radians."""
    delta = normalize_angle(end - start)
    return normalize_angle(start + delta * clamp(alpha, 0.0, 1.0))


def _cross2d(o: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def segments_intersect(
    a1: Tuple[float, float],
    a2: Tuple[float, float],
    b1: Tuple[float, float],
    b2: Tuple[float, float],
) -> bool:
    """Return True if open segments (a1, a2) and (b1, b2) strictly intersect."""
    d1 = _cross2d(b1, b2, a1)
    d2 = _cross2d(b1, b2, a2)
    d3 = _cross2d(a1, a2, b1)
    d4 = _cross2d(a1, a2, b2)
    return ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and (
        (d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)
    )


def compute_polyline_length(points: Sequence[Tuple[float, float]]) -> float:
    """Return total Euclidean path length along ordered 2D points."""
    total = 0.0
    for i in range(1, len(points)):
        total += math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1])
    return total
