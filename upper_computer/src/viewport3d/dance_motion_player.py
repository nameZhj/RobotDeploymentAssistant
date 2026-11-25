# @file: src/viewport3d/dance_motion_player.py
# @brief: Loads 21-joint/29-DOF NPZ dances, 36-col G1_dance.csv mocap, and grounded g1.py walking gaits.
# @exports: DanceMotionClip, DanceMotionPlayer, procedural_gait_angles

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Dict, Optional
import numpy as np

from src.core.paths import get_paths
from src.viewport3d.g1_kinematics_chain import get_g1_kinematics


@dataclass
class DanceMotionClip:
    """Interpolatable 29-DOF full-body motion sequence with optional pelvis orientation."""

    fps: float
    root_z: np.ndarray        # (F,)
    joint_angles: np.ndarray  # (F, 29)
    frame_offset: int = 0
    window_frames: int = 0
    root_quat: Optional[np.ndarray] = None  # (F, 4) xyzw

    @property
    def duration(self) -> float:
        return len(self.joint_angles) / max(1.0, self.fps)

    def sample_pose_at(self, local_t: float) -> tuple[float, np.ndarray, Optional[np.ndarray]]:
        """Sample interpolated (root_z, joint_angles_29, optional root_quat_xyzw) at local_t seconds."""
        n = len(self.joint_angles)
        if n == 0:
            kin = get_g1_kinematics()
            return (kin.default_root_z, kin.default_joint_angles.copy(), None)
        span = self.window_frames if 2 <= self.window_frames <= n else n
        base = self.frame_offset % n
        idx_f = base + ((max(0.0, float(local_t)) * self.fps) % span)
        i0 = int(math.floor(idx_f)) % n
        i1 = (i0 + 1) % n
        alpha = idx_f - math.floor(idx_f)
        z = float(self.root_z[i0] * (1.0 - alpha) + self.root_z[i1] * alpha)
        q = (self.joint_angles[i0] * (1.0 - alpha) + self.joint_angles[i1] * alpha).astype(np.float32)
        quat = None
        if self.root_quat is not None and len(self.root_quat) == n:
            q0 = self.root_quat[i0]
            q1 = self.root_quat[i1] if float(np.dot(self.root_quat[i0], self.root_quat[i1])) >= 0.0 else -self.root_quat[i1]
            qm = (q0 * (1.0 - alpha) + q1 * alpha).astype(np.float32)
            norm = float(np.linalg.norm(qm))
            quat = (qm / norm) if norm > 1e-6 else np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)
        return (z, q, quat)

    def sample_at(self, local_t: float) -> tuple[float, np.ndarray]:
        z, q, _ = self.sample_pose_at(local_t)
        return (z, q)


def procedural_gait_angles(time_s: float, speed_mps: float = 0.0) -> tuple[float, np.ndarray]:
    """Synthesize grounded bipedal standing (from g1.py init_state) and smooth walking gait."""
    kin = get_g1_kinematics()
    q = kin.default_joint_angles.copy()
    if speed_mps < 0.03:
        return (kin.ground_root_z(kin.default_root_z, q), q)

    blend = min(1.0, (float(speed_mps) - 0.03) / 0.15)
    omega = 5.5 + min(3.5, float(speed_mps) * 2.5)
    phase = float(time_s) * omega
    s = math.sin(phase)
    c = math.cos(phase)
    amp = blend * min(0.42, 0.16 + float(speed_mps) * 0.24)

    # Hip pitch: negative rotates leg forward (+X) around URDF +Y left axis
    q[0] -= amp * 0.95 * s
    q[6] += amp * 0.95 * s
    q[1] += blend * 0.04 * c
    q[7] -= blend * 0.04 * c
    # Swing knee flexion & compensating ankle pitch
    q[3] += blend * 0.36 * max(0.0, s) - blend * 0.12 * max(0.0, -s)
    q[9] += blend * 0.36 * max(0.0, -s) - blend * 0.12 * max(0.0, s)
    q[4] -= amp * 0.40 * s
    q[10] += amp * 0.40 * s
    # Counter-rotating torso & opposite arm swing
    q[12] += blend * 0.06 * s
    q[15] += amp * 0.85 * s
    q[22] -= amp * 0.85 * s
    q[18] += blend * 0.14 * abs(s)
    q[25] += blend * 0.14 * abs(s)

    q = kin.clamp_joint_angles(q)
    rz = kin.ground_root_z(kin.default_root_z, q)
    return (rz, q)


