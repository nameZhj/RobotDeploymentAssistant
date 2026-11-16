# @file: src/math/trajectory_sampler.py
# @brief: 50 FPS trajectory generator and continuous pose evaluator supporting uniform S-curve, linear, holdDirection, and endTurn.
# @exports: sample_trajectory_50fps, evaluate_trajectory_pose, TrajectoryMetrics

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import List, Sequence, Tuple
import numpy as np

from src.domain.trajectory_entities import TrajectoryEntity
from src.math.catmull_rom_spline import (
    build_arc_length_table_2d,
    catmull_rom_point_2d,
    u_from_s,
)
from src.math.s_curve_profile import build_smooth_profile, build_time_frames, compute_min_execution_time
from src.math.vec_math import compute_polyline_length, interpolate_angle, normalize_angle
from src.persistence.csv_point_codec import CsvPointCodec


@dataclass(frozen=True)
class TrajectoryMetrics:
    """Physical metrics derived from a trajectory's path geometry."""

    arc_length: float
    min_execution_time: float
    sample_count: int


def sample_trajectory_50fps(
    traj: TrajectoryEntity,
    fps: int = 50,
    max_speed: float = 3.0,
) -> Tuple[np.ndarray, TrajectoryMetrics]:
    """Sample a TrajectoryEntity at exact 50 FPS into (N, 4) [t, x, y, yaw] array and metrics."""
    ctrl = [(p.x, p.y) for p in traj.control_points]
    if not ctrl:
        arr = np.zeros((1, 4), dtype=np.float64)
        return arr, TrajectoryMetrics(0.0, 0.0, 1)
    if len(ctrl) == 1:
        yaw = traj.hold_yaw if traj.hold_direction else traj.control_points[0].yaw
        arr = np.asarray([[0.0, ctrl[0][0], ctrl[0][1], yaw]], dtype=np.float64)
        return arr, TrajectoryMetrics(0.0, 0.0, 1)

    dt = 1.0 / max(1, fps)
    total_time = max(0.1, float(traj.duration))
    t_frames = build_time_frames(total_time, dt)

    if traj.interpolation_mode == "linear":
        arc_len = compute_polyline_length(ctrl)
        pts_xy = _sample_linear(ctrl, t_frames, total_time)
    else:
        table = build_arc_length_table_2d(ctrl)
        arc_len = table.total_length
        profile = build_smooth_profile(arc_len, total_time=total_time)
        pts_xy = [
            catmull_rom_point_2d(ctrl, u_from_s(table, profile.s_at(t)))
            for t in t_frames
        ]

    yaws = _build_yaw_sequence(pts_xy, traj, t_frames, total_time)
    arr = np.column_stack(
        [
            np.asarray(t_frames, dtype=np.float64),
            np.asarray([p[0] for p in pts_xy], dtype=np.float64),
            np.asarray([p[1] for p in pts_xy], dtype=np.float64),
            np.asarray(yaws, dtype=np.float64),
        ]
    )
    t_min = compute_min_execution_time(arc_len, accel=traj.max_acc, max_speed=max_speed)
    traj.point_data_csv = CsvPointCodec.encode_points(arr)
    return arr, TrajectoryMetrics(round(arc_len, 4), round(t_min, 3), len(arr))


def evaluate_trajectory_pose(samples: np.ndarray, local_t: float) -> Tuple[float, float, float]:
    """Interpolate (x, y, yaw) at local elapsed time t in [0, duration] from sampled array."""
    if len(samples) == 0:
        return (0.0, 0.0, 0.0)
    if len(samples) == 1 or local_t <= samples[0, 0]:
        return (float(samples[0, 1]), float(samples[0, 2]), float(samples[0, 3]))
    if local_t >= samples[-1, 0]:
        return (float(samples[-1, 1]), float(samples[-1, 2]), float(samples[-1, 3]))

    t_col = samples[:, 0]
    idx = int(np.searchsorted(t_col, local_t, side="right")) - 1
    idx = max(0, min(idx, len(samples) - 2))
    t0, t1 = float(t_col[idx]), float(t_col[idx + 1])
    alpha = 0.0 if abs(t1 - t0) < 1e-12 else (local_t - t0) / (t1 - t0)
    x = float(samples[idx, 1] + (samples[idx + 1, 1] - samples[idx, 1]) * alpha)
    y = float(samples[idx, 2] + (samples[idx + 1, 2] - samples[idx, 2]) * alpha)
    yaw = interpolate_angle(float(samples[idx, 3]), float(samples[idx + 1, 3]), alpha)
    return (x, y, yaw)


def _sample_linear(
    ctrl: Sequence[Tuple[float, float]],
    t_frames: List[float],
    total_time: float,
) -> List[Tuple[float, float]]:
    cum = [0.0]
    for i in range(1, len(ctrl)):
        cum.append(cum[-1] + math.hypot(ctrl[i][0] - ctrl[i - 1][0], ctrl[i][1] - ctrl[i - 1][1]))
    total_len = cum[-1]
    if total_len <= 1e-9:
        return [ctrl[0] for _ in t_frames]
    out: List[Tuple[float, float]] = []
    for t in t_frames:
        target_s = (t / total_time) * total_len
        seg = 0
        while seg < len(cum) - 2 and cum[seg + 1] < target_s:
            seg += 1
        seg_len = max(1e-9, cum[seg + 1] - cum[seg])
        alpha = (target_s - cum[seg]) / seg_len
        x = ctrl[seg][0] + (ctrl[seg + 1][0] - ctrl[seg][0]) * alpha
        y = ctrl[seg][1] + (ctrl[seg + 1][1] - ctrl[seg][1]) * alpha
        out.append((x, y))
    return out


def _build_yaw_sequence(
    pts: List[Tuple[float, float]],
    traj: TrajectoryEntity,
    t_frames: List[float],
    total_time: float,
) -> List[float]:
    n = len(pts)
    if traj.hold_direction:
        return [float(traj.hold_yaw)] * n

    yaws: List[float] = []
    for i in range(n):
        if i + 1 < n and math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) > 1e-6:
            yaws.append(math.atan2(pts[i + 1][1] - pts[i][1], pts[i + 1][0] - pts[i][0]))
        elif i > 0 and math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]) > 1e-6:
            yaws.append(math.atan2(pts[i][1] - pts[i - 1][1], pts[i][0] - pts[i - 1][0]))
        elif traj.control_points:
            yaws.append(float(traj.control_points[0].yaw))
        else:
            yaws.append(0.0)

    if traj.end_turn and n >= 2:
        blend_window = min(1.0, total_time * 0.25)
        t_blend_start = total_time - blend_window
        for i, t in enumerate(t_frames):
            if t >= t_blend_start:
                alpha = (t - t_blend_start) / max(1e-6, blend_window)
                yaws[i] = interpolate_angle(yaws[i], float(traj.end_yaw), alpha)
    return [normalize_angle(y) for y in yaws]
