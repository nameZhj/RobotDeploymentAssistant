import hashlib
import json
import logging
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from src.core.config_loader import config_loader
from src.infrastructure.graphics.gpu_capability_probe import gpu_capability_probe

logger = logging.getLogger("PointCloudMapLoader")


@dataclass(frozen=True)
class PointCloudMap:
    """LiDAR point cloud stage environment with bounding coordinates."""
    points: List[Tuple[float, float, float]] = field(default_factory=list)
    intensities: List[float] = field(default_factory=list)
    bounds: Tuple[float, float, float, float, float, float] = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    voxel_size_m: float = 0.0
    is_downsampled: bool = False

    @property
    def count(self) -> int:
        return len(self.points)


class PointCloudMapLoader:
    """
    Parses PCD/PLY LiDAR point clouds and applies voxel downsampling in Eco mode
    to guarantee smooth 60 FPS on integrated laptop GPUs. Caches data in runtime/cache/.
    """

    def __init__(self) -> None:
        paths = config_loader.get_paths()
        cache_name = paths.get("cache_dir", "runtime/cache")
        self._cache_dir = Path(cache_name)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[str, PointCloudMap] = {}

    def load_map(self, filepath: Path | str, force_voxel_m: Optional[float] = None) -> PointCloudMap:
        """Load and optionally downsample point cloud based on active GPU profile."""
        path = Path(filepath)
        policy = gpu_capability_probe.get_render_policy()
        voxel_m = force_voxel_m if force_voxel_m is not None else float(policy.get("voxel_downsample_m", 0.15))
        cache_key = f"{path.stem}_{voxel_m:.2f}_{path.stat().st_size if path.exists() else 0}"

        if cache_key in self._memory_cache:
            return self._memory_cache[cache_key]

        cached_file = self._cache_dir / f"pcd_{cache_key}.json"
        if cached_file.is_file():
            try:
                data = json.loads(cached_file.read_text(encoding="utf-8"))
                pc = PointCloudMap(**data)
                self._memory_cache[cache_key] = pc
                return pc
            except Exception as e:
                logger.warning(f"Error reading point cloud cache, rebuilding: {e}")

        raw_points, raw_intensities = self._parse_file(path)
        if not raw_points:
            # Generate synthetic stage boundary point cloud if file does not exist
            raw_points, raw_intensities = self._synthesize_stage_floor()

        # Apply voxel grid downsampling if voxel_m > 0
        final_pts, final_ints, is_down = self.voxel_downsample(raw_points, raw_intensities, voxel_m)
        bounds = self._compute_bounds(final_pts)

        result = PointCloudMap(
            points=final_pts,
            intensities=final_ints,
            bounds=bounds,
            voxel_size_m=voxel_m,
            is_downsampled=is_down,
        )

        try:
            cached_file.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to write point cloud cache: {e}")

        self._memory_cache[cache_key] = result
        return result

    def voxel_downsample(
        self,
        points: List[Tuple[float, float, float]],
        intensities: List[float],
        voxel_size: float,
    ) -> Tuple[List[Tuple[float, float, float]], List[float], bool]:
        """Aggregate points falling into the same 3D voxel cube to centroid."""
        if voxel_size <= 0.01 or len(points) < 500:
            return points, intensities, False

        voxel_dict: Dict[Tuple[int, int, int], List[int]] = {}
        for idx, (x, y, z) in enumerate(points):
            vx = int(math.floor(x / voxel_size))
            vy = int(math.floor(y / voxel_size))
            vz = int(math.floor(z / voxel_size))
            key = (vx, vy, vz)
            if key not in voxel_dict:
                voxel_dict[key] = []
            voxel_dict[key].append(idx)

        sampled_pts: List[Tuple[float, float, float]] = []
        sampled_ints: List[float] = []

        for indices in voxel_dict.values():
            avg_x = sum(points[i][0] for i in indices) / len(indices)
            avg_y = sum(points[i][1] for i in indices) / len(indices)
            avg_z = sum(points[i][2] for i in indices) / len(indices)
            avg_int = sum(intensities[i] for i in indices) / len(indices) if intensities else 1.0

            sampled_pts.append((round(avg_x, 3), round(avg_y, 3), round(avg_z, 3)))
            sampled_ints.append(round(avg_int, 2))

        return sampled_pts, sampled_ints, True

    def _parse_file(self, path: Path) -> Tuple[List[Tuple[float, float, float]], List[float]]:
        if not path.is_file():
            return [], []
        points, intensities = [], []
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                header_passed = False
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("DATA"):
                        header_passed = True
                        continue
                    if header_passed or line[0].isdigit() or line[0] == "-":
                        parts = line.split()
                        if len(parts) >= 3:
                            x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                            intensity = float(parts[3]) if len(parts) > 3 else 1.0
                            points.append((x, y, z))
                            intensities.append(intensity)
        except Exception as e:
            logger.warning(f"Failed to parse point cloud file {path}: {e}")
        return points, intensities

    def _synthesize_stage_floor(self) -> Tuple[List[Tuple[float, float, float]], List[float]]:
        """Synthesize planar stage floor points when no LiDAR map is provided."""
        pts, ints = [], []
        for x in range(-50, 51, 5):
            for y in range(-50, 51, 5):
                pts.append((x * 0.1, y * 0.1, 0.0))
                ints.append(0.8)
        return pts, ints

    @staticmethod
    def _compute_bounds(pts: List[Tuple[float, float, float]]) -> Tuple[float, float, float, float, float, float]:
        if not pts:
            return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        zs = [p[2] for p in pts]
        return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


pointcloud_map_loader = PointCloudMapLoader()

