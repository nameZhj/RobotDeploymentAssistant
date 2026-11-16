# @file: src/domain/trajectory_entities.py
# @brief: Domain entities for 2D control points, trajectory groups, and UniUni-compatible trajectories.
# @exports: ControlPoint2D, TrajectoryGroupEntity, TrajectoryEntity

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class ControlPoint2D:
    """A 2D spline waypoint with optional heading yaw in radians."""

    x: float
    y: float
    yaw: float = 0.0


@dataclass
class TrajectoryGroupEntity:
    """Collapsible folder/group organizing single or formation trajectories and optional track binding."""

    id: Optional[int] = None
    scene_id: int = 1
    name: str = "默认轨迹分组"
    robot_count: int = 1
    bound_track_no: Optional[int] = None
    sort_order: int = 0


@dataclass
class TrajectoryEntity:
    """Trajectory asset matching UniUni trackState/trajectories schema and spline params."""

    id: Optional[int] = None
    group_id: int = 1
    no: int = 100001
    name: str = "未命名轨迹"
    duration: float = 5.0
    control_points: List[ControlPoint2D] = field(default_factory=list)
    interpolation_mode: str = "uniform"  # "uniform" (S-curve arc-length) | "linear"
    hold_direction: bool = False
    hold_yaw: float = 0.0
    end_turn: bool = False
    end_yaw: float = 0.0
    max_acc: float = 1.5
    run_mode: int = 504
    point_data_csv: str = ""
    updated_at: str = field(default_factory=_now_str)

    def start_pose(self) -> tuple[float, float, float]:
        """Return (x, y, yaw) of the initial control point if available."""
        if not self.control_points:
            return (0.0, 0.0, 0.0)
        p = self.control_points[0]
        return (p.x, p.y, p.yaw)

    def end_pose(self) -> tuple[float, float, float]:
        """Return (x, y, yaw) of the final control point if available."""
        if not self.control_points:
            return (0.0, 0.0, 0.0)
        p = self.control_points[-1]
        return (p.x, p.y, self.end_yaw if self.end_turn else p.yaw)
