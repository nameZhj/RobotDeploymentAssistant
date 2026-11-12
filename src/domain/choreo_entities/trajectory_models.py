"""
@file: src/domain/choreo_entities/trajectory_models.py
@brief: 轨迹几何数据 (Trajectory) 与阵型配置 (Formation) 领域实体
@exports: TrajectoryEntity, FormationEntity
"""
from dataclasses import asdict, dataclass, field
import json
from typing import Any, Dict, List, Optional
from src.domain.choreo_entities.domain_validator import DomainValidator


@dataclass
class TrajectoryEntity:
    trajectory_id: str
    scene_id: str
    name: str
    map_id: Optional[str] = None
    robot_id: Optional[str] = None
    group_id: Optional[str] = None
    coordinate_frame_id: str = "map"
    distance_unit: str = "m"
    angle_unit: str = "rad"
    geometry_type: str = "POLYLINE_2D"
    waypoints_data: Dict[str, Any] = field(default_factory=dict)
    point_count: int = 0
    total_length: Optional[float] = None
    estimated_duration_ms: Optional[int] = None
    created_at: str = field(default_factory=DomainValidator.now_utc_iso)
    updated_at: str = field(default_factory=DomainValidator.now_utc_iso)
    revision: int = 1

    def __post_init__(self) -> None:
        self.trajectory_id = DomainValidator.validate_id(self.trajectory_id, "trajectory_id")
        self.scene_id = DomainValidator.validate_id(self.scene_id, "scene_id")
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("轨迹名称不能为空")
        if not self.robot_id and not self.group_id:
            raise ValueError("robot_id 与 group_id 不能同时为空")
        if self.robot_id and self.group_id:
            raise ValueError("robot_id 与 group_id 不能同时赋值")
        if self.geometry_type != "POLYLINE_2D":
            raise ValueError(f"当前阶段仅支持 POLYLINE_2D 几何类型: {self.geometry_type}")

        # Validate waypoints structure
        wps = self.waypoints_data.get("waypoints", [])
        validated_wps = DomainValidator.validate_waypoints(wps)
        self.waypoints_data = {
            "schema_version": int(self.waypoints_data.get("schema_version", 1)),
            "coordinate_frame_id": self.coordinate_frame_id,
            "distance_unit": self.distance_unit,
            "angle_unit": self.angle_unit,
            "geometry_type": self.geometry_type,
            "waypoints": validated_wps,
        }
        self.point_count = len(validated_wps)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FormationEntity:
    formation_id: str
    scene_id: str
    name: str
    layout_type: str = "GRID"
    description: Optional[str] = None
    parameters_json: Dict[str, Any] = field(default_factory=dict)
    member_offsets_json: Dict[str, Dict[str, float]] = field(default_factory=dict)
    created_at: str = field(default_factory=DomainValidator.now_utc_iso)
    updated_at: str = field(default_factory=DomainValidator.now_utc_iso)
    revision: int = 1

    def __post_init__(self) -> None:
        self.formation_id = DomainValidator.validate_id(self.formation_id, "formation_id")
        self.scene_id = DomainValidator.validate_id(self.scene_id, "scene_id")
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("阵型名称不能为空")
        if self.layout_type not in ("GRID", "LINE", "CIRCLE", "CUSTOM"):
            raise ValueError(f"不支持的阵型布局类型: {self.layout_type}")
        for r_id, offset in self.member_offsets_json.items():
            DomainValidator.validate_finite(offset.get("x", 0.0), f"member[{r_id}].x")
            DomainValidator.validate_finite(offset.get("y", 0.0), f"member[{r_id}].y")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
