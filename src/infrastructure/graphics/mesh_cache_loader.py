import io
import logging
import math
import os
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from src.core.config_loader import config_loader

logger = logging.getLogger("MeshCacheLoader")


@dataclass(frozen=True)
class MeshData:
    vertices: List[Tuple[float, float, float]] = field(default_factory=list)
    normals: List[Tuple[float, float, float]] = field(default_factory=list)
    indices: List[int] = field(default_factory=list)
    bbox: Tuple[float, float, float, float, float, float] = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    radius: float = 0.0


class MeshCacheLoader:
    """Loads and caches 3D geometric meshes (STL/OBJ/Primitives) for simulation."""

    def __init__(self) -> None:
        paths = config_loader.get_paths()
        self._assets_dir = Path(paths.get("assets_dir", "assets"))
        self._cache_dir = Path(paths.get("cache_dir", "runtime/cache"))
        self._assets_dir.mkdir(parents=True, exist_ok=True)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[str, MeshData] = {}

    def get_or_load(self, identifier: str) -> Optional[MeshData]:
        """Fetch mesh from in-memory cache or load from disk/synthesizer."""
        if identifier in self._memory_cache:
            return self._memory_cache[identifier]

        resolved_path = self._resolve_path(identifier)
        if resolved_path and resolved_path.is_file():
            mesh = self.load_from_file(resolved_path)
            if mesh:
                self._memory_cache[identifier] = mesh
                return mesh

        # Fallback to primitive if identifier indicates a standard shape
        if identifier.startswith("primitive_box"):
            mesh = self.create_box()
            self._memory_cache[identifier] = mesh
            return mesh
        if identifier.startswith("primitive_cylinder"):
            mesh = self.create_cylinder()
            self._memory_cache[identifier] = mesh
            return mesh

        return None

    def load_from_file(self, filepath: Path) -> Optional[MeshData]:
        """Read and parse 3D mesh file based on extension."""
        suffix = filepath.suffix.lower()
        try:
            if suffix == ".stl":
                return self._parse_stl(filepath)
            if suffix == ".obj":
                return self._parse_obj(filepath)
            logger.warning(f"Unsupported mesh format for {filepath}")
        except Exception as exc:
            logger.error(f"Failed to load mesh from {filepath}: {exc}")
        return None

    def _resolve_path(self, identifier: str) -> Optional[Path]:
        p = Path(identifier)
        if p.is_file():
            return p
        in_assets = self._assets_dir / identifier
        if in_assets.is_file():
            return in_assets
        in_cache = self._cache_dir / identifier
        if in_cache.is_file():
            return in_cache
        return None

    def _parse_stl(self, filepath: Path) -> Optional[MeshData]:
        with open(filepath, "rb") as f:
            header = f.read(80)
            if len(header) < 80:
                return None
            count_bytes = f.read(4)
            if len(count_bytes) < 4:
                return None
            triangle_count = struct.unpack("<I", count_bytes)[0]
            expected_size = 84 + triangle_count * 50
            actual_size = filepath.stat().st_size

            if actual_size == expected_size:
                return self._parse_binary_stl(f, triangle_count)
        return self._parse_ascii_stl(filepath)

    def _parse_binary_stl(self, f: io.BufferedReader, count: int) -> MeshData:
        vertices: List[Tuple[float, float, float]] = []
        normals: List[Tuple[float, float, float]] = []
        indices: List[int] = []

        for i in range(count):
            data = f.read(50)
            if len(data) < 50:
                break
            vals = struct.unpack("<12fH", data)
            nx, ny, nz = vals[0], vals[1], vals[2]
            idx_start = len(vertices)
            for v_idx in range(3):
                vx = vals[3 + v_idx * 3]
                vy = vals[4 + v_idx * 3]
                vz = vals[5 + v_idx * 3]
                vertices.append((vx, vy, vz))
                normals.append((nx, ny, nz))
                indices.append(idx_start + v_idx)

        bbox, center, radius = self.compute_bounds(vertices)
        return MeshData(vertices, normals, indices, bbox, center, radius)

    def _parse_ascii_stl(self, filepath: Path) -> MeshData:
        vertices: List[Tuple[float, float, float]] = []
        normals: List[Tuple[float, float, float]] = []
        indices: List[int] = []
        cur_normal = (0.0, 0.0, 1.0)

        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                parts = line.strip().split()
                if not parts:
                    continue
                if parts[0] == "facet" and len(parts) >= 5 and parts[1] == "normal":
                    cur_normal = (float(parts[2]), float(parts[3]), float(parts[4]))
                elif parts[0] == "vertex" and len(parts) >= 4:
                    indices.append(len(vertices))
                    vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
                    normals.append(cur_normal)

        bbox, center, radius = self.compute_bounds(vertices)
        return MeshData(vertices, normals, indices, bbox, center, radius)

    def _parse_obj(self, filepath: Path) -> MeshData:
        raw_v: List[Tuple[float, float, float]] = []
        vertices: List[Tuple[float, float, float]] = []
        normals: List[Tuple[float, float, float]] = []
        indices: List[int] = []

        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                parts = line.strip().split()
                if not parts:
                    continue
                if parts[0] == "v" and len(parts) >= 4:
                    raw_v.append((float(parts[1]), float(parts[2]), float(parts[3])))
                elif parts[0] == "f" and len(parts) >= 4:
                    f_indices = []
                    for seg in parts[1:4]:
                        v_idx = int(seg.split("/")[0]) - 1
                        f_indices.append(v_idx)
                    idx_base = len(vertices)
                    for vi in f_indices:
                        if 0 <= vi < len(raw_v):
                            vertices.append(raw_v[vi])
                            normals.append((0.0, 0.0, 1.0))
                            indices.append(len(vertices) - 1)

        bbox, center, radius = self.compute_bounds(vertices)
        return MeshData(vertices, normals, indices, bbox, center, radius)

    def create_box(self, width: float = 0.5, height: float = 0.3, depth: float = 0.3) -> MeshData:
        """Create a lightweight rectangular prism for Eco avatar LOD."""
        hw, hh, hd = width / 2.0, height / 2.0, depth / 2.0
        v = [
            (-hw, -hh, -hd), (hw, -hh, -hd), (hw, hh, -hd), (-hw, hh, -hd),
            (-hw, -hh, hd), (hw, -hh, hd), (hw, hh, hd), (-hw, hh, hd)
        ]
        quads = [
            (0, 1, 2, 3), (5, 4, 7, 6), (4, 0, 3, 7),
            (1, 5, 6, 2), (3, 2, 6, 7), (4, 5, 1, 0)
        ]
        vertices: List[Tuple[float, float, float]] = []
        indices: List[int] = []
        for q in quads:
            idx = len(vertices)
            vertices.extend([v[q[0]], v[q[1]], v[q[2]], v[q[3]]])
            indices.extend([idx, idx + 1, idx + 2, idx, idx + 2, idx + 3])
        normals = [(0.0, 0.0, 1.0)] * len(vertices)
        bbox, center, radius = self.compute_bounds(vertices)
        return MeshData(vertices, normals, indices, bbox, center, radius)

    def create_cylinder(self, radius: float = 0.15, height: float = 0.4, segments: int = 12) -> MeshData:
        """Generate a low-poly cylinder for body/wheels representation."""
        vertices: List[Tuple[float, float, float]] = []
        indices: List[int] = []
        hh = height / 2.0

        for i in range(segments):
            angle = 2.0 * math.pi * i / segments
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            vertices.append((x, y, -hh))
            vertices.append((x, y, hh))

        for i in range(segments):
            next_i = (i + 1) % segments
            b1, t1 = i * 2, i * 2 + 1
            b2, t2 = next_i * 2, next_i * 2 + 1
            indices.extend([b1, b2, t1, b2, t2, t1])

        normals = [(0.0, 0.0, 1.0)] * len(vertices)
        bbox, center, radius = self.compute_bounds(vertices)
        return MeshData(vertices, normals, indices, bbox, center, radius)

    @staticmethod
    def compute_bounds(
        vertices: List[Tuple[float, float, float]]
    ) -> Tuple[Tuple[float, float, float, float, float, float], Tuple[float, float, float], float]:
        """Calculate axis-aligned bounding box (min_xyz, max_xyz), center, and radius."""
        if not vertices:
            return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 0.0

        min_x = min(v[0] for v in vertices)
        max_x = max(v[0] for v in vertices)
        min_y = min(v[1] for v in vertices)
        max_y = max(v[1] for v in vertices)
        min_z = min(v[2] for v in vertices)
        max_z = max(v[2] for v in vertices)

        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0
        cz = (min_z + max_z) / 2.0

        radius = max(math.sqrt((v[0] - cx) ** 2 + (v[1] - cy) ** 2 + (v[2] - cz) ** 2) for v in vertices)
        return (min_x, max_x, min_y, max_y, min_z, max_z), (cx, cy, cz), radius

    def clear_cache(self) -> None:
        """Clear the in-memory mesh storage."""
        self._memory_cache.clear()

