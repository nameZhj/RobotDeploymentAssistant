"""
@file: src/core/pcd_loader.py
@brief: 纯 Python 高性能 PCD 点云解析引擎，支持 ASCII 与 Binary 格式解析与流式抽稀
@exports: PcdHeader, PcdData, PcdLoader
"""
from dataclasses import dataclass, field
import os
import re
import struct
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


@dataclass
class PcdHeader:
    version: str = "0.7"
    fields: List[str] = field(default_factory=lambda: ["x", "y", "z"])
    sizes: List[int] = field(default_factory=lambda: [4, 4, 4])
    types: List[str] = field(default_factory=lambda: ["F", "F", "F"])
    counts: List[int] = field(default_factory=lambda: [1, 1, 1])
    width: int = 0
    height: int = 1
    points: int = 0
    data_mode: str = "ascii"
    header_bytes_len: int = 0


@dataclass
class PcdData:
    points: np.ndarray  # shape: (N, 3), columns: x, y, z
    point_count: int
    bounds: Dict[str, float]
    header: PcdHeader

    def get_span(self) -> Dict[str, float]:
        return {
            "dx": round(self.bounds["max_x"] - self.bounds["min_x"], 3),
            "dy": round(self.bounds["max_y"] - self.bounds["min_y"], 3),
            "dz": round(self.bounds["max_z"] - self.bounds["min_z"], 3),
        }


