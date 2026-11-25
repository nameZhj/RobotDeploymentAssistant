# @file: src/viewport3d/stl_vbo_cache.py
# @brief: Vectorized binary/ASCII STL loader with crease-angle smooth normals, GPU VBO pool, and fallback G1 colors.
# @exports: StlMeshData, StlVboCache, StlGpuVboPool, PointCloudVbo, g1_link_material_rgb

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import struct
from typing import Dict, Optional, Tuple
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


def _compute_crease_normals(
    v0: np.ndarray, v1: np.ndarray, v2: np.ndarray,
    fallback_n: Optional[np.ndarray], crease_deg: float,
) -> np.ndarray:
    """Compute area-weighted crease-angle smooth vertex normals from flat triangles."""
    cross_n = np.cross(v1 - v0, v2 - v0).astype(np.float32)
    lens = np.linalg.norm(cross_n, axis=1, keepdims=True)
    deg_mask = lens[:, 0] < 1e-10
    if fallback_n is not None and deg_mask.any():
        cross_n[deg_mask] = fallback_n[deg_mask]
        lens = np.linalg.norm(cross_n, axis=1, keepdims=True)
    safe_lens = np.where(lens < 1e-10, 1.0, lens)
    unit_face_n = cross_n / safe_lens
    zero_face = np.sum(unit_face_n * unit_face_n, axis=1) < 1e-8
    if zero_face.any():
        unit_face_n[zero_face] = np.array([0.0, 0.0, 1.0], dtype=np.float32)

    if crease_deg <= 0.5:
        return np.ascontiguousarray(np.repeat(unit_face_n, 3, axis=0), dtype=np.float32)

    verts = np.stack([v0, v1, v2], axis=1).reshape(-1, 3)
    # 0.1 mm integer vertex welding preserves sharp CAD edges while merging shared manifold vertices
    q = np.round(verts * 10000.0).astype(np.int64)
    packed = np.ascontiguousarray(q).view([("x", "<i8"), ("y", "<i8"), ("z", "<i8")]).ravel()
    uniq_cnt = np.unique(packed, return_inverse=True)
    inv = uniq_cnt[1]
    n_uniq = len(uniq_cnt[0])

    weighted_corner_n = np.repeat(cross_n, 3, axis=0)
    acc = np.zeros((n_uniq, 3), dtype=np.float32)
    np.add.at(acc, inv, weighted_corner_n)
    acc_len = np.linalg.norm(acc, axis=1, keepdims=True)
    acc /= np.where(acc_len < 1e-10, 1.0, acc_len)

    face_rep = np.repeat(unit_face_n, 3, axis=0)
    smooth_corner = acc[inv]
    cos_thresh = math.cos(math.radians(crease_deg))
    dots = np.sum(face_rep * smooth_corner, axis=1)
    use_smooth = (dots >= cos_thresh) & (np.sum(smooth_corner * smooth_corner, axis=1) > 0.5)
    out = np.where(use_smooth[:, None], smooth_corner, face_rep)
    out_len = np.linalg.norm(out, axis=1, keepdims=True)
    out = out / np.where(out_len < 1e-8, 1.0, out_len)
    return np.ascontiguousarray(out, dtype=np.float32)


def load_stl_file(path: Path, crease_deg: float = 38.0) -> Optional[StlMeshData]:
    """Parse binary or ASCII STL file into contiguous float32 vertices with smooth crease normals."""
    if not path.exists():
        return None
    raw = path.read_bytes()
    if len(raw) >= 84:
        tri_count = struct.unpack_from("<I", raw, 80)[0]
        if 84 + tri_count * 50 == len(raw) and tri_count > 0:
            records = np.frombuffer(raw, dtype=_BIN_TRI_DTYPE, count=tri_count, offset=84)
            v0 = np.asarray(records["v0"], dtype=np.float32)
            v1 = np.asarray(records["v1"], dtype=np.float32)
            v2 = np.asarray(records["v2"], dtype=np.float32)
            verts = np.ascontiguousarray(np.stack([v0, v1, v2], axis=1).reshape(-1, 3), dtype=np.float32)
            norms = _compute_crease_normals(v0, v1, v2, records["normal"], crease_deg)
            return StlMeshData(vertices=verts, normals=norms, vertex_count=int(tri_count * 3))

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
    tri_n = len(v_arr) // 3
    if tri_n > 0 and tri_n * 3 == len(v_arr):
        tris = v_arr.reshape(tri_n, 3, 3)
        fb = np.asarray(tri_norms[::3], dtype=np.float32)
        n_arr = _compute_crease_normals(tris[:, 0], tris[:, 1], tris[:, 2], fb, crease_deg)
    else:
        n_arr = np.asarray(tri_norms, dtype=np.float32)
    return StlMeshData(vertices=np.ascontiguousarray(v_arr, dtype=np.float32), normals=n_arr, vertex_count=len(v_arr))


