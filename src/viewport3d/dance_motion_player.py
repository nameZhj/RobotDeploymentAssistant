# @file: src/viewport3d/dance_motion_player.py
# @brief: Loads preview NPZ 21-joint/joint_pos dances, G1_dance.csv 36-col mocap, and BASIC/gait 29-DOF poses.
# @exports: DanceMotionClip, DanceMotionPlayer, procedural_gait_angles

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Dict, Optional
import numpy as np

from src.core.paths import get_paths


@dataclass
class DanceMotionClip:
    """Interpolatable 29-DOF full-body motion sequence."""

    fps: float
    root_z: np.ndarray        # (F,)
    joint_angles: np.ndarray  # (F, 29)
    frame_offset: int = 0
    window_frames: int = 0

    @property
    def duration(self) -> float:
        return len(self.joint_angles) / max(1.0, self.fps)

    def sample_at(self, local_t: float) -> tuple[float, np.ndarray]:
        n = len(self.joint_angles)
        if n == 0:
            return (0.77, np.zeros(29, dtype=np.float32))
        span = self.window_frames if 2 <= self.window_frames <= n else n
        base = self.frame_offset % n
        idx_f = base + ((local_t * self.fps) % span)
        i0 = int(math.floor(idx_f)) % n
        i1 = (i0 + 1) % n
        alpha = idx_f - math.floor(idx_f)
        z = float(self.root_z[i0] * (1.0 - alpha) + self.root_z[i1] * alpha)
        q = self.joint_angles[i0] * (1.0 - alpha) + self.joint_angles[i1] * alpha
        return (z, q.astype(np.float32))


def procedural_gait_angles(time_s: float, speed_mps: float = 0.0) -> tuple[float, np.ndarray]:
    """Synthesize natural bipedal walking leg + counter-arm swing joints from speed."""
    q = np.zeros(29, dtype=np.float32)
    if speed_mps < 0.03:
        q[0], q[3], q[4] = -0.10, 0.22, -0.12
        q[6], q[9], q[10] = -0.10, 0.22, -0.12
        q[18], q[25] = 0.35, 0.35
        return (0.77, q)
    amp = min(0.45, 0.18 + speed_mps * 0.25)
    s = math.sin(time_s * 7.0)
    q[0], q[3], q[4] = -0.15 + amp * s, 0.28 + max(0.0, -s) * 0.35, -0.14 - amp * 0.5 * s
    q[6], q[9], q[10] = -0.15 - amp * s, 0.28 + max(0.0, s) * 0.35, -0.14 + amp * 0.5 * s
    q[15], q[18] = -amp * 0.8 * s, 0.45 + 0.1 * abs(s)
    q[22], q[25] = amp * 0.8 * s, 0.45 + 0.1 * abs(s)
    return (0.76 - 0.02 * abs(s), q)


def _lim_angle(v1: np.ndarray, v2: np.ndarray) -> float:
    n1, n2 = float(np.linalg.norm(v1)), float(np.linalg.norm(v2))
    if n1 < 1e-5 or n2 < 1e-5:
        return 0.0
    return float(math.acos(max(-1.0, min(1.0, float(np.dot(v1, v2) / (n1 * n2))))))


