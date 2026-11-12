"""
@file: tests/unit/test_stage_director_fk_integration.py
@brief: G1 正向运动学齐次矩阵求解、旋转正交性与确定性重算测试
@exports: test_fk_root_and_links_presence, test_rotation_orthogonality, test_fk_deterministic_repeatability
"""
import math
import numpy as np
import pytest
from src.domain.kinematics.urdf_fk_solver import ForwardKinematicsSolver


@pytest.fixture
def solver():
    urdf = "assets/models/g1_description/g1_description/g1_23dof.urdf"
    return ForwardKinematicsSolver(urdf)


def test_fk_root_and_links_presence(solver):
    """验证根节点与各下属连杆齐次变换矩阵正常解算"""
    world_pos = (1.0, 2.0, 0.75)
    yaw_rad = math.radians(30.0)
    joints = {"left_hip_pitch_joint": 0.2, "left_knee_joint": 0.4}

    res = solver.solve_full_body_fk(world_pos, yaw_rad, joints)
    mats = res["link_world_matrices"]

    assert "pelvis" in mats
    assert mats["pelvis"].shape == (4, 4)
    assert np.allclose(mats["pelvis"][:3, 3], np.array(world_pos, dtype=np.float32))

    assert "left_knee_link" in mats
    assert "torso_link" in mats


def test_rotation_orthogonality(solver):
    """验证各 Link 旋转矩阵正交性：R^T @ R = I，det(R) = 1"""
    world_pos = (0.0, 0.0, 0.0)
    yaw_rad = 0.5
    joints = {"left_hip_pitch_joint": 0.3, "left_knee_joint": 0.5, "waist_yaw_joint": -0.2}

    mats = solver.solve_full_body_fk(world_pos, yaw_rad, joints)["link_world_matrices"]
    for link_name, mat in mats.items():
        r = mat[:3, :3]
        identity = np.eye(3, dtype=np.float32)
        assert np.allclose(r.T @ r, identity, atol=1e-4), f"{link_name} 旋转不正交"
        det = float(np.linalg.det(r))
        assert pytest.approx(det, abs=1e-3) == 1.0, f"{link_name} 行列式不为 1"


def test_fk_deterministic_repeatability(solver):
    """验证完全相同的输入在重复计算时产生严格恒等的结果（无随机漂移）"""
    world_pos = (-1.5, 3.2, 0.8)
    yaw_rad = -1.2
    joints = {"right_hip_pitch_joint": -0.4, "right_knee_joint": 0.8}

    res1 = solver.solve_full_body_fk(world_pos, yaw_rad, joints)["link_world_matrices"]
    res2 = solver.solve_full_body_fk(world_pos, yaw_rad, joints)["link_world_matrices"]

    for k in res1:
        assert np.array_equal(res1[k], res2[k])
