"""
@file: src/domain/map/pcd_grid_models.py
@brief: PCD 点云 2D 栅格化配置与结果模型数据类
@exports: GridMapConfig, OriginInfo, PcdBounds, GridPngResult, PcdPointsResult
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import numpy as np


@dataclass
class GridMapConfig:
    """点云 2D 栅格投射与形态学膨胀参数配置"""
    resolution: float = 20.0          # 栅格分辨率 (像素/米，20 对应 0.05m/格)
    stdLimit: float = 0.1            # 障碍物判断高度标准差阈值 (米)
    obstacleLimit: float = 1.0       # 障碍物判断起伏高度差阈值 (米)
    dilationRadius: float = 0.5      # 形态学膨胀半径 (米)
    minHeight: float = -1.0          # 过滤最小高度 (米)
    maxHeight: float = 2.0           # 过滤最大高度 (米)
    renderMode: int = 0              # 渲染模式 (0: 障碍物灰度, 1: 高度灰度, 2: 原始RGB)
    cropCenterX: float = 0.0         # 框选裁剪中心 X
    cropCenterY: float = 0.0         # 框选裁剪中心 Y
    cropWidth: float = 0.0           # 框选裁剪宽度 (0 代表不裁剪)
    cropHeight: float = 0.0          # 框选裁剪高度 (0 代表不裁剪)
    originCenterX: float = 0.0       # 原点调整平移 X
    originCenterY: float = 0.0       # 原点调整平移 Y
    originRotation: float = 0.0      # 原点调整旋转角 (度)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GridMapConfig":
        return cls(
            resolution=float(data.get("resolution", 20.0)),
            stdLimit=float(data.get("stdLimit", 0.1)),
            obstacleLimit=float(data.get("obstacleLimit", 1.0)),
            dilationRadius=float(data.get("dilationRadius", 0.5)),
            minHeight=float(data.get("minHeight", -1.0)),
            maxHeight=float(data.get("maxHeight", 2.0)),
            renderMode=int(data.get("renderMode", 0)),
            cropCenterX=float(data.get("cropCenterX", 0.0)),
            cropCenterY=float(data.get("cropCenterY", 0.0)),
            cropWidth=float(data.get("cropWidth", 0.0)),
            cropHeight=float(data.get("cropHeight", 0.0)),
            originCenterX=float(data.get("originCenterX", 0.0)),
            originCenterY=float(data.get("originCenterY", 0.0)),
            originRotation=float(data.get("originRotation", 0.0)),
        )


@dataclass
class OriginInfo:
    """栅格图像与世界坐标/Three.js 视口坐标映射原点信息"""
    resolution: float
    originPosX: float
    originPosY: float
    originPosInThreeX: float
    originPosInThreeY: float
    width: int
    height: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resolution": self.resolution,
            "originPosX": self.originPosX,
            "originPosY": self.originPosY,
            "originPosInThreeX": self.originPosInThreeX,
            "originPosInThreeY": self.originPosInThreeY,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class PcdBounds:
    """点云三维包围盒边界"""
    minX: float
    maxX: float
    minY: float
    maxY: float
    minZ: float
    maxZ: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "minX": self.minX, "maxX": self.maxX,
            "minY": self.minY, "maxY": self.maxY,
            "minZ": self.minZ, "maxZ": self.maxZ,
        }


@dataclass
class GridPngResult:
    """栅格化生成的 PNG 图像字节流与坐标原点元信息"""
    pngBytes: bytes
    originInfo: OriginInfo
    previewPoints: bytes
    bounds: PcdBounds
    width: int
    height: int

    @property
    def pngBuffer(self) -> bytes:
        return self.pngBytes


@dataclass
class PcdPointsResult:
    """点云解析与降采样结果 (stride-3 float32 字节流)"""
    points: bytes
    bounds: PcdBounds
    totalPoints: int

    @property
    def count(self) -> int:
        return self.totalPoints

    def to_numpy(self) -> np.ndarray:
        if not self.points:
            return np.empty((0, 3), dtype=np.float32)
        return np.frombuffer(self.points, dtype=np.float32).reshape((-1, 3))