def _positions21_to_clip(pos: np.ndarray, fps: float) -> DanceMotionClip:
    """Convert UniUni (F, 21, 3) [X_lat, Y_fwd, Z_up] skeleton keypoints to 29-DOF G1 URDF joint angles."""
    n = len(pos)
    q_all = np.zeros((n, 29), dtype=np.float32)
    rz = np.clip(pos[:, 0, 2].astype(np.float32), 0.52, 0.92)
    for i in range(n):
        f = pos[i]
        # Convert NPZ axes (vx=right/left, vy=forward, vz=up) -> URDF torso axes (fwd=vy, left=-vx, up=vz)
        spine = f[2] - f[0]
        q_all[i, 12] = float(np.clip(math.atan2(float(-spine[0]), max(0.15, float(spine[2]))) * 0.7, -0.5, 0.5))
        q_all[i, 13] = float(np.clip(-math.atan2(float(-spine[0]), max(0.2, float(spine[2]))) * 0.4, -0.35, 0.35))
        q_all[i, 14] = float(np.clip(math.atan2(float(spine[1]), max(0.2, float(spine[2]))), -0.35, 0.5))

        # Left arm (5 shoulder -> 6 elbow -> 7 wrist) & Right arm (9 -> 10 -> 11)
        lu, lf = f[6] - f[5], f[7] - f[6]
        ru, rf = f[10] - f[9], f[11] - f[10]
        # Full arm vector gives clear forward (+Y_npz) & upward (+Z_npz) reach even when elbow colinear
        la, ra = f[7] - f[5], f[11] - f[9]
        q_all[i, 15] = float(np.clip(-math.atan2(float(la[1]), max(0.05, -float(la[2]) + 0.10)), -2.6, 1.5))
        q_all[i, 16] = float(np.clip(math.atan2(float(-la[0]), max(0.06, abs(float(la[2])) + 0.08)) + 0.12, -0.2, 2.2))
        q_all[i, 18] = float(np.clip(0.35 + _lim_angle(lu, lf) * 1.15, 0.15, 2.0))

        q_all[i, 22] = float(np.clip(-math.atan2(float(ra[1]), max(0.05, -float(ra[2]) + 0.10)), -2.6, 1.5))
        q_all[i, 23] = float(np.clip(-math.atan2(float(ra[0]), max(0.06, abs(float(ra[2])) + 0.08)) - 0.12, -2.2, 0.2))
        q_all[i, 25] = float(np.clip(0.35 + _lim_angle(ru, rf) * 1.15, 0.15, 2.0))

        # Left leg (13 hip -> 14 knee -> 15 ankle) & Right leg (17 -> 18 -> 19)
        lt, ls = f[14] - f[13], f[15] - f[14]
        rt, rs = f[18] - f[17], f[19] - f[18]
        ll_full, rl_full = f[15] - f[13], f[19] - f[17]
        lk, rk = _lim_angle(lt, ls), _lim_angle(rt, rs)
        q_all[i, 0] = float(np.clip(-math.atan2(float(ll_full[1]), max(0.08, -float(ll_full[2]))) - 0.55 * lk, -1.6, 1.2))
        q_all[i, 1] = float(np.clip(math.atan2(float(-ll_full[0]), max(0.1, -float(ll_full[2]))), -0.45, 0.55))
        q_all[i, 3] = float(np.clip(lk * 1.35 + 0.12, 0.05, 2.0))
        q_all[i, 4] = float(np.clip(-0.6 * lk, -0.8, 0.6))

        q_all[i, 6] = float(np.clip(-math.atan2(float(rl_full[1]), max(0.08, -float(rl_full[2]))) - 0.55 * rk, -1.6, 1.2))
        q_all[i, 7] = float(np.clip(-math.atan2(float(rl_full[0]), max(0.1, -float(rl_full[2]))), -0.55, 0.45))
        q_all[i, 9] = float(np.clip(rk * 1.35 + 0.12, 0.05, 2.0))
        q_all[i, 10] = float(np.clip(-0.6 * rk, -0.8, 0.6))
    return DanceMotionClip(fps=fps, root_z=rz, joint_angles=q_all)


