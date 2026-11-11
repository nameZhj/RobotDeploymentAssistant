"""
@file: src/domain/kinematics/g1_urdf_mesh_loader.py
@brief: G1 机器人真实 URDF 解析、LOD 双模 STL 网格加载与压缩缓存引擎
@exports: G1LinkInfo, G1JointInfo, G1UrdfMeshLoader, g1_urdf_mesh_loader
"""
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from src.domain.kinematics.g1_stl_mesh_cache import G1StlMeshCache, parse_stl_file


@dataclass
class G1LinkInfo:
    name: str
    visual_mesh_path: Optional[str] = None
    visual_xyz: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    visual_rpy: Tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class G1JointInfo:
    name: str
    parent: str
    child: str
    origin_xyz: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    origin_rpy: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    lower: float = -3.14159
    upper: float = 3.14159


class G1UrdfMeshLoader:
    """真实 URDF 拓扑解析与 165 个 STL 网格的高速加载与 LOD 缓存管理器"""

    DEFAULT_URDF = "assets/models/g1_description/g1_description/g1_23dof.urdf"
    DEFAULT_MESH_DIR = "assets/models/g1_description/g1_description/meshes"

    @classmethod
    def parse_urdf(cls, urdf_path: Optional[str] = None) -> Tuple[Dict[str, G1LinkInfo], Dict[str, G1JointInfo]]:
        path = urdf_path or cls.DEFAULT_URDF
        if not os.path.exists(path):
            candidates = [
                os.path.join("assets", "models", "g1_description", "g1_description", "g1_23dof.urdf"),
                os.path.join("assets", "models", "g1_description", "g1_description", "g1_29dof.urdf")
            ]
            for c in candidates:
                if os.path.exists(c):
                    path = c
                    break
        if not os.path.exists(path):
            raise FileNotFoundError(f"URDF file not found: {path}")

        tree = ET.parse(path)
        root = tree.getroot()
        links: Dict[str, G1LinkInfo] = {}
        joints: Dict[str, G1JointInfo] = {}

        for l_el in root.findall("link"):
            name = l_el.get("name", "")
            if not name: continue
            mesh_path, xyz, rpy = None, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
            vis = l_el.find("visual")
            if vis is not None:
                orig = vis.find("origin")
                if orig is not None:
                    xr = [float(v) for v in orig.get("xyz", "0 0 0").split()]
                    rr = [float(v) for v in orig.get("rpy", "0 0 0").split()]
                    xyz, rpy = (xr[0], xr[1], xr[2]), (rr[0], rr[1], rr[2])
                geom = vis.find("geometry")
                if geom is not None and geom.find("mesh") is not None:
                    mesh_path = geom.find("mesh").get("filename")
            links[name] = G1LinkInfo(name=name, visual_mesh_path=mesh_path, visual_xyz=xyz, visual_rpy=rpy)

        for j_el in root.findall("joint"):
            name = j_el.get("name", "")
            p_el, c_el = j_el.find("parent"), j_el.find("child")
            if not name or p_el is None or c_el is None: continue
            orig = j_el.find("origin")
            o_xyz, o_rpy = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
            if orig is not None:
                ox = [float(v) for v in orig.get("xyz", "0 0 0").split()]
                or_ = [float(v) for v in orig.get("rpy", "0 0 0").split()]
                o_xyz, o_rpy = (ox[0], ox[1], ox[2]), (or_[0], or_[1], or_[2])
            ax = j_el.find("axis")
            axis = tuple(float(v) for v in ax.get("xyz", "0 0 1").split()) if ax is not None else (0.0, 0.0, 1.0)
            lim = j_el.find("limit")
            lower = float(lim.get("lower", -3.14159)) if lim is not None else -3.14159
            upper = float(lim.get("upper", 3.14159)) if lim is not None else 3.14159
            joints[name] = G1JointInfo(name, p_el.get("link", ""), c_el.get("link", ""), o_xyz, o_rpy, axis, lower, upper)
        return links, joints

    @classmethod
    def parse_stl_file(cls, file_path: str, lod_mode: str = "PRO") -> Tuple[np.ndarray, np.ndarray]:
        return parse_stl_file(file_path, lod_mode)

    @classmethod
    def load_all_meshes(
        cls, mesh_dir: Optional[str] = None, lod_mode: str = "PRO",
        cache_dir: Optional[str] = None, max_files: Optional[int] = None
    ) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
        return G1StlMeshCache.load_all_meshes(mesh_dir, lod_mode, cache_dir, max_files)


g1_urdf_mesh_loader = G1UrdfMeshLoader()
