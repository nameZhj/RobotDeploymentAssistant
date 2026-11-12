"""
@file: src/core/models.py
@brief: 统一舞台编导核心数据模型（轨迹、阵型、地图索引与工程全景）
@exports: ControlPoint, SampledPoint, TrajectoryModel, FormationMember, FormationModel, ProjectChoreoModel
"""
from dataclasses import asdict, dataclass, field
import time
from typing import Any, Dict, List, Optional


@dataclass
class ControlPoint:
    seq: int
    x: float
    y: float
    yaw: float = 0.0
    t: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seq": self.seq,
            "x": round(float(self.x), 4),
            "y": round(float(self.y), 4),
            "yaw": round(float(self.yaw), 4),
            "t": round(float(self.t), 3),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ControlPoint":
        return cls(
            seq=int(data.get("seq", 0)),
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            yaw=float(data.get("yaw", 0.0)),
            t=float(data.get("t", 0.0)),
        )


@dataclass
class SampledPoint:
    seq: int
    x: float
    y: float
    yaw: float = 0.0
    t: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    wz: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seq": self.seq,
            "x": round(float(self.x), 4),
            "y": round(float(self.y), 4),
            "yaw": round(float(self.yaw), 4),
            "t": round(float(self.t), 3),
            "vx": round(float(self.vx), 4),
            "vy": round(float(self.vy), 4),
            "wz": round(float(self.wz), 4),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SampledPoint":
        return cls(
            seq=int(data.get("seq", 0)),
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            yaw=float(data.get("yaw", 0.0)),
            t=float(data.get("t", 0.0)),
            vx=float(data.get("vx", 0.0)),
            vy=float(data.get("vy", 0.0)),
            wz=float(data.get("wz", 0.0)),
        )


@dataclass
class TrajectoryModel:
    trajectory_id: str
    name: str
    schema_version: str = "1.0"
    scene_id: str = "scene_001"
    map_id: str = "map_001"
    target_type: str = "single"
    target_id: str = "A"
    formation_id: str = ""
    interpolation: str = "catmull_rom"
    max_velocity: float = 1.2
    control_points: List[ControlPoint] = field(default_factory=list)
    sampled_points: List[SampledPoint] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "trajectory_id": self.trajectory_id,
            "name": self.name,
            "scene_id": self.scene_id,
            "map_id": self.map_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "formation_id": self.formation_id,
            "interpolation": self.interpolation,
            "max_velocity": self.max_velocity,
            "control_points": [cp.to_dict() for cp in self.control_points],
            "sampled_points": [sp.to_dict() for sp in self.sampled_points],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrajectoryModel":
        cps = [ControlPoint.from_dict(p) for p in data.get("control_points", [])]
        sps = [SampledPoint.from_dict(p) for p in data.get("sampled_points", [])]
        return cls(
            schema_version=data.get("schema_version", "1.0"),
            trajectory_id=data.get("trajectory_id", f"traj_{int(time.time())}"),
            name=data.get("name", "未命名轨迹"),
            scene_id=data.get("scene_id", "scene_001"),
            map_id=data.get("map_id", "map_001"),
            target_type=data.get("target_type", "single"),
            target_id=data.get("target_id", "A"),
            formation_id=data.get("formation_id", ""),
            interpolation=data.get("interpolation", "catmull_rom"),
            max_velocity=float(data.get("max_velocity", 1.2)),
            control_points=cps,
            sampled_points=sps,
        )


@dataclass
class FormationMember:
    robot_id: str
    seq: int
    offset_x: float
    offset_y: float
    offset_yaw: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "robot_id": self.robot_id,
            "seq": self.seq,
            "offset_x": round(float(self.offset_x), 4),
            "offset_y": round(float(self.offset_y), 4),
            "offset_yaw": round(float(self.offset_yaw), 4),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FormationMember":
        return cls(
            robot_id=str(data.get("robot_id", "A")),
            seq=int(data.get("seq", 0)),
            offset_x=float(data.get("offset_x", 0.0)),
            offset_y=float(data.get("offset_y", 0.0)),
            offset_yaw=float(data.get("offset_yaw", 0.0)),
        )


@dataclass
class FormationModel:
    formation_id: str
    name: str
    type: str = "grid"
    center: Dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0, "yaw": 0.0})
    params: Dict[str, Any] = field(default_factory=lambda: {"spacing": 1.0, "rows": 2, "cols": 2, "radius": 1.5})
    members: List[FormationMember] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "formation_id": self.formation_id,
            "name": self.name,
            "type": self.type,
            "center": {
                "x": round(float(self.center.get("x", 0.0)), 4),
                "y": round(float(self.center.get("y", 0.0)), 4),
                "yaw": round(float(self.center.get("yaw", 0.0)), 4),
            },
            "params": dict(self.params),
            "members": [m.to_dict() for m in self.members],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FormationModel":
        members = [FormationMember.from_dict(m) for m in data.get("members", [])]
        return cls(
            formation_id=str(data.get("formation_id", f"form_{int(time.time())}")),
            name=str(data.get("name", "未命名阵型")),
            type=str(data.get("type", "grid")),
            center=data.get("center", {"x": 0.0, "y": 0.0, "yaw": 0.0}),
            params=data.get("params", {"spacing": 1.0, "rows": 2, "cols": 2, "radius": 1.5}),
            members=members,
        )


@dataclass
class ProjectChoreoModel:
    scene_id: str
    name: str
    map_id: str = "map_001"
    music_path: str = ""
    music_title: str = "未配置音乐"
    music_duration_s: float = 120.0
    tracks: List[Dict[str, Any]] = field(default_factory=list)
    init_points: List[Dict[str, Any]] = field(default_factory=list)
    trajectories: List[Dict[str, Any]] = field(default_factory=list)
    track_state: List[Dict[str, Any]] = field(default_factory=list)
    fragments: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "name": self.name,
            "map_id": self.map_id,
            "music_path": self.music_path,
            "music_title": self.music_title,
            "music_duration_s": round(float(self.music_duration_s), 2),
            "tracks": list(self.tracks),
            "init_points": list(self.init_points),
            "trajectories": list(self.trajectories),
            "track_state": list(self.track_state),
            "fragments": list(self.fragments),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectChoreoModel":
        return cls(
            scene_id=str(data.get("scene_id", "scene_001")),
            name=str(data.get("name", "默认舞台场景")),
            map_id=str(data.get("map_id", "map_001")),
            music_path=str(data.get("music_path", "")),
            music_title=str(data.get("music_title", "未配置音乐")),
            music_duration_s=float(data.get("music_duration_s", 120.0)),
            tracks=list(data.get("tracks", [])),
            init_points=list(data.get("init_points", [])),
            trajectories=list(data.get("trajectories", [])),
            track_state=list(data.get("track_state", [])),
            fragments=list(data.get("fragments", [])),
        )
