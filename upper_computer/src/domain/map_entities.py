# @file: src/domain/map_entities.py
# @brief: Domain entity for local/SLAM PCD maps, 2D occupancy grid textures, and rigid calibration transforms.
# @exports: PcdMapEntity

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class PcdMapEntity:
    """Metadata and 2D projection parameters for a local or SLAM-generated PCD map."""

    id: Optional[int] = None
    name: str = "未命名地图"
    file_path: str = ""
    file_size: int = 0
    point_count: int = 0
    bbox: Dict[str, float] = field(
        default_factory=lambda: {
            "min_x": -10.0,
            "max_x": 10.0,
            "min_y": -10.0,
            "max_y": 10.0,
            "min_z": 0.0,
            "max_z": 2.5,
        }
    )
    grid_png_path: str = ""
    resolution: float = 0.05
    origin_x: float = 0.0
    origin_y: float = 0.0
    calib_matrix: Dict[str, Any] = field(
        default_factory=lambda: {"tx": 0.0, "ty": 0.0, "tz": 0.0, "yaw_rad": 0.0, "scale": 1.0}
    )
    created_at: str = field(default_factory=_now_str)
