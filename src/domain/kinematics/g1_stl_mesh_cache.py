"""
@file: src/domain/kinematics/g1_stl_mesh_cache.py
@brief: G1 机器人 165 个 STL 网格文件 Binary/ASCII 双模解析与 ECO/PRO 双档 LOD 缓存引擎
@exports: G1StlMeshCache, parse_stl_file
"""
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


def parse_stl_file(file_path: str, lod_mode: str = "PRO") -> Tuple[np.ndarray, np.ndarray]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"STL 文件未找到: {file_path}")
    sz = os.path.getsize(file_path)
    is_bin = False
    if sz >= 84:
        with open(file_path, "rb") as f:
            f.seek(80)
            fc = np.fromfile(f, dtype="<u4", count=1)[0]
        if 84 + fc * 50 == sz:
            is_bin = True

    if is_bin:
        with open(file_path, "rb") as f:
            f.seek(84)
            dt = np.dtype([("normal", "<f4", (3,)), ("v", "<f4", (3, 3)), ("attr", "<u2")])
            data = np.fromfile(f, dtype=dt, count=fc)
        normals, verts = data["normal"], data["v"]
    else:
        n_list: List[List[float]] = []
        v_list: List[List[List[float]]] = []
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            c_norm, c_verts = [0.0, 0.0, 1.0], []
            for line in f:
                p = line.strip().split()
                if len(p) >= 5 and p[0] == "facet" and p[1] == "normal":
                    c_norm = [float(p[2]), float(p[3]), float(p[4])]
                elif len(p) >= 4 and p[0] == "vertex":
                    c_verts.append([float(p[1]), float(p[2]), float(p[3])])
                    if len(c_verts) == 3:
                        n_list.append(c_norm); v_list.append(c_verts); c_verts = []
        normals = np.array(n_list, dtype=np.float32)
        verts = np.array(v_list, dtype=np.float32)

    if lod_mode.upper() == "ECO" and len(verts) > 120:
        step = max(2, len(verts) // 120)
        verts, normals = verts[::step][:120], normals[::step][:120]
    return verts.astype(np.float32), normals.astype(np.float32)


class G1StlMeshCache:
    """165 个 STL 模型高速载入与 ECO/PRO 档 NPZ 缓存管理器"""

    DEFAULT_MESH_DIR = "assets/models/g1_description/g1_description/meshes"
    DEFAULT_CACHE_DIR = "runtime/cache"

    @classmethod
    def load_all_meshes(
        cls, mesh_dir: Optional[str] = None, lod_mode: str = "ECO",
        cache_dir: Optional[str] = None, max_files: Optional[int] = None
    ) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
        b_dir = mesh_dir or cls.DEFAULT_MESH_DIR
        c_dir = cache_dir or cls.DEFAULT_CACHE_DIR
        os.makedirs(c_dir, exist_ok=True)
        cache_npz = os.path.join(c_dir, "g1_stl_lod_cache.npz" if lod_mode.upper() == "ECO" else f"g1_stl_{lod_mode.lower()}.npz")

        if os.path.exists(cache_npz):
            loaded = np.load(cache_npz, allow_pickle=True)
            res: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
            for k in loaded.files:
                if k.endswith("_v"):
                    stem = k[:-2]
                    res[stem] = (loaded[k], loaded[f"{stem}_n"])
            if res:
                return res

        res, payload = {}, {}
        stls = sorted(Path(b_dir).glob("*.stl")) + sorted(Path(b_dir).glob("*.STL"))
        items = list({p.stem.lower(): p for p in stls}.items())
        if max_files: items = items[:max_files]

        for stem, p in items:
            try:
                v, n = parse_stl_file(str(p), lod_mode=lod_mode)
                res[stem] = (v, n)
                payload[f"{stem}_v"], payload[f"{stem}_n"] = v, n
            except Exception:
                continue
        if payload:
            np.savez_compressed(cache_npz, **payload)
        return res


g1_stl_mesh_cache = G1StlMeshCache()

