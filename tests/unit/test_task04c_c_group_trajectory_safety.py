"""
@file: tests/unit/test_task04c_c_group_trajectory_safety.py
@brief: 任务 04C-C 机器人群组轨迹几何安全检测与舞台边界校验单元测试
@exports: 测试用例函数集合
"""
import copy
import math
import pytest

from src.domain.trajectory.group_trajectory_compiler import GroupMemberTrajectory
from src.domain.trajectory.group_trajectory_safety import (
    BoundaryViolation,
    GroupTrajectorySafetyReport,
    GroupTrajectorySafetyValidator,
    PairwiseClearance,
    validate_group_trajectory_safety,
)
from src.domain.trajectory.trajectory_asset import TrajectoryPoint


def _make_member_traj(
    robot_id: str,
    coords: list,
    coordinate_frame: str = "stage_world",
) -> GroupMemberTrajectory:
    """辅助构造 GroupMemberTrajectory 对象。"""
    pts = []
    acc_s = 0.0
    for i, c in enumerate(coords):
        x, y = float(c[0]), float(c[1])
        yaw = float(c[2]) if len(c) > 2 else 0.0
        if i > 0:
            acc_s += math.hypot(x - coords[i - 1][0], y - coords[i - 1][1])
        pts.append(TrajectoryPoint(x_m=x, y_m=y, yaw_deg=yaw, s_m=acc_s))
    return GroupMemberTrajectory(
        robot_id=robot_id,
        reference_trajectory_id="ref_01",
        coordinate_frame=coordinate_frame,
        sampled_points=tuple(pts),
        length_m=acc_s,
    )


def test_01_insufficient_or_single_robot_rejected():
    """1. 单机器人输入或成员数不足拒绝检测。"""
    t1 = _make_member_traj("R1", [(0, 0), (2, 0)])
    with pytest.raises(ValueError, match="至少需要包含 2 个机器人成员"):
        validate_group_trajectory_safety([t1])

    with pytest.raises(ValueError, match="至少需要包含 2 个机器人成员"):
        validate_group_trajectory_safety([])


def test_02_parallel_paths_with_large_clearance_safe():
    """2. 两条平行路径，间距大于安全阈值（1.0m > 0.6m），报告为安全。"""
    t1 = _make_member_traj("R1", [(0, 0), (5, 0)])
    t2 = _make_member_traj("R2", [(0, 1.0), (5, 1.0)])

    report = validate_group_trajectory_safety([t1, t2], required_clearance_m=0.6)
    assert report.is_safe is True
    assert report.violation_count == 0
    assert len(report.pairwise_clearances) == 1
    assert report.pairwise_clearances[0].min_distance_m == pytest.approx(1.0)
    assert report.pairwise_clearances[0].is_clear is True


def test_03_parallel_paths_with_small_clearance_violation():
    """3. 两条平行路径，间距小于安全阈值（0.4m < 0.6m），触发违规报警。"""
    t1 = _make_member_traj("R1", [(0, 0), (5, 0)])
    t2 = _make_member_traj("R2", [(0, 0.4), (5, 0.4)])

    report = validate_group_trajectory_safety([t1, t2], required_clearance_m=0.6)
    assert report.is_safe is False
    assert report.violation_count == 1
    assert report.pairwise_clearances[0].min_distance_m == pytest.approx(0.4)
    assert report.pairwise_clearances[0].is_clear is False


def test_04_perpendicular_intersecting_paths():
    """4. 两条路径垂直相交，最小距离为 0，触发违规。"""
    t_h = _make_member_traj("R_H", [(-2, 0), (2, 0)])
    t_v = _make_member_traj("R_V", [(0, -2), (0, 2)])

    report = validate_group_trajectory_safety([t_h, t_v], required_clearance_m=0.6)
    assert report.is_safe is False
    assert report.pairwise_clearances[0].min_distance_m == pytest.approx(0.0)
    assert report.pairwise_clearances[0].is_clear is False


def test_05_endpoints_touching():
    """5. 两条路径仅端点接触，最小距离为 0。"""
    t1 = _make_member_traj("R1", [(0, 0), (2, 0)])
    t2 = _make_member_traj("R2", [(2, 0), (4, 2)])

    report = validate_group_trajectory_safety([t1, t2], required_clearance_m=0.5)
    assert report.is_safe is False
    assert report.pairwise_clearances[0].min_distance_m == pytest.approx(0.0)


def test_06_collinear_partially_overlapping():
    """6. 两条路径部分共线重叠，最小距离为 0。"""
    t1 = _make_member_traj("R1", [(0, 0), (3, 0)])
    t2 = _make_member_traj("R2", [(2, 0), (5, 0)])

    report = validate_group_trajectory_safety([t1, t2], required_clearance_m=0.5)
    assert report.is_safe is False
    assert report.pairwise_clearances[0].min_distance_m == pytest.approx(0.0)


