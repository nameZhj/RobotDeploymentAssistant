# @file: src/viewport3d/stl_vbo_cache.py
# @brief: Fast vectorized binary/ASCII STL loader and G1 multi-material color mapper for OpenGL.
# @exports: StlMeshData, StlVboCache, g1_link_material_rgb

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import Dict, Optional
import numpy as np


@dataclass(frozen=True)
class StlMeshData:
    """Contiguous triangle buffer for glDrawArrays(GL_TRIANGLES)."""

    vertices: np.ndarray  # (N*3, 3) float32
    normals: np.ndarray   # (N*3, 3) float32
    vertex_count: int


_BIN_TRI_DTYPE = np.dtype(
    [
        ("normal", "<f4", (3,)),
        ("v0", "<f4", (3,)),
        ("v1", "<f4", (3,)),
        ("v2", "<f4", (3,)),
        ("attr", "<u2"),
    ]
)


def load_stl_file(path: Path) -> Optional[StlMeshData]:
    """Parse binary or ASCII STL file quickly into flat float32 numpy vertex/normal arrays."""
    if not path.exists():
        return None
    raw = path.read_bytes()
    if len(raw) >= 84:
        tri_count = struct.unpack_from("<I", raw, 80)[0]
        if 84 + tri_count * 50 == len(raw) and tri_count > 0:
            records = np.frombuffer(raw, dtype=_BIN_TRI_DTYPE, count=tri_count, offset=84)
            v0, v1, v2 = records["v0"], records["v1"], records["v2"]
            verts = np.stack([v0, v1, v2], axis=1).reshape(-1, 3)
            raw_n = records["normal"].copy()
            zero_mask = np.sum(raw_n * raw_n, axis=1) < 1e-8
            if zero_mask.any():
                face_n = np.cross(v1 - v0, v2 - v0)
                lengths = np.linalg.norm(face_n, axis=1, keepdims=True)
                lengths = np.where(lengths < 1e-8, 1.0, lengths)
                raw_n[zero_mask] = (face_n / lengths)[zero_mask]
            norms = np.repeat(raw_n, 3, axis=0)
            return StlMeshData(vertices=np.ascontiguousarray(verts, dtype=np.float32),
                               normals=np.ascontiguousarray(norms, dtype=np.float32),
                               vertex_count=int(tri_count * 3))

    # Fallback ASCII STL parser
    tri_verts = []
    tri_norms = []
    cur_norm = [0.0, 0.0, 1.0]
    for line in raw.decode("utf-8", errors="ignore").splitlines():
        parts = line.strip().split()
        if not parts:
            continue
        if parts[0] == "facet" and len(parts) >= 5:
            cur_norm = [float(parts[2]), float(parts[3]), float(parts[4])]
        elif parts[0] == "vertex" and len(parts) >= 4:
            tri_verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
            tri_norms.append(cur_norm)
    if not tri_verts:
        return None
    v_arr = np.asarray(tri_verts, dtype=np.float32)
    n_arr = np.asarray(tri_norms, dtype=np.float32)
    return StlMeshData(vertices=v_arr, normals=n_arr, vertex_count=len(v_arr))


class StlVboCache:
    """In-memory STL buffer cache indexed by relative URDF mesh path."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self._cache: Dict[str, Optional[StlMeshData]] = {}

    def get_mesh(self, rel_path: str) -> Optional[StlMeshData]:
        if rel_path not in self._cache:
            full_path = self.base_dir / rel_path
            self._cache[rel_path] = load_stl_file(full_path)
        return self._cache[rel_path]

    def preload_all(self, rel_paths: list[str]) -> int:
        loaded = 0
        for rp in rel_paths:
            if self.get_mesh(rp) is not None:
                loaded += 1
        return loaded


def g1_link_material_rgb(
    mesh_rel_path: str, track_rgb: tuple[float, float, float], colliding: bool
) -> tuple[float, float, float]:
    """Authentic Unitree G1 multi-material hardware shading matching web/js/dance_player3d.js."""
    if colliding:
        return (0.94, 0.25, 0.28)
    n = mesh_rel_path.lower()
    if "logo" in n:
        return (0.0, 0.94, 1.0)
    if "head" in n:
        return (0.10, 0.13, 0.17)
    if "rubber_hand" in n or "palm" in n or "hand" in n:
        return (0.11, 0.13, 0.16)
    if any(k in n for k in ("torso", "pelvis", "waist")):
        r, g, b = track_rgb
        return (0.14 + 0.16 * r, 0.16 + 0.16 * g, 0.21 + 0.16 * b)
    return (0.78, 0.82, 0.87)
