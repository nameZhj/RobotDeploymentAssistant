"""
@file: tests/unit/test_task03b_trajectory_compiler_adapter.py
@brief: 任务 03B TrajectoryCompiler 与 TrajectoryAsset 兼容适配单元测试
@exports: 测试用例函数集合
"""
import math
import pytest
from src.domain.trajectory.trajectory_asset import TrajectoryAsset, TrajectoryPoint
from src.domain.trajectory.trajectory_compiler import TrajectoryCompiler


def test_01_legacy_compile_waypoints_works():
    """1. 旧 compile_waypoints 接口继续正常工作，返回 (points, duration)"""
    wps = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0)]
    pts, dur = TrajectoryCompiler.compile_waypoints(
        wps, mode="uniform", max_acc=1.5, v_max=1.0, end_turn=True, end_turn_yaw=90.0
    )
    assert len(pts) > 5
    assert dur > 0.0
    assert pts[0][0] == 0.0
    assert abs(pts[-1][3] - 90.0) < 5.0


def test_02_legacy_parse_trajectory_data_works():
    """2. 旧 parse_trajectory_data 接口继续正常解析 CSV，并支持 JSON 格式"""
    csv_data = "0.00,0.0,0.0,0.0\n1.50,1.0,2.0,45.0\n3.00,3.0,2.0,90.0"
    pts = TrajectoryCompiler.parse_trajectory_data(csv_data)
    assert len(pts) == 3
    assert pts[1] == (1.5, 1.0, 2.0, 45.0)

    # JSON 兼容
    json_data = '[[0.0, 0.0, 0.0, 0.0], [2.0, 4.0, 5.0, 180.0]]'
    pts_json = TrajectoryCompiler.parse_trajectory_data(json_data)
    assert len(pts_json) == 2
    assert pts_json[1] == (2.0, 4.0, 5.0, 180.0)


def test_03_new_compile_asset_normal():
    """3. 新 TrajectoryAsset 编译正常，各字段正确输出"""
    sampled = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
        TrajectoryPoint(x_m=1.0, y_m=0.0, yaw_deg=10.0, s_m=1.0),
        TrajectoryPoint(x_m=2.0, y_m=0.0, yaw_deg=20.0, s_m=2.0),
    ]
    asset = TrajectoryAsset(
        trajectory_id="traj_asset_01",
        name="测试资产",
        control_points=[(0.0, 0.0), (2.0, 0.0)],
        sampled_points=sampled,
        length_m=2.0,
    )
    compiled, dur_s = TrajectoryCompiler.compile_asset(asset, duration_ms=4000)

    assert len(compiled) == 3
    assert dur_s == pytest.approx(4.0)
    assert compiled[0] == (0.0, 0.0, 0.0, 0.0)
    assert compiled[1] == (2.0, 1.0, 0.0, 10.0)
    assert compiled[2] == (4.0, 2.0, 0.0, 20.0)


def test_04_time_start_is_zero():
    """4. 时间起点严格从 0.0 开始"""
    sampled = [
        TrajectoryPoint(x_m=5.0, y_m=5.0, yaw_deg=30.0, s_m=0.0),
        TrajectoryPoint(x_m=8.0, y_m=9.0, yaw_deg=60.0, s_m=5.0),
    ]
    asset = TrajectoryAsset(
        trajectory_id="traj_start",
        name="起点测试",
        control_points=[(5.0, 5.0), (8.0, 9.0)],
        sampled_points=sampled,
        length_m=5.0,
    )
    compiled, _ = TrajectoryCompiler.compile_asset(asset, duration_ms=2500)
    assert compiled[0][0] == 0.0


def test_05_time_end_is_exact_duration():
    """5. 时间终点严格等于 duration_ms / 1000.0"""
    sampled = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
        TrajectoryPoint(x_m=3.0, y_m=4.0, yaw_deg=45.0, s_m=5.0),
    ]
    asset = TrajectoryAsset(
        trajectory_id="traj_end",
        name="终点测试",
        control_points=[(0.0, 0.0), (3.0, 4.0)],
        sampled_points=sampled,
        length_m=5.0,
    )
    compiled, dur_s = TrajectoryCompiler.compile_asset(asset, duration_ms=3750)
    assert compiled[-1][0] == pytest.approx(3.75)
    assert dur_s == pytest.approx(3.75)


