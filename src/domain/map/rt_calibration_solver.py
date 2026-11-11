"""
@file: src/domain/map/rt_calibration_solver.py
@brief: 空间 R/t 坐标三点标定解算、初始点与轨迹位姿刚体变换器
@exports: RtCalibrationSolver, solve_rt_from_pairs, solve_rt_from_point_pairs, transform_init_points, transform_trajectory_point_data
"""
import copy
import json
import math
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np


class RtCalibrationSolver:
    """去质心协方差 SVD 刚体标定求解器，提供点对匹配、精度残差评估与位姿变换"""

    @staticmethod
    def get_default_identity() -> Dict[str, Any]:
        return {
            "r_mat": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            "t_vec": [0.0, 0.0, 0.0],
            "yaw_deg": 0.0,
            "rmse": 0.0,
            "is_valid": True,
            "warning": ""
        }

    @staticmethod
    def is_default_identity(r_mat: List[List[float]], t_vec: List[float]) -> bool:
        r = np.array(r_mat, dtype=float)
        t = np.array(t_vec, dtype=float)
        return bool(np.allclose(r, np.eye(3), atol=1e-3) and np.allclose(t, 0.0, atol=1e-3))

    @classmethod
    def solve_rt_from_pairs(
        cls,
        plan_xy: List[Tuple[float, float]],
        actual_xy: List[Tuple[float, float]]
    ) -> Dict[str, Any]:
        if len(plan_xy) < 3 or len(actual_xy) < 3:
            raise ValueError(f"标定至少需要 3 组点对，当前提供: {len(plan_xy)}")
        if len(plan_xy) != len(actual_xy):
            raise ValueError("规划点对与实测点对数量不一致")

        p_arr = np.array(plan_xy, dtype=np.float64)
        a_arr = np.array(actual_xy, dtype=np.float64)

        p_mean = np.mean(p_arr, axis=0)
        a_mean = np.mean(a_arr, axis=0)
        x_centered = p_arr - p_mean
        y_centered = a_arr - a_mean

        h_mat = x_centered.T @ y_centered
        u, s, vt = np.linalg.svd(h_mat)

        warning = ""
        if len(s) > 1 and (s[1] < 1e-4 or s[0] / max(s[1], 1e-9) > 1e4):
            warning = "标定点近乎共线或奇异分布，可能导致旋转角不稳定"

        r_2d = vt.T @ u.T
        if np.linalg.det(r_2d) < 0:
            d = np.diag([1.0, -1.0])
            r_2d = vt.T @ d @ u.T

        t_2d = a_mean - r_2d @ p_mean
        yaw = float(math.degrees(math.atan2(r_2d[1, 0], r_2d[0, 0])))

        pred_a = p_arr @ r_2d.T + t_2d
        rmse = float(np.sqrt(np.mean(np.sum((a_arr - pred_a) ** 2, axis=1))))

        r_3x3 = [
            [float(r_2d[0, 0]), float(r_2d[0, 1]), 0.0],
            [float(r_2d[1, 0]), float(r_2d[1, 1]), 0.0],
            [0.0, 0.0, 1.0]
        ]
        t_3d = [float(t_2d[0]), float(t_2d[1]), 0.0]

        return {
            "r_mat": r_3x3,
            "t_vec": t_3d,
            "yaw_deg": yaw,
            "rmse": rmse,
            "is_valid": True,
            "warning": warning
        }

    @classmethod
    def transform_init_points(
        cls,
        init_points: List[Dict[str, Any]],
        r_mat: List[List[float]],
        t_vec: List[float]
    ) -> List[Dict[str, Any]]:
        r2 = np.array(r_mat, dtype=float)[:2, :2]
        t2 = np.array(t_vec, dtype=float)[:2]
        r_yaw = math.degrees(math.atan2(r2[1, 0], r2[0, 0]))

        transformed: List[Dict[str, Any]] = []
        for pt in init_points:
            item = copy.deepcopy(pt)
            xy = np.array([float(pt.get("x", 0.0)), float(pt.get("y", 0.0))], dtype=float)
            new_xy = r2 @ xy + t2
            orig_yaw = float(pt.get("yaw", 0.0))
            new_yaw = (orig_yaw + r_yaw + 180.0) % 360.0 - 180.0
            item["x"] = round(float(new_xy[0]), 4)
            item["y"] = round(float(new_xy[1]), 4)
            item["yaw"] = round(float(new_yaw), 2)
            transformed.append(item)
        return transformed

    @classmethod
    def transform_trajectory_point_data(
        cls,
        point_data_str: str,
        r_mat: List[List[float]],
        t_vec: List[float]
    ) -> str:
        if not point_data_str or not point_data_str.strip():
            return ""
        r2 = np.array(r_mat, dtype=float)[:2, :2]
        t2 = np.array(t_vec, dtype=float)[:2]
        r_yaw = math.degrees(math.atan2(r2[1, 0], r2[0, 0]))

        res_lines: List[str] = []
        for line in point_data_str.strip().splitlines():
            parts = [p.strip() for p in line.split(",") if p.strip()]
            if len(parts) >= 4:
                prefix = parts[0]
                xy = np.array([float(parts[1]), float(parts[2])], dtype=float)
                new_xy = r2 @ xy + t2
                orig_yaw = float(parts[3])
                new_yaw = (orig_yaw + r_yaw + 180.0) % 360.0 - 180.0
                rest = [f"{new_xy[0]:.4f}", f"{new_xy[1]:.4f}", f"{new_yaw:.2f}"] + parts[4:]
                res_lines.append(f"{prefix}," + ",".join(rest))
            else:
                res_lines.append(line)
        return "\n".join(res_lines)

    @classmethod
    def export_rt_json(cls, rt_dict: Dict[str, Any]) -> str:
        return json.dumps(rt_dict, indent=2, ensure_ascii=False)

    @classmethod
    def import_rt_json(cls, json_str: str) -> Dict[str, Any]:
        data = json.loads(json_str)
        if "r_mat" not in data or "t_vec" not in data:
            return cls.get_default_identity()
        return data

    @classmethod
    def reset_scene_calibration(cls, scene_id: str, repo: Optional[Any] = None) -> Dict[str, Any]:
        ident = cls.get_default_identity()
        if repo and hasattr(repo, "upsert_scene"):
            curr = repo.get_scene(scene_id) or {"scene_id": scene_id, "name": scene_id}
            curr["calibration_matrix"] = ident
            repo.upsert_scene(curr)
        return ident


rt_calibration_solver = RtCalibrationSolver()
solve_rt_from_pairs = RtCalibrationSolver.solve_rt_from_pairs
solve_rt_from_point_pairs = RtCalibrationSolver.solve_rt_from_pairs
transform_init_points = RtCalibrationSolver.transform_init_points
transform_trajectory_point_data = RtCalibrationSolver.transform_trajectory_point_data
is_default_identity = RtCalibrationSolver.is_default_identity
