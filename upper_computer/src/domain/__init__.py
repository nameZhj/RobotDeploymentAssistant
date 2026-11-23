# @file: src/domain/__init__.py
# @brief: Domain entity exports covering scenes, tasks, tracks, trajectories, actions, timeline blocks, and PCD maps.
# @exports: StageConfig, SceneEntity, TaskEntity, TrackEntity, InitPointItem, InitPointConfig, ControlPoint2D, TrajectoryGroupEntity, TrajectoryEntity, ActionEntity, TimelineBlockEntity, TimelineFragmentEntity, PcdMapEntity

from src.domain.action_entities import ActionEntity
from src.domain.map_entities import PcdMapEntity
from src.domain.scene_entities import SceneEntity, StageConfig, TaskEntity
from src.domain.timeline_entities import TimelineBlockEntity, TimelineFragmentEntity
from src.domain.track_entities import (
    InitPointConfig,
    InitPointItem,
    TRACK_COLOR_PALETTE,
    TrackEntity,
    default_target_alias,
    pick_track_color,
)
from src.domain.trajectory_entities import (
    ControlPoint2D,
    TrajectoryEntity,
    TrajectoryGroupEntity,
)

__all__ = [
    "StageConfig",
    "SceneEntity",
    "TaskEntity",
    "TRACK_COLOR_PALETTE",
    "pick_track_color",
    "default_target_alias",
    "TrackEntity",
    "InitPointItem",
    "InitPointConfig",
    "ControlPoint2D",
    "TrajectoryGroupEntity",
    "TrajectoryEntity",
    "ActionEntity",
    "TimelineBlockEntity",
    "TimelineFragmentEntity",
    "PcdMapEntity",
]
