import hashlib
import hmac
import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from src.core.config_loader import config_loader


@dataclass
class SafetyAuditReport:
    """Consolidated safety check report for multi-robot choreography plans."""
    is_safe: bool
    plan_id: str
    signature: str
    velocity_violations: List[str] = field(default_factory=list)
    collision_alerts: List[str] = field(default_factory=list)
    motion_conflicts: List[str] = field(default_factory=list)


class ChoreoSafetyGuard:
    """
    Clean-Room choreography safety auditing engine.
    Enforces maximum velocity limits, inter-robot Euclidean distance collision checks,
    stationary dance vs locomotive conflict detection, and immutable plan_id signatures.
    """

    def __init__(self, hmac_key: str = "CHOREO_IMMUTABLE_SALT_V1") -> None:
        graphics_cfg = config_loader.get_graphics_3d()
        self._safe_distance_m = float(graphics_cfg.get("collision_warning_radius_m", 0.65))
        self._max_linear_velocity_mps = 1.5
        self._hmac_key = hmac_key.encode("utf-8")

    def validate_trajectory_velocity(
        self,
        waypoints: List[Tuple[float, float, float]],
        max_velocity: Optional[float] = None,
    ) -> List[str]:
        """Validate that speed between consecutive trajectory waypoints (x, y, t) does not exceed limit."""
        v_limit = max_velocity or self._max_linear_velocity_mps
        violations = []
        for i in range(1, len(waypoints)):
            x0, y0, t0 = waypoints[i - 1]
            x1, y1, t1 = waypoints[i]
            dt = t1 - t0
            if dt <= 0.001:
                continue
            dist = math.hypot(x1 - x0, y1 - y0)
            velocity = dist / dt
            if velocity > v_limit:
                violations.append(f"At t={t1:.2f}s: velocity {velocity:.2f}m/s exceeds limit {v_limit:.2f}m/s")
        return violations

    def detect_inter_robot_collisions(
        self,
        trajectories: Dict[str, List[Tuple[float, float, float]]],
        min_distance_m: Optional[float] = None,
    ) -> List[str]:
        """Evaluate Euclidean distance between all robot pairs at synchronized timestamps."""
        safe_r = min_distance_m or self._safe_distance_m
        alerts = []
        aliases = sorted(list(trajectories.keys()))

        # Collect common sampled time points
        time_samples = set()
        for pts in trajectories.values():
            for _, _, t in pts:
                time_samples.add(round(t, 2))

        for t_curr in sorted(list(time_samples)):
            positions: Dict[str, Tuple[float, float]] = {}
            for alias in aliases:
                pts = trajectories[alias]
                # Nearest point lookup
                nearest = min(pts, key=lambda p: abs(p[2] - t_curr))
                if abs(nearest[2] - t_curr) <= 0.2:
                    positions[alias] = (nearest[0], nearest[1])

            # Check distance across all distinct pairs
            for i in range(len(aliases)):
                for j in range(i + 1, len(aliases)):
                    a1, a2 = aliases[i], aliases[j]
                    if a1 in positions and a2 in positions:
                        p1, p2 = positions[a1], positions[a2]
                        d = math.hypot(p1[0] - p2[0], p1[1] - p2[1])
                        if d < safe_r:
                            alerts.append(
                                f"At t={t_curr:.2f}s: collision hazard between [{a1}] and [{a2}] "
                                f"(dist={d:.2f}m < safe_r={safe_r:.2f}m)"
                            )
        return alerts

    def check_motion_conflicts(
        self,
        stationary_actions: List[Dict[str, Any]],
        trajectory_segments: List[Dict[str, Any]],
    ) -> List[str]:
        """Verify that in-place dancing does not conflict with active displacement trajectories."""
        conflicts = []
        for act in stationary_actions:
            act_start = float(act.get("start_ms", 0)) / 1000.0
            act_end = float(act.get("end_ms", 0)) / 1000.0
            robot = act.get("robot_id", "")

            for traj in trajectory_segments:
                if traj.get("robot_id", "") == robot:
                    t_start = float(traj.get("start_time_s", 0))
                    t_end = float(traj.get("end_time_s", 0))
                    # Check temporal overlap
                    if max(act_start, t_start) < min(act_end, t_end):
                        conflicts.append(
                            f"Robot [{robot}] has motion conflict: stationary action "
                            f"[{act.get('action_name')}] ({act_start:.1f}-{act_end:.1f}s) overlaps with MOVE trajectory"
                        )
        return conflicts

    def generate_plan_signature(self, plan_data: Dict[str, Any]) -> Tuple[str, str]:
        """Compile immutable deterministic plan_id and HMAC-SHA256 signature."""
        normalized_json = json.dumps(plan_data, sort_keys=True, separators=(",", ":"))
        content_hash = hashlib.sha256(normalized_json.encode("utf-8")).hexdigest()
        plan_id = f"PLAN_{content_hash[:12].upper()}"
        signature = hmac.new(self._hmac_key, normalized_json.encode("utf-8"), hashlib.sha256).hexdigest()
        return plan_id, signature

    def audit_choreography_plan(
        self,
        plan_data: Dict[str, Any],
        trajectories: Dict[str, List[Tuple[float, float, float]]],
        stationary_actions: Optional[List[Dict[str, Any]]] = None,
    ) -> SafetyAuditReport:
        """Run full safety preflight gate."""
        plan_id, signature = self.generate_plan_signature(plan_data)
        vel_violations = []
        for alias, pts in trajectories.items():
            viol = self.validate_trajectory_velocity(pts)
            for v in viol:
                vel_violations.append(f"[{alias}] {v}")

        col_alerts = self.detect_inter_robot_collisions(trajectories)
        conflicts = self.check_motion_conflicts(stationary_actions or [], plan_data.get("trajectories", []))

        is_safe = len(vel_violations) == 0 and len(col_alerts) == 0 and len(conflicts) == 0
        return SafetyAuditReport(
            is_safe=is_safe,
            plan_id=plan_id,
            signature=signature,
            velocity_violations=vel_violations,
            collision_alerts=col_alerts,
            motion_conflicts=conflicts,
        )


choreo_safety_guard = ChoreoSafetyGuard()

