# @file: src/domain/track_entities.py
# @brief: Domain entities for robot timeline tracks and multi-robot initialization point presets.
# @exports: TRACK_COLOR_PALETTE, TrackEntity, InitPointItem, InitPointConfig

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

TRACK_COLOR_PALETTE = (
    "#2e7bf7",  # --robot-1
    "#8b7cff",  # --robot-2
    "#e06fc4",  # --robot-3
    "#f0a228",  # --robot-4
    "#2bb673",  # --robot-5
)


def pick_track_color(track_no: int) -> str:
    """Return canonical UniUni robot track accent hex color for 1-based track_no."""
    idx = max(0, track_no - 1) % len(TRACK_COLOR_PALETTE)
    return TRACK_COLOR_PALETTE[idx]


def default_target_alias(track_no: int) -> str:
    """Map 1-based track index to LRMP target alias A..Z."""
    idx = max(0, track_no - 1)
    if idx < 26:
        return chr(ord("A") + idx)
    return f"R{track_no}"


@dataclass
class TrackEntity:
    """Represents a single robot timeline track bound to an LRMP target and IP."""

    id: Optional[int] = None
    task_id: int = 1
    track_no: int = 1
    name: str = ""
    target_id: str = ""
    robot_id: str = ""
    robot_ip: str = "192.168.123.101"
    robot_model: str = "G1-29DOF"
    color_hex: str = ""
    init_x: float = 0.0
    init_y: float = 0.0
    init_yaw: float = 0.0
    muted: bool = False
    locked: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            self.name = f"机器人 {self.track_no}"
        if not self.target_id:
            self.target_id = default_target_alias(self.track_no)
        if not self.robot_id:
            self.robot_id = f"Robot_{self.track_no}"
        if not self.color_hex:
            self.color_hex = pick_track_color(self.track_no)


@dataclass
class InitPointItem:
    """Single robot starting pose inside an InitPointConfig preset."""

    track_no: int
    target_id: str = "A"
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0


@dataclass
class InitPointConfig:
    """Named multi-robot starting formation configuration."""

    id: Optional[int] = None
    scene_id: int = 1
    name: str = "默认开场站位"
    points: List[InitPointItem] = field(default_factory=list)
    is_default: bool = True
