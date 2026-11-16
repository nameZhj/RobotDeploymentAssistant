# @file: src/math/catmull_rom_spline.py
# @brief: 2D/3D Catmull-Rom spline evaluator and 2000-sample arc-length lookup table with O(log N) inversion.
# @exports: ArcLengthTable, catmull_rom_point_2d, catmull_rom_derivative_2d, catmull_rom_point_3d, build_arc_length_table_2d, u_from_s, sample_spline_equal_distance_2d

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import List, Sequence, Tuple

from src.math.vec_math import clamp

DEFAULT_ARC_LENGTH_SAMPLES = 2000


@dataclass(frozen=True)
class ArcLengthTable:
    """Mapping between uniform spline parameter u in [0, 1] and cumulative arc length s."""

    u_list: List[float]
    s_list: List[float]
    total_length: float


def _segment_params(point_count: int, u: float) -> Tuple[int, float, int]:
    seg_count = max(1, point_count - 1)
    scaled = clamp(u, 0.0, 1.0) * seg_count
    seg_idx = min(int(math.floor(scaled)), seg_count - 1)
    local_t = scaled - seg_idx
    return seg_idx, local_t, seg_count


def catmull_rom_point_2d(points: Sequence[Tuple[float, float]], u: float) -> Tuple[float, float]:
    """Evaluate 2D Catmull-Rom spline position at normalized parameter u in [0, 1]."""
    n = len(points)
    if n == 0:
        return (0.0, 0.0)
    if n == 1:
        return (float(points[0][0]), float(points[0][1]))
    if n == 2:
        t = clamp(u, 0.0, 1.0)
        return (
            points[0][0] + (points[1][0] - points[0][0]) * t,
            points[0][1] + (points[1][1] - points[0][1]) * t,
        )

    seg_idx, t, _ = _segment_params(n, u)
    p1 = points[seg_idx]
    p2 = points[seg_idx + 1]
    p0 = points[seg_idx - 1] if seg_idx - 1 >= 0 else p1
    p3 = points[seg_idx + 2] if seg_idx + 2 < n else p2
    t2 = t * t
    t3 = t2 * t
    x = 0.5 * (
        2.0 * p1[0]
        + (-p0[0] + p2[0]) * t
        + (2.0 * p0[0] - 5.0 * p1[0] + 4.0 * p2[0] - p3[0]) * t2
        + (-p0[0] + 3.0 * p1[0] - 3.0 * p2[0] + p3[0]) * t3
    )
    y = 0.5 * (
        2.0 * p1[1]
        + (-p0[1] + p2[1]) * t
        + (2.0 * p0[1] - 5.0 * p1[1] + 4.0 * p2[1] - p3[1]) * t2
        + (-p0[1] + 3.0 * p1[1] - 3.0 * p2[1] + p3[1]) * t3
    )
    return (x, y)


def catmull_rom_derivative_2d(points: Sequence[Tuple[float, float]], u: float) -> Tuple[float, float]:
    """Evaluate 2D Catmull-Rom spline derivative dp/du at u in [0, 1]."""
    n = len(points)
    if n < 2:
        return (0.0, 0.0)
    if n == 2:
        return (points[1][0] - points[0][0], points[1][1] - points[0][1])

    seg_idx, t, seg_count = _segment_params(n, u)
    p1 = points[seg_idx]
    p2 = points[seg_idx + 1]
    p0 = points[seg_idx - 1] if seg_idx - 1 >= 0 else p1
    p3 = points[seg_idx + 2] if seg_idx + 2 < n else p2
    t2 = t * t
    dx = 0.5 * (
        -p0[0]
        + p2[0]
        + 2.0 * (2.0 * p0[0] - 5.0 * p1[0] + 4.0 * p2[0] - p3[0]) * t
        + 3.0 * (-p0[0] + 3.0 * p1[0] - 3.0 * p2[0] + p3[0]) * t2
    )
    dy = 0.5 * (
        -p0[1]
        + p2[1]
        + 2.0 * (2.0 * p0[1] - 5.0 * p1[1] + 4.0 * p2[1] - p3[1]) * t
        + 3.0 * (-p0[1] + 3.0 * p1[1] - 3.0 * p2[1] + p3[1]) * t2
    )
    return (dx * seg_count, dy * seg_count)