class StlVboCache:
    """In-memory STL buffer cache indexed by relative URDF mesh path."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self._cache: Dict[str, Optional[StlMeshData]] = {}

    def get_mesh(self, rel_path: str) -> Optional[StlMeshData]:
        if rel_path not in self._cache:
            self._cache[rel_path] = load_stl_file(self.base_dir / rel_path)
        return self._cache[rel_path]

    def preload_all(self, rel_paths: list[str]) -> int:
        return sum(1 for rp in rel_paths if self.get_mesh(rp) is not None)


class StlGpuVboPool:
    """GPU VBO pool sharing static G1 mesh buffers across all robot instances."""

    def __init__(self) -> None:
        self._vbos: Dict[str, Tuple[int, int, int]] = {}

    def draw(self, gl_mod, rel_path: str, mesh: StlMeshData) -> None:
        use_vbo = bool(hasattr(gl_mod, "glGenBuffers") and getattr(gl_mod, "glBufferData", None))
        if not use_vbo:
            gl_mod.glVertexPointer(3, gl_mod.GL_FLOAT, 0, mesh.vertices)
            gl_mod.glNormalPointer(gl_mod.GL_FLOAT, 0, mesh.normals)
            gl_mod.glDrawArrays(gl_mod.GL_TRIANGLES, 0, mesh.vertex_count)
            return

        entry = self._vbos.get(rel_path)
        if entry is None:
            vbo_v = int(gl_mod.glGenBuffers(1))
            gl_mod.glBindBuffer(gl_mod.GL_ARRAY_BUFFER, vbo_v)
            gl_mod.glBufferData(gl_mod.GL_ARRAY_BUFFER, mesh.vertices.nbytes, mesh.vertices, gl_mod.GL_STATIC_DRAW)
            vbo_n = int(gl_mod.glGenBuffers(1))
            gl_mod.glBindBuffer(gl_mod.GL_ARRAY_BUFFER, vbo_n)
            gl_mod.glBufferData(gl_mod.GL_ARRAY_BUFFER, mesh.normals.nbytes, mesh.normals, gl_mod.GL_STATIC_DRAW)
            entry = (vbo_v, vbo_n, mesh.vertex_count)
            self._vbos[rel_path] = entry

        vbo_v, vbo_n, cnt = entry
        gl_mod.glBindBuffer(gl_mod.GL_ARRAY_BUFFER, vbo_v)
        gl_mod.glVertexPointer(3, gl_mod.GL_FLOAT, 0, None)
        gl_mod.glBindBuffer(gl_mod.GL_ARRAY_BUFFER, vbo_n)
        gl_mod.glNormalPointer(gl_mod.GL_FLOAT, 0, None)
        gl_mod.glDrawArrays(gl_mod.GL_TRIANGLES, 0, cnt)
        gl_mod.glBindBuffer(gl_mod.GL_ARRAY_BUFFER, 0)

    def release_all(self, gl_mod) -> None:
        ids = [bid for v, n, _ in self._vbos.values() for bid in (v, n) if bid]
        self._vbos.clear()
        if ids and hasattr(gl_mod, "glDeleteBuffers"):
            try:
                gl_mod.glDeleteBuffers(len(ids), ids)
            except Exception:
                pass


def g1_link_material_rgb(
    mesh_rel_path: str, track_rgb: tuple[float, float, float], colliding: bool
) -> tuple[float, float, float]:
    """Fallback G1 surface color when URDF material tag is absent (never body-paints track colors)."""
    if colliding:
        return (0.92, 0.28, 0.30)
    n = mesh_rel_path.lower()
    if "rubber_hand" in n:
        return (0.15, 0.16, 0.18)
    if any(k in n for k in ("head", "logo", "ankle_roll", "hip_pitch", "pelvis.stl")):
        return (0.19, 0.20, 0.23)
    return (0.74, 0.76, 0.79)


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