def test_06_non_uniform_arc_length_mapping():
    """6. 非均匀弧长采样映射正确反映在时间轴上（按弧长比例分配时间）"""
    # 空间采样点: 0m(0%), 1m(20%), 5m(100%)
    sampled = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
        TrajectoryPoint(x_m=1.0, y_m=0.0, yaw_deg=0.0, s_m=1.0),
        TrajectoryPoint(x_m=5.0, y_m=0.0, yaw_deg=0.0, s_m=5.0),
    ]
    asset = TrajectoryAsset(
        trajectory_id="traj_non_uniform",
        name="非均匀点",
        control_points=[(0.0, 0.0), (5.0, 0.0)],
        sampled_points=sampled,
        length_m=5.0,
    )
    compiled, _ = TrajectoryCompiler.compile_asset(asset, duration_ms=10000)
    assert compiled[0][0] == 0.0
    assert compiled[1][0] == pytest.approx(2.0)  # 1/5 * 10s = 2s
    assert compiled[2][0] == pytest.approx(10.0)  # 5/5 * 10s = 10s


def test_07_duration_ms_zero_rejected():
    """7. duration_ms 为零时拒绝"""
    sampled = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
        TrajectoryPoint(x_m=1.0, y_m=0.0, yaw_deg=0.0, s_m=1.0),
    ]
    asset = TrajectoryAsset(
        trajectory_id="traj_z",
        name="零时长测试",
        control_points=[(0.0, 0.0), (1.0, 0.0)],
        sampled_points=sampled,
        length_m=1.0,
    )
    with pytest.raises(ValueError, match="duration_ms 必须大于 0"):
        TrajectoryCompiler.compile_asset(asset, duration_ms=0)


def test_08_duration_ms_negative_rejected():
    """8. 负 duration_ms 拒绝"""
    sampled = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
        TrajectoryPoint(x_m=1.0, y_m=0.0, yaw_deg=0.0, s_m=1.0),
    ]
    asset = TrajectoryAsset(
        trajectory_id="traj_neg",
        name="负时长测试",
        control_points=[(0.0, 0.0), (1.0, 0.0)],
        sampled_points=sampled,
        length_m=1.0,
    )
    with pytest.raises(ValueError, match="duration_ms 必须大于 0"):
        TrajectoryCompiler.compile_asset(asset, duration_ms=-1500)


def test_09_length_zero_rejected():
    """9. length_m 为零时拒绝编译"""
    asset = TrajectoryAsset(
        trajectory_id="traj_len_zero",
        name="零长草稿",
        control_points=[(1.0, 1.0)],
        sampled_points=[],
        length_m=0.0,
    )
    with pytest.raises(ValueError, match="轨迹长度 length_m 必须大于 0"):
        TrajectoryCompiler.compile_asset(asset, duration_ms=2000)


def test_10_yaw_not_confused_with_radians():
    """10. yaw 角度与弧度不发生混淆，输出保持角度制（如 90.0 而非 1.5708）"""
    sampled = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=90.0, s_m=0.0),
        TrajectoryPoint(x_m=0.0, y_m=2.0, yaw_deg=90.0, s_m=2.0),
    ]
    asset = TrajectoryAsset(
        trajectory_id="traj_yaw_deg",
        name="朝向角度制测试",
        control_points=[(0.0, 0.0), (0.0, 2.0)],
        sampled_points=sampled,
        length_m=2.0,
    )
    compiled, _ = TrajectoryCompiler.compile_asset(asset, duration_ms=2000)
    for p in compiled:
        assert p[3] == pytest.approx(90.0)
        assert abs(p[3] - math.pi / 2.0) > 10.0  # 绝不是弧度 1.57


def test_11_legacy_timestamps_not_used_as_arc_length():
    """11. 旧轨迹时间信息不被误当成弧长，而是通过空间欧氏几何距离计算 s_m"""
    # 历史数据: t=0s, (0,0); t=100s(大时间), 空间移动到 (3,4) (欧氏距离=5m)
    legacy_pts = [
        (0.0, 0.0, 0.0, 0.0),
        (100.0, 3.0, 4.0, 45.0),
    ]
    asset = TrajectoryCompiler.to_trajectory_asset(legacy_pts, trajectory_id="test_legacy")
    # 弧长必须等于 5.0m (sqrt(3^2 + 4^2))，绝不是 t=100.0!
    assert asset.length_m == pytest.approx(5.0)
    assert asset.sampled_points[-1].s_m == pytest.approx(5.0)
    assert asset.sampled_points[-1].s_m != pytest.approx(100.0)


def test_12_original_trajectory_asset_not_mutated():
    """12. 编译过程不得篡改原始 TrajectoryAsset 实例及其内部点集"""
    sampled = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
        TrajectoryPoint(x_m=1.0, y_m=1.0, yaw_deg=45.0, s_m=1.414),
    ]
    asset = TrajectoryAsset(
        trajectory_id="traj_immutable",
        name="不可变测试",
        control_points=[(0.0, 0.0), (1.0, 1.0)],
        sampled_points=sampled,
        length_m=1.414,
    )
    _ = TrajectoryCompiler.compile_asset(asset, duration_ms=5000)

    assert asset.length_m == 1.414
    assert len(asset.sampled_points) == 2
    assert asset.sampled_points[0].s_m == 0.0
    assert asset.sampled_points[1].s_m == 1.414