class DanceMotionPlayer:
    """Caches CSV/NPZ full-body motions and evaluates distinct per-action 29-DOF poses."""

    def __init__(self) -> None:
        self._clips: Dict[str, DanceMotionClip] = {}
        self._default_clip: Optional[DanceMotionClip] = None

    def get_clip_for_action(
        self, file_path: str, lrmp_code: str = "", action_no: int = 0
    ) -> DanceMotionClip:
        code = lrmp_code.strip().upper()
        if code in ("STAND", "GAIT", "PASSIVE", "STOP"):
            return self._basic_directive_clip(code)
        base_clip = self.get_clip(file_path)
        if (not file_path or "g1_dance.csv" in file_path.lower()) and len(base_clip.joint_angles) >= 900:
            off = ((action_no % 5) * 320) % len(base_clip.joint_angles)
            return DanceMotionClip(
                fps=base_clip.fps,
                root_z=base_clip.root_z,
                joint_angles=base_clip.joint_angles,
                frame_offset=off,
                window_frames=400,
            )
        return base_clip

    def get_clip(self, file_path: str) -> DanceMotionClip:
        if file_path and file_path in self._clips:
            return self._clips[file_path]
        if file_path:
            raw_p = Path(file_path)
            candidates = [raw_p] if raw_p.is_absolute() else [
                get_paths().root_dir / file_path,
                get_paths().preview_dir / raw_p.name,
                get_paths().motions_dir / raw_p.name,
            ]
            for resolved in candidates:
                if resolved.exists():
                    clip = self._load_file(resolved)
                    if clip is not None:
                        self._clips[file_path] = clip
                        return clip
        if self._default_clip is None:
            csv_path = get_paths().g1_dance_csv
            self._default_clip = self._load_file(csv_path) or self._fallback_wave_clip()
        return self._default_clip

    def _load_file(self, path: Path) -> Optional[DanceMotionClip]:
        try:
            if path.suffix.lower() == ".csv":
                data = np.loadtxt(str(path), delimiter=",", dtype=np.float32)
                if data.ndim == 2 and data.shape[1] >= 36:
                    return DanceMotionClip(fps=50.0, root_z=data[:, 2], joint_angles=data[:, 7:36])
            elif path.suffix.lower() == ".npz":
                npz = np.load(str(path), allow_pickle=True)
                fps = float(npz["fps"].item()) if "fps" in npz and hasattr(npz["fps"], "item") else 50.0
                if "joint_pos" in npz:
                    jp = np.asarray(npz["joint_pos"], dtype=np.float32)
                    rz = np.asarray(npz["root_pos"][:, 2], dtype=np.float32) if "root_pos" in npz else np.full(len(jp), 0.77, dtype=np.float32)
                    padded = np.zeros((len(jp), 29), dtype=np.float32)
                    cols = min(29, jp.shape[1])
                    padded[:, :cols] = jp[:, :cols]
                    return DanceMotionClip(fps=fps, root_z=rz, joint_angles=padded)
                for key in ("positions", "pos", "joints", "keypoints", "body_pos_w"):
                    if key in npz:
                        pts = np.asarray(npz[key], dtype=np.float32)
                        if pts.ndim == 3 and pts.shape[1] >= 20 and pts.shape[2] == 3:
                            return _positions21_to_clip(pts[:, :21, :], fps)
        except Exception:
            return None
        return None

    @staticmethod
    def _basic_directive_clip(code: str) -> DanceMotionClip:
        n = 120
        q = np.zeros((n, 29), dtype=np.float32)
        z = np.full(n, 0.77, dtype=np.float32)
        if code == "GAIT":
            for i in range(n):
                zi, qi = procedural_gait_angles(i / 50.0, 0.8)
                z[i], q[i] = zi, qi
        elif code == "PASSIVE":
            z[:] = 0.68
            q[:, 0], q[:, 3], q[:, 4] = -0.35, 0.72, -0.36
            q[:, 6], q[:, 9], q[:, 10] = -0.35, 0.72, -0.36
        else:
            for i in range(n):
                _, qi = procedural_gait_angles(0.0, 0.0)
                q[i] = qi
        return DanceMotionClip(fps=50.0, root_z=z, joint_angles=q)

    @staticmethod
    def _fallback_wave_clip() -> DanceMotionClip:
        n = 200
        q = np.zeros((n, 29), dtype=np.float32)
        for i in range(n):
            p = 2.0 * math.pi * i / n
            q[i, 12] = 0.25 * math.sin(p)
            q[i, 15] = -0.6 + 0.4 * math.sin(p * 2.0)
            q[i, 22] = -0.6 - 0.4 * math.sin(p * 2.0)
        return DanceMotionClip(fps=50.0, root_z=np.full(n, 0.77, dtype=np.float32), joint_angles=q)
