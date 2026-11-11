"""
@file: src/domain/trajectory/spline_builder.py
@brief: 向心 Catmull-Rom 样条拟合、弧长均匀化插值、起点锚定定律与轨迹反转编译器
@exports: SplineTrajectoryBuilder, resolve_anchor_pose
"""
import math
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np


class SplineTrajectoryBuilder:
    """提供基于向心样条、折线插值、梯形加减速与起点锚定定律的高精度轨迹生成"""

    @staticmethod
    def _catmull_rom_segment(p0: np.ndarray, p1: np.ndarray,
                             p2: np.ndarray, p3: np.ndarray,
                             n_samples: int = 50, alpha: float = 0.5) -> np.ndarray:
        t0 = 0.0
        t1 = t0 + max(float(np.linalg.norm(p1 - p0)), 1e-6) ** alpha
        t2 = t1 + max(float(np.linalg.norm(p2 - p1)), 1e-6) ** alpha
        t3 = t2 + max(float(np.linalg.norm(p3 - p2)), 1e-6) ** alpha
        t = np.linspace(t1, t2, n_samples)[:, None]
        a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
        a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
        a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
        b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
        b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
        return (t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2

    @classmethod
    def fit_spline_curve(cls, control_pts: List[Tuple[float, float]],
                         alpha: float = 0.5) -> Tuple[np.ndarray, np.ndarray, float]:
        pts = np.array(control_pts, dtype=np.float32)
        if len(pts) < 2:
            single = pts if len(pts) == 1 else np.zeros((1, 2), dtype=np.float32)
            return single, np.zeros(len(single), dtype=np.float32), 0.0
        if len(pts) == 2:
            dist = float(np.linalg.norm(pts[1] - pts[0]))
            steps = max(10, int(math.ceil(dist / 0.01)))
            curve = np.linspace(pts[0], pts[1], steps).astype(np.float32)
            return curve, np.linspace(0.0, dist, steps).astype(np.float32), dist

        p_start, p_end = 2 * pts[0] - pts[1], 2 * pts[-1] - pts[-2]
        padded = np.vstack([p_start, pts, p_end])
        segments: List[np.ndarray] = []
        for i in range(len(pts) - 1):
            seg_dist = max(float(np.linalg.norm(pts[i + 1] - pts[i])), 1e-4)
            n_sub = max(15, int(math.ceil(seg_dist / 0.01)))
            seg = cls._catmull_rom_segment(padded[i], padded[i + 1], padded[i + 2], padded[i + 3], n_sub, alpha)
            segments.append(seg if i == 0 else seg[1:])
        curve = np.vstack(segments).astype(np.float32)
        dists = np.linalg.norm(np.diff(curve, axis=0), axis=1)
        s_cum = np.insert(np.cumsum(dists), 0, 0.0).astype(np.float32)
        return curve, s_cum, float(s_cum[-1])

    @staticmethod
    def compute_trapezoidal_duration(length_m: float, v_max: float = 1.20,
                                     a_max: float = 1.50) -> float:
        if length_m <= 1e-4:
            return 0.0
        l_crit = (v_max ** 2) / a_max
        dur = (length_m / v_max + v_max / a_max) if length_m >= l_crit else (2.0 * math.sqrt(length_m / a_max))
        return round(float(dur), 2)

    @classmethod
    def evaluate_motion_at_time(cls, t: float, duration_s: float, length_m: float,
                                v_max: float = 1.20, a_max: float = 1.50) -> Tuple[float, float]:
        if duration_s <= 1e-4 or length_m <= 1e-4:
            return 0.0, 0.0
        t_c = max(0.0, min(t, duration_s))
        l_crit = (v_max ** 2) / a_max
        if length_m >= l_crit:
            t_acc = v_max / a_max
            t_cruise = duration_s - 2.0 * t_acc
            if t_c <= t_acc:
                return 0.5 * a_max * (t_c ** 2), a_max * t_c
            if t_c <= t_acc + t_cruise:
                return 0.5 * v_max * t_acc + v_max * (t_c - t_acc), v_max
            dt_dec = duration_s - t_c
            return length_m - 0.5 * a_max * (dt_dec ** 2), a_max * dt_dec
        if t_c <= 0.5 * duration_s:
            return 0.5 * a_max * (t_c ** 2), a_max * t_c
        dt_dec = duration_s - t_c
        return length_m - 0.5 * a_max * (dt_dec ** 2), a_max * dt_dec

    @staticmethod
    def parse_trajectory_data(data_str: str) -> List[Tuple[float, float, float, float]]:
        if not data_str or not data_str.strip():
            return []
        pts: List[Tuple[float, float, float, float]] = []
        for line in data_str.strip().splitlines():
            tokens = [t.strip() for t in line.split(",") if t.strip()]
            if len(tokens) >= 4:
                pts.append((float(tokens[0]), float(tokens[1]), float(tokens[2]), float(tokens[3])))
        return pts

    @staticmethod
    def serialize_trajectory_data(points: List[Tuple[float, float, float, float]]) -> str:
        return "\n".join([f"{p[0]:.2f},{p[1]:.4f},{p[2]:.4f},{p[3]:.2f}" for p in points])

    @classmethod
    def compile_waypoints(
        cls,
        waypoints: List[Tuple[float, float]],
        mode: str = "uniform",
        max_acc: float = 1.5,
        v_max: float = 1.2,
        hold_direction: bool = False,
        hold_direction_yaw: float = 0.0,
        end_turn: bool = False,
        end_turn_yaw: float = 0.0
    ) -> Tuple[List[Tuple[float, float, float, float]], float]:
        if len(waypoints) < 2:
            single = waypoints[0] if waypoints else (0.0, 0.0)
            return [(0.0, single[0], single[1], hold_direction_yaw if hold_direction else 0.0)], 0.0

        if mode.lower() == "uniform":
            curve, _, total_len = cls.fit_spline_curve(waypoints)
        else:
            pts = np.array(waypoints, dtype=np.float32)
            dists = np.linalg.norm(np.diff(pts, axis=0), axis=1)
            total_len = float(np.sum(dists))
            curve = np.linspace(pts[0], pts[-1], max(20, int(math.ceil(total_len / 0.02)))).astype(np.float32)

        dur = cls.compute_trapezoidal_duration(total_len, v_max, max_acc)
        n = len(curve)
        t_steps = np.linspace(0.0, dur, n)
        result: List[Tuple[float, float, float, float]] = []

        for i in range(n):
            x, y = float(curve[i, 0]), float(curve[i, 1])
            if hold_direction:
                yaw = hold_direction_yaw
            elif i < n - 1:
                yaw = math.degrees(math.atan2(curve[i + 1, 1] - curve[i, 1], curve[i + 1, 0] - curve[i, 0]))
            else:
                yaw = result[-1][3] if result else 0.0

            if end_turn and i >= int(n * 0.8):
                alpha = (i - int(n * 0.8)) / max(1, n - 1 - int(n * 0.8))
                diff = (end_turn_yaw - yaw + 180.0) % 360.0 - 180.0
                yaw = (yaw + alpha * diff + 180.0) % 360.0 - 180.0
            result.append((float(t_steps[i]), x, y, float(yaw)))
        return result, dur

    @classmethod
    def reverse_trajectory(
        cls, trajectory: Union[str, List[Tuple[float, float, float, float]]]
    ) -> Union[str, List[Tuple[float, float, float, float]]]:
        is_str = isinstance(trajectory, str)
        pts = cls.parse_trajectory_data(trajectory) if is_str else list(trajectory)
        if len(pts) <= 1:
            return trajectory
        n, dur = len(pts), pts[-1][0]
        rev: List[Tuple[float, float, float, float]] = []
        for idx, orig in enumerate(reversed(pts)):
            t_rev = (idx / (n - 1)) * dur if n > 1 else 0.0
            rev.append((float(t_rev), orig[1], orig[2], float((orig[3] + 360.0) % 360.0 - 180.0)))
        return cls.serialize_trajectory_data(rev) if is_str else rev

    @classmethod
    def resolve_anchor_pose(
        cls,
        robot_id: int,
        target_time_s: Optional[float] = None,
        init_points: Optional[List[Dict[str, Any]]] = None,
        track_state: Optional[List[Dict[str, Any]]] = None,
        traj_map: Optional[Dict[int, Any]] = None,
        **kwargs
    ) -> Tuple[float, float, float]:
        t_target = float(target_time_s if target_time_s is not None else kwargs.get("t_sec", 0.0))
        pts_init = init_points or []
        state_list = track_state or []
        t_map = traj_map or kwargs.get("traj_dict_map", {})

        traj_blocks = [
            b for b in state_list
            if int(b.get("robot_id", 0)) == int(robot_id)
            and int(b.get("ignored", 0)) == 0
            and str(b.get("type", "")) == "trajectory"
            and float(b.get("end_time", 0.0)) <= t_target + 1e-5
        ]

        if traj_blocks:
            traj_blocks.sort(key=lambda b: float(b.get("end_time", 0.0)))
            last_blk = traj_blocks[-1]
            raw_pts = last_blk.get("trajectory_point_data") or t_map.get(int(last_blk.get("no", 0)))
            pts = cls.parse_trajectory_data(raw_pts) if isinstance(raw_pts, str) else (raw_pts or [])
            if pts:
                lp = pts[-1]
                return (float(lp[1]), float(lp[2]), float(lp[3])) if len(lp) >= 4 else (float(lp[0]), float(lp[1]), 0.0)

        for pt in pts_init:
            if int(pt.get("robot_id", 0)) == int(robot_id):
                return float(pt.get("x", 0.0)), float(pt.get("y", 0.0)), float(pt.get("yaw", 0.0))
        return 0.0, 0.0, 0.0


resolve_anchor_pose = SplineTrajectoryBuilder.resolve_anchor_pose
