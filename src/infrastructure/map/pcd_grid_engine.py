"""
@file: src/infrastructure/map/pcd_grid_engine.py
@brief: PCD 点云 2D 占据栅格投射、形态学膨胀与零外部图像依赖纯标准库 PNG 生成引擎
@exports: PcdGridEngine, pcd_file_to_points, pcd_file_to_grid_png
"""
import math
import struct
from typing import Optional, Tuple
import zlib
import numpy as np
from scipy import ndimage
from src.domain.map.pcd_grid_models import (
    GridMapConfig, GridPngResult, OriginInfo, PcdBounds, PcdPointsResult
)
from src.infrastructure.map.pcd_io_engine import PcdMapLoader


def encode_png_buffer(raw_bytes: bytes, width: int, height: int, is_rgb: bool = False) -> bytes:
    """使用内置 zlib 与 struct 打包标准 PNG 字节流，零外部图像库依赖"""
    channels = 3 if is_rgb else 1
    color_type = 2 if is_rgb else 0
    stride = width * channels
    scanlines = bytearray()
    for y in range(height):
        scanlines.append(0)  # filter type 0: None
        scanlines.extend(raw_bytes[y * stride : (y + 1) * stride])
    compressed = zlib.compress(bytes(scanlines), level=6)

    def _chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0))
    idat = _chunk(b"IDAT", compressed)
    iend = _chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


