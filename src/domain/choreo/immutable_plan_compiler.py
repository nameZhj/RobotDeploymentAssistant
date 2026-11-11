import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple
from src.domain.choreo.plan_manifest_model import ChoreoPlanManifest


@dataclass(frozen=True)
class CompiledChoreoPlan:
    """Immutable compiled artifact holding the deterministic plan_id and timeline steps."""
    plan_id: str
    content_hash: str
    manifest: ChoreoPlanManifest
    canonical_json: str
    robot_steps: Dict[str, Tuple[Dict[str, Any], ...]] = field(default_factory=dict)


class ImmutablePlanCompiler:
    """
    Deterministically transforms and signs a ChoreoPlanManifest.
    Guarantees that ANY modification to tracks, clips, or barriers produces a distinct plan_id.
    """

    @staticmethod
    def compile(manifest: ChoreoPlanManifest) -> CompiledChoreoPlan:
        """Compile manifest into an immutable artifact with cryptographically verifiable plan_id."""
        valid, err = manifest.validate_cohort()
        if not valid:
            raise ValueError(f"Plan cohort validation failed: {err}")

        manifest.calculate_total_duration()

        # Build clean canonical dictionary strictly ordered for hashing
        canonical_dict: Dict[str, Any] = {
            "name": manifest.plan_name.strip(),
            "locked_robots": sorted(list(manifest.locked_robot_aliases)),
            "music_file": manifest.music_file or "",
            "tracks": {},
            "barriers": [],
        }

        # Canonicalize tracks
        robot_steps: Dict[str, List[Dict[str, Any]]] = {}
        for alias in manifest.locked_robot_aliases:
            track = manifest.tracks.get(alias)
            steps: List[Dict[str, Any]] = []
            clips_data: List[Dict[str, Any]] = []
            traj_data: List[Dict[str, Any]] = []

            if track:
                for c in sorted(track.clips, key=lambda x: (x.start_ms, x.clip_id)):
                    clip_dict = {
                        "clip_id": c.clip_id,
                        "action": c.action_name,
                        "start_ms": c.start_ms,
                        "duration_ms": c.duration_ms,
                        "speed": round(float(c.speed_scale), 3),
                    }
                    clips_data.append(clip_dict)
                    steps.append({"type": "CLIP", "time_ms": c.start_ms, "data": clip_dict})

                for t in sorted(track.trajectories, key=lambda x: (x.start_ms, x.track_id)):
                    pts = [
                        {"x": round(float(p.x), 3), "y": round(float(p.y), 3), "h": round(float(p.heading_deg), 1), "t": p.time_offset_ms}
                        for p in t.points
                    ]
                    t_dict = {
                        "track_id": t.track_id,
                        "start_ms": t.start_ms,
                        "duration_ms": t.duration_ms,
                        "points": pts,
                    }
                    traj_data.append(t_dict)
                    steps.append({"type": "TRAJ", "time_ms": t.start_ms, "data": t_dict})

            canonical_dict["tracks"][alias] = {
                "clips": clips_data,
                "trajectories": traj_data,
            }
            steps.sort(key=lambda s: s["time_ms"])
            robot_steps[alias] = steps

        # Canonicalize barriers
        for b in sorted(manifest.barriers, key=lambda x: (x.target_time_ms, x.barrier_id)):
            canonical_dict["barriers"].append({
                "barrier_id": b.barrier_id,
                "time_ms": b.target_time_ms,
                "robots": sorted(list(b.participating_aliases)),
                "timeout_ms": b.timeout_ms,
            })

        # Serialize canonically with sorted keys to ensure zero non-determinism
        canonical_str = json.dumps(canonical_dict, sort_keys=True, separators=(",", ":"))
        hasher = hashlib.sha256(canonical_str.encode("utf-8"))
        content_hash = hasher.hexdigest()
        plan_id = f"PLAN_{content_hash[:16].upper()}"

        manifest.plan_id = plan_id

        frozen_steps: Dict[str, Tuple[Dict[str, Any], ...]] = {
            alias: tuple(steps) for alias, steps in robot_steps.items()
        }

        return CompiledChoreoPlan(
            plan_id=plan_id,
            content_hash=content_hash,
            manifest=manifest,
            canonical_json=canonical_str,
            robot_steps=frozen_steps,
        )


immutable_plan_compiler = ImmutablePlanCompiler()

