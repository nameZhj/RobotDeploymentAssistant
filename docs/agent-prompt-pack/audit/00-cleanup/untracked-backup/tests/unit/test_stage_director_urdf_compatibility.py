"""
@file: tests/unit/test_stage_director_urdf_compatibility.py
@brief: G1 机器人 23/29 DoF 及含手 URDF 模型解析与网格完整性测试
@exports: test_g1_23dof_model_audit, test_g1_29dof_model_audit, test_g1_29dof_hand_model_audit, test_missing_urdf_fallback
"""
import os
import pytest
from src.ui.stage3d.robot_model_diagnostic import RobotModelDiagnostic


def test_g1_23dof_model_audit():
    """测试 G1 23 DoF 官方模型 URDF 与 Mesh 资产完整性"""
    urdf = "assets/models/g1_description/g1_description/g1_23dof.urdf"
    assert os.path.exists(urdf)
    status = RobotModelDiagnostic.audit_model(urdf)
    assert status.urdf_exists is True
    assert status.total_links == 33
    assert status.total_joints == 32
    assert status.movable_joints == 23
    assert status.fixed_joints == 9
    assert status.mesh_count == 29
    assert len(status.missing_meshes) == 0
    assert status.mesh_complete is True
    assert status.fk_supported is True
    assert status.status_label == "HEALTHY"


def test_g1_29dof_model_audit():
    """测试 G1 29 DoF 官方模型 URDF 与 Mesh 资产完整性"""
    urdf = "assets/models/g1_description/g1_description/g1_29dof.urdf"
    assert os.path.exists(urdf)
    status = RobotModelDiagnostic.audit_model(urdf)
    assert status.urdf_exists is True
    assert status.total_links == 40
    assert status.total_joints == 39
    assert status.movable_joints == 29
    assert status.fixed_joints == 10
    assert status.mesh_count == 36
    assert len(status.missing_meshes) == 0
    assert status.mesh_complete is True
    assert status.fk_supported is True
    assert status.status_label == "HEALTHY"


def test_g1_29dof_hand_model_audit():
    """测试 G1 29 DoF 含多指手模型 URDF 与 Dex1 手部 Mesh 完整性"""
    urdf = "assets/models/g1_description/g1_description/g1_29dof_with_hand.urdf"
    assert os.path.exists(urdf)
    status = RobotModelDiagnostic.audit_model(urdf)
    assert status.urdf_exists is True
    assert status.total_links == 54
    assert status.total_joints == 53
    assert status.movable_joints == 43
    assert status.fixed_joints == 10
    assert status.mesh_count == 50
    assert len(status.missing_meshes) == 0
    assert status.mesh_complete is True
    assert status.status_label == "HEALTHY"


def test_missing_urdf_fallback():
    """测试不存在的模型路径能明确标记为 URDF_MISSING"""
    status = RobotModelDiagnostic.audit_model("assets/non_existent.urdf")
    assert status.urdf_exists is False
    assert status.status_label == "URDF_MISSING"
