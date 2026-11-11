"""
G1 机器人 URDF 解析与 3D 正向运动学 (Forward Kinematics) 求解器
解析 URDF 中的 link 与 joint，计算 3D 舞台坐标系下的 4x4 空间齐次变换矩阵
"""
import math
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np


@dataclass
class URDFJoint:
    name: str
    joint_type: str
    parent: str
    child: str
    origin_xyz: np.ndarray
    origin_rpy: np.ndarray
    axis: np.ndarray


def rpy_to_rot_matrix(r: float, p: float, y: float) -> np.ndarray:
    """欧拉角 (Roll, Pitch, Yaw) 转 3x3 旋转矩阵"""
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    rx = np.array([[1.0, 0.0, 0.0], [0.0, cr, -sr], [0.0, sr, cr]])
    ry = np.array([[cp, 0.0, sp], [0.0, 1.0, 0.0], [-sp, 0.0, cp]])
    rz = np.array([[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]])
    return rz @ ry @ rx


def axis_angle_to_rot_matrix(axis: np.ndarray, angle: float) -> np.ndarray:
    """罗德里格斯公式：旋转轴 + 旋转角度转 3x3 旋转矩阵"""
    norm = np.linalg.norm(axis)
    if norm < 1e-6:
        return np.eye(3)
    u = axis / norm
    c = math.cos(angle)
    s = math.sin(angle)
    ux, uy, uz = u[0], u[1], u[2]
    k = np.array([[0.0, -uz, uy], [uz, 0.0, -ux], [-uy, ux, 0.0]])
    return np.eye(3) * c + (1.0 - c) * np.outer(u, u) + s * k


def make_transform_matrix(xyz: np.ndarray, rot: np.ndarray) -> np.ndarray:
    """构建 4x4 齐次变换矩阵"""
    t = np.eye(4)
    t[:3, :3] = rot
    t[:3, 3] = xyz
    return t


class UrdfFkSolver:
    """G1 机器人 URDF 正向运动学求解器"""

    def __init__(self, urdf_path: Optional[str] = None):
        self.urdf_path = urdf_path or self._find_default_urdf()
        self.joints: Dict[str, URDFJoint] = {}
        self.links: List[str] = []
        self.parent_map: Dict[str, Tuple[str, URDFJoint]] = {}
        self.root_link: str = "pelvis"
        self._parse_urdf()

    def _find_default_urdf(self) -> str:
        candidates = [
            os.path.join("assets", "models", "g1_description", "g1_description", "g1_23dof.urdf"),
            os.path.join("assets", "models", "g1_avatar", "g1_description", "g1_23dof.urdf"),
            os.path.join("assets", "models", "g1_description", "g1_23dof.urdf"),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return candidates[0]

    def _parse_urdf(self) -> None:
        if not os.path.exists(self.urdf_path):
            self._init_fallback_structure()
            return
        tree = ET.parse(self.urdf_path)
        root = tree.getroot()
        all_children = set()
        for link in root.findall("link"):
            name = link.get("name")
            if name:
                self.links.append(name)
        for joint in root.findall("joint"):
            j_name = joint.get("name", "")
            j_type = joint.get("type", "fixed")
            parent_el = joint.find("parent")
            child_el = joint.find("child")
            if parent_el is None or child_el is None:
                continue
            parent = parent_el.get("link", "")
            child = child_el.get("link", "")
            all_children.add(child)
            orig_el = joint.find("origin")
            xyz = np.fromstring(orig_el.get("xyz", "0 0 0"), sep=" ") if orig_el is not None else np.zeros(3)
            rpy = np.fromstring(orig_el.get("rpy", "0 0 0"), sep=" ") if orig_el is not None else np.zeros(3)
            axis_el = joint.find("axis")
            axis = np.fromstring(axis_el.get("xyz", "0 0 1"), sep=" ") if axis_el is not None else np.array([0., 0., 1.])
            uj = URDFJoint(j_name, j_type, parent, child, xyz, rpy, axis)
            self.joints[j_name] = uj
            self.parent_map[child] = (parent, uj)

        parents = {j.parent for j in self.joints.values()}
        roots = list(parents - all_children)
        if "pelvis" in roots or "pelvis" in self.links:
            self.root_link = "pelvis"
        elif roots:
            self.root_link = roots[0]

    def _init_fallback_structure(self) -> None:
        """URDF 文件缺失时的标准 23 自由度结构兜底"""
        self.root_link = "pelvis"
        self.links = ["pelvis", "torso_link"]

    def compute_fk(self, base_pose: Tuple[float, float, float, float],
                   joint_positions: Dict[str, float]) -> Dict[str, np.ndarray]:
        """
        计算各 link 在 3D 舞台坐标系下的 4x4 空间变换矩阵
        base_pose: (X, Y, Z, Yaw)
        joint_positions: {joint_name: angle_in_radians}
        """
        x, y, z, yaw = base_pose
        base_rot = rpy_to_rot_matrix(0.0, 0.0, yaw)
        base_tf = make_transform_matrix(np.array([x, y, z]), base_rot)

        link_transforms: Dict[str, np.ndarray] = {self.root_link: base_tf}
        children_map: Dict[str, List[Tuple[str, URDFJoint]]] = {}
        for child, (parent, j_obj) in self.parent_map.items():
            children_map.setdefault(parent, []).append((child, j_obj))

        queue = [self.root_link]
        while queue:
            curr = queue.pop(0)
            t_curr = link_transforms[curr]
            for child, j_obj in children_map.get(curr, []):
                t_orig = make_transform_matrix(
                    j_obj.origin_xyz,
                    rpy_to_rot_matrix(j_obj.origin_rpy[0], j_obj.origin_rpy[1], j_obj.origin_rpy[2])
                )
                q = joint_positions.get(j_obj.name, 0.0)
                if j_obj.joint_type in ("revolute", "continuous"):
                    r_joint = axis_angle_to_rot_matrix(j_obj.axis, q)
                else:
                    r_joint = np.eye(3)
                t_j = make_transform_matrix(np.zeros(3), r_joint)
                link_transforms[child] = t_curr @ t_orig @ t_j
                queue.append(child)

        return link_transforms

    def get_link_positions(self, base_pose: Tuple[float, float, float, float],
                           joint_positions: Dict[str, float]) -> Dict[str, Tuple[float, float, float]]:
        """便捷获取所有连杆在世界坐标系下的 (X, Y, Z) 空间位置"""
        transforms = self.compute_fk(base_pose, joint_positions)
        res: Dict[str, Tuple[float, float, float]] = {}
        for k, tf in transforms.items():
            pos = tf[:3, 3]
            res[k] = (float(pos[0]), float(pos[1]), float(pos[2]))
        return res

    def get_active_joint_names(self) -> List[str]:
        """返回所有可旋转的主动关节名列表"""
        return [j.name for j in self.joints.values() if j.joint_type in ("revolute", "continuous")]

