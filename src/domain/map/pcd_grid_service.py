"""
@file: src/domain/map/pcd_grid_service.py
@brief: 点云读取、体素降采样与 2D 占据栅格生成业务服务
@exports: PcdGridService, pcd_file_to_points, pcd_file_to_grid_png, generate_default_stage_pcd
"""
import os
from typing import Optional
import numpy as np
from src.domain.map.pcd_grid_models import (
    GridMapConfig, GridPngResult, OriginInfo, PcdBounds, PcdPointsResult
)
from src.infrastructure.map.pcd_grid_engine import (
    PcdGridEngine, pcd_file_to_grid_png, pcd_file_to_points
)
from src.infrastructure.map.pcd_io_engine import PcdMapLoader


class PcdGridService:
    """封装点云高低格式解析、2D 栅格投射与默认点云资产生成"""

    @staticmethod
    def load_points(pcd_path: str, max_points: int = 100000) -> PcdPointsResult:
        return pcd_file_to_points(pcd_path, max_points=max_points)

    @staticmethod
    def generate_grid_png(pcd_path: str, config: Optional[GridMapConfig] = None) -> GridPngResult:
        cfg = config or GridMapConfig()
        return pcd_file_to_grid_png(pcd_path, cfg)

    @staticmethod
    def generate_default_stage_pcd(file_path: Optional[str] = None) -> np.ndarray:
        target = file_path or os.path.join("runtime", "cache", "default_stage.pcd")
        return PcdMapLoader.load_or_create_default(target)


pcd_grid_service = PcdGridService()
generate_default_stage_pcd = PcdGridService.generate_default_stage_pcd

