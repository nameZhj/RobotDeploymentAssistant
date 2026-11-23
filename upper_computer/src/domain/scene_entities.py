# @file: src/domain/scene_entities.py
# @brief: Domain entities representing UniUni stage physical bounds, scenes, and choreography tasks.
# @exports: StageConfig, SceneEntity, TaskEntity

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class StageConfig:
    """Physical stage dimensions, safety margin, and grid display scale."""

    width: float = 12.0
    height: float = 8.0
    margin: float = 0.5
    grid_step: float = 1.0
    subgrid_step: float = 0.2
    origin_x: float = 0.0
    origin_y: float = 0.0

    def half_extents(self) -> tuple[float, float]:
        """Return half-width and half-height centered around origin."""
        return (self.width * 0.5, self.height * 0.5)


@dataclass
class SceneEntity:
    """Top-level stage project scene with music BPM and active PCD map reference."""

    id: Optional[int] = None
    name: str = "默认舞台"
    stage_width: float = 12.0
    stage_height: float = 8.0
    safety_margin: float = 0.5
    active_map_id: Optional[int] = None
    bpm: float = 120.0
    time_signature: str = "4/4"
    audio_path: str = ""
    updated_at: str = field(default_factory=_now_str)

    def to_stage_config(self) -> StageConfig:
        """Convert persisted dimensions to StageConfig value object."""
        return StageConfig(
            width=self.stage_width,
            height=self.stage_height,
            margin=self.safety_margin,
        )


@dataclass
class TaskEntity:
    """Editable multi-track choreography task inside a Scene."""

    id: Optional[int] = None
    scene_id: int = 1
    name: str = "主舞台编排"
    total_duration: float = 30.0
    is_active: bool = True
    created_at: str = field(default_factory=_now_str)
    updated_at: str = field(default_factory=_now_str)
