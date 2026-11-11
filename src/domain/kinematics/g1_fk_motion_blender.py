"""
@file: src/domain/kinematics/g1_fk_motion_blender.py
@brief: G1 正向运动学求解器与 60Hz 走位/舞蹈步态全身融合采样引擎
@exports: G1ForwardKinematics, G1MotionBlender, g1_motion_blender
"""
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from src.domain.kinematics.performance_sampler import StagePerformanceSampler
from src.domain.kinematics.urdf_fk_solver import ForwardKinematicsSolver


class G1ForwardKinematics:
    """基于罗德里格斯旋转公式与树状递归遍历的 3D 正向运动学求解器兼容包装"""

    def __init__(self, urdf_path: Optional[str] = None) -> None:
        self.solver = ForwardKinematicsSolver(urdf_path)
        self.root_link = self.solver.root_link

    def compute_fk(
        self, world_pos: Tuple[float, float, float], yaw_deg: float, joint_angles: Dict[str, float]
    ) -> Dict[str, np.ndarray]:
        return self.solver.solve_full_body_fk(world_pos, yaw_deg, joint_angles)["link_world_matrices"]

    def solve_full_body_fk(
        self, base_xyz: Tuple[float, float, float], base_yaw: float, joint_angles_dict: Dict[str, float]
    ) -> Dict[str, Any]:
        return self.solver.solve_full_body_fk(base_xyz, base_yaw, joint_angles_dict)


class G1MotionBlender(StagePerformanceSampler):
    """双层时间轴驱动：融合下层轨迹走位双足步态与上层舞蹈动作关节角序列"""

    def __init__(self, urdf_path: Optional[str] = None) -> None:
        super().__init__(ForwardKinematicsSolver(urdf_path))
        self.fk = G1ForwardKinematics(urdf_path)


g1_motion_blender = G1MotionBlender()
