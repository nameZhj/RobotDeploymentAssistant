"""
@file: tests/compatibility/test_3d_preview_contracts.py
@brief: 3D 舞蹈预览管理器与模型解析契约测试 (2026-10-01 前基线)
@exports: test_preview_manager_builtin_models, test_preview_manager_model_info
"""
import os
import pytest
from backend.preview_manager import preview_manager


def test_preview_manager_builtin_models():
    """验证 3D 预览管理器的内置模型目录可访问，且包含 G1 29DOF URDF 资源。"""
    builtin_dir = preview_manager.get_builtin_models_dir()
    assert os.path.exists(builtin_dir)
    g1_rubber = os.path.join(builtin_dir, "g1_29dof_rubber_hand")
    assert os.path.exists(g1_rubber)
    assert os.path.isfile(os.path.join(g1_rubber, "g1_29dof_mode_15.urdf"))


def test_preview_manager_model_info():
    """验证 G1 模型信息解析正确提取关节列表与刚体链接。"""
    info = preview_manager._get_default_model_info()
    assert isinstance(info, dict)
    assert "links" in info
    assert "joints" in info
    assert len(info["links"]) > 10
    assert len(info["joints"]) > 10
