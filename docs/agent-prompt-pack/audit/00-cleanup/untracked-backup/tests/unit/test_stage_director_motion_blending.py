"""
@file: tests/unit/test_stage_director_motion_blending.py
@brief: 双层时间轴轨迹走位根节点移动与舞蹈动作姿态波形融合测试
@exports: test_trajectory_root_interpolation, test_dance_waveform_resolution, test_multi_robot_isolation
"""
import pytest
from src.domain.simulation.stage_performance_sampler import StagePerformanceSampler


@pytest.fixture
def sampler():
    return StagePerformanceSampler()


def test_trajectory_root_interpolation(sampler):
    """验证下层轨迹片段线性时间插值计算世界位置与朝向"""
    blocks = [{
        "start_s": 1.0,
        "duration_s": 4.0,
        "points": [(0.0, 0.0), (4.0, 0.0)]
    }]

    # At t=0.5 (before start): initial point
    p_before = sampler.sample_robot_pose("Robot_1", 0.5, blocks, [])
    assert p_before.x == 0.0 and p_before.y == 0.0

    # At t=3.0 (halfway: progress = (3.0-1.0)/4.0 = 0.5): x=2.0
    p_mid = sampler.sample_robot_pose("Robot_1", 3.0, blocks, [])
    assert pytest.approx(p_mid.x, abs=1e-2) == 2.0
    assert pytest.approx(p_mid.y, abs=1e-2) == 0.0


def test_dance_waveform_resolution(sampler):
    """验证上层动作片段根据名称与时刻解析出对应的关节角字典"""
    action_blocks = [{
        "name": "POPPING1",
        "start_s": 0.0,
        "duration_s": 3.0
    }]
    state = sampler.sample_robot_pose("Robot_1", 1.5, [], action_blocks)
    assert len(state.joint_angles) > 0
    assert "left_elbow_joint" in state.joint_angles or "waist_yaw_joint" in state.joint_angles


def test_multi_robot_isolation(sampler):
    """验证多机器人姿态独立隔离，互不串扰"""
    r1_blocks = [{"start_s": 0.0, "duration_s": 2.0, "points": [(-2.0, 0.0), (-2.0, 2.0)]}]
    r2_blocks = [{"start_s": 0.0, "duration_s": 2.0, "points": [(2.0, 0.0), (2.0, -2.0)]}]

    s1 = sampler.sample_robot_pose("Robot_1", 1.0, r1_blocks, [])
    s2 = sampler.sample_robot_pose("Robot_2", 1.0, r2_blocks, [])

    assert pytest.approx(s1.x, abs=1e-2) == -2.0
    assert pytest.approx(s2.x, abs=1e-2) == 2.0
    assert s1.robot_alias != s2.robot_alias
