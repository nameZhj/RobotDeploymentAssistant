"""
@file: src/domain/choreo_entities/asset_models.py
@brief: 地图点云资源 (MapAsset) 与机器人动作资源 (ActionAsset) 领域实体
@exports: MapAssetEntity, ActionAssetEntity
"""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from src.domain.choreo_entities.domain_validator import DomainValidator


@dataclass
class MapAssetEntity:
    map_id: str
    display_name: str
    file_uri: str
    source_filename: str
    format: str = "PCD"
    encoding: str = "ASCII"
    scene_id: Optional[str] = None
    point_count: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fields: List[str] = field(default_factory=lambda: ["x", "y", "z"])
    resolution: Optional[float] = 0.05
    bounds: Dict[str, float] = field(default_factory=dict)
    origin_pose: Dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0})
    coordinate_frame_id: str = "map"
    distance_unit: str = "m"
    sha256: str = ""
    file_size_bytes: int = 0
    import_state: str = "READY"
    import_error_code: Optional[str] = None
    import_error_message: Optional[str] = None
    created_at: str = field(default_factory=DomainValidator.now_utc_iso)
    updated_at: str = field(default_factory=DomainValidator.now_utc_iso)

    def __post_init__(self) -> None:
        self.map_id = DomainValidator.validate_id(self.map_id, "map_id")
        self.display_name = self.display_name.strip()
        if not self.display_name:
            raise ValueError("地图显示名称不能为空")
        if self.import_state not in ("IMPORTING", "READY", "FAILED", "MISSING"):
            raise ValueError(f"未知地图导入状态: {self.import_state}")
        if self.import_state == "READY" and self.file_size_bytes < 0:
            raise ValueError("就绪地图文件大小必须非负")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ActionAssetEntity:
    action_id: str
    name: str
    model_type: str = "Unitree_G1"
    asset_uri: str = ""
    source_filename: str = ""
    file_sha256: Optional[str] = None
    duration_ms: Optional[int] = None
    sample_rate_hz: Optional[float] = None
    joint_names: List[str] = field(default_factory=list)
    compatibility_json: Dict[str, Any] = field(default_factory=dict)
    metadata_json: Dict[str, Any] = field(default_factory=dict)
    import_state: str = "READY"
    created_at: str = field(default_factory=DomainValidator.now_utc_iso)
    updated_at: str = field(default_factory=DomainValidator.now_utc_iso)

    def __post_init__(self) -> None:
        self.action_id = DomainValidator.validate_id(self.action_id, "action_id")
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("动作名称不能为空")
        if self.duration_ms is not None and self.duration_ms <= 0:
            raise ValueError("动作持续时长 (duration_ms) 必须大于 0")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
