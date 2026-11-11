"""
UGC 轨迹几何平滑采样与多机时间轴防碰撞安全校验引擎
"""
import math
from typing import Any, Dict, List, Optional, Tuple


class UgcSafetyGuard:
    """轨迹几何平滑计算与多机碰撞检测守卫"""

    @classmethod
    def compute_duration(cls, waypoints: List[Tuple[float, float]], speed: float = 0.6) -> float:
        """
        计算手绘折线航点的实际耗时 (秒，保留 2 位小数)
        duration = total_length / speed
        """
        if len(waypoints) < 2:
            return 1.00

        total_length = 0.0
        for i in range(len(waypoints) - 1):
            dx = waypoints[i + 1][0] - waypoints[i][0]
            dy = waypoints[i + 1][1] - waypoints[i][1]
            total_length += math.hypot(dx, dy)

        v = max(speed, 0.05)
        duration = max(total_length / v, 0.50)
        return round(duration, 2)

    @classmethod
    def sample_trajectory(cls, waypoints: List[Tuple[float, float]],
                          speed: float = 0.6,
                          dt: float = 0.05) -> List[Dict[str, float]]:
        """
        对航点序列进行时间参数化平滑插值采样
        返回 [{'x': x, 'y': y, 't': t}, ...]
        """
        if not waypoints:
            return []
        if len(waypoints) == 1:
            return [{"x": round(waypoints[0][0], 4), "y": round(waypoints[0][1], 4), "t": 0.0}]

        duration = cls.compute_duration(waypoints, speed)

        # 计算各线段累计弧长
        seg_lengths = []
        total_len = 0.0
        for i in range(len(waypoints) - 1):
            L = math.hypot(waypoints[i + 1][0] - waypoints[i][0], waypoints[i + 1][1] - waypoints[i][1])
            seg_lengths.append(L)
            total_len += L

        samples: List[Dict[str, float]] = []
        num_steps = max(int(duration / dt), 1)

        for step in range(num_steps + 1):
            curr_t = min(step * dt, duration)
            ratio = curr_t / duration if duration > 0 else 1.0
            dist_target = ratio * total_len

            accum = 0.0
            x, y = waypoints[-1][0], waypoints[-1][1]
            for i, seg_l in enumerate(seg_lengths):
                if accum + seg_l >= dist_target or i == len(seg_lengths) - 1:
                    local_r = (dist_target - accum) / seg_l if seg_l > 1e-6 else 0.0
                    local_r = max(0.0, min(1.0, local_r))
                    p0 = waypoints[i]
                    p1 = waypoints[i + 1]
                    x = p0[0] + (p1[0] - p0[0]) * local_r
                    y = p0[1] + (p1[1] - p0[1]) * local_r
                    break
                accum += seg_l

            samples.append({"x": round(x, 4), "y": round(y, 4), "t": round(curr_t, 3)})

        return samples

    @classmethod
    def interpolate_position(cls, samples: List[Dict[str, float]], t: float) -> Tuple[float, float]:
        """查询时间戳 t 对应的插值坐标 (x, y)"""
        if not samples:
            return 0.0, 0.0
        if t <= samples[0]["t"]:
            return samples[0]["x"], samples[0]["y"]
        if t >= samples[-1]["t"]:
            return samples[-1]["x"], samples[-1]["y"]

        # 二分查找
        low, high = 0, len(samples) - 1
        while low <= high:
            mid = (low + high) // 2
            if samples[mid]["t"] <= t:
                low = mid + 1
            else:
                high = mid - 1

        idx0 = max(0, high)
        idx1 = min(len(samples) - 1, idx0 + 1)
        p0, p1 = samples[idx0], samples[idx1]
        dt = p1["t"] - p0["t"]
        if dt < 1e-6:
            return p0["x"], p0["y"]
        alpha = (t - p0["t"]) / dt
        x = p0["x"] + (p1["x"] - p0["x"]) * alpha
        y = p0["y"] + (p1["y"] - p0["y"]) * alpha
        return x, y

    @classmethod
    def check_fleet_collisions(cls, fleet_trajectories: Dict[str, Dict[str, Any]],
                               safe_radius: float = 0.6,
                               time_step_s: float = 0.1) -> List[Dict[str, Any]]:
        """
        按 100ms 扫描全时间轴，检测多机间距是否低于安全半径 0.6m
        返回碰撞风险列表 [{'time': t, 'robot_a': id_a, 'robot_b': id_b, 'distance': d, ...}]
        """
        if len(fleet_trajectories) < 2:
            return []

        # 获取全局时间范围
        global_min_t = float("inf")
        global_max_t = float("-inf")
        robot_items = []

        for rid, item in fleet_trajectories.items():
            start_t = float(item.get("start_time", 0.0))
            samples = item.get("samples", [])
            if not samples:
                continue
            dur = samples[-1]["t"]
            end_t = start_t + dur
            global_min_t = min(global_min_t, start_t)
            global_max_t = max(global_max_t, end_t)
            robot_items.append((rid, start_t, samples))

        if global_min_t >= global_max_t or len(robot_items) < 2:
            return []

        collisions = []
        curr_t = global_min_t

        while curr_t <= global_max_t + 1e-4:
            # 获取每台机器当前坐标
            positions = {}
            for rid, start_t, samples in robot_items:
                rel_t = curr_t - start_t
                pos = cls.interpolate_position(samples, rel_t)
                positions[rid] = pos

            rids = list(positions.keys())
            for i in range(len(rids)):
                for j in range(i + 1, len(rids)):
                    ra, rb = rids[i], rids[j]
                    pa, pb = positions[ra], positions[rb]
                    dist = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
                    if dist < safe_radius:
                        collisions.append({
                            "time": round(curr_t, 2),
                            "robot_a": ra,
                            "robot_b": rb,
                            "distance": round(dist, 3),
                            "pos_a": (round(pa[0], 3), round(pa[1], 3)),
                            "pos_b": (round(pb[0], 3), round(pb[1], 3))
                        })

            curr_t += time_step_s

        return collisions

