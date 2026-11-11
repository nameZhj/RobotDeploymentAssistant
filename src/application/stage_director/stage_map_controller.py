"""
@file: src/application/stage_director/stage_map_controller.py
@brief: 本地 PCD 地图控制器：导入验证、持久化协调、2D 栅格投射与使用保护
@exports: StageMapController
"""
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from PySide6.QtGui import QImage
from src.domain.map.grid_and_calibration import MapGridProcessor
from src.domain.map.stage_map_asset import (
    InvalidPcdFileError,
    StageMapAsset,
    UnsupportedPcdFormatError,
    validate_pcd_file,
)
from src.infrastructure.map.pcd_io_engine import PcdMapLoader
from src.infrastructure.storage.stage_map_sqlite_adapter import (
    StageMapSqliteAdapter,
    atomic_copy_pcd,
)

logger = logging.getLogger("StageMapController")


class StageMapController:
    """提供本地 PCD 地图导入校验、文件隔离复制、SQLite 元信息同步与 2D 视口加载"""

    def __init__(self, db_path: Optional[str] = None, map_dir: str = "runtime/stage_maps") -> None:
        self.map_dir = map_dir
        self.adapter = StageMapSqliteAdapter(db_path)
        self._active_map_id: Optional[str] = None

    def import_pcd_file(self, src_path: str, custom_name: Optional[str] = None) -> StageMapAsset:
        """导入本地 PCD 文件：格式校验 -> 原子复制 -> 点云解析 -> 2D 栅格化 -> 持久化"""
        validate_pcd_file(src_path)
        dest_path = atomic_copy_pcd(src_path, dest_dir=self.map_dir)
        points = PcdMapLoader.load_pcd(dest_path)
        if len(points) == 0:
            if os.path.exists(dest_path) and dest_path != src_path:
                try:
                    os.remove(dest_path)
                except OSError:
                    pass
            raise InvalidPcdFileError("PCD 点云数据解析失败或点数为 0")

        _, _, info = MapGridProcessor.generate_2d_occupancy_grid(points)
        min_x = float(points[:, 0].min())
        max_x = float(points[:, 0].max())
        min_y = float(points[:, 1].min())
        max_y = float(points[:, 1].max())
        min_z = float(points[:, 2].min())
        max_z = float(points[:, 2].max())

        map_id = f"map_{int(time.time() * 1000)}"
        stem = os.path.splitext(os.path.basename(dest_path))[0]
        name = custom_name.strip() if custom_name and custom_name.strip() else stem
        file_size = os.path.getsize(dest_path)

        asset = StageMapAsset(
            map_id=map_id,
            name=name,
            file_path=dest_path,
            file_size_bytes=file_size,
            point_count=len(points),
            min_x=min_x,
            max_x=max_x,
            min_y=min_y,
            max_y=max_y,
            min_z=min_z,
            max_z=max_z,
            origin_x=float(info.get("origin_x", 0.0)),
            origin_y=float(info.get("origin_y", 0.0)),
            resolution=float(info.get("resolution", 0.05)),
            width=int(info.get("width", 0)),
            height=int(info.get("height", 0)),
            created_at=time.time(),
            updated_at=time.time(),
        )
        self.adapter.save_map(asset)
        return asset

    def list_maps(self) -> List[StageMapAsset]:
        return self.adapter.list_maps()

    def get_map(self, map_id: str) -> Optional[StageMapAsset]:
        return self.adapter.get_map(map_id)

    def get_active_map_id(self) -> Optional[str]:
        return self._active_map_id

    def set_active_map_id(self, map_id: Optional[str]) -> None:
        self._active_map_id = map_id

    def get_active_map(self) -> Optional[StageMapAsset]:
        return self.get_map(self._active_map_id) if self._active_map_id else None

    def delete_map(self, map_id: str) -> Tuple[bool, str]:
        """安全删除地图：拦截舞台在用地图，确保文件与 DB 记录双向彻底清除"""
        if self._active_map_id and map_id == self._active_map_id:
            return False, "当前舞台正在加载该地图，无法直接删除。请先卸载或切换至其他地图。"
        if self.adapter.check_map_in_use(map_id, self._active_map_id):
            return False, "当前场景工程正在引用该地图，无法直接删除。"

        asset = self.get_map(map_id)
        if not asset:
            return False, f"未找到指定的地图记录: '{map_id}'"

        deleted = self.adapter.delete_map(map_id)
        if deleted and os.path.exists(asset.file_path):
            try:
                os.remove(asset.file_path)
            except OSError as e:
                logger.warning(f"删除地图磁盘文件失败: {asset.file_path}, err: {e}")
        return deleted, "地图已成功删除"

    def render_grid_image(self, points: np.ndarray) -> Tuple[QImage, Dict[str, Any]]:
        """从点云数组生成 2D 占据栅格半透明 QImage 与尺寸信息"""
        _, inflated, info = MapGridProcessor.generate_2d_occupancy_grid(points)
        flipped = np.flipud(inflated)
        h, w = flipped.shape
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        rgba[flipped > 0] = [56, 189, 248, 140]
        img = QImage(rgba.data, w, h, w * 4, QImage.Format_RGBA8888).copy()
        return img, info

    def load_map_to_stage(self, map_id: str) -> Tuple[Optional[QImage], Optional[Dict[str, Any]], Dict[str, Any]]:
        """从本地磁盘读取选定地图，生成 2D 视口占有栅格图像与元数据"""
        asset = self.get_map(map_id)
        if not asset:
            raise FileNotFoundError(f"未找到指定的地图资产: '{map_id}'")
        if not os.path.exists(asset.file_path):
            raise FileNotFoundError(f"地图物理文件不存在: '{asset.file_path}'")

        points = PcdMapLoader.load_pcd(asset.file_path)
        img, info = self.render_grid_image(points)
        self._active_map_id = map_id
        meta = {
            "name": asset.name,
            "map_file": os.path.basename(asset.file_path),
            "file_path": asset.file_path,
            "dimensions": asset.formatted_dimensions(),
            "resolution": asset.resolution,
            "origin": f"({info['origin_x']:.1f}, {info['origin_y']:.1f})",
            "status": "已加载 (Loaded)",
            "map_id": asset.map_id,
        }
        return img, info, meta

    def unload_map(self) -> None:
        self._active_map_id = None