def catmull_rom_point_3d(points: Sequence[Tuple[float, float, float]], u: float) -> Tuple[float, float, float]:
    """Evaluate 3D Catmull-Rom spline position at u in [0, 1]."""
    n = len(points)
    if n == 0:
        return (0.0, 0.0, 0.0)
    if n == 1:
        return (float(points[0][0]), float(points[0][1]), float(points[0][2]))
    if n == 2:
        t = clamp(u, 0.0, 1.0)
        return (
            points[0][0] + (points[1][0] - points[0][0]) * t,
            points[0][1] + (points[1][1] - points[0][1]) * t,
            points[0][2] + (points[1][2] - points[0][2]) * t,
        )
    seg_idx, t, _ = _segment_params(n, u)
    p1, p2 = points[seg_idx], points[seg_idx + 1]
    p0 = points[seg_idx - 1] if seg_idx - 1 >= 0 else p1
    p3 = points[seg_idx + 2] if seg_idx + 2 < n else p2
    t2, t3 = t * t, t * t * t
    coords = []
    for dim in range(3):
        v = 0.5 * (
            2.0 * p1[dim]
            + (-p0[dim] + p2[dim]) * t
            + (2.0 * p0[dim] - 5.0 * p1[dim] + 4.0 * p2[dim] - p3[dim]) * t2
            + (-p0[dim] + 3.0 * p1[dim] - 3.0 * p2[dim] + p3[dim]) * t3
        )
        coords.append(v)
    return (coords[0], coords[1], coords[2])


def build_arc_length_table_2d(
    points: Sequence[Tuple[float, float]],
    resolution: int = DEFAULT_ARC_LENGTH_SAMPLES,
) -> ArcLengthTable:
    """Build 2000-sample cumulative arc-length table for constant-speed lookup."""
    u_list: List[float] = []
    s_list: List[float] = []
    length = 0.0
    last_u = 0.0
    res = max(2, resolution)
    for i in range(res):
        u = i / (res - 1)
        u_list.append(u)
        if i == 0:
            s_list.append(0.0)
            last_u = u
            continue
        du = u - last_u
        d = catmull_rom_derivative_2d(points, u)
        length += math.hypot(d[0], d[1]) * du
        s_list.append(length)
        last_u = u
    return ArcLengthTable(u_list=u_list, s_list=s_list, total_length=length)


def u_from_s(table: ArcLengthTable, s: float) -> float:
    """Invert cumulative arc length s -> u in [0, 1] using binary search."""
    if s <= 0.0 or not table.s_list:
        return 0.0
    if s >= table.s_list[-1]:
        return 1.0
    left = 0
    right = len(table.s_list) - 1
    while right - left > 1:
        mid = (left + right) >> 1
        if table.s_list[mid] > s:
            right = mid
        else:
            left = mid
    s0, s1 = table.s_list[left], table.s_list[right]
    u0, u1 = table.u_list[left], table.u_list[right]
    ratio = 0.0 if abs(s1 - s0) < 1e-12 else (s - s0) / (s1 - s0)
    return u0 + ratio * (u1 - u0)


def sample_spline_equal_distance_2d(
    points: Sequence[Tuple[float, float]],
    samples: int = 100,
) -> List[Tuple[float, float]]:
    """Sample spline at evenly spaced arc-length increments for visual drawing."""
    if len(points) <= 1:
        return list(points)
    table = build_arc_length_table_2d(points)
    cnt = max(2, samples)
    return [
        catmull_rom_point_2d(points, u_from_s(table, (i / (cnt - 1)) * table.total_length))
        for i in range(cnt)
    ]
