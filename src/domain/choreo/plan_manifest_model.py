from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class MotionClipSegment:
    """Individual choreo motion action block placed on a timeline track."""
    clip_id: str
    action_name: str
    start_ms: int
    duration_ms: int
    speed_scale: float = 1.0
    extra_params: Dict[str, Any] = field(default_factory=dict)

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.duration_ms


@dataclass(frozen=True)
class SpatialTrackPoint:
    """Waypoints defining spatial displacement across time."""
    x: float
    y: float
    heading_deg: float
    time_offset_ms: int


@dataclass(frozen=True)
class SpatialSplineTrack:
    """Trajectory displacement spline segment attached to a timeline track."""
    track_id: str
    start_ms: int
    duration_ms: int
    points: Tuple[SpatialTrackPoint, ...] = field(default_factory=tuple)

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.duration_ms


@dataclass(frozen=True)
class BarrierSyncMarker:
    """Synchronization barrier where all participating robots must report arrival."""
    barrier_id: str
    target_time_ms: int
    participating_aliases: Tuple[str, ...]
    timeout_ms: int = 5000


@dataclass
class RobotChoreoTrack:
    """Channel containing actions and trajectories for a specific bound robot."""
    robot_alias: str
    clips: List[MotionClipSegment] = field(default_factory=list)
    trajectories: List[SpatialSplineTrack] = field(default_factory=list)

    def add_clip(self, clip: MotionClipSegment) -> None:
        self.clips.append(clip)
        self.clips.sort(key=lambda c: c.start_ms)

    def add_trajectory(self, trajectory: SpatialSplineTrack) -> None:
        self.trajectories.append(trajectory)
        self.trajectories.sort(key=lambda t: t.start_ms)


@dataclass
class ChoreoPlanManifest:
    """
    Root entity defining the complete multi-robot dance choreography plan.
    Strictly locks the designated participating robots list upon creation.
    """
    plan_name: str
    locked_robot_aliases: Tuple[str, ...]
    tracks: Dict[str, RobotChoreoTrack] = field(default_factory=dict)
    barriers: List[BarrierSyncMarker] = field(default_factory=list)
    total_duration_ms: int = 0
    music_file: Optional[str] = None
    plan_id: str = ""

    def __post_init__(self) -> None:
        # Standardize and deduplicate locked robot aliases into immutable tuple
        clean_aliases = tuple(sorted(set(str(a).strip().upper() for a in self.locked_robot_aliases if str(a).strip())))
        self.locked_robot_aliases = clean_aliases

        # Initialize dedicated tracks for all locked robots
        for alias in self.locked_robot_aliases:
            if alias not in self.tracks:
                self.tracks[alias] = RobotChoreoTrack(robot_alias=alias)

    def is_robot_locked(self, alias: str) -> bool:
        """Verify whether an alias belongs to the locked choreography cohort."""
        return alias.strip().upper() in self.locked_robot_aliases

    def validate_cohort(self) -> Tuple[bool, str]:
        """Ensure no alien robot tracks have infiltrated the locked manifest."""
        for track_alias in self.tracks.keys():
            if not self.is_robot_locked(track_alias):
                return False, f"Alien robot track [{track_alias}] rejected: not in locked cohort {self.locked_robot_aliases}"

        for barrier in self.barriers:
            for p_alias in barrier.participating_aliases:
                if not self.is_robot_locked(p_alias):
                    return False, f"Barrier [{barrier.barrier_id}] includes uninvited robot [{p_alias}]"

        return True, "Cohort validated successfully"

    def calculate_total_duration(self) -> int:
        """Compute the overall span of the choreo from all tracks and barriers."""
        max_ms = 0
        for track in self.tracks.values():
            for c in track.clips:
                max_ms = max(max_ms, c.end_ms)
            for t in track.trajectories:
                max_ms = max(max_ms, t.end_ms)
        for b in self.barriers:
            max_ms = max(max_ms, b.target_time_ms)
        self.total_duration_ms = max_ms
        return max_ms

