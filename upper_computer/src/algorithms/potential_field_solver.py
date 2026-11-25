# @file: src/algorithms/potential_field_solver.py
# @brief: stage potential-field collision-free swarm trajectory planner with 3-pass safety projection and RDP simplification.
# @exports: PotentialFieldParams, SwarmSimulationResult, rdp_simplify, compute_segment_times, solve_swarm_potential_field

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import List, Optional, Sequence, Tuple

from src.algorithms.spatial_hash_grid import SpatialHashGrid
from src.algorithms.target_assignment import assign_targets_2opt

Point2D = Tuple[float, float]


@dataclass
class PotentialFieldParams:
    """Tuning gains matching standard stage specs RobotAction & algorithms-RYCS08SV solver."""

    safety_dist: float = 0.60
    repel_range: float = 1.20
    k_attract: float = 3.0
    k_repel: float = 9.0
    k_avoid: float = 2.0
    max_speed: float = 1.5
    sim_dt: float = 0.02
    max_frames: int = 3000
    arrival_threshold: float = 0.05
    sync_arrival: bool = True
    rdp_epsilon: float = 0.03


@dataclass
class SwarmSimulationResult:
    """Simulated collision-free trajectories, simplified RDP knots, and min separation metrics."""

    raw_paths: List[List[Point2D]]
    simplified_knots: List[List[Point2D]]
    assignment: List[int]
    min_distance: float
    min_pair: Tuple[int, int]
    total_sim_time: float
    converged: bool = True


def rdp_simplify(pts: Sequence[Point2D], eps: float = 0.02) -> List[Point2D]:
    """Ramer-Douglas-Peucker polyline simplifier preserving key obstacle-avoidance bends."""
    if len(pts) <= 2:
        return list(pts)
    first, last = pts[0], pts[-1]
    dx, dy = last[0] - first[0], last[1] - first[1]
    len_sq = dx * dx + dy * dy
    max_dist, max_idx = 0.0, 0
    for i in range(1, len(pts) - 1):
        if len_sq < 1e-12:
            dist = math.hypot(pts[i][0] - first[0], pts[i][1] - first[1])
        else:
            t = max(0.0, min(1.0, ((pts[i][0] - first[0]) * dx + (pts[i][1] - first[1]) * dy) / len_sq))
            dist = math.hypot(pts[i][0] - (first[0] + t * dx), pts[i][1] - (first[1] + t * dy))
        if dist > max_dist:
            max_dist = dist
            max_idx = i
    if max_dist > eps:
        left = rdp_simplify(pts[: max_idx + 1], eps)
        right = rdp_simplify(pts[max_idx:], eps)
        return left[:-1] + right
    return [first, last]


def compute_segment_times(key_pts: Sequence[Point2D], max_acc: float = 1.5, max_speed: float = 3.0) -> List[float]:
    """Compute cumulative kinematic timestamps for each simplified waypoint."""
    times = [0.0]
    acc = max_acc if max_acc > 0.0 else 1.5
    spd = max_speed if max_speed > 0.0 else 3.0
    accel_t = spd / acc
    accel_d = acc * accel_t * accel_t
    elapsed = 0.0
    for k in range(1, len(key_pts)):
        seg_len = math.hypot(key_pts[k][0] - key_pts[k - 1][0], key_pts[k][1] - key_pts[k - 1][1])
        seg_t = (accel_t * 2.0 + (seg_len - accel_d) / spd) if seg_len >= accel_d else 2.0 * math.sqrt(seg_len / acc)
        elapsed += max(seg_t, 0.1)
        times.append(round(elapsed, 4))
    return times


def _norm2(vx: float, vy: float) -> Tuple[float, float, float]:
    length = math.hypot(vx, vy)
    if length <= 1e-10:
        return (0.0, 0.0, 0.0)
    return (vx / length, vy / length, length)


