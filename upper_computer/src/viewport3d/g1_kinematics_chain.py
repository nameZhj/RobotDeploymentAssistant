# @file: src/viewport3d/g1_kinematics_chain.py
# @brief: Vectorized 29-DOF URDF Forward Kinematics solver backed by backend/models/g1_29dof_rubber_hand/g1_29dof_mode_15.urdf.
# @exports: UrdfJoint, UrdfVisualLink, G1KinematicsChain, get_g1_kinematics

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
import xml.etree.ElementTree as ET
import numpy as np

from src.core.paths import get_paths


@dataclass(frozen=True)
class UrdfJoint:
    """Single URDF joint definition."""

    name: str
    joint_type: str
    parent: str
    child: str
    origin_xyz: np.ndarray
    origin_mat: np.ndarray
    axis: np.ndarray


@dataclass(frozen=True)
class UrdfVisualLink:
    """Visual mesh attachment metadata relative to its parent link frame."""

    link_name: str
    mesh_rel_path: str
    visual_mat: np.ndarray


def _rpy_matrix(r: float, p: float, y: float) -> np.ndarray:
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    mat = np.eye(4, dtype=np.float32)
    mat[0, 0] = cy * cp
    mat[0, 1] = cy * sp * sr - sy * cr
    mat[0, 2] = cy * sp * cr + sy * sr
    mat[1, 0] = sy * cp
    mat[1, 1] = sy * sp * sr + cy * cr
    mat[1, 2] = sy * sp * cr - cy * sr
    mat[2, 0] = -sp
    mat[2, 1] = cp * sr
    mat[2, 2] = cp * cr
    return mat


def _rodrigues_4x4(axis: np.ndarray, angle: float) -> np.ndarray:
    mat = np.eye(4, dtype=np.float32)
    if abs(angle) < 1e-7:
        return mat
    ax = axis / max(1e-8, float(np.linalg.norm(axis)))
    x, y, z = float(ax[0]), float(ax[1]), float(ax[2])
    c, s = math.cos(angle), math.sin(angle)
    omc = 1.0 - c
    mat[0, 0] = c + x * x * omc
    mat[0, 1] = x * y * omc - z * s
    mat[0, 2] = x * z * omc + y * s
    mat[1, 0] = y * x * omc + z * s
    mat[1, 1] = c + y * y * omc
    mat[1, 2] = y * z * omc - x * s
    mat[2, 0] = z * x * omc - y * s
    mat[2, 1] = z * y * omc + x * s
    mat[2, 2] = c + z * z * omc
    return mat


def _origin_to_mat(elem: Optional[ET.Element]) -> np.ndarray:
    if elem is None:
        return np.eye(4, dtype=np.float32)
    xyz_raw = [float(v) for v in elem.attrib.get("xyz", "0 0 0").split()]
    rpy_raw = [float(v) for v in elem.attrib.get("rpy", "0 0 0").split()]
    mat = _rpy_matrix(rpy_raw[0], rpy_raw[1], rpy_raw[2])
    mat[0, 3], mat[1, 3], mat[2, 3] = xyz_raw[0], xyz_raw[1], xyz_raw[2]
    return mat


