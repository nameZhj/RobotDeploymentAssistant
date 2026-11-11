"""
@file: src/domain/project/show_project.py
@brief: 统一舞台编导工程领域实体契约（项目、机器人、群组、阵型与动作素材）
@exports: ShowProject, Robot, RobotGroup, Formation, MotionAsset
"""
from dataclasses import asdict, dataclass, field
import time
from typing import Any, Dict, List, Optional


@dataclass
class Robot:
    """机器人实体契约，记录稳定唯一 robot_id、机型与当前能力状态"""
    robot_id: str
    model: str = "Unitree_G1"
    display_name: str = ""
    status: str = "AVAILABLE"  # AVAILABLE, UNSUPPORTED, NOT_CONNECTED

    def __post_init__(self) -> None:
        if not self.robot_id or not str(self.robot_id).strip():
            raise ValueError("robot_id 不能为空")
        if not self.display_name:
            self.display_name = f"Robot_{self.robot_id}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Robot":
        return cls(
            robot_id=str(data["robot_id"]),
            model=str(data.get("model", "Unitree_G1")),
            display_name=str(data.get("display_name", "")),
            status=str(data.get("status", "AVAILABLE")),
        )


@dataclass
class RobotGroup:
    """机器人群组编队聚合实体契约"""
    group_id: str
    name: str = ""
    member_robot_ids: List[str] = field(default_factory=list)
    default_formation_id: str = ""

    def __post_init__(self) -> None:
        if not self.group_id or not str(self.group_id).strip():
            raise ValueError("group_id 不能为空")
        if not self.name:
            self.name = f"Group_{self.group_id}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RobotGroup":
        return cls(
            group_id=str(data["group_id"]),
            name=str(data.get("name", "")),
            member_robot_ids=[str(rid) for rid in data.get("member_robot_ids", [])],
            default_formation_id=str(data.get("default_formation_id", "")),
        )


@dataclass
class Formation:
    """阵型配置契约，定义几何形状、间距与确定性成员槽位分配"""
    formation_id: str
    name: str = ""
    formation_type: str = "LINE"  # LINE, COLUMN, GRID, CIRCLE, CUSTOM
    slots: List[Dict[str, Any]] = field(default_factory=list)
    member_mapping: Dict[str, int] = field(default_factory=dict)
    spacing_m: float = 1.2
    heading_deg: float = 0.0
    parameters: Dict[str, Any] = field(default_factory=dict)
    version: int = 1

    def __post_init__(self) -> None:
        if not self.formation_id or not str(self.formation_id).strip():
            raise ValueError("formation_id 不能为空")
        if not self.name:
            self.name = f"Formation_{self.formation_id}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Formation":
        return cls(
            formation_id=str(data["formation_id"]),
            name=str(data.get("name", "")),
            formation_type=str(data.get("formation_type", "LINE")),
            slots=list(data.get("slots", [])),
            member_mapping=dict(data.get("member_mapping", {})),
            spacing_m=float(data.get("spacing_m", 1.2)),
            heading_deg=float(data.get("heading_deg", 0.0)),
            parameters=dict(data.get("parameters", {})),
            version=int(data.get("version", 1)),
        )


@dataclass
class MotionAsset:
    """真实动作素材资产契约，追踪来源文件、关节映射、帧数与有效性状态"""
    motion_id: str
    name: str
    file_path: str
    robot_model: str = "Unitree_G1"
    joint_mapping: List[str] = field(default_factory=list)
    frame_count: int = 0
    duration_s: float = 0.0
    fps: float = 30.0
    angle_unit: str = "rad"  # rad, deg
    sha256: str = ""
    source: str = "local"
    validation_status: str = "VALID"  # VALID, INVALID, UNCHECKED

    def __post_init__(self) -> None:
        if not self.motion_id or not str(self.motion_id).strip():
            raise ValueError("motion_id 不能为空")
        if not self.name:
            self.name = f"Motion_{self.motion_id}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MotionAsset":
        return cls(
            motion_id=str(data["motion_id"]),
            name=str(data.get("name", "")),
            file_path=str(data.get("file_path", "")),
            robot_model=str(data.get("robot_model", "Unitree_G1")),
            joint_mapping=[str(j) for j in data.get("joint_mapping", [])],
            frame_count=int(data.get("frame_count", 0)),
            duration_s=float(data.get("duration_s", 0.0)),
            fps=float(data.get("fps", 30.0)),
            angle_unit=str(data.get("angle_unit", "rad")),
            sha256=str(data.get("sha256", "")),
            source=str(data.get("source", "local")),
            validation_status=str(data.get("validation_status", "VALID")),
        )


@dataclass
class ShowProject:
    """顶层舞台编导项目聚合根实体契约"""
    project_id: str
    name: str
    current_map_id: str = ""
    coordinate_frame: str = "stage_world"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.project_id or not str(self.project_id).strip():
            raise ValueError("project_id 不能为空")
        if not self.name or not str(self.name).strip():
            raise ValueError("项目名称不能为空")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ShowProject":
        return cls(
            project_id=str(data["project_id"]),
            name=str(data["name"]),
            current_map_id=str(data.get("current_map_id", "")),
            coordinate_frame=str(data.get("coordinate_frame", "stage_world")),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            version=int(data.get("version", 1)),
            metadata=dict(data.get("metadata", {})),
        )