def test_07_endpoints_far_apart_but_segments_cross_in_middle():
    """7. 采样点端点相距较远，但线段中间交叉，线段距离精确计算为 0。"""
    # 端点 (-10, -10) 到 (-10, 10) 距离为 20，但两线段在 (0, 0) 交叉
    t1 = _make_member_traj("R1", [(-10, -10), (10, 10)])
    t2 = _make_member_traj("R2", [(-10, 10), (10, -10)])

    report = validate_group_trajectory_safety([t1, t2], required_clearance_m=0.6)
    assert report.is_safe is False
    assert report.pairwise_clearances[0].min_distance_m == pytest.approx(0.0)


def test_08_degenerate_zero_length_segment():
    """8. 包含零长度退化线段时正确计算，无除零崩溃。"""
    t1 = _make_member_traj("R1", [(0, 0), (0, 0), (2, 0)])
    t2 = _make_member_traj("R2", [(0, 1), (2, 1)])

    report = validate_group_trajectory_safety([t1, t2], required_clearance_m=0.6)
    assert report.is_safe is True
    assert report.pairwise_clearances[0].min_distance_m == pytest.approx(1.0)


def test_09_all_trajectories_within_bounds():
    """9. 舞台边界内的轨迹全部通过，边界违规为空。"""
    t1 = _make_member_traj("R1", [(-40, -40), (40, 40)])
    t2 = _make_member_traj("R2", [(-40, -35), (40, 45)])

    report = validate_group_trajectory_safety([t1, t2], stage_bounds=(-50, 50, -50, 50))
    assert len(report.boundary_violations) == 0


def test_10_x_axis_boundary_violations():
    """10. 超出 X 轴边界的点被精准识别并记录违规信息。"""
    t1 = _make_member_traj("R_OverX", [(0, 0), (55.0, 10.0), (-52.0, 5.0)])
    t2 = _make_member_traj("R_Normal", [(0, 0), (10, 10), (20, 20)])

    report = validate_group_trajectory_safety([t1, t2], stage_bounds=(-50.0, 50.0, -50.0, 50.0))
    assert len(report.boundary_violations) == 2

    v1 = report.boundary_violations[0]
    assert v1.robot_id == "R_OverX"
    assert v1.point_index == 1
    assert v1.x_m == pytest.approx(55.0)
    assert v1.boundary == "x_max"

    v2 = report.boundary_violations[1]
    assert v2.robot_id == "R_OverX"
    assert v2.point_index == 2
    assert v2.x_m == pytest.approx(-52.0)
    assert v2.boundary == "x_min"


def test_11_y_axis_boundary_violations():
    """11. 超出 Y 轴边界的点被精准识别。"""
    t1 = _make_member_traj("R_OverY", [(0, 0), (10.0, 52.0), (10.0, -55.0)])
    t2 = _make_member_traj("R_Normal", [(0, 0), (10, 10), (20, 20)])

    report = validate_group_trajectory_safety([t1, t2], stage_bounds=(-50.0, 50.0, -50.0, 50.0))
    assert len(report.boundary_violations) == 2
    assert report.boundary_violations[0].boundary == "y_max"
    assert report.boundary_violations[1].boundary == "y_min"


def test_12_points_on_boundary_are_valid():
    """12. 正好落在舞台边界上的点视为合法。"""
    t1 = _make_member_traj("R1", [(-50.0, -50.0), (50.0, 50.0)])
    t2 = _make_member_traj("R2", [(-50.0, 0.0), (50.0, 0.0)])

    report = validate_group_trajectory_safety([t1, t2], stage_bounds=(-50.0, 50.0, -50.0, 50.0))
    assert len(report.boundary_violations) == 0


def test_13_three_robots_pairwise_screening():
    """13. 三机器人完整两两检测 (A-B, A-C, B-C)。"""
    t_a = _make_member_traj("A", [(0, 0), (5, 0)])
    t_b = _make_member_traj("B", [(0, 1), (5, 1)])
    t_c = _make_member_traj("C", [(0, 3), (5, 3)])

    report = validate_group_trajectory_safety([t_a, t_b, t_c], required_clearance_m=0.8)
    assert len(report.pairwise_clearances) == 3

    pairs = [(c.robot_id_a, c.robot_id_b) for c in report.pairwise_clearances]
    assert pairs == [("A", "B"), ("A", "C"), ("B", "C")]

    # A-B 间距 1.0 >= 0.8
    # A-C 间距 3.0 >= 0.8
    # B-C 间距 2.0 >= 0.8
    assert all(c.is_clear for c in report.pairwise_clearances)
    assert report.is_safe is True


