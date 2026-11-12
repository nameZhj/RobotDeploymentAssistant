"""
@file: tests/unit/test_stage_director_preview_sampling.py
@brief: StagePreviewCoordinator 统一播放时钟 Tick 响应、Seek 一致性与确定性测试
@exports: test_coordinator_tick_dispatch, test_coordinator_seek_repeatability
"""
import sys
import pytest
from PySide6.QtWidgets import QApplication
from src.application.stage_director.stage_preview_coordinator import StagePreviewCoordinator


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def coordinator(qapp):
    return StagePreviewCoordinator()


def test_coordinator_tick_dispatch(coordinator):
    """验证统一播放时钟 Tick 驱动下多机器人姿态与碰撞结果广播"""
    dispatched_poses = {}
    diagnosed_info = {}

    coordinator.posesUpdated.connect(lambda p: dispatched_poses.update(p))
    coordinator.collisionDiagnosed.connect(lambda d: diagnosed_info.update(d))

    coordinator.on_player_tick(2500)

    assert "Robot_1" in dispatched_poses
    assert "Robot_2" in dispatched_poses
    assert dispatched_poses["Robot_1"].timestamp_s == 2.5
    assert "status" in diagnosed_info


def test_coordinator_seek_repeatability(coordinator):
    """验证 Seek 拖动前后在相同时间戳产生绝对一致的位姿采样"""
    poses_a = coordinator.sample_at_time(3000)
    # 模拟时间轴向前再向后 seek 回 3000ms
    _ = coordinator.sample_at_time(5000)
    _ = coordinator.sample_at_time(1000)
    poses_b = coordinator.sample_at_time(3000)

    assert poses_a["Robot_1"].x == poses_b["Robot_1"].x
    assert poses_a["Robot_1"].y == poses_b["Robot_1"].y
    assert poses_a["Robot_1"].yaw_deg == poses_b["Robot_1"].yaw_deg
    assert poses_a["Robot_2"].x == poses_b["Robot_2"].x
