"""
@file: tests/unit/test_stage_director_collision_visualization.py
@brief: 时空防撞安全等级计算与 3D 碰撞光环/标牌风险态势呈现测试
@exports: test_collision_status_classification, test_viewport_collision_diagnostics_integration
"""
import sys
import pytest
from PySide6.QtWidgets import QApplication
from src.application.stage_director.stage_preview_coordinator import StagePreviewCoordinator
from src.domain.simulation.stage_performance_sampler import AvatarSimulationState
from src.ui.stage3d.stage_viewport_3d import StageViewport3D


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_collision_status_classification():
    """验证安全距离 (>1.0m)、预警距离 (0.65m~1.0m) 与阻断硬冲突 (<0.65m) 的三档风险划分"""
    coord = StagePreviewCoordinator()

    # 1. 安全状态 (间距 4.0m)
    poses_safe = {
        "Robot_1": AvatarSimulationState(0.0, "Robot_1", -2.0, 0.0, 0.0, 0.0),
        "Robot_2": AvatarSimulationState(0.0, "Robot_2", 2.0, 0.0, 0.0, 0.0),
    }
    diag_safe = coord.check_collision_status(poses_safe)
    assert diag_safe["status"] == "NORMAL"
    assert len(diag_safe["alerts"]) == 0

    # 2. 预警状态 (间距 0.8m)
    poses_warn = {
        "Robot_1": AvatarSimulationState(0.0, "Robot_1", 0.0, 0.0, 0.0, 0.0),
        "Robot_2": AvatarSimulationState(0.0, "Robot_2", 0.8, 0.0, 0.0, 0.0),
    }
    diag_warn = coord.check_collision_status(poses_warn)
    assert diag_warn["status"] == "WARNING"
    assert len(diag_warn["alerts"]) == 1

    # 3. 阻断状态 (间距 0.4m < 0.65m)
    poses_block = {
        "Robot_1": AvatarSimulationState(0.0, "Robot_1", 0.0, 0.0, 0.0, 0.0),
        "Robot_2": AvatarSimulationState(0.0, "Robot_2", 0.4, 0.0, 0.0, 0.0),
    }
    diag_block = coord.check_collision_status(poses_block)
    assert diag_block["status"] == "BLOCKED"
    assert len(diag_block["alerts"]) == 1


def test_viewport_collision_diagnostics_integration(qapp):
    """验证 3D 视口接收冲突诊断信息后能够正确记录各机器人的危险状态"""
    vp = StageViewport3D()
    diag_payload = {
        "status": "BLOCKED",
        "alerts": [{"level": "BLOCKED", "robots": ("Robot_1", "Robot_2")}]
    }
    vp.set_collision_diagnostics(diag_payload)
    assert vp._collision_alerts.get("Robot_1") == "BLOCKED"
    assert vp._collision_alerts.get("Robot_2") == "BLOCKED"