class PcdLoader:
    """高性能纯 Python PCD 解析引擎，严格避免第三方 C++ 依赖"""

    @classmethod
    def load_pcd(cls, file_path: str) -> PcdData:
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"PCD 文件不存在: {file_path}")

        with open(file_path, "rb") as fp:
            header = cls._parse_header(fp)
            if header.data_mode == "ascii":
                fp.seek(header.header_bytes_len)
                raw_text = fp.read().decode("utf-8", errors="ignore")
                points = cls._parse_ascii_data(raw_text, header)
            elif header.data_mode == "binary":
                fp.seek(header.header_bytes_len)
                raw_bytes = fp.read()
                points = cls._parse_binary_data(raw_bytes, header)
            elif header.data_mode == "binary_compressed":
                points = cls._parse_compressed_binary(fp, header)
            else:
                raise ValueError(f"未知或不支持的 PCD 数据格式: {header.data_mode}")

        bounds = cls._calculate_bounds(points)
        return PcdData(points=points, point_count=len(points), bounds=bounds, header=header)

    @classmethod
    def downsample(cls, points: np.ndarray, max_points: int = 30000) -> np.ndarray:
        """等间距均匀抽稀点云，保护原始点云数据不被就地修改"""
        if points is None or len(points) <= max_points:
            return points
        step = max(1, len(points) // max_points)
        return points[::step][:max_points].copy()

    @classmethod
    def _parse_header(cls, fp) -> PcdHeader:
        hdr = PcdHeader()
        header_lines: List[str] = []
        bytes_read = 0

        while True:
            line_bytes = fp.readline()
            if not line_bytes:
                break
            bytes_read += len(line_bytes)
            line = line_bytes.decode("utf-8", errors="ignore").strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()
            key = parts[0].upper()
            val_parts = parts[1:]

            if key == "VERSION" and val_parts:
                hdr.version = val_parts[0]
            elif key == "FIELDS":
                hdr.fields = val_parts
            elif key == "SIZE":
                hdr.sizes = [int(v) for v in val_parts]
            elif key == "TYPE":
                hdr.types = val_parts
            elif key == "COUNT":
                hdr.counts = [int(v) for v in val_parts]
            elif key == "WIDTH" and val_parts:
                hdr.width = int(val_parts[0])
            elif key == "HEIGHT" and val_parts:
                hdr.height = int(val_parts[0])
            elif key == "POINTS" and val_parts:
                hdr.points = int(val_parts[0])
            elif key == "DATA" and val_parts:
                hdr.data_mode = val_parts[0].lower()
                break

        hdr.header_bytes_len = bytes_read
        return hdr

    @classmethod
    def _parse_ascii_data(cls, text: str, header: PcdHeader) -> np.ndarray:
        lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
        if not lines:
            return np.zeros((0, 3), dtype=np.float32)

        idx_x, idx_y, idx_z = cls._get_field_indices(header.fields)
        pts: List[Tuple[float, float, float]] = []

        for line in lines:
            parts = line.split()
            if len(parts) <= max(idx_x, idx_y, idx_z):
                continue
            try:
                x = float(parts[idx_x])
                y = float(parts[idx_y])
                z = float(parts[idx_z])
                pts.append((x, y, z))
            except ValueError:
                continue

        return np.array(pts, dtype=np.float32) if pts else np.zeros((0, 3), dtype=np.float32)

    @classmethod
    def _parse_binary_data(cls, raw_bytes: bytes, header: PcdHeader) -> np.ndarray:
        record_len = sum(s * c for s, c in zip(header.sizes, header.counts))
        if record_len <= 0 or not raw_bytes:
            return np.zeros((0, 3), dtype=np.float32)

        offsets, type_codes = cls._calc_field_offsets(header)
        idx_x, idx_y, idx_z = cls._get_field_indices(header.fields)
        off_x, off_y, off_z = offsets[idx_x], offsets[idx_y], offsets[idx_z]
        tc_x, tc_y, tc_z = type_codes[idx_x], type_codes[idx_y], type_codes[idx_z]

        total_pts = len(raw_bytes) // record_len
        pts = np.empty((total_pts, 3), dtype=np.float32)

        for i in range(total_pts):
            base = i * record_len
            x = struct.unpack_from(tc_x, raw_bytes, base + off_x)[0]
            y = struct.unpack_from(tc_y, raw_bytes, base + off_y)[0]
            z = struct.unpack_from(tc_z, raw_bytes, base + off_z)[0]
            pts[i] = (x, y, z)

        return pts

    @classmethod
    def _parse_compressed_binary(cls, fp, header: PcdHeader) -> np.ndarray:
        try:
            import lzf  # type: ignore
        except ImportError:
            raise ValueError("不支持 binary_compressed 格式：系统未安装 lzf 解压库，请使用标准 ASCII 或 Binary 格式 PCD 点云文件")

        # 压缩尺寸读取
        comp_sizes = fp.read(8)
        if len(comp_sizes) < 8:
            return np.zeros((0, 3), dtype=np.float32)
        compressed_len, uncompressed_len = struct.unpack("II", comp_sizes)
        comp_data = fp.read(compressed_len)
        decomp = lzf.decompress(comp_data, uncompressed_len)
        return cls._parse_binary_data(decomp, header)

    @staticmethod
    def _get_field_indices(fields: List[str]) -> Tuple[int, int, int]:
        f_lower = [f.lower() for f in fields]
        idx_x = f_lower.index("x") if "x" in f_lower else 0
        idx_y = f_lower.index("y") if "y" in f_lower else 1
        idx_z = f_lower.index("z") if "z" in f_lower else 2
        return idx_x, idx_y, idx_z

    @staticmethod
    def _calc_field_offsets(header: PcdHeader) -> Tuple[List[int], List[str]]:
        offsets: List[int] = []
        type_codes: List[str] = []
        curr = 0
        type_map = {
            ("F", 4): "f", ("F", 8): "d",
            ("I", 1): "b", ("I", 2): "h", ("I", 4): "i",
            ("U", 1): "B", ("U", 2): "H", ("U", 4): "I",
        }
        for t, s, c in zip(header.types, header.sizes, header.counts):
            offsets.append(curr)
            type_codes.append(type_map.get((t.upper(), s), "f"))
            curr += s * c
        return offsets, type_codes

    @staticmethod
    def _calculate_bounds(points: np.ndarray) -> Dict[str, float]:
        if points is None or len(points) == 0:
            return {"min_x": 0.0, "max_x": 0.0, "min_y": 0.0, "max_y": 0.0, "min_z": 0.0, "max_z": 0.0}
        return {
            "min_x": round(float(np.min(points[:, 0])), 3),
            "max_x": round(float(np.max(points[:, 0])), 3),
            "min_y": round(float(np.min(points[:, 1])), 3),
            "max_y": round(float(np.max(points[:, 1])), 3),
            "min_z": round(float(np.min(points[:, 2])), 3),
            "max_z": round(float(np.max(points[:, 2])), 3),
        }
