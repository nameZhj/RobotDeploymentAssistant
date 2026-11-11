"""
PCD 点云文件解析引擎
支持 ASCII 与 Binary 格式解析，并提供开箱即用的默认场地环境点云生成器
"""
import os
import re
from typing import Dict, List, Optional, Tuple
import numpy as np


class PcdParserEngine:
    """高效解析 PCD 文件并提取 (x, y, z) 坐标"""

    @classmethod
    def parse_file(cls, file_path: str) -> np.ndarray:
        if not file_path or not os.path.exists(file_path):
            return cls.generate_default_point_cloud()

        with open(file_path, "rb") as f:
            header, data_type, header_len = cls._parse_header(f)
            points_count = header.get("POINTS", 0)

            if data_type == "binary":
                f.seek(header_len)
                return cls._read_binary(f, header, points_count)
            else:
                f.seek(header_len)
                content = f.read().decode("utf-8", errors="ignore")
                return cls._read_ascii(content, header, points_count)

    @classmethod
    def _parse_header(cls, f) -> Tuple[Dict[str, any], str, int]:
        header: Dict[str, any] = {}
        data_type = "ascii"
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
                data_type = parts[1].lower()
                break

        return header, data_type, offset

    @classmethod
    def _read_ascii(cls, content: str, header: Dict[str, any], points_count: int) -> np.ndarray:
        fields = header.get("FIELDS", ["x", "y", "z"])
        x_idx = fields.index("x") if "x" in fields else 0
        y_idx = fields.index("y") if "y" in fields else 1
        z_idx = fields.index("z") if "z" in fields else 2

        coords: List[List[float]] = []
        for line in content.splitlines():
            parts = line.strip().split()
            if len(parts) >= 3:
                try:
                    coords.append([float(parts[x_idx]), float(parts[y_idx]), float(parts[z_idx])])
                except (ValueError, IndexError):
                    continue
                if points_count > 0 and len(coords) >= points_count:
                    break

        if not coords:
            return cls.generate_default_point_cloud()
        return np.array(coords, dtype=np.float32)

    @classmethod
    def _read_binary(cls, f, header: Dict[str, any], points_count: int) -> np.ndarray:
        fields = header.get("FIELDS", ["x", "y", "z"])
        sizes = header.get("SIZE", [4] * len(fields))
        types = header.get("TYPE", ["F"] * len(fields))

        type_map = {"F": "f", "I": "i", "U": "u"}
        dtype_list = []
        for name, sz, tp in zip(fields, sizes, types):
            code = f"<{type_map.get(tp, 'f')}{sz}"
            dtype_list.append((name, code))

        point_dtype = np.dtype(dtype_list)
        raw_bytes = f.read()
        arr = np.frombuffer(raw_bytes, dtype=point_dtype, count=points_count)

        if "x" in arr.dtype.names and "y" in arr.dtype.names and "z" in arr.dtype.names:
            pts = np.column_stack((arr["x"], arr["y"], arr["z"])).astype(np.float32)
            return pts
        return cls.generate_default_point_cloud()

    @classmethod
    def save_ascii(cls, file_path: str, points: np.ndarray) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        n = len(points)
        lines = [
            "# .PCD v.7 - Point Cloud Data",
            "VERSION .7",
            "FIELDS x y z",
            "SIZE 4 4 4",
            "TYPE F F F",
            "COUNT 1 1 1",
            f"WIDTH {n}",
            "HEIGHT 1",
            "VIEWPOINT 0 0 0 1 0 0 0",
            f"POINTS {n}",
            "DATA ascii"
        ]
        for pt in points:
            lines.append(f"{pt[0]:.4f} {pt[1]:.4f} {pt[2]:.4f}")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    @classmethod
    def generate_default_point_cloud(cls, num_points: int = 15000) -> np.ndarray:
        """
        生成开箱即用的矩形房间点云环境
        范围 x in [-14, 0], y in [-5, 3], z in [0, 2.8]
        """
        pts = []
        wall_pts = int(num_points * 0.65)
        per_wall = wall_pts // 4

        # West wall (x = -14)
        y_w = np.random.uniform(-5.0, 3.0, per_wall)
        z_w = np.random.uniform(0.0, 2.8, per_wall)
        x_w = np.full(per_wall, -14.0) + np.random.normal(0, 0.02, per_wall)
        pts.append(np.column_stack((x_w, y_w, z_w)))

        # East wall (x = 0)
        y_e = np.random.uniform(-5.0, 3.0, per_wall)
        z_e = np.random.uniform(0.0, 2.8, per_wall)
        x_e = np.full(per_wall, 0.0) + np.random.normal(0, 0.02, per_wall)
        pts.append(np.column_stack((x_e, y_e, z_e)))

        # South wall (y = -5)
        x_s = np.random.uniform(-14.0, 0.0, per_wall)
        z_s = np.random.uniform(0.0, 2.8, per_wall)
        y_s = np.full(per_wall, -5.0) + np.random.normal(0, 0.02, per_wall)
        pts.append(np.column_stack((x_s, y_s, z_s)))

        # North wall (y = 3)
        x_n = np.random.uniform(-14.0, 0.0, per_wall)
        z_n = np.random.uniform(0.0, 2.8, per_wall)
        y_n = np.full(per_wall, 3.0) + np.random.normal(0, 0.02, per_wall)
        pts.append(np.column_stack((x_n, y_n, z_n)))

        # Pillars & obstacles (15% points)
        pillar_pts = int(num_points * 0.20) // 2
        for cx, cy, rad in [(-10.0, -1.0, 0.45), (-4.5, 0.5, 0.5)]:
            angles = np.random.uniform(0, 2 * np.pi, pillar_pts)
            px = cx + rad * np.cos(angles) + np.random.normal(0, 0.015, pillar_pts)
            py = cy + rad * np.sin(angles) + np.random.normal(0, 0.015, pillar_pts)
            pz = np.random.uniform(0.0, 2.5, pillar_pts)
            pts.append(np.column_stack((px, py, pz)))

        # Low obstacle / divider wall (remaining points)
        div_pts = num_points - sum(len(p) for p in pts)
        if div_pts > 0:
            dx = np.random.uniform(-9.0, -6.5, div_pts)
            dy = np.full(div_pts, 0.5) + np.random.normal(0, 0.03, div_pts)
            dz = np.random.uniform(0.0, 1.2, div_pts)
            pts.append(np.column_stack((dx, dy, dz)))

        all_pts = np.vstack(pts).astype(np.float32)
        return all_pts
