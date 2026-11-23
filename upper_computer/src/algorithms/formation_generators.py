# @file: src/algorithms/formation_generators.py
# @brief: Parametric 2D multi-robot formation generators (line, circle, grid, wedge, staggered, polygon).
# @exports: FormationKind, generate_formation

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

Point2D = Tuple[float, float]


def transform_points(
    points: Sequence[Point2D],
    center: Point2D = (0.0, 0.0),
    rotation_rad: float = 0.0,
) -> List[Point2D]:
    """Rotate local formation coordinates around origin and translate to center."""
    c = math.cos(rotation_rad)
    s = math.sin(rotation_rad)
    cx, cy = center
    return [(round(cx + x * c - y * s, 4), round(cy + x * s + y * c, 4)) for x, y in points]


def generate_line_formation(count: int, spacing: float = 1.2) -> List[Point2D]:
    n = max(1, count)
    offset = (n - 1) * spacing * 0.5
    return [(i * spacing - offset, 0.0) for i in range(n)]


def generate_circle_formation(count: int, radius: float = 2.5, start_angle: float = -math.pi * 0.5) -> List[Point2D]:
    n = max(1, count)
    r = max(0.3, radius)
    return [
        (r * math.cos(start_angle + 2.0 * math.pi * i / n), r * math.sin(start_angle + 2.0 * math.pi * i / n))
        for i in range(n)
    ]


def generate_grid_formation(count: int, cols: int = 3, spacing: float = 1.2) -> List[Point2D]:
    n = max(1, count)
    safe_cols = max(1, cols)
    rows = max(1, math.ceil(n / safe_cols))
    off_x = (safe_cols - 1) * spacing * 0.5
    off_y = (rows - 1) * spacing * 0.5
    pts: List[Point2D] = []
    for r in range(rows):
        for c in range(safe_cols):
            if len(pts) >= n:
                break
            pts.append((c * spacing - off_x, r * spacing - off_y))
    return pts


def generate_wedge_formation(count: int, spacing: float = 1.2, half_angle_deg: float = 35.0) -> List[Point2D]:
    n = max(1, count)
    ang = math.radians(max(10.0, min(80.0, half_angle_deg)))
    pts: List[Point2D] = [(0.0, spacing * 0.6)]
    for idx in range(1, n):
        rank = (idx + 1) // 2
        side = -1.0 if idx % 2 == 1 else 1.0
        dx = side * rank * spacing * math.sin(ang)
        dy = spacing * 0.6 - rank * spacing * math.cos(ang)
        pts.append((dx, dy))
    return pts


def generate_staggered_formation(count: int, cols: int = 3, spacing: float = 1.2) -> List[Point2D]:
    n = max(1, count)
    safe_cols = max(1, cols)
    rows = max(1, math.ceil(n / safe_cols))
    off_x = (safe_cols - 1) * spacing * 0.5
    off_y = (rows - 1) * spacing * 0.5
    pts: List[Point2D] = []
    for r in range(rows):
        row_shift = spacing * 0.5 if (r % 2 == 1) else 0.0
        for c in range(safe_cols):
            if len(pts) >= n:
                break
            pts.append((c * spacing - off_x + row_shift, r * spacing - off_y))
    return pts


def generate_polygon_formation(count: int, polygon_pts: Sequence[Point2D]) -> List[Point2D]:
    """Resample count evenly spaced formation slots along a closed or open user polygon."""
    n = max(1, count)
    if len(polygon_pts) == 0:
        return [(0.0, 0.0) for _ in range(n)]
    if len(polygon_pts) == 1:
        return [polygon_pts[0] for _ in range(n)]
    cum = [0.0]
    for i in range(1, len(polygon_pts)):
        cum.append(cum[-1] + math.hypot(polygon_pts[i][0] - polygon_pts[i - 1][0], polygon_pts[i][1] - polygon_pts[i - 1][1]))
    total = cum[-1]
    if total < 1e-6:
        return [polygon_pts[0] for _ in range(n)]
    out: List[Point2D] = []
    for idx in range(n):
        target_s = 0.0 if n == 1 else (idx / (n - 1)) * total
        seg = 0
        while seg < len(cum) - 2 and cum[seg + 1] < target_s:
            seg += 1
        seg_len = max(1e-9, cum[seg + 1] - cum[seg])
        alpha = (target_s - cum[seg]) / seg_len
        out.append(
            (
                polygon_pts[seg][0] + (polygon_pts[seg + 1][0] - polygon_pts[seg][0]) * alpha,
                polygon_pts[seg][1] + (polygon_pts[seg + 1][1] - polygon_pts[seg][1]) * alpha,
            )
        )
    return out


def generate_formation(
    kind: str,
    count: int,
    spacing: float = 1.2,
    radius: float = 2.5,
    cols: int = 3,
    center: Point2D = (0.0, 0.0),
    rotation_rad: float = 0.0,
    custom_polygon: Sequence[Point2D] = (),
    text_content: str = "G1",
    text_width_m: float = 5.0,
) -> List[Point2D]:
    """Unified formation dispatcher returning world-space (x, y) target slots."""
    k = kind.strip().lower()
    if k == "line":
        local = generate_line_formation(count, spacing)
    elif k == "circle":
        local = generate_circle_formation(count, radius)
    elif k == "grid":
        local = generate_grid_formation(count, cols, spacing)
    elif k == "wedge":
        local = generate_wedge_formation(count, spacing)
    elif k == "staggered":
        local = generate_staggered_formation(count, cols, spacing)
    elif k == "text":
        from src.algorithms.text_formation import generate_text_formation
        local = generate_text_formation(text_content, count, width_m=max(2.0, text_width_m))
    elif k == "polygon" and custom_polygon:
        return list(generate_polygon_formation(count, custom_polygon))
    else:
        local = generate_grid_formation(count, cols, spacing)
    return transform_points(local, center=center, rotation_rad=rotation_rad)
