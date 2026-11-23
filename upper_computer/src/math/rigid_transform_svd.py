# @file: src/math/rigid_transform_svd.py
# @brief: 2D and 3D Kabsch SVD rigid registration solvers (R, t, yaw, RMSE) for coordinate & map calibration.
# @exports: RigidCalibration2D, solve_kabsch_2d, solve_kabsch_3d, apply_rigid_2d

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Tuple
import numpy as np


@dataclass(frozen=True)
class RigidCalibration2D:
    """Result of 2D rigid point-pair alignment dst = R @ src + t."""

    rot_2x2: np.ndarray
    trans_2: np.ndarray
    yaw_rad: float
    rmse_m: float

    @property
    def yaw_deg(self) -> float:
        return math.degrees(self.yaw_rad)


def solve_kabsch_2d(src_xy: np.ndarray, dst_xy: np.ndarray) -> RigidCalibration2D:
    """Compute least-squares proper 2D rotation + translation from >= 2 corresponding pairs."""
    s = np.asarray(src_xy, dtype=np.float64).reshape(-1, 2)
    d = np.asarray(dst_xy, dtype=np.float64).reshape(-1, 2)
    if len(s) != len(d) or len(s) < 2:
        raise ValueError("Need at least 2 matching 2D point pairs for SVD calibration")

    mu_s = s.mean(axis=0)
    mu_d = d.mean(axis=0)
    cs = s - mu_s
    cd = d - mu_d
    cov = cs.T @ cd
    u, _sigma, vt = np.linalg.svd(cov)
    rot = vt.T @ u.T
    if np.linalg.det(rot) < 0:
        vt[-1, :] *= -1.0
        rot = vt.T @ u.T
    trans = mu_d - rot @ mu_s
    pred = (rot @ s.T).T + trans
    rmse = float(np.sqrt(np.mean(np.sum((pred - d) ** 2, axis=1))))
    yaw = math.atan2(float(rot[1, 0]), float(rot[0, 0]))
    return RigidCalibration2D(rot_2x2=rot, trans_2=trans, yaw_rad=yaw, rmse_m=rmse)


def solve_kabsch_3d(src_xyz: np.ndarray, dst_xyz: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float]:
    """Compute proper 3D rigid transform (R_3x3, t_3, rmse_m) from >= 3 corresponding 3D points."""
    s = np.asarray(src_xyz, dtype=np.float64).reshape(-1, 3)
    d = np.asarray(dst_xyz, dtype=np.float64).reshape(-1, 3)
    if len(s) != len(d) or len(s) < 3:
        raise ValueError("Need at least 3 matching 3D points for 3D Kabsch SVD")

    mu_s = s.mean(axis=0)
    mu_d = d.mean(axis=0)
    u, _sig, vt = np.linalg.svd((s - mu_s).T @ (d - mu_d))
    rot = vt.T @ u.T
    if np.linalg.det(rot) < 0:
        vt[-1, :] *= -1.0
        rot = vt.T @ u.T
    trans = mu_d - rot @ mu_s
    pred = (rot @ s.T).T + trans
    rmse = float(np.sqrt(np.mean(np.sum((pred - d) ** 2, axis=1))))
    return (rot, trans, rmse)


def apply_rigid_2d(pts_xy: np.ndarray, rot_2x2: np.ndarray, trans_2: np.ndarray) -> np.ndarray:
    """Apply calibrated 2D rigid transform R @ p + t to (N, 2) array."""
    pts = np.asarray(pts_xy, dtype=np.float64).reshape(-1, 2)
    return (rot_2x2 @ pts.T).T + trans_2