class PcdGridEngine:
    """点云 2D 栅格投射、形态学圆盘膨胀与三模 PNG 生成引擎"""

    @classmethod
    def pcd_file_to_points(cls, pcd_path: str, max_points: Optional[int] = None) -> PcdPointsResult:
        pts = PcdMapLoader.load_pcd(pcd_path)
        if len(pts) == 0:
            pts = PcdMapLoader.load_or_create_default()

        bounds = PcdBounds(
            minX=float(pts[:, 0].min()), maxX=float(pts[:, 0].max()),
            minY=float(pts[:, 1].min()), maxY=float(pts[:, 1].max()),
            minZ=float(pts[:, 2].min()), maxZ=float(pts[:, 2].max())
        )

        if max_points is not None and len(pts) > max_points:
            stride = max(1, int(math.ceil(len(pts) / max_points)))
            pts = pts[::stride][:max_points]

        pts_f32 = pts.astype(np.float32)
        return PcdPointsResult(points=pts_f32.tobytes(), bounds=bounds, totalPoints=len(pts_f32))

    @classmethod
    def _apply_transforms(cls, points: np.ndarray, cfg: GridMapConfig) -> np.ndarray:
        pts = points.copy()
        if cfg.originRotation != 0.0:
            rad = math.radians(cfg.originRotation)
            c, s = math.cos(rad), math.sin(rad)
            nx = pts[:, 0] * c - pts[:, 1] * s
            ny = pts[:, 0] * s + pts[:, 1] * c
            pts[:, 0], pts[:, 1] = nx, ny

        if cfg.originCenterX != 0.0 or cfg.originCenterY != 0.0:
            pts[:, 0] += cfg.originCenterX
            pts[:, 1] += cfg.originCenterY

        if cfg.cropWidth > 0.0 and cfg.cropHeight > 0.0:
            hw, hh = cfg.cropWidth / 2.0, cfg.cropHeight / 2.0
            mask_crop = (
                (pts[:, 0] >= cfg.cropCenterX - hw) & (pts[:, 0] <= cfg.cropCenterX + hw) &
                (pts[:, 1] >= cfg.cropCenterY - hh) & (pts[:, 1] <= cfg.cropCenterY + hh)
            )
            pts = pts[mask_crop]

        mask_h = (pts[:, 2] >= cfg.minHeight) & (pts[:, 2] <= cfg.maxHeight)
        return pts[mask_h].astype(np.float32)

    @classmethod
    def _render_image(cls, occ_grid: np.ndarray, h_grid: np.ndarray, cfg: GridMapConfig) -> bytes:
        h, w = occ_grid.shape
        if cfg.renderMode == 0:  # 0: 障碍物灰度 (平坦区 254 白, 障碍物 0 黑)
            img_arr = np.where(occ_grid > 0, 0, 254).astype(np.uint8)
            return encode_png_buffer(img_arr.tobytes(), w, h, is_rgb=False)
        if cfg.renderMode == 1:  # 1: 高度归一化灰度
            h_norm = np.clip(h_grid * 255.0, 0, 255).astype(np.uint8)
            return encode_png_buffer(h_norm.tobytes(), w, h, is_rgb=False)
        # 2: 蓝青白高程 RGB
        norm = np.clip(h_grid, 0.0, 1.0)
        r = np.clip(255.0 * norm, 0, 255).astype(np.uint8)
        g = np.clip(255.0 * (1.0 - np.abs(norm - 0.5) * 2.0), 0, 255).astype(np.uint8)
        b = np.clip(255.0 * (1.0 - norm), 0, 255).astype(np.uint8)
        rgb = np.stack([r, g, b], axis=-1)
        return encode_png_buffer(rgb.tobytes(), w, h, is_rgb=True)

    @classmethod
    def pcd_file_to_grid_png(cls, pcd_path: str, config: Optional[GridMapConfig] = None) -> GridPngResult:
        cfg = config or GridMapConfig()
        raw_pts = PcdMapLoader.load_pcd(pcd_path)
        if len(raw_pts) == 0:
            raw_pts = PcdMapLoader.load_or_create_default()

        pts = cls._apply_transforms(raw_pts, cfg)
        if len(pts) == 0:
            pts = np.array([[0.0, 0.0, 0.0]], dtype=np.float32)

        min_x, max_x = float(pts[:, 0].min()), float(pts[:, 0].max())
        min_y, max_y = float(pts[:, 1].min()), float(pts[:, 1].max())
        min_z, max_z = float(pts[:, 2].min()), float(pts[:, 2].max())
        span_z = max(max_z - min_z, 1e-4)

        res = cfg.resolution
        w = max(1, int(math.ceil((max_x - min_x) * res)))
        h = max(1, int(math.ceil((max_y - min_y) * res)))

        grid_max = np.full((h, w), -9999.0, dtype=np.float32)
        grid_min = np.full((h, w), 9999.0, dtype=np.float32)
        h_grid = np.zeros((h, w), dtype=np.float32)

        cols = np.clip(((pts[:, 0] - min_x) * res).astype(int), 0, w - 1)
        rows = np.clip(((pts[:, 1] - min_y) * res).astype(int), 0, h - 1)
        z_vals = pts[:, 2]

        np.maximum.at(grid_max, (rows, cols), z_vals)
        np.minimum.at(grid_min, (rows, cols), z_vals)
        np.maximum.at(h_grid, (rows, cols), (z_vals - min_z) / span_z)

        diff = np.where((grid_max > -9000.0) & (grid_min < 9000.0), grid_max - grid_min, 0.0)
        occ = (diff > cfg.obstacleLimit).astype(np.uint8)

        if cfg.dilationRadius > 0.0:
            k = max(1, int(round(cfg.dilationRadius * res)))
            y, x = np.ogrid[-k : k + 1, -k : k + 1]
            disk = (x * x + y * y) <= (k * k)
            occ = ndimage.binary_dilation(occ > 0, structure=disk).astype(np.uint8)

        png_bytes = cls._render_image(occ, h_grid, cfg)

        origin_info = OriginInfo(
            resolution=res, originPosX=min_x, originPosY=min_y,
            originPosInThreeX=(min_x + max_x) / 2.0, originPosInThreeY=(min_y + max_y) / 2.0,
            width=w, height=h
        )
        bounds = PcdBounds(minX=min_x, maxX=max_x, minY=min_y, maxY=max_y, minZ=min_z, maxZ=max_z)
        stride = max(1, len(pts) // 3000)
        preview_bytes = pts[::stride].astype(np.float32).tobytes()

        return GridPngResult(
            pngBytes=png_bytes, originInfo=origin_info, previewPoints=preview_bytes,
            bounds=bounds, width=w, height=h
        )


pcd_file_to_points = PcdGridEngine.pcd_file_to_points
pcd_file_to_grid_png = PcdGridEngine.pcd_file_to_grid_png
