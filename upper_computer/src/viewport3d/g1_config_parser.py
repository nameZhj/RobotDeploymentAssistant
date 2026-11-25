# @file: src/viewport3d/g1_config_parser.py
# @brief: URDF math primitives, joint/visual dataclasses, and AST-based g1.py init_state parser (no isaaclab dependency).
# @exports: UrdfJoint, UrdfVisualLink, rpy_matrix, quat_xyzw_to_mat3, rodrigues_4x4, origin_to_mat, parse_g1_py_cfg

from __future__ import annotations

import ast
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
import xml.etree.ElementTree as ET
import numpy as np


@dataclass(frozen=True)
class UrdfJoint:
    """Single URDF joint definition including joint angle limits."""

    name: str
    joint_type: str
    parent: str
    child: str
    origin_xyz: np.ndarray
    origin_mat: np.ndarray
    axis: np.ndarray
    lower: float = -3.14159
    upper: float = 3.14159


@dataclass(frozen=True)
class UrdfVisualLink:
    """Visual mesh attachment metadata relative to its parent link frame."""

    link_name: str
    mesh_rel_path: str
    visual_mat: np.ndarray
    material_name: str = ""
    material_rgba: Optional[Tuple[float, float, float, float]] = None


def rpy_matrix(r: float, p: float, y: float) -> np.ndarray:
    """Construct a 4x4 homogeneous rotation matrix from roll, pitch, yaw (ZYX extrinsic / XYZ intrinsic)."""
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    mat = np.eye(4, dtype=np.float32)
    mat[0, 0], mat[0, 1], mat[0, 2] = cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr
    mat[1, 0], mat[1, 1], mat[1, 2] = sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr
    mat[2, 0], mat[2, 1], mat[2, 2] = -sp, cp * sr, cp * cr
    return mat


def quat_xyzw_to_mat3(quat_xyzw: Sequence[float]) -> np.ndarray:
    """Convert normalized [qx, qy, qz, qw] quaternion into 3x3 rotation matrix."""
    qx, qy, qz, qw = [float(v) for v in quat_xyzw[:4]]
    n = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
    if n < 1e-8:
        return np.eye(3, dtype=np.float32)
    qx, qy, qz, qw = qx / n, qy / n, qz / n, qw / n
    xx, yy, zz = qx * qx, qy * qy, qz * qz
    xy, xz, yz = qx * qy, qx * qz, qy * qz
    wx, wy, wz = qw * qx, qw * qy, qw * qz
    return np.asarray(
        [
            [1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy)],
            [2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)],
            [2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy)],
        ],
        dtype=np.float32,
    )


def rodrigues_4x4(axis: np.ndarray, angle: float) -> np.ndarray:
    """Compute 4x4 pure rotation matrix around unit axis by angle (rad)."""
    mat = np.eye(4, dtype=np.float32)
    if abs(angle) < 1e-7:
        return mat
    ax = axis / max(1e-8, float(np.linalg.norm(axis)))
    x, y, z = float(ax[0]), float(ax[1]), float(ax[2])
    c, s = math.cos(angle), math.sin(angle)
    omc = 1.0 - c
    mat[0, 0], mat[0, 1], mat[0, 2] = c + x * x * omc, x * y * omc - z * s, x * z * omc + y * s
    mat[1, 0], mat[1, 1], mat[1, 2] = y * x * omc + z * s, c + y * y * omc, y * z * omc - x * s
    mat[2, 0], mat[2, 1], mat[2, 2] = z * x * omc - y * s, z * y * omc + x * s, c + z * z * omc
    return mat


def origin_to_mat(elem: Optional[ET.Element]) -> np.ndarray:
    """Convert URDF <origin xyz rpy/> element to 4x4 homogeneous transform."""
    if elem is None:
        return np.eye(4, dtype=np.float32)
    xyz = [float(v) for v in elem.attrib.get("xyz", "0 0 0").split()]
    rpy = [float(v) for v in elem.attrib.get("rpy", "0 0 0").split()]
    mat = rpy_matrix(rpy[0], rpy[1], rpy[2])
    mat[0, 3], mat[1, 3], mat[2, 3] = xyz[0], xyz[1], xyz[2]
    return mat


def parse_g1_py_cfg(g1_py_path: Path) -> Tuple[float, Dict[str, float], List[str]]:
    """Safely extract init_state (pos, joint_pos) and joint_sdk_names from g1.py via AST without isaaclab."""
    default_z = 0.76
    joint_pos_rules: Dict[str, float] = {
        ".*_hip_pitch_joint": -0.312, ".*_knee_joint": 0.669, ".*_ankle_pitch_joint": -0.363,
        ".*_elbow_joint": 0.6, "left_shoulder_roll_joint": 0.2, "left_shoulder_pitch_joint": 0.2,
        "right_shoulder_roll_joint": -0.2, "right_shoulder_pitch_joint": 0.2,
    }
    sdk_names: List[str] = []
    if not g1_py_path.exists():
        return default_z, joint_pos_rules, sdk_names
    try:
        tree = ast.parse(g1_py_path.read_text(encoding="utf-8"))
        candidates = {
            node.targets[0].id: node.value
            for node in tree.body
            if isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Call)
        }
        target_call = next((candidates[n] for n in ("G1_M15_UA", "G1_M15", "G1_CFG") if n in candidates), None)
        if target_call is None:
            return default_z, joint_pos_rules, sdk_names
        for kw in target_call.keywords:
            if kw.arg == "init_state" and isinstance(kw.value, ast.Call):
                for ikw in kw.value.keywords:
                    if ikw.arg == "pos":
                        pos = ast.literal_eval(ikw.value)
                        if isinstance(pos, (list, tuple)) and len(pos) >= 3:
                            default_z = float(pos[2])
                    elif ikw.arg == "joint_pos":
                        jp = ast.literal_eval(ikw.value)
                        if isinstance(jp, dict):
                            joint_pos_rules = {str(k): float(v) for k, v in jp.items()}
            elif kw.arg == "joint_sdk_names":
                jn = ast.literal_eval(kw.value)
                if isinstance(jn, (list, tuple)):
                    sdk_names = [str(s) for s in jn]
    except Exception:
        pass
    return default_z, joint_pos_rules, sdk_names