def test_14_violation_report_has_correct_segment_indices():
    """14. 违规报告记录精准的线段索引段。"""
    # t1 有 3 个段：0: (0,0)->(2,0), 1: (2,0)->(4,0), 2: (4,0)->(6,0)
    # t2 在 x=3 处穿过 t1 (位于 t1 的段 1)
    t1 = _make_member_traj("R1", [(0, 0), (2, 0), (4, 0), (6, 0)])
    t2 = _make_member_traj("R2", [(3, -2), (3, 2)])

    report = validate_group_trajectory_safety([t1, t2], required_clearance_m=0.5)
    c = report.pairwise_clearances[0]
    assert c.is_clear is False
    assert c.segment_index_a == 1
    assert c.segment_index_b == 0


def test_15_different_clearance_thresholds():
    """15. 不同安全阈值对相同轨迹产生正确的判定分流。"""
    t1 = _make_member_traj("R1", [(0, 0), (5, 0)])
    t2 = _make_member_traj("R2", [(0, 0.5), (5, 0.5)])

    # 阈值 0.4m -> 安全
    rep_safe = validate_group_trajectory_safety([t1, t2], required_clearance_m=0.4)
    assert rep_safe.is_safe is True

    # 阈值 0.6m -> 不安全
    rep_unsafe = validate_group_trajectory_safety([t1, t2], required_clearance_m=0.6)
    assert rep_unsafe.is_safe is False


def test_16_reject_invalid_inputs():
    """16. NaN/Inf、重复 ID、非法阈值及非法边界明确被拒绝。"""
    t1 = _make_member_traj("R1", [(0, 0), (5, 0)])
    t2 = _make_member_traj("R2", [(0, 1), (5, 1)])

    # 重复 robot_id
    t_dup = _make_member_traj("R1", [(0, 2), (5, 2)])
    with pytest.raises(ValueError, match="检测到重复的 robot_id"):
        validate_group_trajectory_safety([t1, t_dup])

    # 负数安全阈值
    with pytest.raises(ValueError, match="安全距离阈值不能为负数"):
        validate_group_trajectory_safety([t1, t2], required_clearance_m=-0.1)

    # 坐标系不一致
    t_other_frame = _make_member_traj("R3", [(0, 1), (5, 1)], coordinate_frame="local_frame")
    with pytest.raises(ValueError, match="坐标系不一致"):
        validate_group_trajectory_safety([t1, t_other_frame])

    # 无效边界 (min >= max)
    with pytest.raises(ValueError, match="最小值必须严格小于最大值"):
        validate_group_trajectory_safety([t1, t2], stage_bounds=(50, -50, -50, 50))


def test_17_input_trajectories_immutable():
    """17. 校验过程绝对不修改输入轨迹对象。"""
    t1 = _make_member_traj("R1", [(0, 0), (5, 0)])
    t2 = _make_member_traj("R2", [(0, 1), (5, 1)])
    dict1_before = t1.to_dict()
    dict2_before = t2.to_dict()

    validate_group_trajectory_safety([t1, t2])

    assert t1.to_dict() == dict1_before
    assert t2.to_dict() == dict2_before


def test_18_deterministic_repeated_validation():
    """18. 相同输入多次校验结果完全一致。"""
    t1 = _make_member_traj("R1", [(0, 0), (5, 0)])
    t2 = _make_member_traj("R2", [(0, 0.4), (5, 0.4)])

    rep1 = validate_group_trajectory_safety([t1, t2], required_clearance_m=0.6)
    rep2 = validate_group_trajectory_safety([t1, t2], required_clearance_m=0.6)

    assert rep1.to_dict() == rep2.to_dict()


def test_19_safety_report_serialization_roundtrip():
    """19. 安全报告序列化与反序列化往返一致。"""
    t1 = _make_member_traj("R1", [(0, 0), (60.0, 0)])
    t2 = _make_member_traj("R2", [(0, 0.3), (60.0, 0.3)])

    rep = validate_group_trajectory_safety([t1, t2], required_clearance_m=0.6)
    d = rep.to_dict()

    assert "is_safe" in d
    assert "boundary_violations" in d
    assert "pairwise_clearances" in d
    assert "violation_count" in d

    restored = GroupTrajectorySafetyReport.from_dict(d)
    assert restored.is_safe == rep.is_safe
    assert restored.violation_count == rep.violation_count
    assert len(restored.boundary_violations) == len(rep.boundary_violations)
    assert len(restored.pairwise_clearances) == len(rep.pairwise_clearances)
    assert restored.to_dict() == d