def _lim_angle(v1: np.ndarray, v2: np.ndarray) -> float:
    n1, n2 = float(np.linalg.norm(v1)), float(np.linalg.norm(v2))
    return 0.0 if (n1 < 1e-5 or n2 < 1e-5) else float(math.acos(max(-1.0, min(1.0, float(np.dot(v1, v2) / (n1 * n2))))))


def _smooth_sequence(arr: np.ndarray) -> np.ndarray:
    if len(arr) < 3:
        return arr
    padded = np.pad(arr, ((1, 1), (0, 0)), mode="edge")
    return (0.25 * padded[:-2] + 0.50 * padded[1:-1] + 0.25 * padded[2:]).astype(np.float32)


def _positions21_to_clip(pos: np.ndarray, fps: float) -> DanceMotionClip:
    """Retarget (F, 21, 3) [X_lat, Y_fwd, Z_up] skeleton keypoints to clamped, grounded 29-DOF poses."""
    kin = get_g1_kinematics()
    n = len(pos)
    q_all = np.tile(kin.default_joint_angles, (n, 1)).astype(np.float32)
    for i in range(n):
        f = pos[i]
        spine = f[2] - f[0]
        q_all[i, 12] = math.atan2(float(-spine[0]), max(0.15, float(spine[2]))) * 0.65
        q_all[i, 13] = -math.atan2(float(-spine[0]), max(0.20, float(spine[2]))) * 0.35
        q_all[i, 14] = math.atan2(float(spine[1]), max(0.20, float(spine[2])))
        lu, lf, la = f[6] - f[5], f[7] - f[6], f[7] - f[5]
        ru, rf, ra = f[10] - f[9], f[11] - f[10], f[11] - f[9]
        q_all[i, 15] = -math.atan2(float(la[1]), max(0.05, -float(la[2]) + 0.10))
        q_all[i, 16] = math.atan2(float(-la[0]), max(0.06, abs(float(la[2])) + 0.08)) + 0.12
        q_all[i, 18] = 0.35 + _lim_angle(lu, lf) * 1.15
        q_all[i, 22] = -math.atan2(float(ra[1]), max(0.05, -float(ra[2]) + 0.10))
        q_all[i, 23] = -math.atan2(float(ra[0]), max(0.06, abs(float(ra[2])) + 0.08)) - 0.12
        q_all[i, 25] = 0.35 + _lim_angle(ru, rf) * 1.15
        lt, ls, ll = f[14] - f[13], f[15] - f[14], f[15] - f[13]
        rt, rs, rl = f[18] - f[17], f[19] - f[18], f[19] - f[17]
        lk, rk = _lim_angle(lt, ls), _lim_angle(rt, rs)
        q_all[i, 0] = -math.atan2(float(ll[1]), max(0.08, -float(ll[2]))) - 0.45 * lk
        q_all[i, 1] = math.atan2(float(-ll[0]), max(0.10, -float(ll[2]))) * 0.85
        q_all[i, 3] = max(0.12, lk * 1.25 + 0.18)
        q_all[i, 4] = -0.55 * q_all[i, 3]
        q_all[i, 6] = -math.atan2(float(rl[1]), max(0.08, -float(rl[2]))) - 0.45 * rk
        q_all[i, 7] = -math.atan2(float(rl[0]), max(0.10, -float(rl[2]))) * 0.85
        q_all[i, 9] = max(0.12, rk * 1.25 + 0.18)
        q_all[i, 10] = -0.55 * q_all[i, 9]
    q_all = _smooth_sequence(q_all)
    for i in range(n):
        q_all[i] = kin.clamp_joint_angles(q_all[i])
    foot_z = np.min(pos[:, [15, 16, 19, 20], 2], axis=1)
    base_pelvis_z = np.clip(pos[:, 0, 2].astype(np.float32), 0.56, 0.90)
    rz = np.asarray([kin.ground_root_z(float(base_pelvis_z[i]), q_all[i]) + max(0.0, float(foot_z[i]) - 0.08) for i in range(n)], dtype=np.float32)
    return DanceMotionClip(fps=fps, root_z=rz, joint_angles=q_all)


