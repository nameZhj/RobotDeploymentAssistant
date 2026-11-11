"""
@file: src/domain/map/grid_and_calibration.py
@brief: 2D 占据栅格生成、膨胀、坐标标定及 3D 体素着色降采样引擎
@exports: MapGridProcessor, pcd_file_to_points, pcd_file_to_grid_png
"""
import math
from typing import Any, Dict, Optional, Tuple
import numpy as np
from scipy import ndimage


class MapGridProcessor:
    """提供点云刚体标定、2D 栅格投射、膨胀处理与多档位 3D 体素渲染预处理"""

    @staticmethod
    def calibrate_points(points: np.ndarray, dx: float, dy: float,
                         dyaw_deg: float) -> np.ndarray:
        if len(points) == 0:
            return np.empty((0, 3), dtype=np.float32)
        rad = math.radians(dyaw_deg)
        c, s = math.cos(rad), math.sin(rad)
        px = points[:, 0]
        py = points[:, 1]
        pz = points[:, 2]
        new_x = c * px - s * py + dx
        new_y = s * px + c * py + dy
        return np.column_stack([new_x, new_y, pz]).astype(np.float32)

    @staticmethod
    def extract_2d_wall_points(points: np.ndarray, min_z: float = 0.15,
                               max_z: float = 1.65) -> np.ndarray:
        if len(points) == 0:
            return np.empty((0, 3), dtype=np.float32)
        mask = (points[:, 2] >= min_z) & (points[:, 2] <= max_z)
        return points[mask].astype(np.float32)

    @classmethod
    def generate_2d_occupancy_grid(
        cls, points: np.ndarray, resolution: float = 0.05,
        min_z: float = 0.15, max_z: float = 1.65,
        inflate_radius: float = 0.35
    ) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
        wall_pts = cls.extract_2d_wall_points(points, min_z, max_z)
        margin = 0.5
        min_x = float(np.floor(points[:, 0].min() - margin)) if len(points) else -15.0
        max_x = float(np.ceil(points[:, 0].max() + margin)) if len(points) else 1.0
        min_y = float(np.floor(points[:, 1].min() - margin)) if len(points) else -5.0
        max_y = float(np.ceil(points[:, 1].max() + margin)) if len(points) else 4.0

        w = int(math.ceil((max_x - min_x) / resolution)) + 1
        h = int(math.ceil((max_y - min_y) / resolution)) + 1
        occ = np.zeros((h, w), dtype=np.uint8)

        if len(wall_pts) > 0:
            cols = np.clip(((wall_pts[:, 0] - min_x) / resolution).astype(int), 0, w - 1)
            rows = np.clip(((wall_pts[:, 1] - min_y) / resolution).astype(int), 0, h - 1)
            occ[rows, cols] = 100

        k = max(1, int(round(inflate_radius / resolution)))
        y, x = np.ogrid[-k:k + 1, -k:k + 1]
        disk = (x * x + y * y) <= (k * k)
        dilated = ndimage.binary_dilation(occ == 100, structure=disk)
        inflated = np.zeros_like(occ)
        inflated[dilated] = 100

        info = {
            "origin_x": min_x, "origin_y": min_y,
            "resolution": resolution, "width": w, "height": h,
            "inflate_radius_m": inflate_radius, "inflate_cells": k
        }
        return occ, inflated, info

    @staticmethod
    def downsample_3d_colored(points: np.ndarray,
                              mode: str = "eco") -> Tuple[np.ndarray, np.ndarray]:
        if len(points) == 0:
            return np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.uint8)
        voxel_size = 0.12 if mode.lower() == "eco" else 0.04
        vox = np.floor(points / voxel_size).astype(np.int32)
        _, uidx = np.unique(vox, axis=0, return_index=True)
        downsampled = points[uidx].astype(np.float32)

        z_vals = downsampled[:, 2]
        z_min = float(points[:, 2].min())
        z_max = float(points[:, 2].max())
        den = max(z_max - z_min, 1e-4)
        h = np.clip((z_vals - z_min) / den, 0.0, 1.0)

        red = np.clip(35 + 160.0 * (h ** 2), 0, 255).astype(np.uint8)
        green = np.clip(145 + 110.0 * h, 0, 255).astype(np.uint8)
        blue = np.full_like(red, 255, dtype=np.uint8)
        colors = np.column_stack([red, green, blue]).astype(np.uint8)
        return downsampled, colors


def pcd_file_to_points(pcd_path: str, max_points: Optional[int] = None):
    from src.infrastructure.map.pcd_grid_engine import pcd_file_to_points as _fn
    return _fn(pcd_path, max_points)


def pcd_file_to_grid_png(pcd_path: str, config: Optional[Any] = None):
    from src.infrastructure.map.pcd_grid_engine import pcd_file_to_grid_png as _fn
    return _fn(pcd_path, config)


