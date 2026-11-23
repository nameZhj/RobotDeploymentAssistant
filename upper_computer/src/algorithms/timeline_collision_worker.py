# @file: src/algorithms/timeline_collision_worker.py
# @brief: Multi-robot timeline collision detector sampling every 0.05s and outputting red warning intervals.
# @exports: CollisionInterval, detect_timeline_collisions

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, List, Sequence, Tuple
import numpy as np

from src.domain.timeline_entities import TimelineBlockEntity
from src.domain.track_entities import TrackEntity
from src.domain.trajectory_entities import TrajectoryEntity
from src.math.trajectory_sampler import evaluate_trajectory_pose, sample_trajectory_50fps
from src.persistence.csv_point_codec import CsvPointCodec


@dataclass
class CollisionInterval:
    """Merged timeline interval during which pairwise separation falls below safety_dist."""

    start: float
    end: float
    robots: Tuple[str, str]
    min_dist: float

    @property
    def start_time(self) -> float:
        return self.start

    @property
    def end_time(self) -> float:
        return self.end

    @property
    def track_a(self) -> str:
        return self.robots[0]

    @property
    def track_b(self) -> str:
        return self.robots[1]

    def to_dict(self) -> Dict[str, object]:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "robots": f"{self.robots[0]} ↔ {self.robots[1]}",
            "minDist": round(self.min_dist, 3),
        }


def _prepare_sampled_trajs(
    trajectories: Dict[int, TrajectoryEntity],
) -> Dict[int, np.ndarray]:
    cache: Dict[int, np.ndarray] = {}
    for tid, traj in trajectories.items():
        if traj.point_data_csv:
            arr = CsvPointCodec.decode_points(traj.point_data_csv)
            if len(arr) >= 2:
                cache[tid] = arr
                continue
        arr, _ = sample_trajectory_50fps(traj)
        cache[tid] = arr
    return cache


def _robot_xy_at(
    track: TrackEntity,
    blocks: Sequence[TimelineBlockEntity],
    sampled_trajs: Dict[int, np.ndarray],
    t: float,
) -> Tuple[float, float]:
    """Evaluate (x, y) holding the last executed trajectory endpoint when idle per collision.worker.js."""
    last_end_xy = (track.init_x, track.init_y)
    for blk in blocks:
        if blk.is_ignored or blk.block_type != "trajectory":
            continue
        samples = sampled_trajs.get(blk.ref_id)
        if samples is None or len(samples) == 0:
            continue
        if blk.start_time <= t <= blk.end_time:
            x, y, _ = evaluate_trajectory_pose(samples, t - blk.start_time)
            return (x, y)
        if blk.end_time < t:
            last_end_xy = (float(samples[-1, 1]), float(samples[-1, 2]))
    return last_end_xy


def detect_timeline_collisions(
    tracks: Sequence[TrackEntity],
    blocks: Sequence[TimelineBlockEntity],
    trajectories: Dict[int, TrajectoryEntity],
    safety_dist: float = 0.60,
    time_step: float = 0.05,
) -> List[CollisionInterval]:
    """Scan all active robot tracks at 0.05s steps and merge pairwise separation violations."""
    if len(tracks) < 2:
        return []
    sampled = _prepare_sampled_trajs(trajectories)
    blocks_by_track: Dict[int, List[TimelineBlockEntity]] = {}
    max_end = 0.0
    for blk in blocks:
        if blk.is_ignored:
            continue
        blocks_by_track.setdefault(blk.track_id, []).append(blk)
        max_end = max(max_end, blk.end_time)
    for blks in blocks_by_track.values():
        blks.sort(key=lambda b: b.start_time)

    if max_end <= 0.0:
        return []

    active_open: Dict[Tuple[int, int], CollisionInterval] = {}
    finished: List[CollisionInterval] = []
    dt = max(0.01, time_step)
    t = 0.0
    while t <= max_end + 1e-6:
        xy_map = {
            i: _robot_xy_at(tracks[i], blocks_by_track.get(tracks[i].id or -1, ()), sampled, t)
            for i in range(len(tracks))
        }
        for i in range(len(tracks)):
            for j in range(i + 1, len(tracks)):
                d = math.hypot(xy_map[i][0] - xy_map[j][0], xy_map[i][1] - xy_map[j][1])
                pair_key = (i, j)
                if d < safety_dist:
                    if pair_key in active_open:
                        cur = active_open[pair_key]
                        cur.end = t + dt
                        cur.min_dist = min(cur.min_dist, d)
                    else:
                        active_open[pair_key] = CollisionInterval(
                            start=t,
                            end=t + dt,
                            robots=(tracks[i].name, tracks[j].name),
                            min_dist=d,
                        )
                elif pair_key in active_open:
                    finished.append(active_open.pop(pair_key))
        t += dt

    finished.extend(active_open.values())
    finished.sort(key=lambda seg: seg.start)
    return finished
