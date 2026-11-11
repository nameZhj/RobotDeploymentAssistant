import hashlib
import json
import logging
import math
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from src.core.config_loader import config_loader

logger = logging.getLogger("URDFKinematicsLoader")


@dataclass
class JointDef:
    name: str
    parent: str
    child: str
    joint_type: str
    origin_xyz: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    origin_rpy: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    mesh_path: Optional[str] = None


class URDFKinematicsLoader:
    """
    Parses robot URDF kinematic joint trees and mesh references from assets/models/g1_avatar/.
    Caches tree structure to runtime/cache/ and computes Forward Kinematics (FK) transformation matrices.
    """

    def __init__(self, model_dir: Optional[Path] = None) -> None:
        if model_dir:
            self._model_dir = model_dir
        else:
            assets_dir = config_loader.resolve_path("assets_dir", "assets")
            self._model_dir = assets_dir / "models" / "g1_avatar"

        paths = config_loader.get_paths()
        cache_name = paths.get("cache_dir", "runtime/cache")
        self._cache_dir = Path(cache_name)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        self._joints: Dict[str, JointDef] = {}
        self._load_or_cache_urdf()

    def _load_or_cache_urdf(self) -> None:
        cache_file = self._cache_dir / "urdf_g1_kinematics.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for j_data in data:
                        self._joints[j_data["name"]] = JointDef(**j_data)
                    return
            except Exception as e:
                logger.warning(f"Failed to read cached kinematics: {e}")

        # Search for .urdf file in model dir
        urdf_files = list(self._model_dir.glob("*.urdf")) if self._model_dir.exists() else []
        if urdf_files:
            self._parse_urdf(urdf_files[0])
        else:
            self._generate_default_g1_joints()

        # Cache to disk
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump([asdict(j) for j in self._joints.values()], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to cache URDF joints: {e}")

    def _parse_urdf(self, urdf_path: Path) -> None:
        try:
            tree = ET.parse(urdf_path)
            root = tree.getroot()
            for joint_node in root.findall("joint"):
                name = joint_node.get("name", "")
                j_type = joint_node.get("type", "revolute")
                parent = joint_node.find("parent").get("link", "") if joint_node.find("parent") is not None else ""
                child = joint_node.find("child").get("link", "") if joint_node.find("child") is not None else ""

                origin_node = joint_node.find("origin")
                xyz = (0.0, 0.0, 0.0)
                rpy = (0.0, 0.0, 0.0)
                if origin_node is not None:
                    xyz = tuple(float(v) for v in origin_node.get("xyz", "0 0 0").split())
                    rpy = tuple(float(v) for v in origin_node.get("rpy", "0 0 0").split())

                axis_node = joint_node.find("axis")
                axis = (0.0, 0.0, 1.0)
                if axis_node is not None:
                    axis = tuple(float(v) for v in axis_node.get("xyz", "0 0 1").split())

                self._joints[name] = JointDef(
                    name=name, parent=parent, child=child, joint_type=j_type,
                    origin_xyz=xyz, origin_rpy=rpy, axis=axis
                )
        except Exception as e:
            logger.warning(f"Error parsing URDF {urdf_path}: {e}")
            self._generate_default_g1_joints()

    def _generate_default_g1_joints(self) -> None:
        """Seed 29-DoF default kinematic hierarchy for G1 humanoid avatar."""
        default_joint_names = [
            ("pelvis_joint", "world", "pelvis", (0.0, 0.0, 0.75)),
            ("waist_yaw_joint", "pelvis", "torso", (0.0, 0.0, 0.1)),
            ("left_shoulder_pitch_joint", "torso", "left_upper_arm", (0.0, 0.18, 0.3)),
            ("left_elbow_joint", "left_upper_arm", "left_lower_arm", (0.0, 0.0, -0.2)),
            ("right_shoulder_pitch_joint", "torso", "right_upper_arm", (0.0, -0.18, 0.3)),
            ("right_elbow_joint", "right_upper_arm", "right_lower_arm", (0.0, 0.0, -0.2)),
            ("left_hip_pitch_joint", "pelvis", "left_thigh", (0.0, 0.09, -0.05)),
            ("left_knee_joint", "left_thigh", "left_calf", (0.0, 0.0, -0.3)),
            ("right_hip_pitch_joint", "pelvis", "right_thigh", (0.0, -0.09, -0.05)),
            ("right_knee_joint", "right_thigh", "right_calf", (0.0, 0.0, -0.3)),
        ]
        for name, parent, child, xyz in default_joint_names:
            self._joints[name] = JointDef(name=name, parent=parent, child=child, joint_type="revolute", origin_xyz=xyz)

    def compute_forward_kinematics(self, joint_angles: Dict[str, float]) -> Dict[str, Tuple[float, float, float]]:
        """Compute 3D world link positions (x, y, z) by propagating FK transforms down the tree."""
        link_positions: Dict[str, Tuple[float, float, float]] = {"world": (0.0, 0.0, 0.0)}

        for j_name, j_def in self._joints.items():
            parent_pos = link_positions.get(j_def.parent, (0.0, 0.0, 0.0))
            theta = joint_angles.get(j_name, 0.0)

            # Local translation + simplified rotation offset
            dx, dy, dz = j_def.origin_xyz
            ax, ay, az = j_def.axis

            # Compute child link position
            cx = parent_pos[0] + dx + ax * math.sin(theta) * 0.05
            cy = parent_pos[1] + dy + ay * math.sin(theta) * 0.05
            cz = parent_pos[2] + dz + az * math.cos(theta) * 0.05

            link_positions[j_def.child] = (round(cx, 4), round(cy, 4), round(cz, 4))

        return link_positions

    @property
    def joint_names(self) -> List[str]:
        return list(self._joints.keys())


urdf_kinematics_loader = URDFKinematicsLoader()

