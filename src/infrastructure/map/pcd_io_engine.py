"""
@file: src/infrastructure/map/pcd_io_engine.py
@brief: PCD 点云文件读写引擎与默认倾斜舞台点云生成器
@exports: PcdMapLoader, pcd_file_to_points, pcd_file_to_grid_png
"""
import os
import re
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


class PcdMapLoader:
    """提供 ASCII 与 Binary 格式的 PCD 文件解析、持久化及默认舞台合成"""

    @classmethod
    def load_pcd(cls, file_path: str) -> np.ndarray:
        if not file_path or not os.path.exists(file_path):
            return cls.generate_default_stage_points()
        with open(file_path, "rb") as f:
            header, data_mode, offset = cls._read_header(f)
            count = header.get("POINTS", 0)
            f.seek(offset)
            if data_mode == "binary_compressed":
                from src.domain.map.stage_map_asset import UnsupportedPcdFormatError
                raise UnsupportedPcdFormatError(
                    "binary_compressed PCD 暂不支持，请先转换为标准 binary 或 ASCII 格式"
                )
            if data_mode == "binary":
                return cls._parse_binary_body(f, header, count)
            return cls._parse_ascii_body(f, header, count)

    @classmethod
    def _read_header(cls, f) -> Tuple[Dict[str, any], str, int]:
        header: Dict[str, any] = {}
        data_mode = "ascii"
        offset = 0
        while True:
            line_bytes = f.readline()
            if not line_bytes:
                break
            offset += len(line_bytes)
            line = line_bytes.decode("utf-8", errors="ignore").strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            key = parts[0].upper()
            if key in ("FIELDS", "TYPE"):
                header[key] = parts[1:]
            elif key in ("SIZE", "COUNT"):
                header[key] = [int(p) for p in parts[1:]]
            elif key in ("WIDTH", "HEIGHT", "POINTS"):
                header[key] = int(parts[1])
            elif key == "DATA":
                data_mode = parts[1].lower()
                break
        return header, data_mode, offset

    @classmethod
    def _parse_ascii_body(cls, f, header: Dict[str, any], count: int) -> np.ndarray:
        fields = header.get("FIELDS", ["x", "y", "z"])
        xi = fields.index("x") if "x" in fields else 0
        yi = fields.index("y") if "y" in fields else 1
        zi = fields.index("z") if "z" in fields else 2
        coords: List[List[float]] = []
        for line in f.read().decode("utf-8", errors="ignore").splitlines():
            tokens = line.strip().split()
            if len(tokens) >= 3:
                try:
                    coords.append([float(tokens[xi]), float(tokens[yi]), float(tokens[zi])])
                except (ValueError, IndexError):
                    continue
                if count > 0 and len(coords) >= count:
                    break
        if not coords:
            return cls.generate_default_stage_points()
        return np.array(coords, dtype=np.float32)

    @classmethod
    def _parse_binary_body(cls, f, header: Dict[str, any], count: int) -> np.ndarray:
        fields = header.get("FIELDS", ["x", "y", "z"])
        sizes = header.get("SIZE", [4] * len(fields))
        types = header.get("TYPE", ["F"] * len(fields))
        type_map = {"F": "f", "I": "i", "U": "u"}
        dtype_list = [(name, f"<{type_map.get(tp, 'f')}{sz}") for name, sz, tp in zip(fields, sizes, types)]
        raw = f.read()
        arr = np.frombuffer(raw, dtype=np.dtype(dtype_list), count=count)
        if "x" in arr.dtype.names and "y" in arr.dtype.names and "z" in arr.dtype.names:
            return np.column_stack((arr["x"], arr["y"], arr["z"])).astype(np.float32)
        return cls.generate_default_stage_points()

    @classmethod
    def save_ascii(cls, file_path: str, points: np.ndarray) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        n = len(points)
        hdr = (
            f"# .PCD v.7 - Point Cloud Data\nVERSION .7\nFIELDS x y z\n"
            f"SIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\nWIDTH {n}\nHEIGHT 1\n"
            f"VIEWPOINT 0 0 0 1 0 0 0\nPOINTS {n}\nDATA ascii\n"
        )
        lines = [f"{p[0]:.4f} {p[1]:.4f} {p[2]:.4f}\n" for p in points]
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(hdr + "".join(lines))

    @classmethod
    def save_binary(cls, file_path: str, points: np.ndarray) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        n = len(points)
        hdr = (
            f"# .PCD v.7 - Point Cloud Data\nVERSION .7\nFIELDS x y z\n"
            f"SIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\nWIDTH {n}\nHEIGHT 1\n"
            f"VIEWPOINT 0 0 0 1 0 0 0\nPOINTS {n}\nDATA binary\n"
        )
        with open(file_path, "wb") as f:
            f.write(hdr.encode("utf-8"))
            f.write(points.astype(np.float32).tobytes())

    @classmethod
    def generate_default_stage_points(cls, count: int = 24000) -> np.ndarray:
        np.random.seed(42)
        n_noise = 800
        n_wall = max(0, count - n_noise)
        z_rings = np.linspace(0.25, 1.95, 5)
        segs = [
            ((-7.0, -2.5), (7.0, -2.5)), ((-7.0, 2.5), (7.0, 2.5)),
            ((-7.0, -2.5), (-7.0, 2.5)), ((7.0, -2.5), (7.0, 2.5)),
            ((-3.0, 0.0), (2.0, 0.0)), ((0.0, -2.5), (0.0, 0.0))
        ]
        lens = [np.hypot(p2[0]-p1[0], p2[1]-p1[1]) for p1, p2 in segs]
        weights = [l / sum(lens) for l in lens]
        pts_list: List[np.ndarray] = []
        for (p1, p2), w in zip(segs, weights):
            np_seg = int(round(n_wall * w))
            t = np.random.uniform(0, 1, np_seg)
            sx = p1[0] + t * (p2[0] - p1[0]) + np.random.normal(0, 0.01, np_seg)
            sy = p1[1] + t * (p2[1] - p1[1]) + np.random.normal(0, 0.01, np_seg)
            zr = np.random.choice(z_rings, np_seg) + np.random.normal(0, 0.01, np_seg)
            pts_list.append(np.column_stack([sx, sy, zr]))
        wall_pts = np.vstack(pts_list)
        if len(wall_pts) > n_wall:
            wall_pts = wall_pts[:n_wall]
        elif len(wall_pts) < n_wall:
            wall_pts = np.vstack([wall_pts, wall_pts[:n_wall - len(wall_pts)]])
        noise = np.column_stack([
            np.random.uniform(-7.0, 7.0, n_noise),
            np.random.uniform(-2.5, 2.5, n_noise),
            np.random.uniform(0.1, 2.1, n_noise)
        ])
        all_pts = np.vstack([wall_pts, noise])
        rad = np.radians(15.0)
        c, s = np.cos(rad), np.sin(rad)
        px = all_pts[:, 0] * c - all_pts[:, 1] * s - 7.0
        py = all_pts[:, 0] * s + all_pts[:, 1] * c - 0.5
        pz = np.clip(all_pts[:, 2], 0.0, 2.2)
        return np.column_stack([px, py, pz]).astype(np.float32)

    @classmethod
    def load_or_create_default(cls, file_path: Optional[str] = None) -> np.ndarray:
        target_path = file_path or os.path.join("runtime", "cache", "default_stage.pcd")
        if os.path.exists(target_path):
            return cls.load_pcd(target_path)
        points = cls.generate_default_stage_points()
        cls.save_binary(target_path, points)
        return points


def pcd_file_to_points(pcd_path: str, max_points: Optional[int] = None):
    from src.infrastructure.map.pcd_grid_engine import pcd_file_to_points as _fn
    return _fn(pcd_path, max_points)


def pcd_file_to_grid_png(pcd_path: str, config: Optional[Any] = None):
    from src.infrastructure.map.pcd_grid_engine import pcd_file_to_grid_png as _fn
    return _fn(pcd_path, config)