class DanceMotionPlayer:
    """Caches CSV/NPZ full-body motions and evaluates grounded 29-DOF poses."""

    def __init__(self) -> None:
        self._clips: Dict[str, DanceMotionClip] = {}
        self._default_clip: Optional[DanceMotionClip] = None

    def resolve_dance_file(self, alias_or_path: str) -> str:
        """Resolve a dance alias (e.g. 'TIKTOK') or path against preview/*.npz and assets/motions/*."""
        raw = str(alias_or_path or "").strip()
        if not raw:
            return ""
        p = Path(raw)
        paths = get_paths()
        for cand in ([p] if p.is_absolute() else [paths.root_dir / p, paths.preview_dir / p.name, paths.motions_dir / p.name]):
            if cand.exists() and cand.is_file():
                return str(cand)
        key = p.stem.upper()
        candidates = []
        for d in (paths.preview_dir, paths.motions_dir):
            if d.exists():
                candidates.extend(sorted(f for f in d.iterdir() if f.suffix.lower() in (".npz", ".csv")))
        for cand in candidates:
            if cand.stem.upper() == key:
                return str(cand)
        for cand in candidates:
            st = cand.stem.upper()
            if key in st or st in key:
                return str(cand)
        return ""

    def get_clip_for_action(
        self, file_path: str, lrmp_code: str = "", action_no: int = 0
    ) -> DanceMotionClip:
        code = lrmp_code.strip().upper()
        if code in ("STAND", "GAIT", "PASSIVE", "STOP"):
            return self._basic_directive_clip(code)
        resolved = self.resolve_dance_file(file_path) or file_path
        base_clip = self.get_clip(resolved)
        if (not file_path or "g1_dance.csv" in str(file_path).lower()) and len(base_clip.joint_angles) >= 900:
            off = ((action_no % 5) * 320) % len(base_clip.joint_angles)
            return DanceMotionClip(
                fps=base_clip.fps, root_z=base_clip.root_z, joint_angles=base_clip.joint_angles,
                frame_offset=off, window_frames=400, root_quat=base_clip.root_quat,
            )
        return base_clip

    def get_clip(self, file_path: str) -> DanceMotionClip:
        key = self.resolve_dance_file(file_path) or file_path
        if key and key in self._clips:
            return self._clips[key]
        if key:
            p = Path(key)
            if p.exists():
                clip = self._load_file(p)
                if clip is not None:
                    self._clips[key] = clip
                    if file_path and file_path != key:
                        self._clips[file_path] = clip
                    return clip
        if self._default_clip is None:
            self._default_clip = self._load_file(get_paths().g1_dance_csv) or self._fallback_wave_clip()
        return self._default_clip

    def _load_file(self, path: Path) -> Optional[DanceMotionClip]:
        kin = get_g1_kinematics()
        try:
            if path.suffix.lower() == ".csv":
                data = np.loadtxt(str(path), delimiter=",", dtype=np.float32)
                if data.ndim == 2 and data.shape[1] >= 36:
                    return DanceMotionClip(fps=50.0, root_z=data[:, 2], joint_angles=data[:, 7:36], root_quat=data[:, 3:7])
            elif path.suffix.lower() == ".npz":
                npz = np.load(str(path), allow_pickle=True)
                fps = float(npz["fps"].item()) if "fps" in npz and hasattr(npz["fps"], "item") else 50.0
                for jkey in ("joint_pos", "dof_pos", "q"):
                    if jkey in npz:
                        return self._load_joint_npz(npz, jkey, fps, kin)
                for pkey in ("positions", "pos", "joints", "keypoints", "body_pos_w"):
                    if pkey in npz:
                        pts = np.asarray(npz[pkey], dtype=np.float32)
                        if pts.ndim == 3 and pts.shape[1] >= 20 and pts.shape[2] == 3:
                            return _positions21_to_clip(pts[:, :21, :], fps)
        except Exception:
            return None
        return None

    @staticmethod
    def _load_joint_npz(npz, jkey: str, fps: float, kin) -> DanceMotionClip:
        jp = np.asarray(npz[jkey], dtype=np.float32)
        if jp.ndim == 1:
            jp = jp.reshape(1, -1)
        padded = np.zeros((len(jp), 29), dtype=np.float32)
        if "joint_names" in npz:
            names = [str(s) for s in np.asarray(npz["joint_names"]).tolist()]
            src_map = {name: i for i, name in enumerate(names)}
            for dst_i, jn in enumerate(kin.revolute_joint_names):
                if jn in src_map and src_map[jn] < jp.shape[1]:
                    padded[:, dst_i] = jp[:, src_map[jn]]
        else:
            cols = min(29, jp.shape[1])
            padded[:, :cols] = jp[:, :cols]
        if "root_pos" in npz:
            rz = np.asarray(npz["root_pos"][:, 2], dtype=np.float32)
        else:
            rz = np.asarray([kin.ground_root_z(kin.default_root_z, padded[i]) for i in range(len(padded))], dtype=np.float32)
        rquat = None
        for qk in ("root_quat", "root_rot"):
            if qk in npz and np.asarray(npz[qk]).ndim == 2 and np.asarray(npz[qk]).shape[1] >= 4:
                rquat = np.asarray(npz[qk], dtype=np.float32)[:, :4]
                break
        return DanceMotionClip(fps=fps, root_z=rz, joint_angles=padded, root_quat=rquat)

    @staticmethod
    def _basic_directive_clip(code: str) -> DanceMotionClip:
        kin = get_g1_kinematics()
        n = 120
        q = np.tile(kin.default_joint_angles, (n, 1)).astype(np.float32)
        z = np.full(n, kin.default_root_z, dtype=np.float32)
        if code == "GAIT":
            for i in range(n):
                z[i], q[i] = procedural_gait_angles(i / 50.0, 0.75)
        elif code == "PASSIVE":
            q[:, 0] = -0.42
            q[:, 3] = 0.88
            q[:, 4] = -0.46
            q[:, 6] = -0.42
            q[:, 9] = 0.88
            q[:, 10] = -0.46
            for i in range(n):
                q[i] = kin.clamp_joint_angles(q[i])
            z[:] = kin.ground_root_z(0.68, q[0])
        else:
            z[:] = kin.ground_root_z(kin.default_root_z, q[0])
        return DanceMotionClip(fps=50.0, root_z=z, joint_angles=q)

    @staticmethod
    def _fallback_wave_clip() -> DanceMotionClip:
        kin = get_g1_kinematics()
        n = 200
        q = np.tile(kin.default_joint_angles, (n, 1)).astype(np.float32)
        for i in range(n):
            p = 2.0 * math.pi * i / n
            q[i, 12] = 0.22 * math.sin(p)
            q[i, 15] = -0.55 + 0.45 * math.sin(p * 2.0)
            q[i, 22] = -0.55 - 0.45 * math.sin(p * 2.0)
        rz = np.full(n, kin.ground_root_z(kin.default_root_z, q[0]), dtype=np.float32)
        return DanceMotionClip(fps=50.0, root_z=rz, joint_angles=q)
