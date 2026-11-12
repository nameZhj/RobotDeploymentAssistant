"""
@file: src/core/formation_calc.py
@brief: 机器人阵型几何计算、安全防碰撞间距校验与群体轨迹多机位姿展开引擎
@exports: FormationCalculator
"""
import math
from typing import Any, Dict, List, Optional, Tuple


class FormationCalculator:
    """机器人阵型几何计算器，支持横排/纵列/圆形/网格四种构型与轨迹展开"""

    DEFAULT_SAFE_DISTANCE = 0.6  # 默认防碰撞最小安全距离 0.6m

    @staticmethod
    def calculate_offsets(
        formation_type: str,
        robot_ids: List[str],
        spacing: float = 1.0,
        rows: int = 2,
        cols: int = 2,
        radius: float = 1.5,
        facing: str = "forward",
    ) -> List[Dict[str, Any]]:
        """计算各机器人在阵型中心局部坐标系下的相对偏移 (offset_x, offset_y, offset_yaw)"""
        n = len(robot_ids)
        if n == 0:
            return []

        ft = str(formation_type).lower().strip()
        members: List[Dict[str, Any]] = []

        if ft in ("line_row", "row"):
            # 横排：垂直于航向左右对称排列，沿局部 Y 轴分布
            for i, rid in enumerate(robot_ids):
                oy = round(((n - 1) / 2.0 - i) * spacing, 4)
                members.append({"robot_id": rid, "seq": i, "offset_x": 0.0, "offset_y": oy, "offset_yaw": 0.0})

        elif ft in ("line_col", "col"):
            # 纵列：沿着航向前进方向前后排列，沿局部 X 轴分布
            for i, rid in enumerate(robot_ids):
                ox = round(((n - 1) / 2.0 - i) * spacing, 4)
                members.append({"robot_id": rid, "seq": i, "offset_x": ox, "offset_y": 0.0, "offset_yaw": 0.0})

        elif ft in ("circle", "ring"):
            # 圆形：以 radius 为半径在圆周上均匀分布
            actual_radius = radius if radius > 0 else max(1.0, (n * spacing) / (2.0 * math.pi))
            angle_step = (2.0 * math.pi) / n
            for i, rid in enumerate(robot_ids):
                theta = i * angle_step
                ox = round(actual_radius * math.cos(theta), 4)
                oy = round(actual_radius * math.sin(theta), 4)
                if facing == "inward":
                    oyaw = round(theta + math.pi, 4)
                elif facing == "outward":
                    oyaw = round(theta, 4)
                else:  # forward
                    oyaw = 0.0
                members.append({"robot_id": rid, "seq": i, "offset_x": ox, "offset_y": oy, "offset_yaw": oyaw})

        else:
            # 矩形网格 (grid)
            r_cnt = max(1, rows)
            c_cnt = max(1, cols)
            idx = 0
            for r in range(r_cnt):
                for c in range(c_cnt):
                    if idx >= n:
                        break
                    rid = robot_ids[idx]
                    ox = round(((r_cnt - 1) / 2.0 - r) * spacing, 4)
                    oy = round((c - (c_cnt - 1) / 2.0) * spacing, 4)
                    members.append({"robot_id": rid, "seq": idx, "offset_x": ox, "offset_y": oy, "offset_yaw": 0.0})
                    idx += 1

        return members

    @classmethod
    def calculate_world_poses(
        cls,
        members: List[Dict[str, Any]],
        center_x: float,
        center_y: float,
        center_yaw: float,
    ) -> List[Dict[str, Any]]:
        """将局部偏移根据阵型中心世界位姿变换为全局世界位姿"""
        results: List[Dict[str, Any]] = []
        cos_y = math.cos(center_yaw)
        sin_y = math.sin(center_yaw)

        for m in members:
            ox = float(m.get("offset_x", 0.0))
            oy = float(m.get("offset_y", 0.0))
            oyaw = float(m.get("offset_yaw", 0.0))

            wx = round(center_x + ox * cos_y - oy * sin_y, 4)
            wy = round(center_y + ox * sin_y + oy * cos_y, 4)
            wyaw = round((center_yaw + oyaw + math.pi) % (2.0 * math.pi) - math.pi, 4)

            results.append({
                "robot_id": m.get("robot_id", ""),
                "seq": m.get("seq", 0),
                "offset_x": ox,
                "offset_y": oy,
                "offset_yaw": oyaw,
                "world_x": wx,
                "world_y": wy,
                "world_yaw": wyaw,
            })
        return results

    @classmethod
    def check_safety_distances(
        cls,
        members: List[Dict[str, Any]],
        safe_distance: float = DEFAULT_SAFE_DISTANCE,
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        """两两计算阵型中机器人之间的欧氏距离，若小于安全距离返回碰撞告警对"""
        warnings: List[Dict[str, Any]] = []
        n = len(members)

        for i in range(n):
            for j in range(i + 1, n):
                xi = float(members[i].get("offset_x", members[i].get("world_x", 0.0)))
                yi = float(members[i].get("offset_y", members[i].get("world_y", 0.0)))
                xj = float(members[j].get("offset_x", members[j].get("world_x", 0.0)))
                yj = float(members[j].get("offset_y", members[j].get("world_y", 0.0)))

                dist = math.hypot(xi - xj, yi - yj)
                if dist < safe_distance:
                    warnings.append({
                        "robot_a": members[i].get("robot_id", f"R{i}"),
                        "robot_b": members[j].get("robot_id", f"R{j}"),
                        "distance": round(dist, 3),
                        "safe_distance": round(safe_distance, 3),
                    })

        is_safe = (len(warnings) == 0)
        return is_safe, warnings

    @classmethod
    def expand_swarm_trajectory(
        cls,
        swarm_traj_dict: Dict[str, Any],
        formation_dict: Dict[str, Any],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """将群体中心轨迹离散点结合阵型偏移解算为各成员机器人的独立时序轨迹"""
        sampled_points = swarm_traj_dict.get("sampled_points", [])
        members = formation_dict.get("members", [])
        if not sampled_points or not members:
            return {}

        results: Dict[str, List[Dict[str, Any]]] = {m.get("robot_id", "A"): [] for m in members}

        for sp in sampled_points:
            cx = float(sp.get("x", 0.0))
            cy = float(sp.get("y", 0.0))
            cyaw = float(sp.get("yaw", 0.0))
            t = float(sp.get("t", 0.0))
            cvx = float(sp.get("vx", 0.0))
            cvy = float(sp.get("vy", 0.0))
            cwz = float(sp.get("wz", 0.0))
            seq = int(sp.get("seq", 0))

            cos_y = math.cos(cyaw)
            sin_y = math.sin(cyaw)

            for m in members:
                rid = str(m.get("robot_id", "A"))
                ox = float(m.get("offset_x", 0.0))
                oy = float(m.get("offset_y", 0.0))
                oyaw = float(m.get("offset_yaw", 0.0))

                rx = round(cx + ox * cos_y - oy * sin_y, 4)
                ry = round(cy + ox * sin_y + oy * cos_y, 4)
                ryaw = round((cyaw + oyaw + math.pi) % (2.0 * math.pi) - math.pi, 4)

                # 刚体自转角速度产生的线速度分量 v = v_center + w x r
                vx = round(cvx - cwz * (ox * sin_y + oy * cos_y), 4)
                vy = round(cvy + cwz * (ox * cos_y - oy * sin_y), 4)

                results[rid].append({
                    "seq": seq,
                    "x": rx,
                    "y": ry,
                    "yaw": ryaw,
                    "t": t,
                    "vx": vx,
                    "vy": vy,
                    "wz": cwz,
                })

        return results
