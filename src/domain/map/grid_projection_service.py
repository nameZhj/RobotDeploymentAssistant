"""
栅格投影与坐标标定服务
提供点云 2D 占据栅格切片、3D 蓝青色高程渐变着色及齐次坐标变换
"""
from typing import Dict, Optional, Tuple
import numpy as np


class GridProjectionService:
    """点云切片投影与空间标定变换引擎"""

    @classmethod
    def filter_and_project_2d(cls, points_3d: np.ndarray,
                              min_z: float = 0.05,
                              max_z: float = 2.0,
                              resolution: float = 0.05) -> Tuple[np.ndarray, np.ndarray]:
        """
        按高程 [min_z, max_z] 切片点云，并降采样去重投影为 2D 占据栅格坐标
        返回 (points_2d, occupied_cells)
        """
        if points_3d.size == 0:
            empty = np.zeros((0, 2), dtype=np.float32)
            return empty, np.zeros((0, 2), dtype=np.int32)

        z = points_3d[:, 2]
        mask = (z >= min_z) & (z <= max_z)
        valid_pts = points_3d[mask]

        if len(valid_pts) == 0:
            empty = np.zeros((0, 2), dtype=np.float32)
            return empty, np.zeros((0, 2), dtype=np.int32)

        ix = np.floor(valid_pts[:, 0] / resolution).astype(np.int32)
        iy = np.floor(valid_pts[:, 1] / resolution).astype(np.int32)
        raw_cells = np.column_stack((ix, iy))
        occupied_cells = np.unique(raw_cells, axis=0)

        points_2d = occupied_cells.astype(np.float32) * resolution + (resolution / 2.0)
        return points_2d, occupied_cells

    @classmethod
    def compute_height_colors(cls, points_3d: np.ndarray,
                              min_z: Optional[float] = None,
                              max_z: Optional[float] = None) -> np.ndarray:
        """
        根据点云 Z 轴高程生成蓝青色渐变 (Deep Blue -> Cyan -> Bright Cyan)
        返回 Nx4 RGBA 浮点色彩矩阵 [0.0, 1.0]
        """
        n = len(points_3d)
        if n == 0:
            return np.zeros((0, 4), dtype=np.float32)

        z = points_3d[:, 2]
        z_min = float(np.min(z)) if min_z is None else min_z
        z_max = float(np.max(z)) if max_z is None else max_z
        span = max(z_max - z_min, 1e-4)

        norm_t = np.clip((z - z_min) / span, 0.0, 1.0)

        # 渐变基准色：低位深蓝 (0.05, 0.22, 0.85)，中位青蓝 (0.0, 0.85, 0.95)，高位亮青白 (0.70, 0.96, 1.0)
        c_low = np.array([0.05, 0.22, 0.85, 1.0], dtype=np.float32)
        c_mid = np.array([0.00, 0.85, 0.95, 1.0], dtype=np.float32)
        c_high = np.array([0.70, 0.96, 1.00, 1.0], dtype=np.float32)

        colors = np.zeros((n, 4), dtype=np.float32)
        lower_mask = norm_t < 0.5
        upper_mask = ~lower_mask

        t_low = norm_t[lower_mask] / 0.5
        colors[lower_mask] = (1.0 - t_low[:, None]) * c_low + t_low[:, None] * c_mid

        t_high = (norm_t[upper_mask] - 0.5) / 0.5
        colors[upper_mask] = (1.0 - t_high[:, None]) * c_mid + t_high[:, None] * c_high

        return colors

    @classmethod
    def apply_calibration(cls, points: np.ndarray,
                          delta_x: float,
                          delta_y: float,
                          delta_theta_rad: float,
                          delta_z: float = 0.0) -> np.ndarray:
        """
        对点云坐标执行平面旋转与平移齐次矩阵变换
        x' = x*cosθ - y*sinθ + Δx
        y' = x*sinθ + y*cosθ + Δy
        z' = z + Δz
        """
        if points.size == 0:
            return points.copy()

        transformed = points.copy()
        c = np.cos(delta_theta_rad)
        s = np.sin(delta_theta_rad)

        x = points[:, 0]
        y = points[:, 1]
        transformed[:, 0] = x * c - y * s + delta_x
        transformed[:, 1] = x * s + y * c + delta_y

        if transformed.shape[1] >= 3:
            transformed[:, 2] = points[:, 2] + delta_z

        return transformed

    @classmethod
    def compute_bounds(cls, points: np.ndarray) -> Dict[str, float]:
        """计算点云的轴对齐包围盒 (AABB)"""
        if len(points) == 0:
            return {"min_x": 0.0, "max_x": 0.0, "min_y": 0.0, "max_y": 0.0, "min_z": 0.0, "max_z": 0.0}

        bounds = {
            "min_x": float(np.min(points[:, 0])),
            "max_x": float(np.max(points[:, 0])),
            "min_y": float(np.min(points[:, 1])),
            "max_y": float(np.max(points[:, 1])),
            "min_z": float(np.min(points[:, 2])) if points.shape[1] >= 3 else 0.0,
            "max_z": float(np.max(points[:, 2])) if points.shape[1] >= 3 else 0.0,
        }
        return bounds
