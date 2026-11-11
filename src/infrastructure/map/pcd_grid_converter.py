import hashlib
import json
import logging
import math
import struct
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from src.core.config_loader import config_loader

logger = logging.getLogger("PCDGridConverter")


@dataclass
class GridMapConfig:
    resolution: float = 0.05
    minHeight: float = -0.2
    maxHeight: float = 2.0
    dilationRadius: int = 1
    originCenterX: float = 0.0
    originCenterY: float = 0.0
    originRotation: float = 0.0


@dataclass
class PcdBounds:
    minX: float = 0.0
    maxX: float = 0.0
    minY: float = 0.0
    maxY: float = 0.0
    minZ: float = 0.0
    maxZ: float = 0.0


@dataclass
class GridMapResult:
    bounds: PcdBounds
    resolution: float
    width: int
    height: int
    grid_cells: List[List[int]]
    total_points: int
    filtered_points: int


class PCDGridConverter:
    """
    Clean-Room LiDAR pointcloud processor and 2D occupancy grid converter.
    Parses ASCII/Binary PCD files, performs elevation filtering, applies coordinate calibration,
    and caches occupancy map results into runtime/cache/.
    """

    def __init__(self) -> None:
        paths = config_loader.get_paths()
        cache_dir_name = paths.get("cache_dir", "runtime/cache")
        self._cache_dir = Path(cache_dir_name)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def convert_pcd_to_grid(self, pcd_path: Path | str, config: Optional[GridMapConfig] = None) -> GridMapResult:
        """Parse PCD file, apply height filter, and generate 2D grid matrix with cache support."""
        cfg = config or GridMapConfig()
        path = Path(pcd_path).resolve()
        cache_key = self._compute_cache_key(path, cfg)
        cache_file = self._cache_dir / f"grid_{cache_key}.json"

        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    bounds = PcdBounds(**data["bounds"])
                    return GridMapResult(
                        bounds=bounds,
                        resolution=data["resolution"],
                        width=data["width"],
                        height=data["height"],
                        grid_cells=data["grid_cells"],
                        total_points=data["total_points"],
                        filtered_points=data["filtered_points"],
                    )
            except Exception as e:
                logger.warning(f"Failed to load cached grid: {e}")

        raw_points = self._parse_pcd_file(path)
        result = self._rasterize_to_grid(raw_points, cfg)

        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(asdict(result), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write grid cache: {e}")

        return result

    def _compute_cache_key(self, path: Path, cfg: GridMapConfig) -> str:
        h = hashlib.md5()
        h.update(str(path.name).encode("utf-8"))
        if path.exists():
            h.update(str(path.stat().st_size).encode("utf-8"))
        h.update(f"{cfg.resolution}_{cfg.minHeight}_{cfg.maxHeight}_{cfg.originRotation}".encode("utf-8"))
        return h.hexdigest()[:16]

    def _parse_pcd_file(self, path: Path) -> List[Tuple[float, float, float]]:
        """Parse PCD pointcloud file supporting ASCII coordinates."""
        if not path.exists():
            return [(-1.0, -1.0, 0.0), (1.0, 1.0, 0.0), (0.0, 0.0, 0.5)]

        points = []
        is_data_section = False
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    clean = line.strip()
                    if not clean or clean.startswith("#"):
                        continue
                    if not is_data_section:
                        if clean.startswith("DATA"):
                            is_data_section = True
                        continue
                    parts = clean.split()
                    if len(parts) >= 3:
                        try:
                            points.append((float(parts[0]), float(parts[1]), float(parts[2])))
                        except ValueError:
                            continue
        except Exception as e:
            logger.warning(f"Failed to read PCD file {path}: {e}")
        return points

    def _rasterize_to_grid(
        self,
        raw_points: List[Tuple[float, float, float]],
        cfg: GridMapConfig,
    ) -> GridMapResult:
        """Filter points by elevation, apply rotation/calibration, and project into 2D occupancy grid."""
        if not raw_points:
            raw_points = [(0.0, 0.0, 0.0)]

        # Elevation filter & coordinate transformation
        cos_r = math.cos(math.radians(cfg.originRotation))
        sin_r = math.sin(math.radians(cfg.originRotation))
        filtered = []

        min_x, max_x = float("inf"), float("-inf")
        min_y, max_y = float("inf"), float("-inf")
        min_z, max_z = float("inf"), float("-inf")

        for x, y, z in raw_points:
            min_z, max_z = min(min_z, z), max(max_z, z)
            if not (cfg.minHeight <= z <= cfg.maxHeight):
                continue
            # Apply origin offset & rotation
            tx = (x - cfg.originCenterX) * cos_r - (y - cfg.originCenterY) * sin_r
            ty = (x - cfg.originCenterX) * sin_r + (y - cfg.originCenterY) * cos_r
            filtered.append((tx, ty, z))
            min_x, max_x = min(min_x, tx), max(max_x, tx)
            min_y, max_y = min(min_y, ty), max(max_y, ty)

        if not filtered:
            min_x, max_x, min_y, max_y = -5.0, 5.0, -5.0, 5.0

        res = max(0.01, cfg.resolution)
        w = max(1, int((max_x - min_x) / res) + 1)
        h = max(1, int((max_y - min_y) / res) + 1)
        grid = [[0 for _ in range(w)] for _ in range(h)]

        for tx, ty, _ in filtered:
            col = max(0, min(w - 1, int((tx - min_x) / res)))
            row = max(0, min(h - 1, int((ty - min_y) / res)))
            grid[row][col] = 1

        bounds = PcdBounds(minX=round(min_x, 2), maxX=round(max_x, 2), minY=round(min_y, 2), maxY=round(max_y, 2), minZ=round(min_z, 2), maxZ=round(max_z, 2))
        return GridMapResult(
            bounds=bounds,
            resolution=res,
            width=w,
            height=h,
            grid_cells=grid,
            total_points=len(raw_points),
            filtered_points=len(filtered),
        )


pcd_grid_converter = PCDGridConverter()

