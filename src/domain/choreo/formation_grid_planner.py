import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from src.core.config_loader import config_loader
from src.domain.choreo.plan_manifest_model import SpatialSplineTrack, SpatialTrackPoint


@dataclass(frozen=True)
class FormationPoint:
    """Designated 2D stage position for a robot."""
    alias: str
    x: float
    y: float
    heading_deg: float = 0.0


@dataclass(frozen=True)
class CollisionAlert:
    """Inter-robot proximity hazard detection event."""
    time_ms: int
    robot_pair: Tuple[str, str]
    distance_m: float
    min_safe_radius_m: float


class FormationGridPlanner:
    """
    Computes NxM matrix and geometric formation layouts (Line, V-shape, Circle).
    Generates transitional spatial trajectories and detects dynamic inter-robot collision risks.
    """

    def __init__(self) -> None:
        cfg = config_loader.get_graphics_3d()
        self._min_safe_radius = float(cfg.get("collision_warning_radius_m", 0.65))

    def generate_grid_formation(
        self,
        aliases: List[str],
        rows: int,
        cols: int,
        row_spacing_m: float = 1.2,
        col_spacing_m: float = 1.2,
        center_x: float = 0.0,
        center_y: float = 0.0,
        yaw_deg: float = 0.0,
    ) -> Dict[str, FormationPoint]:
        """Calculate NxM spatial grid slots centered at (center_x, center_y)."""
        results: Dict[str, FormationPoint] = {}
        rad = math.radians(yaw_deg)
        cos_y, sin_y = math.cos(rad), math.sin(rad)

        offset_x = ((cols - 1) * col_spacing_m) / 2.0
        offset_y = ((rows - 1) * row_spacing_m) / 2.0

        idx = 0
        for r in range(rows):
            for c in range(cols):
                if idx >= len(aliases):
                    break
                alias = aliases[idx]
                lx = (c * col_spacing_m) - offset_x
                ly = (r * row_spacing_m) - offset_y

                # Apply yaw rotation
                gx = center_x + (lx * cos_y - ly * sin_y)
                gy = center_y + (lx * sin_y + ly * cos_y)

                results[alias] = FormationPoint(
                    alias=alias,
                    x=round(gx, 3),
                    y=round(gy, 3),
                    heading_deg=yaw_deg,
                )
                idx += 1

        return results

    def plan_transition_trajectories(
        self,
        start_slots: Dict[str, FormationPoint],
        end_slots: Dict[str, FormationPoint],
        start_ms: int,
        duration_ms: int,
    ) -> Dict[str, SpatialSplineTrack]:
        """Generate smooth linear/spline transitional tracks from start to end slots."""
        tracks: Dict[str, SpatialSplineTrack] = {}
        aliases = set(start_slots.keys()).intersection(end_slots.keys())

        for alias in aliases:
            p0 = start_slots[alias]
            p1 = end_slots[alias]

            pts = (
                SpatialTrackPoint(x=p0.x, y=p0.y, heading_deg=p0.heading_deg, time_offset_ms=0),
                SpatialTrackPoint(x=p1.x, y=p1.y, heading_deg=p1.heading_deg, time_offset_ms=duration_ms),
            )
            tracks[alias] = SpatialSplineTrack(
                track_id=f"traj_{alias}_{start_ms}",
                start_ms=start_ms,
                duration_ms=duration_ms,
                points=pts,
            )

        return tracks

    def detect_trajectory_collisions(
        self,
        tracks: Dict[str, SpatialSplineTrack],
        sample_step_ms: int = 100,
    ) -> List[CollisionAlert]:
        """Sample synchronized spatial positions and detect inter-robot proximity hazards."""
        alerts: List[CollisionAlert] = []
        if len(tracks) < 2:
            return alerts

        aliases = sorted(list(tracks.keys()))
        min_start = min(t.start_ms for t in tracks.values())
        max_end = max(t.end_ms for t in tracks.values())

        for t_ms in range(min_start, max_end + 1, sample_step_ms):
            positions: Dict[str, Tuple[float, float]] = {}
            for alias, track in tracks.items():
                if track.start_ms <= t_ms <= track.end_ms:
                    pos = self._sample_position_at(track, t_ms)
                    if pos:
                        positions[alias] = pos

            # Evaluate all unique pairs
            pos_keys = list(positions.keys())
            for i in range(len(pos_keys)):
                for j in range(i + 1, len(pos_keys)):
                    a1, a2 = pos_keys[i], pos_keys[j]
                    x1, y1 = positions[a1]
                    x2, y2 = positions[a2]
                    dist = math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)

                    if dist < self._min_safe_radius:
                        alerts.append(CollisionAlert(
                            time_ms=t_ms,
                            robot_pair=(a1, a2),
                            distance_m=round(dist, 3),
                            min_safe_radius_m=self._min_safe_radius,
                        ))

        return alerts

    @staticmethod
    def _sample_position_at(track: SpatialSplineTrack, t_ms: int) -> Optional[Tuple[float, float]]:
        """Interpolate 2D position along spline track points."""
        if not track.points:
            return None
        if len(track.points) == 1:
            return track.points[0].x, track.points[0].y

        offset = t_ms - track.start_ms
        p0, p1 = track.points[0], track.points[1]
        ratio = max(0.0, min(1.0, offset / max(1.0, float(track.duration_ms))))

        x = p0.x + (p1.x - p0.x) * ratio
        y = p0.y + (p1.y - p0.y) * ratio
        return x, y


formation_grid_planner = FormationGridPlanner()

