# @file: src/algorithms/scatter_stage.py
# @brief: Two-ring radial intermediate scatter formation breaking high-crossing deadlocks in swarm transitions.
# @exports: CROSSING_THRESHOLD, generate_scatter_positions

from __future__ import annotations

import math
from typing import List, Tuple

Point2D = Tuple[float, float]
CROSSING_THRESHOLD = 30


def generate_scatter_positions(
    count: int,
    outer_radius: float = 2.8,
    inner_radius: float = 1.4,
    center: Point2D = (0.0, 0.0),
) -> List[Point2D]:
    """Generate two-ring outer(65%) + inner(35%) scatter waypoints matching UniUni algorithms-RYCS08SV."""
    n = max(1, count)
    outer = math.ceil(n * 0.65)
    inner = n - outer
    cx, cy = center
    positions: List[Point2D] = []
    for i in range(outer):
        angle = 2.0 * math.pi * i / outer - math.pi * 0.5
        positions.append((round(cx + outer_radius * math.cos(angle), 4), round(cy + outer_radius * math.sin(angle), 4)))
    if inner > 0:
        for i in range(inner):
            angle = 2.0 * math.pi * i / inner - math.pi * 0.5 + math.pi / inner
            positions.append((round(cx + inner_radius * math.cos(angle), 4), round(cy + inner_radius * math.sin(angle), 4)))
    return positions
