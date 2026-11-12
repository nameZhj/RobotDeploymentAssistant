"""
@file: src/domain/choreo_entities/timeline_models.py
@brief: 时间轴 (Timeline)、轨道 (TimelineTrack) 与片段 (TimelineClip) 领域实体
@exports: TimelineEntity, TimelineTrackEntity, TimelineClipEntity
"""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from src.domain.choreo_entities.domain_validator import DomainValidator


@dataclass
class TimelineEntity:
    timeline_id: str
    scene_id: str
    name: str
    duration_ms: int = 120000
    frame_rate: Optional[float] = 30.0
    created_at: str = field(default_factory=DomainValidator.now_utc_iso)
    updated_at: str = field(default_factory=DomainValidator.now_utc_iso)
    revision: int = 1

    def __post_init__(self) -> None:
        self.timeline_id = DomainValidator.validate_id(self.timeline_id, "timeline_id")
        self.scene_id = DomainValidator.validate_id(self.scene_id, "scene_id")
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("时间轴名称不能为空")
        if self.duration_ms < 0:
            raise ValueError("时间轴时长必须非负")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TimelineTrackEntity:
    track_id: str
    timeline_id: str
    track_type: str = "ROBOT"
    robot_id: Optional[str] = None
    group_id: Optional[str] = None
    display_order: int = 0
    muted: bool = False
    locked: bool = False

    def __post_init__(self) -> None:
        self.track_id = DomainValidator.validate_id(self.track_id, "track_id")
        self.timeline_id = DomainValidator.validate_id(self.timeline_id, "timeline_id")
        if self.track_type not in ("ROBOT", "ACTION", "TRAJECTORY", "EVENT"):
            raise ValueError(f"不支持的轨道类型: {self.track_type}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TimelineClipEntity:
    clip_id: str
    track_id: str
    source_type: str
    source_id: str
    start_ms: int
    duration_ms: int
    offset_ms: int = 0
    playback_rate: float = 1.0
    enabled: bool = True
    revision: int = 1

    def __post_init__(self) -> None:
        self.clip_id = DomainValidator.validate_id(self.clip_id, "clip_id")
        self.track_id = DomainValidator.validate_id(self.track_id, "track_id")
        self.source_id = DomainValidator.validate_id(self.source_id, "source_id")
        if self.source_type not in ("ACTION", "TRAJECTORY", "EVENT", "DANCE"):
            raise ValueError(f"不支持的片段资源类型: {self.source_type}")
        if self.start_ms < 0:
            raise ValueError("片段起始时间 (start_ms) 必须非负")
        if self.duration_ms <= 0:
            raise ValueError("片段持续时长 (duration_ms) 必须大于 0")
        if self.offset_ms < 0:
            raise ValueError("片段偏移时间 (offset_ms) 必须非负")
        if not (0.1 <= self.playback_rate <= 10.0):
            raise ValueError(f"播放速率超出合法区间 [0.1, 10.0]: {self.playback_rate}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
