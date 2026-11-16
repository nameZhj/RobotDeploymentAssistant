# @file: src/domain/action_entities.py
# @brief: Domain entity for dance and humanoid action assets (LRMP 33 official dances and custom CSV/NPZ).
# @exports: ActionEntity

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ActionEntity:
    """Represents a robot dance or action block assignable onto any timeline track."""

    id: Optional[int] = None
    no: int = 1001
    name: str = ""
    category: str = "G1_GENERAL"  # G1_GENERAL | G2_POPULAR | G3_HUMANOID | BASIC | CUSTOM
    lrmp_code: str = ""
    robot_model: str = "G1"
    duration: float = 10.0
    motion_file_path: str = ""
    is_builtin: bool = True
    sync_status: str = "synced"  # synced | new | updated
    allow_move: bool = False
    allow_stretch: bool = False
