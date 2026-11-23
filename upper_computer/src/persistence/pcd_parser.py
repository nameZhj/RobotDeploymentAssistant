# @file: src/persistence/pcd_parser.py
# @brief: Memory-safe streaming PCD parser supporting ASCII, binary, and binary_compressed LZF point clouds.
# @exports: PcdHeader, PcdPointCloud, parse_pcd_header, load_pcd, write_ascii_pcd

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import Dict, List, Optional, Tuple
import numpy as np


_PCD_DTYPE_MAP = {
    ("F", 4): "<f4",
    ("F", 8): "<f8",
    ("U", 1): "|u1",
    ("U", 2): "<u2",
    ("U", 4): "<u4",
    ("I", 1): "|i1",
    ("I", 2): "<i2",
    ("I", 4): "<i4",
}


@dataclass(frozen=True)
class PcdHeader:
    """Parsed metadata header from a PCL .pcd file."""

    fields: Tuple[str, ...]
    sizes: Tuple[int, ...]
    types: Tuple[str, ...]
    counts: Tuple[int, ...]
    width: int
    height: int
    points: int
    data_format: str
    data_offset: int
    point_step: int


@dataclass
class PcdPointCloud:
    """Downsampled point cloud payload with computed XYZ bounds."""

    header: PcdHeader
    points_xyz: np.ndarray      # (N, 3) float32
    colors_rgb: Optional[np.ndarray]  # (N, 3) float32 or None
    bounds_min: Tuple[float, float, float]
    bounds_max: Tuple[float, float, float]


def _lzf_decompress(src: bytes, expected_len: int) -> bytes:
    """Pure-Python LZF block decompressor for PCL binary_compressed clouds."""
    out = bytearray()
    i, n = 0, len(src)
    while i < n and len(out) < expected_len:
        ctrl = src[i]
        i += 1
        if ctrl < 32:
            lit_len = ctrl + 1
            out.extend(src[i : i + lit_len])
            i += lit_len
        else:
            ref_len = ctrl >> 5
            ref = len(out) - ((ctrl & 0x1F) << 8) - 1
            if ref_len == 7:
                ref_len += src[i]
                i += 1
            ref -= src[i]
            i += 1
            ref_len += 2
            for k in range(ref_len):
                out.append(out[ref + k])
    return bytes(out[:expected_len])


def parse_pcd_header(path: Path) -> PcdHeader:
    """Read only header lines from .pcd without loading massive binary payloads."""
    meta: Dict[str, List[str]] = {}
    data_offset = 0
    with open(path, "rb") as fh:
        while True:
            raw_line = fh.readline()
            if not raw_line:
                break
            line = raw_line.decode("ascii", errors="ignore").strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            key = parts[0].upper()
            meta[key] = parts[1:]
            if key == "DATA":
                data_offset = fh.tell()
                break

    fields = tuple(meta.get("FIELDS", ["x", "y", "z"]))
    sizes = tuple(int(v) for v in meta.get("SIZE", ["4"] * len(fields)))
    types = tuple(meta.get("TYPE", ["F"] * len(fields)))
    counts = tuple(int(v) for v in meta.get("COUNT", ["1"] * len(fields)))
    width = int(meta.get("WIDTH", ["0"])[0])
    height = int(meta.get("HEIGHT", ["1"])[0])
    points = int(meta.get("POINTS", [str(width * height)])[0])
    data_fmt = meta.get("DATA", ["ascii"])[0].lower()
    step = sum(s * c for s, c in zip(sizes, counts))
    return PcdHeader(fields, sizes, types, counts, width, height, points, data_fmt, data_offset, step)


def _build_structured_dtype(header: PcdHeader) -> Tuple[np.dtype, Tuple[str, str, str]]:
    dtype_fields = []
    for name, sz, tp, cnt in zip(header.fields, header.sizes, header.types, header.counts):
        dt = _PCD_DTYPE_MAP.get((tp.upper(), sz), "<f4")
        if cnt > 1:
            dtype_fields.append((name, dt, (cnt,)))
        else:
            dtype_fields.append((name, dt))
    xyz_keys = ("x", "y", "z")
    return np.dtype(dtype_fields), xyz_keys


