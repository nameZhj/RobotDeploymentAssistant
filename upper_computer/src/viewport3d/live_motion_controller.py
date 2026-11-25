# @file: src/viewport3d/live_motion_controller.py
# @brief: Tracks live ROS robot poses, velocity-estimated walking gaits, and active NPZ dance sync for StageViewport3D.
# @exports: LiveMotionController

from __future__ import annotations

import math
import time
from typing import Dict, Optional, Tuple
import numpy as np

from src.viewport3d.dance_motion_player import DanceMotionPlayer, procedural_gait_angles


class LiveMotionController:
    """Estimates per-robot speed and resolves live/timeline 29-DOF poses without UI boilerplate."""

    def __init__(self, motion_player: DanceMotionPlayer) -> None:
        self.motion_player = motion_player
        self.live_poses: Dict[str, Tuple[float, float, float]] = {}
        self.live_states: Dict[str, Dict[str, object]] = {}
        self._vel_tracker: Dict[str, Dict[str, float]] = {}

    def set_poses(self, poses: Dict[str, Tuple[float, float, float]]) -> None:
        now = time.monotonic()
        self.live_poses = {k.upper(): v for k, v in poses.items()}
        for tid, pose in self.live_poses.items():
            self._update_vel(tid, pose[0], pose[1], now)
            st = self.live_states.setdefault(tid, {})
            st["pose"] = pose
        for tid in [k for k in self.live_states if k not in self.live_poses]:
            del self.live_states[tid]

    def set_states(self, states: Dict[str, Dict[str, object]]) -> None:
        now = time.monotonic()
        norm_states: Dict[str, Dict[str, object]] = {}
        new_poses: Dict[str, Tuple[float, float, float]] = {}
        for k, rec in states.items():
            tid = k.upper()
            entry = dict(rec)
            norm_states[tid] = entry
            p = entry.get("pose")
            if isinstance(p, (tuple, list)) and len(p) >= 3:
                pt = (float(p[0]), float(p[1]), float(p[2]))
                new_poses[tid] = pt
                self._update_vel(tid, pt[0], pt[1], now)
        self.live_states = norm_states
        self.live_poses = new_poses

    def _update_vel(self, tid: str, x: float, y: float, now: float) -> None:
        tr = self._vel_tracker.get(tid)
        if tr is None:
            self._vel_tracker[tid] = {"x": x, "y": y, "t": now, "move_t": 0.0, "v": 0.0}
            return
        dist = math.hypot(x - tr["x"], y - tr["y"])
        dt = now - tr["t"]
        if dist > 0.002 and 0.015 <= dt <= 2.5:
            tr["v"] = 0.45 * tr["v"] + 0.55 * min(2.0, dist / dt)
            tr["move_t"] = now
            tr["x"], tr["y"], tr["t"] = x, y, now
        elif (now - tr["move_t"]) > 0.65:
            tr["v"] = 0.0
            tr["x"], tr["y"], tr["t"] = x, y, now

    def decay_and_check_active(self) -> bool:
        """Decay stale speeds and return True when any live robot needs continuous animation ticks."""
        now = time.monotonic()
        for tr in self._vel_tracker.values():
            if (now - tr["move_t"]) > 0.65:
                tr["v"] = 0.0
        for tid, st in self.live_states.items():
            ms = str(st.get("motion_state") or "").upper()
            v = self._vel_tracker.get(tid, {}).get("v", 0.0)
            if st.get("active_dance") or ms == "GAIT" or v >= 0.03:
                return True
        return False

    def resolve_live_motion(
        self, tid: str, now_mono: float
    ) -> Tuple[float, np.ndarray, Optional[np.ndarray], str]:
        st = self.live_states.get(tid, {})
        ms = str(st.get("motion_state") or "").upper()
        dance = str(st.get("active_dance") or "").strip()
        if ms in ("ESTOP", "FAULT"):
            z, q, _ = self.motion_player._basic_directive_clip("PASSIVE").sample_pose_at(0.0)
            return z, q, None, ms
        if dance:
            start_s = float(st.get("dance_start_s") or now_mono)
            clip = self.motion_player.get_clip(self.motion_player.resolve_dance_file(dance) or dance)
            z, q, rq = clip.sample_pose_at(max(0.0, now_mono - start_s))
            return z, q, rq, "DANCE"
        if ms == "PASSIVE":
            z, q, _ = self.motion_player._basic_directive_clip("PASSIVE").sample_pose_at(0.0)
            return z, q, None, "PASSIVE"
        v = float(self._vel_tracker.get(tid, {}).get("v", 0.0))
        if v >= 0.03 or ms == "GAIT":
            z, q = procedural_gait_angles(now_mono, max(v, 0.35 if ms == "GAIT" else v))
            return z, q, None, "WALK"
        z, q = procedural_gait_angles(0.0, 0.0)
        return z, q, None, ""

    def resolve_timeline_motion(
        self, state, track, t: float
    ) -> Tuple[float, np.ndarray, Optional[np.ndarray], str]:
        action = state.active_action_at(track, t)
        if action is not None:
            blk = next((b for b in state.blocks if b.track_id == track.id and not b.is_ignored and b.block_type == "action" and b.start_time <= t <= b.end_time), None)
            local_t = max(0.0, t - blk.start_time) if blk is not None else t
            z, q, rq = self.motion_player.get_clip_for_action(action.motion_file_path, lrmp_code=action.lrmp_code, action_no=action.no).sample_pose_at(local_t)
            return z, q, rq, ""
        x0, y0, _ = state.evaluate_robot_pose(track, max(0.0, t - 0.05))
        x1, y1, _ = state.evaluate_robot_pose(track, t + 0.05)
        z, q = procedural_gait_angles(t, math.hypot(x1 - x0, y1 - y0) / 0.1)
        return z, q, None, ""
