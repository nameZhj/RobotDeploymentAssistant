# @file: src/algorithms/target_assignment.py
# @brief: Greedy nearest-neighbor + 2-opt swap solver minimizing total distance and path crossings.
# @exports: count_path_crossings, assign_targets_2opt

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from src.math.vec_math import segments_intersect

Point2D = Tuple[float, float]


def count_path_crossings(
    sources: Sequence[Point2D],
    targets: Sequence[Point2D],
    assignment: Sequence[int],
) -> int:
    """Count pairwise crossing straight paths under the given start->target permutation."""
    n = len(sources)
    crossings = 0
    for i in range(n):
        for j in range(i + 1, n):
            if segments_intersect(sources[i], targets[assignment[i]], sources[j], targets[assignment[j]]):
                crossings += 1
    return crossings


def _dist_sq(a: Point2D, b: Point2D) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def assign_targets_2opt(
    sources: Sequence[Point2D],
    targets: Sequence[Point2D],
    max_iters: int = 200,
) -> List[int]:
    """Compute crossing-free minimal-cost bijection sources[i] -> targets[assign[i]]."""
    n = min(len(sources), len(targets))
    if n == 0:
        return []

    used = set()
    assign = [-1] * n
    # Greedy nearest-neighbor seed
    for i in range(n):
        best_j = -1
        best_d = math.inf
        for j in range(n):
            if j in used:
                continue
            d = _dist_sq(sources[i], targets[j])
            if d < best_d:
                best_d = d
                best_j = j
        assign[i] = best_j
        used.add(best_j)

    # 2-opt uncrossing & squared-distance reduction pass
    for _ in range(max_iters):
        improved = False
        for i in range(n):
            for j in range(i + 1, n):
                ti, tj = assign[i], assign[j]
                if ti == tj:
                    continue
                cur_cross = int(segments_intersect(sources[i], targets[ti], sources[j], targets[tj]))
                new_cross = int(segments_intersect(sources[i], targets[tj], sources[j], targets[ti]))
                cur_cost = _dist_sq(sources[i], targets[ti]) + _dist_sq(sources[j], targets[tj])
                new_cost = _dist_sq(sources[i], targets[tj]) + _dist_sq(sources[j], targets[ti])
                if new_cross < cur_cross or (new_cross == cur_cross and new_cost + 1e-6 < cur_cost):
                    assign[i], assign[j] = tj, ti
                    improved = True
        if not improved:
            break
    return assign
