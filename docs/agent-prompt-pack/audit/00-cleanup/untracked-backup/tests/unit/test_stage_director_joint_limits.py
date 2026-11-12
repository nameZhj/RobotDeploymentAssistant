"""
@file: tests/unit/test_stage_director_joint_limits.py
@brief: G1 关节限位抽取、越界截断与非有限异常值软限保护测试
@exports: test_extract_joint_limits, test_clamp_out_of_bounds, test_reject_nan_and_inf
"""
import pytest
from src.ui.stage3d.robot_model_diagnostic import RobotModelDiagnostic


def test_extract_joint_limits():
    """测试从 23 DoF URDF 中抽取各关节上下限"""
    urdf = "assets/models/g1_description/g1_description/g1_23dof.urdf"
    limits = RobotModelDiagnostic.extract_joint_limits(urdf)
    assert len(limits) == 23
    assert "left_hip_pitch_joint" in limits
    low, high = limits["left_hip_pitch_joint"]
    assert low < high


def test_clamp_out_of_bounds():
    """测试超出关节限位的角度被安全截断至上下限，并生成诊断告警"""
    limits = {
        "left_knee_joint": (-0.1, 2.5),
        "waist_yaw_joint": (-2.6, 2.6)
    }
    input_joints = {
        "left_knee_joint": 3.8,   # 超上限
        "waist_yaw_joint": -4.0,  # 超下限
    }
    clamped, diags = RobotModelDiagnostic.validate_and_clamp_joints(input_joints, limits)
    assert clamped["left_knee_joint"] == 2.5
    assert clamped["waist_yaw_joint"] == -2.6
    assert len(diags) == 2
    assert "上限截断" in diags[0]
    assert "下限截断" in diags[1]


def test_reject_nan_and_inf():
    """测试 NaN 和 Inf 等非有限数值被拒绝并安全回退至 0.0"""
    limits = {"left_elbow_joint": (-1.0, 1.5)}
    input_joints = {
        "left_elbow_joint": float("nan"),
        "right_elbow_joint": float("inf"),
    }
    clamped, diags = RobotModelDiagnostic.validate_and_clamp_joints(input_joints, limits)
    assert clamped["left_elbow_joint"] == 0.0
    assert clamped["right_elbow_joint"] == 0.0
    assert len(diags) == 2
    assert "数值异常" in diags[0]
