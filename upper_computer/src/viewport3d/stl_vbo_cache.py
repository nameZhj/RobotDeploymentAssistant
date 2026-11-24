# @file: src/viewport3d/stl_vbo_cache.py
# @brief: Fast vectorized binary/ASCII STL loader, GPU point-cloud VBO manager, and G1 material color mapper.
# @exports: StlMeshData, StlVboCache, PointCloudVbo, g1_link_material_rgb

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


class PointCloudVbo:
    """GPU VBO owner for dynamic SLAM/PCD clouds with explicit buffer release to avoid VRAM leaks."""

    def __init__(self) -> None:
        self._vbo_xyz: int = 0
        self._vbo_rgb: int = 0
        self._dirty: bool = False
        self._count: int = 0

    def mark_dirty(self, count: int) -> None:
        self._count = count
        self._dirty = True

    def release(self, gl_mod) -> None:
        ids = [b for b in (self._vbo_xyz, self._vbo_rgb) if b]
        self._vbo_xyz = self._vbo_rgb = 0
        if ids and hasattr(gl_mod, "glDeleteBuffers"):
            try:
                gl_mod.glDeleteBuffers(len(ids), ids)
            except Exception:
                pass

    def draw(self, gl_mod, xyz: np.ndarray, rgb: Optional[np.ndarray]) -> None:
        use_vbo = bool(hasattr(gl_mod, "glGenBuffers") and bool(getattr(gl_mod, "glBufferData", None)))
        if not use_vbo:
            gl_mod.glVertexPointer(3, gl_mod.GL_FLOAT, 0, xyz)
            if rgb is not None:
                gl_mod.glEnableClientState(gl_mod.GL_COLOR_ARRAY)
                gl_mod.glColorPointer(3, gl_mod.GL_FLOAT, 0, rgb)
            else:
                gl_mod.glColor3f(0.35, 0.65, 0.78)
            gl_mod.glDrawArrays(gl_mod.GL_POINTS, 0, len(xyz))
            if rgb is not None:
                gl_mod.glDisableClientState(gl_mod.GL_COLOR_ARRAY)
            return

        if self._dirty:
            self.release(gl_mod)
            self._vbo_xyz = int(gl_mod.glGenBuffers(1))
            gl_mod.glBindBuffer(gl_mod.GL_ARRAY_BUFFER, self._vbo_xyz)
            gl_mod.glBufferData(gl_mod.GL_ARRAY_BUFFER, xyz.nbytes, xyz, gl_mod.GL_DYNAMIC_DRAW)
            if rgb is not None:
                self._vbo_rgb = int(gl_mod.glGenBuffers(1))
                gl_mod.glBindBuffer(gl_mod.GL_ARRAY_BUFFER, self._vbo_rgb)
                gl_mod.glBufferData(gl_mod.GL_ARRAY_BUFFER, rgb.nbytes, rgb, gl_mod.GL_DYNAMIC_DRAW)
            self._dirty = False

        gl_mod.glBindBuffer(gl_mod.GL_ARRAY_BUFFER, self._vbo_xyz)
        gl_mod.glVertexPointer(3, gl_mod.GL_FLOAT, 0, None)
        if self._vbo_rgb and rgb is not None:
            gl_mod.glEnableClientState(gl_mod.GL_COLOR_ARRAY)
            gl_mod.glBindBuffer(gl_mod.GL_ARRAY_BUFFER, self._vbo_rgb)
            gl_mod.glColorPointer(3, gl_mod.GL_FLOAT, 0, None)
        else:
            gl_mod.glColor3f(0.35, 0.65, 0.78)
        gl_mod.glDrawArrays(gl_mod.GL_POINTS, 0, self._count)
        gl_mod.glBindBuffer(gl_mod.GL_ARRAY_BUFFER, 0)
        if self._vbo_rgb and rgb is not None:
            gl_mod.glDisableClientState(gl_mod.GL_COLOR_ARRAY)
