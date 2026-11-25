# @file: src/viewport3d/g1_kinematics_chain.py
# @brief: Vectorized 29-DOF URDF Forward Kinematics, joint limits, foot contact geometry, and g1.py init_state grounding.
# @exports: UrdfJoint, UrdfVisualLink, G1KinematicsChain, get_g1_kinematics

from __future__ import annotations

import math
from pathlib import Path
import re
from typing import Dict, List, Optional, Sequence, Tuple
import xml.etree.ElementTree as ET
import numpy as np

from src.core.paths import get_paths
from src.viewport3d.g1_config_parser import (
    UrdfJoint, UrdfVisualLink, origin_to_mat, parse_g1_py_cfg,
    quat_xyzw_to_mat3, rodrigues_4x4, rpy_matrix,
)


class G1KinematicsChain:
    """Computes full-body 4x4 link transforms, URDF limits, materials, and g1.py standing state."""

    def __init__(self, urdf_path: Optional[Path] = None) -> None:
        paths = get_paths()
        self.urdf_path = Path(urdf_path) if urdf_path else paths.g1_urdf_file
        self.base_dir = self.urdf_path.parent
        self.joints_by_child: Dict[str, UrdfJoint] = {}
        self.revolute_joint_names: List[str] = []
        self.visuals: List[UrdfVisualLink] = []
        self.topo_links: List[str] = []
        self.mesh_material_rgba: Dict[str, Tuple[float, float, float, float]] = {}
        self.mesh_material_name: Dict[str, str] = {}
        self.joint_limits: np.ndarray = np.tile(np.array([-3.14159, 3.14159], dtype=np.float32), (29, 1))
        self.foot_contact_points: Dict[str, List[Tuple[float, float, float]]] = {}
        self.default_root_z: float = 0.76
        self.default_joint_angles: np.ndarray = np.zeros(29, dtype=np.float32)
        self.joint_sdk_names: List[str] = []
        self._parse_urdf()
        self._load_g1_py_defaults()

    def _parse_urdf(self) -> None:
        if not self.urdf_path.exists():
            return
        root = ET.parse(str(self.urdf_path)).getroot()
        named_materials: Dict[str, Tuple[float, float, float, float]] = {}
        for m_el in root.findall("material"):
            color_el = m_el.find("color")
            if m_el.attrib.get("name") and color_el is not None:
                vals = [float(v) for v in color_el.attrib.get("rgba", "1 1 1 1").split()[:4]]
                while len(vals) < 4:
                    vals.append(1.0)
                named_materials[m_el.attrib["name"]] = (vals[0], vals[1], vals[2], vals[3])

        children_map: Dict[str, List[str]] = {}
        all_children, limits_list = set(), []
        for j in root.findall("joint"):
            j_name, j_type = j.attrib.get("name", ""), j.attrib.get("type", "fixed")
            parent_el, child_el = j.find("parent"), j.find("child")
            if parent_el is None or child_el is None:
                continue
            p_link, c_link = parent_el.attrib["link"], child_el.attrib["link"]
            o_mat = origin_to_mat(j.find("origin"))
            ax_el = j.find("axis")
            ax = np.asarray([float(v) for v in ax_el.attrib.get("xyz", "0 1 0").split()] if ax_el is not None else [0.0, 1.0, 0.0], dtype=np.float32)
            lim_el = j.find("limit")
            lo = float(lim_el.attrib.get("lower", -3.14159)) if lim_el is not None else -3.14159
            hi = float(lim_el.attrib.get("upper", 3.14159)) if lim_el is not None else 3.14159
            self.joints_by_child[c_link] = UrdfJoint(j_name, j_type, p_link, c_link, o_mat[:3, 3].copy(), o_mat, ax, lo, hi)
            children_map.setdefault(p_link, []).append(c_link)
            all_children.add(c_link)
            if j_type in ("revolute", "continuous"):
                self.revolute_joint_names.append(j_name)
                limits_list.append((lo, hi))
        if limits_list:
            self.joint_limits = np.asarray(limits_list, dtype=np.float32)

        roots = [l.attrib.get("name", "") for l in root.findall("link") if l.attrib.get("name", "") not in all_children]
        queue, visited = roots or ["pelvis"], set()
        while queue:
            cur = queue.pop(0)
            if cur in visited:
                continue
            visited.add(cur)
            self.topo_links.append(cur)
            queue.extend(children_map.get(cur, []))

        for l in root.findall("link"):
            l_name = l.attrib.get("name", "")
            for vis in l.findall("visual"):
                geom = vis.find("geometry")
                mesh_el = geom.find("mesh") if geom is not None else None
                if mesh_el is None:
                    continue
                fn = mesh_el.attrib.get("filename", "").replace("\\", "/").lstrip("/")
                if not fn:
                    continue
                mat_el = vis.find("material")
                mat_name = mat_el.attrib.get("name", "") if mat_el is not None else ""
                rgba = named_materials.get(mat_name) if mat_el is not None else None
                inline_color = mat_el.find("color") if mat_el is not None else None
                if rgba is None and inline_color is not None:
                    vals = [float(v) for v in inline_color.attrib.get("rgba", "1 1 1 1").split()[:4]]
                    rgba = (vals[0], vals[1], vals[2], vals[3])
                self.visuals.append(UrdfVisualLink(l_name, fn, origin_to_mat(vis.find("origin")), mat_name, rgba))
                if mat_name:
                    self.mesh_material_name[fn] = mat_name
                if rgba is not None:
                    self.mesh_material_rgba[fn] = rgba
            if "ankle_roll_link" in l_name:
                pts: List[Tuple[float, float, float]] = []
                for col in l.findall("collision"):
                    geom = col.find("geometry")
                    sph = geom.find("sphere") if geom is not None else None
                    if sph is not None:
                        orig = col.find("origin")
                        xyz = [float(v) for v in orig.attrib.get("xyz", "0 0 0").split()] if orig is not None else [0.0, 0.0, 0.0]
                        pts.append((xyz[0], xyz[1], xyz[2] - float(sph.attrib.get("radius", "0.005"))))
                self.foot_contact_points[l_name] = pts or [(0.0, 0.0, -0.035)]

    def _load_g1_py_defaults(self) -> None:
        default_z, jp_rules, sdk_names = parse_g1_py_cfg(self.base_dir / "g1.py")
        self.default_root_z = default_z
        self.joint_sdk_names = sdk_names or list(self.revolute_joint_names)
        n_dof = max(1, len(self.revolute_joint_names))
        q = np.zeros(n_dof, dtype=np.float32)
        for idx, j_name in enumerate(self.revolute_joint_names):
            if j_name in jp_rules:
                q[idx] = jp_rules[j_name]
                continue
            for pat, val in jp_rules.items():
                if re.fullmatch(pat, j_name):
                    q[idx] = val
                    break
        self.default_joint_angles = self.clamp_joint_angles(q)

    def clamp_joint_angles(self, joint_angles: Sequence[float]) -> np.ndarray:
        """Clamp 29-DOF joint vector against authoritative URDF lower/upper limits."""
        arr = np.asarray(joint_angles, dtype=np.float32).copy()
        n = min(len(arr), len(self.joint_limits))
        if n > 0:
            arr[:n] = np.clip(arr[:n], self.joint_limits[:n, 0], self.joint_limits[:n, 1])
        return arr

    def solve_link_transforms(
        self, root_x: float = 0.0, root_y: float = 0.0, root_yaw: float = 0.0,
        root_z: float = 0.76, joint_angles: Optional[Sequence[float]] = None,
        root_quat_xyzw: Optional[Sequence[float]] = None,
    ) -> Dict[str, np.ndarray]:
        """Solve world 4x4 link transforms for pelvis and every child link."""
        q_map: Dict[str, float] = {}
        if joint_angles is not None:
            for j_name, val in zip(self.revolute_joint_names, joint_angles):
                q_map[j_name] = float(val)
        base_tf = rpy_matrix(0.0, 0.0, root_yaw)
        if root_quat_xyzw is not None:
            base_tf[:3, :3] = base_tf[:3, :3] @ quat_xyzw_to_mat3(root_quat_xyzw)
        base_tf[0, 3], base_tf[1, 3], base_tf[2, 3] = root_x, root_y, root_z
        link_tfs: Dict[str, np.ndarray] = {}
        for link in self.topo_links:
            j = self.joints_by_child.get(link)
            if j is None:
                link_tfs[link] = base_tf
                continue
            parent_tf = link_tfs.get(j.parent, base_tf)
            ang = q_map.get(j.name, 0.0) if j.joint_type in ("revolute", "continuous") else 0.0
            rot_tf = rodrigues_4x4(j.axis, ang) if abs(ang) > 1e-6 else np.eye(4, dtype=np.float32)
            link_tfs[link] = parent_tf @ j.origin_mat @ rot_tf
        return link_tfs

    def compute_foot_min_z(
        self, root_z: float, joint_angles: Optional[Sequence[float]] = None,
        root_quat_xyzw: Optional[Sequence[float]] = None,
    ) -> float:
        """Compute lowest world Z across all URDF ankle-roll foot contact spheres."""
        link_tfs = self.solve_link_transforms(0.0, 0.0, 0.0, root_z, joint_angles, root_quat_xyzw)
        min_z = float("inf")
        contacts = self.foot_contact_points or {"left_ankle_roll_link": [(0.0, 0.0, -0.035)], "right_ankle_roll_link": [(0.0, 0.0, -0.035)]}
        for lname, pts in contacts.items():
            lt = link_tfs.get(lname)
            if lt is None:
                continue
            for px, py, pz in pts:
                wz = float(lt[2, 0] * px + lt[2, 1] * py + lt[2, 2] * pz + lt[2, 3])
                if wz < min_z:
                    min_z = wz
        return 0.0 if not math.isfinite(min_z) else min_z

    def ground_root_z(
        self, root_z: float, joint_angles: Optional[Sequence[float]] = None,
        min_clearance: float = 0.002, root_quat_xyzw: Optional[Sequence[float]] = None,
    ) -> float:
        """Shift pelvis height so the lowest foot sole rests cleanly on stage z >= min_clearance."""
        return float(root_z + (min_clearance - self.compute_foot_min_z(root_z, joint_angles, root_quat_xyzw)))

    def solve_fk(
        self, root_x: float = 0.0, root_y: float = 0.0, root_yaw: float = 0.0,
        root_z: float = 0.76, joint_angles: Optional[Sequence[float]] = None,
        root_quat_xyzw: Optional[Sequence[float]] = None,
    ) -> List[Tuple[str, np.ndarray]]:
        """Solve world 4x4 matrices for all visual STL meshes; returns [(mesh_rel_path, mat4x4)]."""
        link_tfs = self.solve_link_transforms(root_x, root_y, root_yaw, root_z, joint_angles, root_quat_xyzw)
        return [(vis.mesh_rel_path, link_tfs[vis.link_name] @ vis.visual_mat) for vis in self.visuals if vis.link_name in link_tfs]


_CHAIN_SINGLETON: Optional[G1KinematicsChain] = None


def get_g1_kinematics() -> G1KinematicsChain:
    """Return cached G1KinematicsChain singleton parsed from backend assets."""
    global _CHAIN_SINGLETON
    if _CHAIN_SINGLETON is None:
        _CHAIN_SINGLETON = G1KinematicsChain()
    return _CHAIN_SINGLETON
