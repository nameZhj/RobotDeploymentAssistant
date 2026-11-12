"""
@file: src/domain/trajectory/trajectory_interpolator.py
@brief: 轨迹曲线插值与全状态采样引擎（支持 Linear 与 Catmull-Rom 插值及速度角速度解算）
@exports: TrajectoryInterpolator
"""
import math
from typing import Any, Dict, List, Tuple


class TrajectoryInterpolator:
    """高精度 2D 轨迹插值器，提供 Catmull-Rom 样条拟合与全状态时间微分解算"""

    @classmethod
    def sample_trajectory(
        cls,
        control_points: List[Dict[str, Any]],
        mode: str = "catmull_rom",
        max_velocity: float = 0.8,
        dt: float = 0.05,
    ) -> List[Dict[str, Any]]:
        """
        对控制点进行连续密集重采样，解算 (seq, x, y, yaw, t, vx, vy, wz)
        """
        if not control_points:
            return []
        if len(control_points) == 1:
            p0 = control_points[0]
            return [{
                "seq": 0, "x": float(p0["x"]), "y": float(p0["y"]),
                "yaw": float(p0.get("yaw", 0.0)), "t": 0.0,
                "vx": 0.0, "vy": 0.0, "wz": 0.0,
            }]

        # 1. 插值几何路径点 (x, y)
        raw_pts = [(float(p["x"]), float(p["y"])) for p in control_points]
        if mode == "linear" or len(raw_pts) < 3:
            geom_points = cls._interpolate_linear(raw_pts, step=0.08)
        else:
            geom_points = cls._interpolate_catmull_rom(raw_pts, samples_per_seg=25)

        # 2. 计算累计弧长
        s_list = [0.0]
        for i in range(1, len(geom_points)):
            dx = geom_points[i][0] - geom_points[i - 1][0]
            dy = geom_points[i][1] - geom_points[i - 1][1]
            s_list.append(s_list[-1] + math.hypot(dx, dy))
        total_len = s_list[-1]
        if total_len <= 1e-4:
            total_len = 0.01

        # 3. 规划时间轴
        target_v = max(0.1, min(1.5, float(max_velocity)))
        total_time = max(0.5, total_len / target_v)

        # 4. 固定时间步长采样
        samples: List[Dict[str, Any]] = []
        num_steps = max(2, int(total_time / dt) + 1)
        prev_yaw = float(control_points[0].get("yaw", 0.0))

        for step in range(num_steps):
            t = min(total_time, step * dt)
            dist = (t / total_time) * total_len

            # 二分定位
            idx = cls._find_segment_index(s_list, dist)
            if idx >= len(geom_points) - 1:
                idx = len(geom_points) - 2

            seg_len = s_list[idx + 1] - s_list[idx]
            ratio = (dist - s_list[idx]) / max(1e-5, seg_len)
            x = geom_points[idx][0] + (geom_points[idx + 1][0] - geom_points[idx][0]) * ratio
            y = geom_points[idx][1] + (geom_points[idx + 1][1] - geom_points[idx][1]) * ratio

            dx = geom_points[idx + 1][0] - geom_points[idx][0]
            dy = geom_points[idx + 1][1] - geom_points[idx][1]
            yaw = math.atan2(dy, dx) if math.hypot(dx, dy) > 1e-4 else prev_yaw

            # 速度与角速度
            vx = round(target_v * math.cos(yaw), 4)
            vy = round(target_v * math.sin(yaw), 4)
            delta_yaw = (yaw - prev_yaw + math.pi) % (2.0 * math.pi) - math.pi
            wz = round(delta_yaw / max(0.001, dt), 4)
            prev_yaw = yaw

            samples.append({
                "seq": step,
                "x": round(float(x), 4),
                "y": round(float(y), 4),
                "yaw": round(float(yaw), 4),
                "t": round(float(t), 3),
                "vx": vx, "vy": vy, "wz": wz,
            })

        return samples

    @classmethod
    def _interpolate_linear(cls, points: List[Tuple[float, float]], step: float = 0.08) -> List[Tuple[float, float]]:
        res: List[Tuple[float, float]] = [points[0]]
        for i in range(len(points) - 1):
            p0, p1 = points[i], points[i + 1]
            dist = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            count = max(1, int(dist / step))
            for k in range(1, count + 1):
                r = k / count
                res.append((p0[0] + (p1[0] - p0[0]) * r, p0[1] + (p1[1] - p0[1]) * r))
        return res

    @classmethod
    def _interpolate_catmull_rom(cls, points: List[Tuple[float, float]], samples_per_seg: int = 25) -> List[Tuple[float, float]]:
        pts = [points[0]] + list(points) + [points[-1]]
        out: List[Tuple[float, float]] = []
        for i in range(len(pts) - 3):
            p0, p1, p2, p3 = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
            for step in range(samples_per_seg):
                t = step / float(samples_per_seg)
                t2, t3 = t * t, t * t * t
                x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
                y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
                out.append((x, y))
        out.append(points[-1])
        return out

    @staticmethod
    def _find_segment_index(s_list: List[float], s: float) -> int:
        low, high = 0, len(s_list) - 1
        while low <= high:
            mid = (low + high) // 2
            if s_list[mid] <= s:
                low = mid + 1
            else:
                high = mid - 1
        return max(0, min(high, len(s_list) - 2))
