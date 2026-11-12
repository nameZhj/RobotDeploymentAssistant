"""
@file: src/ui/stage3d/robot_model_diagnostic.py
@brief: G1 多型号 URDF 解析、关节限位校验与模型健康诊断器
@exports: RobotModelDiagnostic, ModelHealthStatus
"""
import math
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ModelHealthStatus:
    model_name: str
    urdf_exists: bool = False
    mesh_complete: bool = False
    total_links: int = 0
    total_joints: int = 0
    movable_joints: int = 0
    fixed_joints: int = 0
    mesh_count: int = 0
    missing_meshes: List[str] = field(default_factory=list)
    fk_supported: bool = False
    lod_supported: bool = True
    status_label: str = "UNKNOWN"


class RobotModelDiagnostic:
    """提供 G1 23/29 DoF URDF 完整性审计、关节限位软限夹紧与健康状态评估"""

    DEFAULT_BASE_DIR = "assets/models/g1_description/g1_description"

    @classmethod
    def audit_model(cls, urdf_path: str, mesh_dir: Optional[str] = None) -> ModelHealthStatus:
        m_name = os.path.basename(urdf_path)
        status = ModelHealthStatus(model_name=m_name)
        if not os.path.exists(urdf_path):
            status.status_label = "URDF_MISSING"
            return status

        status.urdf_exists = True
        m_dir = mesh_dir or os.path.join(os.path.dirname(urdf_path), "meshes")

        try:
            tree = ET.parse(urdf_path)
            root = tree.getroot()
            links = root.findall("link")
            joints = root.findall("joint")
            status.total_links = len(links)
            status.total_joints = len(joints)

            movable = [j for j in joints if j.get("type") in ("revolute", "continuous")]
            fixed = [j for j in joints if j.get("type") == "fixed"]
            status.movable_joints = len(movable)
            status.fixed_joints = len(fixed)

            mesh_files_on_disk = set(f.lower() for f in os.listdir(m_dir)) if os.path.exists(m_dir) else set()
            missing = []
            m_count = 0

            for l in links:
                vis = l.find("visual")
                if vis is None:
                    continue
                geom = vis.find("geometry")
                if geom is None or geom.find("mesh") is None:
                    continue
                m_count += 1
                fn = os.path.basename(geom.find("mesh").get("filename", ""))
                if fn.lower() not in mesh_files_on_disk:
                    missing.append(fn)

            status.mesh_count = m_count
            status.missing_meshes = missing
            status.mesh_complete = (len(missing) == 0 and m_count > 0)
            status.fk_supported = (status.movable_joints in (23, 29, 43))
            status.status_label = "HEALTHY" if status.mesh_complete and status.fk_supported else "DEGRADED"
        except Exception:
            status.status_label = "PARSE_ERROR"

        return status

    @classmethod
    def extract_joint_limits(cls, urdf_path: str) -> Dict[str, Tuple[float, float]]:
        if not os.path.exists(urdf_path):
            return {}
        try:
            tree = ET.parse(urdf_path)
            root = tree.getroot()
            limits: Dict[str, Tuple[float, float]] = {}
            for j in root.findall("joint"):
                name = j.get("name", "")
                if j.get("type") in ("revolute", "continuous"):
                    lim = j.find("limit")
                    if lim is not None:
                        limits[name] = (float(lim.get("lower", -3.14159)), float(lim.get("upper", 3.14159)))
                    else:
                        limits[name] = (-3.14159, 3.14159)
            return limits
        except Exception:
            return {}

    @classmethod
    def validate_and_clamp_joints(
        cls, joint_angles: Dict[str, float], limits: Dict[str, Tuple[float, float]]
    ) -> Tuple[Dict[str, float], List[str]]:
        clamped: Dict[str, float] = {}
        diagnostics: List[str] = []

        for name, val in joint_angles.items():
            if not isinstance(val, (int, float)) or not math.isfinite(val):
                diagnostics.append(f"关节 {name} 数值异常 ({val})，安全回退 0.0")
                clamped[name] = 0.0
                continue

            q = float(val)
            if name in limits:
                low, high = limits[name]
                if q < low:
                    diagnostics.append(f"关节 {name} 下限截断: {q:.3f} -> {low:.3f}")
                    q = low
                elif q > high:
                    diagnostics.append(f"关节 {name} 上限截断: {q:.3f} -> {high:.3f}")
                    q = high
            clamped[name] = q

        return clamped, diagnostics

    @classmethod
    def get_official_model_matrix(cls, base_dir: Optional[str] = None) -> List[ModelHealthStatus]:
        b_dir = base_dir or cls.DEFAULT_BASE_DIR
        models = ["g1_23dof.urdf", "g1_29dof.urdf", "g1_29dof_with_hand.urdf"]
        results: List[ModelHealthStatus] = []
        for m in models:
            p = os.path.join(b_dir, m)
            results.append(cls.audit_model(p))
        return results
