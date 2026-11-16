# @file: src/math/s_curve_profile.py
# @brief: 7-segment jerk-limited S-curve velocity profile and physical minimum duration calculator matching UniUni.
# @exports: SmoothProfile, compute_min_execution_time, build_time_frames, build_smooth_profile

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import List

from src.math.vec_math import clamp

DEFAULT_ACCEL_RATIO = 0.2
DEFAULT_JERK_RATIO = 0.3
DEFAULT_DT_FINE = 0.02


@dataclass
class SmoothProfile:
    """Pre-integrated 7-segment jerk-limited S-curve position and velocity profile."""

    total_time: float
    time_table: List[float]
    speed_table: List[float]
    acc_table: List[float]
    dist_table: List[float]

    def s_at(self, t: float) -> float:
        return _sample_table(self.time_table, self.dist_table, t, self.total_time)

    def v_at(self, t: float) -> float:
        return _sample_table(self.time_table, self.speed_table, t, self.total_time)


def compute_min_execution_time(
    length: float,
    accel: float = 1.5,
    max_speed: float = 3.0,
) -> float:
    """Compute physical lower-bound duration T_min for traversing path length under accel/speed caps."""
    if not math.isfinite(length) or length <= 0.0:
        return 0.0
    safe_acc = accel if accel > 0.0 else 1.5
    safe_spd = max_speed if max_speed > 0.0 else 3.0
    acc_time = safe_spd / safe_acc
    acc_dist = safe_acc * acc_time * acc_time
    if length >= acc_dist:
        cruise_dist = length - acc_dist
        return acc_time * 2.0 + cruise_dist / safe_spd
    return 2.0 * math.sqrt(length / safe_acc)


def build_time_frames(total_time: float, step: float) -> List[float]:
    """Generate uniform frame timestamps covering [0, total_time]."""
    safe_total = max(0.0, float(total_time))
    safe_step = step if step > 0.0 else max(safe_total, 0.02)
    frames: List[float] = []
    t = 0.0
    while t < safe_total - 1e-9:
        frames.append(round(t, 6))
        t += safe_step
    if not frames or abs(frames[-1] - safe_total) > 1e-6:
        frames.append(round(safe_total, 6))
    return frames


def _sample_table(t_axis: List[float], values: List[float], t: float, total_time: float) -> float:
    if not values or not t_axis:
        return 0.0
    clamped = clamp(t, 0.0, total_time)
    if clamped <= t_axis[0]:
        return values[0]
    if clamped >= total_time:
        return values[-1]
    left = 0
    right = len(t_axis) - 1
    while right - left > 1:
        mid = (left + right) >> 1
        if t_axis[mid] > clamped:
            right = mid
        else:
            left = mid
    t0, t1 = t_axis[left], t_axis[right]
    ratio = 0.0 if abs(t1 - t0) < 1e-12 else (clamped - t0) / (t1 - t0)
    return values[left] + (values[right] - values[left]) * ratio


def build_smooth_profile(
    total_length: float,
    total_time: float = 5.0,
    accel_ratio: float = DEFAULT_ACCEL_RATIO,
    jerk_ratio: float = DEFAULT_JERK_RATIO,
    dt_fine: float = DEFAULT_DT_FINE,
) -> SmoothProfile:
    """Integrate normalized 7-segment jerk-limited acceleration curve and scale to total_length."""
    t_tot = max(0.05, float(total_time))
    t_acc = clamp(accel_ratio, 0.05, 0.48) * t_tot
    t_jerk = clamp(jerk_ratio, 0.05, 0.49) * t_acc
    t_flat_acc = max(0.0, t_acc - 2.0 * t_jerk)
    t_const = max(0.0, t_tot - 2.0 * t_acc)
    t_smooth = build_time_frames(t_tot, dt_fine)

    def a_unit(t: float) -> float:
        if t < t_jerk:
            return t / t_jerk
        if t < t_jerk + t_flat_acc:
            return 1.0
        if t < t_acc:
            return 1.0 - (t - (t_jerk + t_flat_acc)) / t_jerk
        if t < t_acc + t_const:
            return 0.0
        if t < t_acc + t_const + t_jerk:
            return -(t - (t_acc + t_const)) / t_jerk
        if t < t_acc + t_const + t_jerk + t_flat_acc:
            return -1.0
        return -1.0 + (t - (t_acc + t_const + t_jerk + t_flat_acc)) / t_jerk

    a_u = [a_unit(t) for t in t_smooth]
    v_u: List[float] = []
    s_u: List[float] = []
    v = 0.0
    s = 0.0
    for idx, acc_val in enumerate(a_u):
        step_dt = dt_fine if idx == 0 else max(1e-6, t_smooth[idx] - t_smooth[idx - 1])
        v += acc_val * step_dt
        s += v * step_dt
        v_u.append(v)
        s_u.append(s)

    s_max = s_u[-1] if s_u and s_u[-1] > 1e-12 else 1.0
    scale = total_length / s_max if total_length > 0.0 else 0.0
    return SmoothProfile(
        total_time=t_tot,
        time_table=t_smooth,
        speed_table=[val * scale for val in v_u],
        acc_table=[acc_val * scale for acc_val in a_u],
        dist_table=[s_val * scale for s_val in s_u],
    )
