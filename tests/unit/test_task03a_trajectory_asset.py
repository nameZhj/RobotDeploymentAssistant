"""
@file: tests/unit/test_task03a_trajectory_asset.py
@brief: 任务 03A TrajectoryAsset 统一轨迹领域模型与采样点单元测试
@exports: 测试用例函数集合
"""
import math
import time
import pytest
from src.domain.trajectory.trajectory_asset import (
    ARC_LENGTH_TOLERANCE,
    TrajectoryAsset,
    TrajectoryPoint,
    normalize_angle_deg,
)


def test_01_normal_trajectory_creation():
    """1. 正常轨迹创建与 committable 状态验证"""
    pts = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
        TrajectoryPoint(x_m=1.0, y_m=0.0, yaw_deg=0.0, s_m=1.0),
        TrajectoryPoint(x_m=2.0, y_m=1.0, yaw_deg=45.0, s_m=2.414),
    ]
    asset = TrajectoryAsset(
        trajectory_id="traj_001",
        name="主舞台进场弧线",
        coordinate_frame="stage_world",
        control_points=[(0.0, 0.0), (1.0, 0.0), (2.0, 1.0)],
        sampled_points=pts,
        length_m=2.414,
        recommended_speed_mps=0.8,
        spline_type="catmull_rom",
    )
    assert asset.trajectory_id == "traj_001"
    assert asset.name == "主舞台进场弧线"
    assert asset.length_m == pytest.approx(2.414, abs=1e-3)
    assert asset.is_draft() is True
    assert asset.is_committable() is True


def test_02_single_control_point_draft():
    """2. 单控制点 Draft 允许保存，但不能标记为可提交运动轨迹"""
    draft = TrajectoryAsset(
        trajectory_id="traj_draft_01",
        name="未完成起跳草稿",
        control_points=[(0.5, 1.2)],
        sampled_points=[],
        length_m=0.0,
    )
    assert draft.is_draft() is True
    assert draft.is_committable() is False


def test_03_empty_control_points_rejected():
    """3. 空控制点拒绝"""
    with pytest.raises(ValueError, match="control_points 不能为空"):
        TrajectoryAsset(
            trajectory_id="traj_empty",
            name="空轨迹",
            control_points=[],
        )


def test_04_nan_infinity_rejected():
    """4. NaN/Infinity 坐标、角度、弧长拒绝"""
    with pytest.raises(ValueError, match="禁止为 NaN 或 Infinity"):
        TrajectoryPoint(x_m=float("nan"), y_m=1.0, yaw_deg=0.0, s_m=0.0)

    with pytest.raises(ValueError, match="禁止为 NaN 或 Infinity"):
        TrajectoryPoint(x_m=1.0, y_m=float("inf"), yaw_deg=0.0, s_m=0.0)

    with pytest.raises(ValueError, match="禁止为 NaN 或 Infinity"):
        TrajectoryAsset(
            trajectory_id="traj_nan",
            name="NaN轨迹",
            control_points=[(0.0, 0.0), (float("nan"), 1.0)],
        )

    with pytest.raises(ValueError, match="禁止为 NaN 或 Infinity"):
        TrajectoryAsset(
            trajectory_id="traj_inf_len",
            name="Inf长",
            control_points=[(0.0, 0.0), (1.0, 1.0)],
            length_m=float("inf"),
        )


def test_05_string_coordinates_rejected():
    """5. 字符串坐标严格拒绝，杜绝隐式类型污染"""
    with pytest.raises(TypeError, match="必须为浮点数或整数"):
        TrajectoryPoint(x_m="1.23", y_m=0.0, yaw_deg=0.0, s_m=0.0)

    with pytest.raises(TypeError, match="必须为浮点数或整数"):
        TrajectoryAsset(
            trajectory_id="traj_str",
            name="字符串点",
            control_points=[("0.0", "1.0")],
        )


def test_06_negative_arc_length_rejected():
    """6. 负弧长及负速度拒绝"""
    with pytest.raises(ValueError, match="禁止为负数"):
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=-0.5)

    with pytest.raises(ValueError, match="禁止为负数"):
        TrajectoryAsset(
            trajectory_id="traj_neg_v",
            name="负速度",
            control_points=[(0.0, 0.0), (1.0, 1.0)],
            recommended_speed_mps=-1.0,
        )


