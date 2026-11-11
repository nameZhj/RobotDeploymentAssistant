"""
@file: src/domain/kinematics/urdf_fk_solver.py
@brief: G1 机器人 URDF 解析、双模几何加载与 3D 齐次变换正向运动学求解器
@exports: UrdfAvatarModel, ForwardKinematicsSolver, rpy_to_rot_matrix, axis_angle_to_rot_matrix, solve_full_body_fk
"""
import math
import os
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from src.domain.kinematics.g1_stl_mesh_cache import G1StlMeshCache


def rpy_to_rot_matrix(r: float, p: float, y: float) -> np.ndarray:
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    rx = np.array([[1.0, 0.0, 0.0], [0.0, cr, -sr], [0.0, sr, cr]], dtype=np.float32)
    ry = np.array([[cp, 0.0, sp], [0.0, 1.0, 0.0], [-sp, 0.0, cp]], dtype=np.float32)
    rz = np.array([[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
    return rz @ ry @ rx


def axis_angle_to_rot_matrix(axis: np.ndarray, angle: float) -> np.ndarray:
    norm = float(np.linalg.norm(axis))
    if norm < 1e-6:
        return np.eye(3, dtype=np.float32)
    u = (axis / norm).astype(np.float32)
    c, s = math.cos(angle), math.sin(angle)
    k = np.array([[0.0, -u[2], u[1]], [u[2], 0.0, -u[0]], [-u[1], u[0], 0.0]], dtype=np.float32)
    return (np.eye(3, dtype=np.float32) * c + (1.0 - c) * np.outer(u, u) + s * k).astype(np.float32)


class UrdfAvatarModel:
    """提供核显 Eco 简模几何体与独显 Pro 级网格缓存加载"""

    @classmethod
    def load_eco_geometries(cls) -> Dict[str, Dict[str, Any]]:
        geoms: Dict[str, Dict[str, Any]] = {}
        links = ["pelvis", "torso_link", "head_link", "left_hip_pitch_link", "left_knee_link",
                 "left_ankle_roll_link", "right_hip_pitch_link", "right_knee_link",
                 "right_ankle_roll_link", "left_shoulder_pitch_link", "left_elbow_link",
                 "right_shoulder_pitch_link", "right_elbow_link"]
        for name in links:
            shape = "prism" if "torso" in name else ("sphere" if "head" in name else "cylinder")
            geoms[name] = {"shape": shape, "dimensions": (0.20, 0.25, 0.40) if "torso" in name else (0.08, 0.08, 0.30),
                           "color_rgba": (0.2, 0.6, 0.9, 1.0) if "head" in name else (0.8, 0.8, 0.8, 1.0)}
        return geoms

    @classmethod
    def load_pro_meshes(cls, cache_path: Optional[str] = None) -> Dict[str, Any]:
        return G1StlMeshCache.load_all_meshes(lod_mode="PRO", cache_dir=cache_path)


class ForwardKinematicsSolver:
    """基于罗德里格斯旋转公式与树状遍历的三维齐次矩阵求解器"""

    def __init__(self, urdf_path: Optional[str] = None) -> None:
        self.urdf_path = urdf_path or self._find_urdf()
        self.root_link = "pelvis"
        self.links: List[str] = []
        self.joint_origins: Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray, str, str]] = {}
        self.children_map: Dict[str, List[Tuple[str, str, np.ndarray, np.ndarray, np.ndarray]]] = {}
        self._parse_urdf()

    def _find_urdf(self) -> str:
        candidates = [
            os.path.join("assets", "models", "g1_description", "g1_description", "g1_23dof.urdf"),
            os.path.join("assets", "models", "g1_description", "g1_description", "g1_29dof.urdf")
        ]
        for c in candidates:
            if os.path.exists(c): return c
        return candidates[0]

    def _parse_urdf(self) -> None:
        if not os.path.exists(self.urdf_path):
            self.links = ["pelvis", "torso_link"]; return
        tree = ET.parse(self.urdf_path)
        root = tree.getroot()
        for link in root.findall("link"):
            n = link.get("name")
            if n: self.links.append(n)
        for joint in root.findall("joint"):
            j_name = joint.get("name", "")
            p_el, c_el = joint.find("parent"), joint.find("child")
            if p_el is None or c_el is None: continue
            parent, child = p_el.get("link", ""), c_el.get("link", "")
            orig = joint.find("origin")
            xyz = np.fromstring(orig.get("xyz", "0 0 0"), sep=" ") if orig is not None else np.zeros(3)
            rpy = np.fromstring(orig.get("rpy", "0 0 0"), sep=" ") if orig is not None else np.zeros(3)
            ax_el = joint.find("axis")
            axis = np.fromstring(ax_el.get("xyz", "0 0 1"), sep=" ") if ax_el is not None else np.array([0., 0., 1.])
            xyz_f, rpy_f, ax_f = xyz.astype(np.float32), rpy.astype(np.float32), axis.astype(np.float32)
            self.joint_origins[j_name] = (xyz_f, rpy_f, ax_f, parent, child)
            self.children_map.setdefault(parent, []).append((child, j_name, xyz_f, rpy_f, ax_f))

    def compute_fk(self, world_pos: Tuple[float, float, float], yaw_rad: float, joint_angles: Dict[str, float]) -> Dict[str, np.ndarray]:
        res = self.solve_full_body_fk(world_pos, yaw_rad, joint_angles)
        return res["link_world_matrices"]

    def solve_full_body_fk(
        self, base_xyz: Tuple[float, float, float], base_yaw: float, joint_angles_dict: Dict[str, float]
    ) -> Dict[str, Any]:
        y_rad = math.radians(base_yaw) if abs(base_yaw) > 2 * math.pi else float(base_yaw)
        cy, sy = math.cos(y_rad), math.sin(y_rad)
        root_mat = np.eye(4, dtype=np.float32)
        root_mat[:3, :3] = np.array([[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
        root_mat[:3, 3] = np.array(base_xyz, dtype=np.float32)

        matrices: Dict[str, np.ndarray] = {self.root_link: root_mat}
        joint_coords: Dict[str, Tuple[float, float, float]] = {}
        queue = [self.root_link]

        while queue:
            p_link = queue.pop(0)
            p_mat = matrices[p_link]
            for child, j_name, xyz, rpy, axis in self.children_map.get(p_link, []):
                t_orig = np.eye(4, dtype=np.float32)
                t_orig[:3, :3] = rpy_to_rot_matrix(rpy[0], rpy[1], rpy[2])
                t_orig[:3, 3] = xyz
                j_world = p_mat @ t_orig
                joint_coords[j_name] = (float(j_world[0, 3]), float(j_world[1, 3]), float(j_world[2, 3]))

                q = joint_angles_dict.get(j_name, 0.0)
                t_joint = np.eye(4, dtype=np.float32)
                t_joint[:3, :3] = axis_angle_to_rot_matrix(axis, q)
                matrices[child] = j_world @ t_joint
                queue.append(child)

        return {"link_world_matrices": matrices, "joint_coords": joint_coords}


def solve_full_body_fk(base_xyz: Tuple[float, float, float], base_yaw: float, joint_angles_dict: Dict[str, float]) -> Dict[str, Any]:
    return ForwardKinematicsSolver().solve_full_body_fk(base_xyz, base_yaw, joint_angles_dict)
