"""
@file: src/domain/choreo_entities/scene_models.py
@brief: 场景 (Scene)、机器人持久配置/运行时状态 (Robot) 与机器人群组 (RobotGroup) 领域实体
@exports: SceneEntity, RobotEntity, RobotTelemetry, RobotGroupEntity
"""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from src.domain.choreo_entities.domain_validator import DomainValidator


@dataclass
class SceneEntity:
    scene_id: str
    name: str
    description: Optional[str] = None
    active_map_id: Optional[str] = None
    coordinate_frame_id: Optional[str] = "map"
    distance_unit: str = "m"
    angle_unit: str = "rad"
    created_at: str = field(default_factory=DomainValidator.now_utc_iso)
    updated_at: str = field(default_factory=DomainValidator.now_utc_iso)
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.scene_id = DomainValidator.validate_id(self.scene_id, "scene_id")
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("场景名称 (name) 不能为空")
        if self.distance_unit not in ("m", "cm"):
            raise ValueError(f"不支持的距离单位: {self.distance_unit}")
        if self.angle_unit not in ("rad", "deg"):
            raise ValueError(f"不支持的角度单位: {self.angle_unit}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneEntity":
        return cls(
            scene_id=data["scene_id"],
            name=data["name"],
            description=data.get("description"),
            active_map_id=data.get("active_map_id"),
            coordinate_frame_id=data.get("coordinate_frame_id", "map"),
            distance_unit=data.get("distance_unit", "m"),
            angle_unit=data.get("angle_unit", "rad"),
            created_at=data.get("created_at") or DomainValidator.now_utc_iso(),
            updated_at=data.get("updated_at") or DomainValidator.now_utc_iso(),
            schema_version=int(data.get("schema_version", 1)),
        )


@dataclass
class RobotTelemetry:
    connection_state: str = "UNKNOWN"
    battery_percent: Optional[float] = None
    pose: Optional[Dict[str, Any]] = None
    last_seen_at: Optional[str] = None
    stale: bool = True

    def __post_init__(self) -> None:
        if self.connection_state not in ("ONLINE", "OFFLINE", "DEGRADED", "UNKNOWN"):
            raise ValueError(f"未知连接状态: {self.connection_state}")
        if self.battery_percent is not None:
            self.battery_percent = max(0.0, min(100.0, DomainValidator.validate_finite(self.battery_percent, "battery_percent")))


@dataclass
class RobotEntity:
    robot_id: str
    display_name: str
    model_type: str = "Unitree_G1"
    hardware_id: Optional[str] = None
    transport_kind: str = "SIM"
    namespace: str = ""
    enabled: bool = True
    created_at: str = field(default_factory=DomainValidator.now_utc_iso)
    updated_at: str = field(default_factory=DomainValidator.now_utc_iso)
    telemetry: RobotTelemetry = field(default_factory=RobotTelemetry)

    def __post_init__(self) -> None:
        self.robot_id = DomainValidator.validate_id(self.robot_id, "robot_id")
        self.display_name = self.display_name.strip()
        if not self.display_name:
            raise ValueError("机器人显示名称不能为空")

    def to_dict(self, include_telemetry: bool = False) -> Dict[str, Any]:
        d = {
            "robot_id": self.robot_id,
            "display_name": self.display_name,
            "model_type": self.model_type,
            "hardware_id": self.hardware_id,
            "transport_kind": self.transport_kind,
            "namespace": self.namespace,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if include_telemetry:
            d["telemetry"] = asdict(self.telemetry)
        return d


@dataclass
class RobotGroupEntity:
    group_id: str
    scene_id: str
    name: str
    member_robot_ids: List[str]
    description: Optional[str] = None
    formation_id: Optional[str] = None
    created_at: str = field(default_factory=DomainValidator.now_utc_iso)
    updated_at: str = field(default_factory=DomainValidator.now_utc_iso)

    def __post_init__(self) -> None:
        self.group_id = DomainValidator.validate_id(self.group_id, "group_id")
        self.scene_id = DomainValidator.validate_id(self.scene_id, "scene_id")
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("群组名称不能为空")
        if not isinstance(self.member_robot_ids, list):
            raise ValueError("member_robot_ids 必须为列表")
        if len(self.member_robot_ids) != len(set(self.member_robot_ids)):
            raise ValueError("member_robot_ids 包含重复机器人 ID")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