def test_07_arc_length_decrease_rejected():
    """7. 采样点弧长不连续或倒退拒绝"""
    pts = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
        TrajectoryPoint(x_m=1.0, y_m=0.0, yaw_deg=0.0, s_m=1.0),
        TrajectoryPoint(x_m=0.5, y_m=0.0, yaw_deg=0.0, s_m=0.8),  # 倒退
    ]
    with pytest.raises(ValueError, match="采样点弧长 s_m 必须非递减"):
        TrajectoryAsset(
            trajectory_id="traj_decrease",
            name="倒退弧长",
            control_points=[(0.0, 0.0), (1.0, 0.0)],
            sampled_points=pts,
            length_m=1.0,
        )


def test_08_yaw_normalization_across_180():
    """8. yaw 跨越 180° 的规范化至 [-180.0, 180.0)"""
    assert normalize_angle_deg(0.0) == 0.0
    assert normalize_angle_deg(90.0) == 90.0
    assert normalize_angle_deg(180.0) == -180.0
    assert normalize_angle_deg(190.0) == pytest.approx(-170.0)
    assert normalize_angle_deg(360.0) == 0.0
    assert normalize_angle_deg(540.0) == -180.0
    assert normalize_angle_deg(-200.0) == pytest.approx(160.0)
    assert normalize_angle_deg(-270.0) == pytest.approx(90.0)

    # 通过 Point 初始化自动规范化
    pt = TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=210.0, s_m=0.0)
    assert pt.yaw_deg == pytest.approx(-150.0)


def test_09_length_and_final_arc_mismatch_rejected():
    """9. length_m 与最后一个 s_m 不一致时严格拒绝"""
    pts = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
        TrajectoryPoint(x_m=2.0, y_m=0.0, yaw_deg=0.0, s_m=2.0),
    ]
    with pytest.raises(ValueError, match="与最终采样点弧长 .* 不一致"):
        TrajectoryAsset(
            trajectory_id="traj_mismatch",
            name="长度不匹配",
            control_points=[(0.0, 0.0), (2.0, 0.0)],
            sampled_points=pts,
            length_m=3.5,  # 错误长度
        )


def test_10_dict_serialization_roundtrip():
    """10. 字典序列化与反序列化往返一致性"""
    pts = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=10.0, s_m=0.0),
        TrajectoryPoint(x_m=1.5, y_m=2.0, yaw_deg=190.0, s_m=2.5),
    ]
    asset = TrajectoryAsset(
        trajectory_id="traj_rt_01",
        name="回环测试轨迹",
        coordinate_frame="stage_world",
        control_points=[(0.0, 0.0), (1.5, 2.0)],
        sampled_points=pts,
        length_m=2.5,
        recommended_speed_mps=0.6,
        spline_type="bezier",
    )
    d = asset.to_dict()
    restored = TrajectoryAsset.from_dict(d)

    assert restored.trajectory_id == asset.trajectory_id
    assert restored.name == asset.name
    assert restored.coordinate_frame == asset.coordinate_frame
    assert restored.control_points == asset.control_points
    assert len(restored.sampled_points) == len(asset.sampled_points)
    for p1, p2 in zip(restored.sampled_points, asset.sampled_points):
        assert p1.x_m == pytest.approx(p2.x_m)
        assert p1.y_m == pytest.approx(p2.y_m)
        assert p1.yaw_deg == pytest.approx(p2.yaw_deg)
        assert p1.s_m == pytest.approx(p2.s_m)
    assert restored.length_m == pytest.approx(asset.length_m)
    assert restored.recommended_speed_mps == pytest.approx(asset.recommended_speed_mps)
    assert restored.spline_type == asset.spline_type


def test_11_large_point_set_performance():
    """11. 10,000 级超大点集的基础性能和内存行为验证（执行耗时应 < 0.2s）"""
    t0 = time.perf_counter()
    n_pts = 10000
    step = 0.01
    large_pts = [
        TrajectoryPoint(x_m=i * step, y_m=0.0, yaw_deg=float(i % 360), s_m=i * step)
        for i in range(n_pts)
    ]
    total_len = (n_pts - 1) * step
    asset = TrajectoryAsset(
        trajectory_id="traj_perf_10k",
        name="高密点集性能测试",
        control_points=[(0.0, 0.0), (total_len, 0.0)],
        sampled_points=large_pts,
        length_m=total_len,
    )
    d = asset.to_dict()
    restored = TrajectoryAsset.from_dict(d)
    elapsed = time.perf_counter() - t0

    assert len(restored.sampled_points) == n_pts
    assert elapsed < 0.2, f"10k 点集校验反序列化耗时过高: {elapsed:.4f}s"
