"""
@file: src/domain/map/stage_map_asset.py
@brief: 本地 PCD 舞台地图素材资产领域模型、格式校验异常与解析校验器
@exports: StageMapAsset, UnsupportedPcdFormatError, InvalidPcdFileError, DuplicateMapError, validate_pcd_file
"""
from dataclasses import dataclass, field
import os
import time
from typing import Any, Dict, List, Optional, Tuple


class UnsupportedPcdFormatError(ValueError):
    """PCD 格式不受支持（例如 binary_compressed 格式）"""
    pass


class InvalidPcdFileError(ValueError):
    """PCD 文件无效、损坏、空文件或非 PCD 格式"""
    pass


class DuplicateMapError(ValueError):
    """PCD 地图文件哈希重复已存在"""
    def __init__(self, message: str, existing_map_id: str, existing_name: str) -> None:
        super().__init__(message)
        self.existing_map_id = existing_map_id
        self.existing_name = existing_name


@dataclass
class StageMapAsset:
    """本地 PCD 舞台地图资产，记录元信息、点云规模、2D 栅格尺寸与世界坐标原点"""
    map_id: str
    name: str
    file_path: str
    file_size_bytes: int
    point_count: int
    min_x: float
    max_x: float
    min_y: float
    max_y: float
    min_z: float
    max_z: float
    origin_x: float = 0.0
    origin_y: float = 0.0
    resolution: float = 0.05
    width: int = 0
    height: int = 0
    project_id: str = ""
    sha256: str = ""
    pcd_encoding: str = "ascii"
    pcd_fields: str = "x y z"
    import_status: str = "READY"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def formatted_file_size(self) -> str:
        """返回人性化文件大小字符串"""
        size = self.file_size_bytes
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024.0:.1f} KB"
        return f"{size / (1024.0 * 1024.0):.2f} MB"

    def formatted_dimensions(self) -> str:
        """返回米制场景物理覆盖范围字符串"""
        w_m = self.width * self.resolution
        h_m = self.height * self.resolution
        return f"{w_m:.1f}m × {h_m:.1f}m"

    def bounds_tuple(self) -> Tuple[float, float, float, float, float, float]:
        return (self.min_x, self.max_x, self.min_y, self.max_y, self.min_z, self.max_z)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "map_id": self.map_id,
            "name": self.name,
            "file_path": self.file_path,
            "file_size_bytes": self.file_size_bytes,
            "point_count": self.point_count,
            "min_x": self.min_x,
            "max_x": self.max_x,
            "min_y": self.min_y,
            "max_y": self.max_y,
            "min_z": self.min_z,
            "max_z": self.max_z,
            "origin_x": self.origin_x,
            "origin_y": self.origin_y,
            "resolution": self.resolution,
            "width": self.width,
            "height": self.height,
            "project_id": self.project_id,
            "sha256": self.sha256,
            "pcd_encoding": self.pcd_encoding,
            "pcd_fields": self.pcd_fields,
            "import_status": self.import_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StageMapAsset":
        return cls(
            map_id=str(data["map_id"]),
            name=str(data.get("name", "未命名地图")),
            file_path=str(data["file_path"]),
            file_size_bytes=int(data.get("file_size_bytes", 0)),
            point_count=int(data.get("point_count", 0)),
            min_x=float(data.get("min_x", 0.0)),
            max_x=float(data.get("max_x", 0.0)),
            min_y=float(data.get("min_y", 0.0)),
            max_y=float(data.get("max_y", 0.0)),
            min_z=float(data.get("min_z", 0.0)),
            max_z=float(data.get("max_z", 0.0)),
            origin_x=float(data.get("origin_x", 0.0)),
            origin_y=float(data.get("origin_y", 0.0)),
            resolution=float(data.get("resolution", 0.05)),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            project_id=str(data.get("project_id", "")),
            sha256=str(data.get("sha256", "")),
            pcd_encoding=str(data.get("pcd_encoding", "ascii")),
            pcd_fields=str(data.get("pcd_fields", "x y z")),
            import_status=str(data.get("import_status", "READY")),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
        )


def validate_pcd_file(file_path: str) -> Dict[str, Any]:
    """严格校验 PCD 文件的存在性、扩展名、非空性与格式规范"""
    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError(f"PCD 文件不存在: '{file_path}'")
    if not os.path.isfile(file_path):
        raise InvalidPcdFileError(f"指定的路径不是合法文件: '{file_path}'")
    if not file_path.lower().endswith(".pcd"):
        raise InvalidPcdFileError(f"文件扩展名不正确，必须为 .pcd 格式: '{file_path}'")
    file_size = os.path.getsize(file_path)
    if file_size == 0:
        raise InvalidPcdFileError(f"PCD 文件为空 (0 字节): '{file_path}'")

    header: Dict[str, Any] = {}
    data_mode = "ascii"
    with open(file_path, "rb") as f:
        while True:
            line_bytes = f.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="ignore").strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            key = parts[0].upper()
            if key in ("FIELDS", "TYPE"):
                header[key] = [p.lower() for p in parts[1:]]
            elif key in ("SIZE", "COUNT"):
                header[key] = [int(p) for p in parts[1:]]
            elif key in ("WIDTH", "HEIGHT", "POINTS"):
                header[key] = int(parts[1])
            elif key == "DATA":
                data_mode = parts[1].lower()
                break

    if data_mode == "binary_compressed":
        raise UnsupportedPcdFormatError(
            "binary_compressed PCD 暂不支持，请先转换为标准 binary 或 ASCII 格式"
        )
    if data_mode not in ("ascii", "binary"):
        raise UnsupportedPcdFormatError(f"不支持的 PCD 数据格式模式: '{data_mode}'")

    fields = header.get("FIELDS", [])
    if not all(f in fields for f in ("x", "y", "z")):
        raise InvalidPcdFileError(f"PCD 缺少必要的三维空间字段 x, y, z: {fields}")

    points_count = header.get("POINTS", 0)
    if points_count <= 0 and header.get("WIDTH", 0) <= 0:
        raise InvalidPcdFileError("PCD 头部声明的点云点数无效 (<= 0)")

    return {
        "header": header,
        "data_mode": data_mode,
        "declared_points": points_count,
        "file_size": file_size,
    }