def load_pcd(path: Path, max_points: int = 180000) -> PcdPointCloud:
    """Load and uniformly downsample .pcd point cloud without memory spikes."""
    hdr = parse_pcd_header(path)
    n_pts = max(0, hdr.points)
    if n_pts == 0:
        empty = np.zeros((0, 3), dtype=np.float32)
        return PcdPointCloud(hdr, empty, None, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    stride = max(1, (n_pts + max_points - 1) // max_points) if max_points > 0 else 1
    xyz = np.zeros((0, 3), dtype=np.float32)

    if hdr.data_format == "ascii":
        ix = hdr.fields.index("x") if "x" in hdr.fields else 0
        iy = hdr.fields.index("y") if "y" in hdr.fields else 1
        iz = hdr.fields.index("z") if "z" in hdr.fields else 2
        rows = []
        with open(path, "rb") as fh:
            fh.seek(hdr.data_offset)
            for idx, raw in enumerate(fh):
                if idx % stride != 0:
                    continue
                vals = raw.decode("ascii", errors="ignore").split()
                if len(vals) > max(ix, iy, iz):
                    rows.append((float(vals[ix]), float(vals[iy]), float(vals[iz])))
        if rows:
            xyz = np.asarray(rows, dtype=np.float32)

    elif hdr.data_format == "binary":
        struct_dt, (kx, ky, kz) = _build_structured_dtype(hdr)
        mm = np.memmap(str(path), dtype=struct_dt, mode="r", offset=hdr.data_offset, shape=(n_pts,))
        sampled = mm[::stride]
        xyz = np.column_stack([sampled[kx], sampled[ky], sampled[kz]]).astype(np.float32)
        del mm

    elif hdr.data_format == "binary_compressed":
        with open(path, "rb") as fh:
            fh.seek(hdr.data_offset)
            comp_sz, uncomp_sz = struct.unpack("<II", fh.read(8))
            raw_comp = fh.read(comp_sz)
        uncomp = _lzf_decompress(raw_comp, uncomp_sz)
        # PCL stores column-major per field
        pts_list = []
        offset = 0
        for name, sz, tp, cnt in zip(hdr.fields, hdr.sizes, hdr.types, hdr.counts):
            dt = np.dtype(_PCD_DTYPE_MAP.get((tp.upper(), sz), "<f4"))
            span = n_pts * sz * cnt
            if name in ("x", "y", "z"):
                arr = np.frombuffer(uncomp, dtype=dt, count=n_pts, offset=offset)[::stride]
                pts_list.append(arr.astype(np.float32))
            offset += span
        if len(pts_list) == 3:
            xyz = np.column_stack(pts_list)

    valid = np.isfinite(xyz).all(axis=1)
    xyz = xyz[valid]
    if len(xyz) == 0:
        return PcdPointCloud(hdr, xyz, None, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    bmin = tuple(float(v) for v in xyz.min(axis=0))
    bmax = tuple(float(v) for v in xyz.max(axis=0))
    # Height-mapped cyan-teal color ramp matching UniUni dark aesthetics
    z_norm = np.clip((xyz[:, 2] - bmin[2]) / max(0.25, bmax[2] - bmin[2]), 0.0, 1.0)
    colors = np.column_stack([0.16 + 0.35 * z_norm, 0.58 + 0.30 * z_norm, 0.65 + 0.25 * (1.0 - z_norm)]).astype(np.float32)
    return PcdPointCloud(hdr, np.ascontiguousarray(xyz), colors, bmin, bmax)


def write_ascii_pcd(path: Path, points_xyz: np.ndarray, intensities: Optional[np.ndarray] = None) -> Path:
    """Save XYZ (or XYZI) numpy array as canonical ASCII .pcd file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pts = np.asarray(points_xyz, dtype=np.float32)
    n = len(pts)
    has_i = intensities is not None and len(intensities) == n
    header = (
        "# .PCD v0.7 - Point Cloud Data file format\n"
        "VERSION 0.7\n"
        f"FIELDS x y z{' intensity' if has_i else ''}\n"
        f"SIZE 4 4 4{' 4' if has_i else ''}\n"
        f"TYPE F F F{' F' if has_i else ''}\n"
        f"COUNT 1 1 1{' 1' if has_i else ''}\n"
        f"WIDTH {n}\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\n"
        f"POINTS {n}\nDATA ascii\n"
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(header)
        if has_i:
            for (x, y, z), val in zip(pts, intensities):
                fh.write(f"{x:.4f} {y:.4f} {z:.4f} {float(val):.2f}\n")
        else:
            for x, y, z in pts:
                fh.write(f"{x:.4f} {y:.4f} {z:.4f}\n")
    return path
