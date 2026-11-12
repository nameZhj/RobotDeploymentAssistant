"""
@file: src/domain/trajectory/ugc_guard_validator.py
@brief: UGC 轨迹五维编排安全校验与多机时空防撞护栏引擎
@exports: UgcGuardValidator
"""
import math
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np


class UgcGuardValidator:
    """提供起点锚定、连续性、栅格穿墙、运动学超限及全场时空防撞的五维安全审计"""

    @staticmethod
    def _extract_xy(pos: Union[Tuple, List, Dict[str, Any]]) -> Tuple[float, float]:
        if isinstance(pos, dict):
            return float(pos.get("x", 0.0)), float(pos.get("y", 0.0))
        if len(pos) >= 4:
            return float(pos[1]), float(pos[2])
        return float(pos[0]), float(pos[1])

    @classmethod
    def check_rule1_anchor(
        cls, track_id: int,
        first_start: Union[Tuple, List, Dict[str, Any]],
        init_pos: Union[Tuple, List, Dict[str, Any]],
        tolerance: float = 0.20
    ) -> Tuple[bool, Optional[str]]:
        sx, sy = cls._extract_xy(first_start)
        ix, iy = cls._extract_xy(init_pos)
        dist = math.hypot(sx - ix, sy - iy)
        if dist <= tolerance:
            return True, None
        return False, f"机器人 {track_id} 起点锚定失败: 首段起点 ({sx:.3f}, {sy:.3f}) 与初始点 ({ix:.3f}, {iy:.3f}) 距离 {dist:.3f}m > {tolerance}m"

    @classmethod
    def check_rule2_continuity(
        cls, track_id: int, segments: List[Dict[str, Any]], tolerance: float = 0.20
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        if len(segments) <= 1:
            return True, None
        for k in range(1, len(segments)):
            prev_pts = segments[k - 1].get("points", [])
            curr_pts = segments[k].get("points", [])
            if not prev_pts or not curr_pts:
                continue
            pe_x, pe_y = cls._extract_xy(prev_pts[-1])
            cs_x, cs_y = cls._extract_xy(curr_pts[0])
            dist = math.hypot(cs_x - pe_x, cs_y - pe_y)
            if dist > tolerance:
                return False, {
                    "track_id": track_id, "segment_index": k, "gap_m": round(dist, 3),
                    "break_coord": (cs_x, cs_y), "msg": f"第 {k} 段起点与前序终点断开 {dist:.3f}m"
                }
        return True, None

    @classmethod
    def check_rule3_wall_collision(
        cls, points: List[Union[Tuple, List]], inflated_grid: np.ndarray, grid_info: Dict[str, Any]
    ) -> Tuple[bool, List[Tuple[float, float]]]:
        ox = float(grid_info.get("origin_x", 0.0))
        oy = float(grid_info.get("origin_y", 0.0))
        res = float(grid_info.get("resolution", 0.05))
        h, w = inflated_grid.shape
        collisions: List[Tuple[float, float]] = []
        is_mode0 = bool(inflated_grid.max() > 100)

        for p in points:
            x, y = cls._extract_xy(p)
            col = int(math.floor((x - ox) / res))
            row = int(math.floor((y - oy) / res))
            if col < 0 or col >= w or row < 0 or row >= h:
                collisions.append((round(x, 3), round(y, 3)))
                continue
            val = inflated_grid[row, col]
            if (val == 100) or (is_mode0 and val == 0):
                collisions.append((round(x, 3), round(y, 3)))
        return len(collisions) == 0, collisions

    @staticmethod
    def check_rule4_kinematics(
        samples: List[Dict[str, float]], max_v: float = 2.0, max_omega: float = 3.14
    ) -> Tuple[bool, List[str]]:
        violations: List[str] = []
        for s in samples:
            v, w, t = abs(s.get("v", 0.0)), abs(s.get("omega", 0.0)), s.get("t", 0.0)
            if v > max_v:
                violations.append(f"时刻 {t:.2f}s 线速度超限: {v:.2f}m/s > {max_v}m/s")
            if w > max_omega:
                violations.append(f"时刻 {t:.2f}s 角速度超限: {w:.2f}rad/s > {max_omega}rad/s")
        return len(violations) == 0, violations

    @classmethod
    def get_robot_position_at_time(
        cls, t: float, missions: List[Dict[str, Any]], init_xy: Tuple[float, float]
    ) -> Tuple[float, float]:
        curr_xy = init_xy
        for m in missions:
            t_start = float(m.get("start_s", 0.0))
            t_dur = float(m.get("duration_s", 0.0))
            pts = m.get("sampled_points", [])
            if not pts:
                continue
            if t < t_start:
                return curr_xy
            if t_start <= t <= t_start + t_dur:
                frac = min(1.0, max(0.0, (t - t_start) / max(t_dur, 1e-4)))
                idx = min(len(pts) - 1, int(frac * (len(pts) - 1)))
                return pts[idx]["x"], pts[idx]["y"]
            curr_xy = (pts[-1]["x"], pts[-1]["y"])
        return curr_xy

    @classmethod
    def check_rule5_swarm_collision(
        cls, tracks_data: Dict[int, List[Dict[str, Any]]],
        init_positions: Dict[int, Any], dt: float = 0.05, safe_dist: float = 0.65
    ) -> List[Dict[str, Any]]:
        t_max = 0.0
        for m_list in tracks_data.values():
            for m in m_list:
                t_max = max(t_max, float(m.get("start_s", 0.0)) + float(m.get("duration_s", 0.0)))
        if t_max <= 0.0:
            return []

        robot_ids = sorted(tracks_data.keys())
        alerts: List[Dict[str, Any]] = []
        n_steps = int(math.ceil(t_max / dt)) + 1
        init_xy_map = {rid: cls._extract_xy(init_positions.get(rid, (0.0, 0.0))) for rid in robot_ids}

        for step in range(n_steps):
            t = min(step * dt, t_max)
            coords = {rid: cls.get_robot_position_at_time(t, tracks_data[rid], init_xy_map[rid]) for rid in robot_ids}
            for i in range(len(robot_ids)):
                for j in range(i + 1, len(robot_ids)):
                    ra, rb = robot_ids[i], robot_ids[j]
                    pa, pb = coords[ra], coords[rb]
                    d = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
                    if d < safe_dist:
                        alerts.append({
                            "time_s": round(t, 2), "robot_a": ra, "robot_b": rb,
                            "distance_m": round(d, 3),
                            "pos_xy": (round(0.5 * (pa[0] + pb[0]), 3), round(0.5 * (pa[1] + pb[1]), 3))
                        })
        return alerts

    @classmethod
    def validate_mission(
        cls, tracks_data: Dict[int, List[Dict[str, Any]]],
        init_positions: Dict[int, Any],
        inflated_grid: Optional[np.ndarray] = None,
        grid_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        errors: List[str] = []
        for rid, segs in tracks_data.items():
            if not segs:
                continue
            first_pts = segs[0].get("points", [])
            init_pos = init_positions.get(rid, (0.0, 0.0))
            if first_pts:
                ok1, msg1 = cls.check_rule1_anchor(rid, first_pts[0], init_pos)
                if not ok1 and msg1:
                    errors.append(msg1)
            ok2, err2 = cls.check_rule2_continuity(rid, segs)
            if not ok2 and err2:
                errors.append(err2["msg"])
            for seg in segs:
                samples = seg.get("sampled_points", [])
                ok4, err4 = cls.check_rule4_kinematics(samples)
                errors.extend(err4)
                if inflated_grid is not None and grid_info is not None:
                    ok3, cols = cls.check_rule3_wall_collision(samples, inflated_grid, grid_info)
                    if not ok3:
                        errors.append(f"机器人 {rid} 发生穿墙碰撞，共 {len(cols)} 处")

        col_alerts = cls.check_rule5_swarm_collision(tracks_data, init_positions)
        if col_alerts:
            errors.append(f"检测到 {len(col_alerts)} 次多机时空防撞冲突")
        return {"valid": len(errors) == 0, "errors": errors, "details": {"collision_alerts": col_alerts}}

    @classmethod
    def validate_five_guards(cls, *args, **kwargs) -> Dict[str, Any]:
        return cls.validate_mission(*args, **kwargs)