def solve_swarm_potential_field(
    sources: Sequence[Point2D],
    targets: Sequence[Point2D],
    assignment: Optional[Sequence[int]] = None,
    params: Optional[PotentialFieldParams] = None,
) -> SwarmSimulationResult:
    """Run stage artificial potential-field swarm simulation with tangential avoidance & 3-pass projection."""
    p = params or PotentialFieldParams()
    n = min(len(sources), len(targets))
    if n == 0:
        return SwarmSimulationResult([], [], [], math.inf, (-1, -1), 0.0, True)

    assign = list(assignment) if assignment is not None else assign_targets_2opt(sources, targets)
    pos = [[float(x), float(y)] for x, y in sources[:n]]
    raw_frames: List[List[Point2D]] = []
    grid = SpatialHashGrid(max(p.repel_range, p.safety_dist) + 0.02)
    min_dist = math.inf
    min_pair = (-1, -1)
    converged = False

    for step in range(p.max_frames):
        raw_frames.append([(pt[0], pt[1]) for pt in pos])
        remains = [math.hypot(targets[assign[i]][0] - pos[i][0], targets[assign[i]][1] - pos[i][1]) for i in range(n)]
        max_rem = max(remains)
        if max_rem <= p.arrival_threshold:
            converged = True
            break

        grid.rebuild([(pt[0], pt[1]) for pt in pos])
        progress = min(step / 400.0, 1.0)
        cur_repel = max(p.safety_dist * 1.1, p.repel_range * (1.0 - progress * 0.45))
        cur_max = p.max_speed + progress * 1.0

        vels: List[Tuple[float, float]] = []
        for i in range(n):
            tx, ty = targets[assign[i]]
            dx, dy = tx - pos[i][0], ty - pos[i][1]
            ux, uy, d_t = _norm2(dx, dy)
            if d_t <= p.arrival_threshold * 0.5:
                vels.append((0.0, 0.0))
                continue
            sync_scale = max(d_t / max_rem, 0.1) if (p.sync_arrival and max_rem > p.arrival_threshold * 2.0) else 1.0
            k_cur = p.k_attract + progress * 3.0
            spd = max(min(d_t * k_cur, cur_max), 0.18) * sync_scale
            vx, vy = ux * spd, uy * spd

            for j in grid.query_neighbors(pos[i][0], pos[i][1]):
                if i == j:
                    continue
                rx, ry, d = _norm2(pos[i][0] - pos[j][0], pos[i][1] - pos[j][1])
                if 1e-9 < d < cur_repel:
                    ratio = (cur_repel - d) / cur_repel
                    f_rep = p.k_repel * ratio * ratio
                    vx += rx * f_rep
                    vy += ry * f_rep
                    # Right-hand tangential swirl breaks head-on deadlocks cleanly
                    vx += -ry * (p.k_avoid * ratio)
                    vy += rx * (p.k_avoid * ratio)

            nx, ny, sp = _norm2(vx, vy)
            cap = cur_max * sync_scale
            if sp > cap and sp > 1e-10:
                vx, vy = nx * cap, ny * cap
            vels.append((vx, vy))

        for i in range(n):
            pos[i][0] += vels[i][0] * p.sim_dt
            pos[i][1] += vels[i][1] * p.sim_dt

        for _ in range(3):
            grid.rebuild([(pt[0], pt[1]) for pt in pos])
            for i in range(n):
                for j in grid.query_neighbors(pos[i][0], pos[i][1]):
                    if j <= i:
                        continue
                    rx, ry, d = _norm2(pos[i][0] - pos[j][0], pos[i][1] - pos[j][1])
                    if 1e-9 < d < p.safety_dist:
                        push = (p.safety_dist - d) * 0.55
                        pos[i][0] += rx * push
                        pos[i][1] += ry * push
                        pos[j][0] -= rx * push
                        pos[j][1] -= ry * push

        for i in range(n):
            for j in range(i + 1, n):
                d = math.hypot(pos[i][0] - pos[j][0], pos[i][1] - pos[j][1])
                if d < min_dist:
                    min_dist = d
                    min_pair = (i, j)

    # 25-frame Hermite smooth landing to exact targets
    snap = [(pt[0], pt[1]) for pt in pos]
    for f in range(1, 26):
        e = f / 25.0
        h = e * e * (3.0 - 2.0 * e)
        frame = [
            (
                snap[i][0] + (targets[assign[i]][0] - snap[i][0]) * h,
                snap[i][1] + (targets[assign[i]][1] - snap[i][1]) * h,
            )
            for i in range(n)
        ]
        raw_frames.append(frame)

    raw_paths = [[frame[i] for frame in raw_frames] for i in range(n)]
    knots = [rdp_simplify(path, eps=p.rdp_epsilon) for path in raw_paths]
    total_t = round(len(raw_frames) * p.sim_dt, 3)
    return SwarmSimulationResult(
        raw_paths=raw_paths,
        simplified_knots=knots,
        assignment=assign,
        min_distance=round(min_dist, 4) if math.isfinite(min_dist) else p.safety_dist,
        min_pair=min_pair,
        total_sim_time=total_t,
        converged=converged,
    )
