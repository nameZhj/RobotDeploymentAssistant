"""
@file: src/domain/timeline/beat_and_collision_service.py
@brief: BPM 小节节拍双向换算器、全场位姿导出与多机时空碰撞安全扫描服务
@exports: BpmTimeConverter, export_current_positions, scan_multi_robot_collisions
"""
import math
from typing import Any, Dict, List, Optional, Tuple
from src.domain.trajectory.anchor_pose_resolver import sample_robot_world_pose_at


class BpmTimeConverter:
    """音乐 BPM 与小节.拍数 (如 003.2) 双向换算器"""

    def __init__(self, bpm: float = 120.0, beat_numerator: int = 4, beat_denominator: int = 4) -> None:
        self.bpm = max(10.0, float(bpm))
        self.numerator = max(1, int(beat_numerator))
        self.denominator = max(1, int(beat_denominator))

    @property
    def seconds_per_beat(self) -> float:
        return 60.0 / self.bpm

    def sec_to_measure_beat(self, sec: float) -> str:
        s = max(0.0, float(sec))
        total_beats = s / self.seconds_per_beat
        measure = int(total_beats // self.numerator) + 1
        beat_in_measure = (total_beats % self.numerator) + 1.0
        b_val = int(beat_in_measure) if abs(beat_in_measure - round(beat_in_measure)) < 1e-4 else round(beat_in_measure, 1)
        return f"{measure:03d}.{b_val}"

    def measure_beat_to_sec(self, mb_str: str) -> float:
        clean = mb_str.strip()
        parts = clean.split(".")
        if len(parts) >= 2:
            measure = max(1, int(parts[0]))
            beat = max(1.0, float(parts[1]))
            total_beats = (measure - 1) * self.numerator + (beat - 1.0)
            return round(total_beats * self.seconds_per_beat, 3)
        return 0.0


def export_current_positions(
    t_sec: float,
    robot_ids: List[int],
    init_points: List[Dict[str, Any]],
    track_state: List[Dict[str, Any]],
    traj_dict_map: Dict[int, Any]
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for rid in robot_ids:
        pose = sample_robot_world_pose_at(rid, t_sec, init_points, track_state, traj_dict_map)
        results.append({
            "robot_id": rid,
            "x": pose["x"],
            "y": pose["y"],
            "yaw": pose["yaw"],
            "is_moving": pose["is_moving"]
        })
    return results


def scan_multi_robot_collisions(
    total_duration_s: float,
    robot_ids: List[int],
    init_points: List[Dict[str, Any]],
    track_state: List[Dict[str, Any]],
    traj_dict_map: Dict[int, Any],
    step_s: float = 0.05,
    safe_radius_m: float = 0.65
) -> List[Dict[str, Any]]:
    if len(robot_ids) < 2 or total_duration_s <= 0:
        return []

    collisions_raw: List[Tuple[float, int, int, float]] = []
    n_steps = int(math.ceil(total_duration_s / step_s)) + 1

    for step_idx in range(n_steps):
        t = min(step_idx * step_s, total_duration_s)
        poses = {}
        for rid in robot_ids:
            p = sample_robot_world_pose_at(rid, t, init_points, track_state, traj_dict_map)
            poses[rid] = (p["x"], p["y"])

        for i in range(len(robot_ids)):
            for j in range(i + 1, len(robot_ids)):
                r1, r2 = robot_ids[i], robot_ids[j]
                p1, p2 = poses[r1], poses[r2]
                dist = math.hypot(p1[0] - p2[0], p1[1] - p2[1])
                if dist < safe_radius_m:
                    pair = (min(r1, r2), max(r1, r2))
                    collisions_raw.append((t, pair[0], pair[1], dist))

    if not collisions_raw:
        return []

    intervals: List[Dict[str, Any]] = []
    by_pair: Dict[Tuple[int, int], List[Tuple[float, float]]] = {}
    for t, r1, r2, dist in collisions_raw:
        by_pair.setdefault((r1, r2), []).append((t, dist))

    for (r1, r2), events in by_pair.items():
        events.sort(key=lambda x: x[0])
        start_t = end_t = events[0][0]
        min_d = events[0][1]

        for t_val, d_val in events[1:]:
            if t_val - end_t <= step_s * 1.5:
                end_t = t_val
                min_d = min(min_d, d_val)
            else:
                pct = round(start_t / max(total_duration_s, 1e-4) * 100.0, 1)
                intervals.append({
                    "robot_a": r1, "robot_b": r2,
                    "start_s": round(start_t, 2), "end_s": round(end_t, 2),
                    "min_dist_m": round(min_d, 3), "progress_percent": pct
                })
                start_t = end_t = t_val
                min_d = d_val

        pct = round(start_t / max(total_duration_s, 1e-4) * 100.0, 1)
        intervals.append({
            "robot_a": r1, "robot_b": r2,
            "start_s": round(start_t, 2), "end_s": round(end_t, 2),
            "min_dist_m": round(min_d, 3), "progress_percent": pct
        })

    intervals.sort(key=lambda x: x["start_s"])
    return intervals

