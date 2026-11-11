"""
@file: src/domain/map/rt_calibration_engine.py
@brief: 空间坐标刚体变换与三点及以上去质心 SVD R/t 标定解算器
@exports: RtCalibrationEngine, RtCalibrationResult, rt_calibration_engine
"""
import json
import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np


@dataclass
class RtCalibrationResult:
    """R/t 刚体变换解算结果与精度评估"""
    r_mat: List[List[float]]
    t_vec: List[float]
    yaw_deg: float
    rmse: float
    is_valid: bool
    warning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RtCalibrationResult":
        return cls(
            r_mat=data.get("r_mat", [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
            t_vec=data.get("t_vec", [0.0, 0.0, 0.0]),
            yaw_deg=float(data.get("yaw_deg", 0.0)),
            rmse=float(data.get("rmse", 0.0)),
            is_valid=bool(data.get("is_valid", True)),
            warning=str(data.get("warning", ""))
        )


class RtCalibrationEngine:
    """去质心协方差 SVD 标定解算器，支持 2D/3D 刚体转换与轨迹批量映射"""

    def __init__(self) -> None:
        self.current_result = self.get_default_identity()
        self.needs_grid_regenerate: bool = False

    @staticmethod
    def get_default_identity() -> RtCalibrationResult:
        return RtCalibrationResult(
            r_mat=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            t_vec=[0.0, 0.0, 0.0],
            yaw_deg=0.0,
            rmse=0.0,
            is_valid=True,
            warning=""
        )

    @staticmethod
    def is_default_identity(
        r_mat: Union[List[List[float]], np.ndarray],
        t_vec: Union[List[float], np.ndarray]
    ) -> bool:
        r = np.array(r_mat, dtype=float)
        t = np.array(t_vec, dtype=float)
        return bool(np.allclose(r, np.eye(3), atol=1e-3) and np.allclose(t, 0.0, atol=1e-3))

    def solve_rt_from_point_pairs(
        self,
        plan_points: List[Tuple[float, float]],
        actual_points: List[Tuple[float, float]]
    ) -> RtCalibrationResult:
        if len(plan_points) < 3 or len(actual_points) < 3:
            raise ValueError(f"标定至少需要 3 组点对，当前提供: {len(plan_points)}")
        if len(plan_points) != len(actual_points):
            raise ValueError("规划点对与实测点对数量不一致")

        p_arr = np.array(plan_points, dtype=np.float64)
        a_arr = np.array(actual_points, dtype=np.float64)

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

        res = RtCalibrationResult(
            r_mat=r_3x3,
            t_vec=t_3d,
            yaw_deg=yaw,
            rmse=rmse,
            is_valid=True,
            warning=warning
        )
        self.current_result = res
        self.needs_grid_regenerate = True
        return res

    @staticmethod
    def transform_pose_2d(
        x: float, y: float, yaw_deg: float,
        r_mat: Union[List[List[float]], np.ndarray],
        t_vec: Union[List[float], np.ndarray]
    ) -> Tuple[float, float, float]:
        r2 = np.array(r_mat, dtype=float)[:2, :2]
        t2 = np.array(t_vec, dtype=float)[:2]
        trans_xy = r2 @ np.array([x, y], dtype=float) + t2
        r_yaw = math.degrees(math.atan2(r2[1, 0], r2[0, 0]))
        new_yaw = (yaw_deg + r_yaw + 180.0) % 360.0 - 180.0
        return float(trans_xy[0]), float(trans_xy[1]), float(new_yaw)

    @classmethod
    def transform_trajectory_data_str(
        cls,
        point_data_str: str,
        r_mat: Union[List[List[float]], np.ndarray],
        t_vec: Union[List[float], np.ndarray]
    ) -> str:
        if not point_data_str or not point_data_str.strip():
            return ""
        lines = point_data_str.strip().splitlines()
        res_lines: List[str] = []
        for line in lines:
            parts = [p.strip() for p in line.split(",") if p.strip()]
            if len(parts) >= 4:
                prefix = parts[0]
                x_val, y_val, yaw_val = float(parts[1]), float(parts[2]), float(parts[3])
                nx, ny, nyaw = cls.transform_pose_2d(x_val, y_val, yaw_val, r_mat, t_vec)
                rest = [f"{nx:.4f}", f"{ny:.4f}", f"{nyaw:.2f}"] + parts[4:]
                res_lines.append(f"{prefix}," + ",".join(rest))
            else:
                res_lines.append(line)
        return "\n".join(res_lines)

    def export_json(self) -> str:
        return json.dumps(self.current_result.to_dict(), indent=2, ensure_ascii=False)

    def import_json(self, json_str: str) -> RtCalibrationResult:
        data = json.loads(json_str)
        self.current_result = RtCalibrationResult.from_dict(data)
        self.needs_grid_regenerate = True
        return self.current_result

    def reset_to_identity(self) -> RtCalibrationResult:
        self.current_result = self.get_default_identity()
        self.needs_grid_regenerate = True
        return self.current_result


rt_calibration_engine = RtCalibrationEngine()

