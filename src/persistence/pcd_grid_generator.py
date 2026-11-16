# @file: src/persistence/pcd_grid_generator.py
# @brief: Projects 3D PCD clouds into height-filtered 2D occupancy grid PNGs for StageCanvas2D overlay.
# @exports: GridMapResult, generate_occupancy_grid_png

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import numpy as np
from PySide6.QtGui import QImage

from src.persistence.pcd_parser import PcdPointCloud


@dataclass(frozen=True)
class GridMapResult:
    """Generated 2D occupancy image metadata compatible with WorldCanvas overlays."""

    png_path: str
    origin_x: float
    origin_y: float
    resolution: float
    width_px: int
    height_px: int


def generate_occupancy_grid_png(
    cloud: PcdPointCloud,
    out_png: Path,
    resolution: float = 0.05,
    z_min: float = 0.15,
    z_max: float = 2.0,
    max_dim_px: int = 2048,
    calib_matrix: dict | None = None,
) -> GridMapResult:
    """Project obstacle slice [z_min, z_max] into an RGBA PNG grid (applying optional SVD R/t)."""
    out_png.parent.mkdir(parents=True, exist_ok=True)
    pts = np.array(cloud.points_xyz, dtype=np.float32, copy=True)
    if len(pts) > 0 and isinstance(calib_matrix, dict) and "rot_2x2" in calib_matrix and "trans_2" in calib_matrix:
        rot = np.asarray(calib_matrix["rot_2x2"], dtype=np.float64).reshape(2, 2)
        trans = np.asarray(calib_matrix["trans_2"], dtype=np.float64).reshape(2)
        xy = (rot @ pts[:, :2].astype(np.float64).T).T + trans
        pts[:, :2] = xy.astype(np.float32)
    if len(pts) == 0:
        img = QImage(64, 64, QImage.Format.Format_RGBA8888)
        img.fill(0)
        img.save(str(out_png), "PNG")
        return GridMapResult(str(out_png), -1.6, -1.6, resolution, 64, 64)

    mask = (pts[:, 2] >= z_min) & (pts[:, 2] <= z_max)
    obs = pts[mask] if mask.any() else pts

    min_x, min_y = float(pts[:, 0].min()), float(pts[:, 1].min())
    max_x, max_y = float(pts[:, 0].max()), float(pts[:, 1].max())
    span_x = max(1.0, max_x - min_x)
    span_y = max(1.0, max_y - min_y)

    # Adapt resolution upward if map spans hundreds of meters so PNG stays fast and sharp
    eff_res = max(float(resolution), span_x / max_dim_px, span_y / max_dim_px)
    w = max(8, min(max_dim_px, int(np.ceil(span_x / eff_res)) + 1))
    h = max(8, min(max_dim_px, int(np.ceil(span_y / eff_res)) + 1))

    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    # Paint free-floor footprint faintly from all points
    fx = np.clip(((pts[:, 0] - min_x) / eff_res).astype(np.int32), 0, w - 1)
    fy = np.clip(h - 1 - ((pts[:, 1] - min_y) / eff_res).astype(np.int32), 0, h - 1)
    rgba[fy, fx] = (28, 36, 46, 95)

    # Paint obstacle slice in UniUni teal/white highlight
    ox = np.clip(((obs[:, 0] - min_x) / eff_res).astype(np.int32), 0, w - 1)
    oy = np.clip(h - 1 - ((obs[:, 1] - min_y) / eff_res).astype(np.int32), 0, h - 1)
    rgba[oy, ox] = (86, 212, 198, 225)

    img = QImage(rgba.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
    img.save(str(out_png), "PNG")
    return GridMapResult(
        png_path=str(out_png),
        origin_x=min_x,
        origin_y=min_y,
        resolution=eff_res,
        width_px=w,
        height_px=h,
    )