class G1KinematicsChain:
    """Computes full-body 4x4 link transforms for Unitree G1 29-DOF URDF models."""

    def __init__(self, urdf_path: Optional[Path] = None) -> None:
        paths = get_paths()
        self.urdf_path = Path(urdf_path) if urdf_path else paths.g1_urdf_file
        self.base_dir = self.urdf_path.parent
        self.joints_by_child: Dict[str, UrdfJoint] = {}
        self.revolute_joint_names: List[str] = []
        self.visuals: List[UrdfVisualLink] = []
        self.topo_links: List[str] = []
        self._parse_urdf()

    def _parse_urdf(self) -> None:
        if not self.urdf_path.exists():
            return
        root = ET.parse(str(self.urdf_path)).getroot()
        children_map: Dict[str, List[str]] = {}
        all_children = set()
        for j in root.findall("joint"):
            j_name = j.attrib.get("name", "")
            j_type = j.attrib.get("type", "fixed")
            parent_el = j.find("parent")
            child_el = j.find("child")
            if parent_el is None or child_el is None:
                continue
            p_link = parent_el.attrib["link"]
            c_link = child_el.attrib["link"]
            o_mat = _origin_to_mat(j.find("origin"))
            ax_el = j.find("axis")
            ax = np.asarray(
                [float(v) for v in ax_el.attrib.get("xyz", "0 1 0").split()] if ax_el is not None else [0.0, 1.0, 0.0],
                dtype=np.float32,
            )
            uj = UrdfJoint(j_name, j_type, p_link, c_link, o_mat[:3, 3].copy(), o_mat, ax)
            self.joints_by_child[c_link] = uj
            children_map.setdefault(p_link, []).append(c_link)
            all_children.add(c_link)
            if j_type in ("revolute", "continuous"):
                self.revolute_joint_names.append(j_name)

        roots = [l.attrib.get("name", "") for l in root.findall("link") if l.attrib.get("name", "") not in all_children]
        queue = roots or ["pelvis"]
        visited = set()
        while queue:
            cur = queue.pop(0)
            if cur in visited:
                continue
            visited.add(cur)
            self.topo_links.append(cur)
            queue.extend(children_map.get(cur, []))

        for l in root.findall("link"):
            l_name = l.attrib.get("name", "")
            vis = l.find("visual")
            if vis is None:
                continue
            geom = vis.find("geometry")
            mesh_el = geom.find("mesh") if geom is not None else None
            if mesh_el is None:
                continue
            fn = mesh_el.attrib.get("filename", "").replace("\\", "/").lstrip("/")
            if fn:
                self.visuals.append(UrdfVisualLink(l_name, fn, _origin_to_mat(vis.find("origin"))))

    def solve_fk(
        self,
        root_x: float = 0.0,
        root_y: float = 0.0,
        root_yaw: float = 0.0,
        root_z: float = 0.77,
        joint_angles: Optional[Sequence[float]] = None,
    ) -> List[Tuple[str, np.ndarray]]:
        """Solve world 4x4 matrices for all visual STL meshes; returns [(mesh_rel_path, mat4x4)]."""
        q_map: Dict[str, float] = {}
        if joint_angles is not None:
            for j_name, val in zip(self.revolute_joint_names, joint_angles):
                q_map[j_name] = float(val)

        base_tf = _rpy_matrix(0.0, 0.0, root_yaw)
        base_tf[0, 3] = root_x
        base_tf[1, 3] = root_y
        base_tf[2, 3] = root_z

        link_tfs: Dict[str, np.ndarray] = {}
        for link in self.topo_links:
            j = self.joints_by_child.get(link)
            if j is None:
                link_tfs[link] = base_tf
                continue
            parent_tf = link_tfs.get(j.parent, base_tf)
            ang = q_map.get(j.name, 0.0) if j.joint_type in ("revolute", "continuous") else 0.0
            rot_tf = _rodrigues_4x4(j.axis, ang) if abs(ang) > 1e-6 else np.eye(4, dtype=np.float32)
            link_tfs[link] = parent_tf @ j.origin_mat @ rot_tf

        out: List[Tuple[str, np.ndarray]] = []
        for vis in self.visuals:
            lt = link_tfs.get(vis.link_name)
            if lt is not None:
                out.append((vis.mesh_rel_path, lt @ vis.visual_mat))
        return out


_CHAIN_SINGLETON: Optional[G1KinematicsChain] = None


def get_g1_kinematics() -> G1KinematicsChain:
    """Return cached G1KinematicsChain singleton parsed from backend assets."""
    global _CHAIN_SINGLETON
    if _CHAIN_SINGLETON is None:
        _CHAIN_SINGLETON = G1KinematicsChain()
    return _CHAIN_SINGLETON
