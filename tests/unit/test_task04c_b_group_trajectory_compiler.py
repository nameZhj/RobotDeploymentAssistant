"""
@file: tests/unit/test_task04c_b_group_trajectory_compiler.py
@brief: 任务 04C-B 机器人群组轨迹几何变换与独立弧长计算单元测试
@exports: 测试用例函数集合
"""
import copy
import math
import pytest

from src.domain.trajectory.group_trajectory import GroupTrajectory, GroupTrajectoryMember
from src.domain.trajectory.group_trajectory_compiler import (
    GroupMemberTrajectory,
    GroupTrajectoryCompiler,
    compile_group_trajectory,
)
from src.domain.trajectory.trajectory_asset import TrajectoryAsset, TrajectoryPoint


def _make_straight_x_asset(trajectory_id: str = "traj_x") -> TrajectoryAsset:
    """构造沿 X 轴正方向前进的参考轨迹素材 (0,0) -> (4,0)，yaw=0度。"""
    pts = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
        TrajectoryPoint(x_m=2.0, y_m=0.0, yaw_deg=0.0, s_m=2.0),
        TrajectoryPoint(x_m=4.0, y_m=0.0, yaw_deg=0.0, s_m=4.0),
    ]
    return TrajectoryAsset(
        trajectory_id=trajectory_id,
        name="直行X参考轨迹",
        coordinate_frame="stage_world",
        control_points=[(0.0, 0.0), (4.0, 0.0)],
        sampled_points=pts,
        length_m=4.0,
    )


def _make_straight_y_asset(trajectory_id: str = "traj_y") -> TrajectoryAsset:
    """构造沿 Y 轴正方向前进的参考轨迹素材 (0,0) -> (0,4)，yaw=90度。"""
    pts = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=90.0, s_m=0.0),
        TrajectoryPoint(x_m=0.0, y_m=2.0, yaw_deg=90.0, s_m=2.0),
        TrajectoryPoint(x_m=0.0, y_m=4.0, yaw_deg=90.0, s_m=4.0),
    ]
    return TrajectoryAsset(
        trajectory_id=trajectory_id,
        name="直行Y参考轨迹",
        coordinate_frame="stage_world",
        control_points=[(0.0, 0.0), (0.0, 4.0)],
        sampled_points=pts,
        length_m=4.0,
    )


def test_01_reference_path_x_axis_positive_tangent_and_normal():
    """1. 参考路径沿 X 轴正向，验证正纵向 (前进) 与正横向 (左侧法线) 偏移。"""
    ref = _make_straight_x_asset("traj_01")
    m1 = GroupTrajectoryMember(robot_id="R1", offset_x_m=1.0, offset_y_m=0.5, delta_yaw_deg=0.0)
    m2 = GroupTrajectoryMember(robot_id="R2", offset_x_m=-0.5, offset_y_m=-0.5, delta_yaw_deg=0.0)
    group = GroupTrajectory("grp_01", "测试群组", "traj_01", members=(m1, m2))

    res = compile_group_trajectory(group, ref)
    assert len(res) == 2

    # R1: theta=0度，cos=1, sin=0。
    # x_world = x + dx = x + 1.0; y_world = y + dy = y + 0.5 (沿 +Y 左侧法线)
    r1_pts = res[0].sampled_points
    assert r1_pts[0].x_m == pytest.approx(1.0)
    assert r1_pts[0].y_m == pytest.approx(0.5)
    assert r1_pts[1].x_m == pytest.approx(3.0)
    assert r1_pts[1].y_m == pytest.approx(0.5)
    assert r1_pts[2].x_m == pytest.approx(5.0)
    assert r1_pts[2].y_m == pytest.approx(0.5)
    assert res[0].length_m == pytest.approx(4.0)


def test_02_reference_path_y_axis_left_normal_direction():
    """2. 参考路径沿 Y 轴正向 (yaw=90°)，验证左侧法线方向为 -X。"""
    ref = _make_straight_y_asset("traj_02")
    m1 = GroupTrajectoryMember(robot_id="R1", offset_x_m=1.0, offset_y_m=0.5, delta_yaw_deg=0.0)
    m2 = GroupTrajectoryMember(robot_id="R2", offset_x_m=0.0, offset_y_m=0.0, delta_yaw_deg=0.0)
    group = GroupTrajectory("grp_02", "测试群组", "traj_02", members=(m1, m2))

    res = compile_group_trajectory(group, ref)
    r1_pts = res[0].sampled_points

    # yaw=90度: cos=0, sin=1
    # x_world = x + dx*0 - dy*1 = x - dy = 0 - 0.5 = -0.5 (朝向 +Y 前进时，左侧为 -X 轴)
    # y_world = y + dx*1 + dy*0 = y + dx = y + 1.0 (沿 +Y 轴前进方向纵向超前)
    assert r1_pts[0].x_m == pytest.approx(-0.5)
    assert r1_pts[0].y_m == pytest.approx(1.0)
    assert r1_pts[2].x_m == pytest.approx(-0.5)
    assert r1_pts[2].y_m == pytest.approx(5.0)
    assert res[0].length_m == pytest.approx(4.0)


def test_03_reference_path_45_degrees_rotation_matrix():
    """3. 参考路径为 45 度方向，验证刚性旋转矩阵计算正确性。"""
    c45 = math.sqrt(2.0) / 2.0
    pts = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=45.0, s_m=0.0),
        TrajectoryPoint(x_m=2.0 * c45, y_m=2.0 * c45, yaw_deg=45.0, s_m=2.0),
    ]
    ref = TrajectoryAsset(
        trajectory_id="traj_45",
        name="45度斜线",
        coordinate_frame="stage_world",
        control_points=[(0.0, 0.0), (2.0 * c45, 2.0 * c45)],
        sampled_points=pts,
        length_m=2.0,
    )

    m1 = GroupTrajectoryMember(robot_id="R1", offset_x_m=1.0, offset_y_m=1.0, delta_yaw_deg=0.0)
    m2 = GroupTrajectoryMember(robot_id="R2", offset_x_m=0.0, offset_y_m=0.0, delta_yaw_deg=0.0)
    group = GroupTrajectory("grp_45", "45度群组", "traj_45", members=(m1, m2))

    res = compile_group_trajectory(group, ref)
    r1_pts = res[0].sampled_points

    # dx=1, dy=1:
    # x_world = 0 + 1*c45 - 1*c45 = 0.0
    # y_world = 0 + 1*c45 + 1*c45 = 2*c45 = sqrt(2) ≈ 1.41421356
    assert r1_pts[0].x_m == pytest.approx(0.0, abs=1e-6)
    assert r1_pts[0].y_m == pytest.approx(math.sqrt(2.0), abs=1e-6)
    assert res[0].length_m == pytest.approx(2.0, abs=1e-6)


def test_04_multiple_members_different_offsets_no_pollution():
    """4. 两个成员采用不同偏移，结果位置不同且对象互不污染。"""
    ref = _make_straight_x_asset("traj_04")
    m1 = GroupTrajectoryMember(robot_id="R_Left", offset_x_m=0.0, offset_y_m=1.5)
    m2 = GroupTrajectoryMember(robot_id="R_Right", offset_x_m=0.0, offset_y_m=-1.5)
    group = GroupTrajectory("grp_04", "分道群组", "traj_04", members=(m1, m2))

    res = compile_group_trajectory(group, ref)
    r1, r2 = res[0], res[1]

    assert r1.robot_id == "R_Left"
    assert r2.robot_id == "R_Right"
    assert r1.sampled_points[0].y_m == pytest.approx(1.5)
    assert r2.sampled_points[0].y_m == pytest.approx(-1.5)
    assert r1.sampled_points is not r2.sampled_points


def test_05_delta_yaw_deg_positive_negative_and_normalization():
    """5. delta_yaw_deg 正负角度计算及角度规范化测试。"""
    pts = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=150.0, s_m=0.0),
        TrajectoryPoint(x_m=-1.0, y_m=0.0, yaw_deg=-170.0, s_m=1.0),
    ]
    ref = TrajectoryAsset(
        trajectory_id="traj_yaw",
        name="大角度轨迹",
        control_points=[(0.0, 0.0), (-1.0, 0.0)],
        sampled_points=pts,
        length_m=1.0,
    )
    # 150 + 50 = 200 -> -160度
    # -170 + (-20) = -190 -> 170度
    m1 = GroupTrajectoryMember(robot_id="R1", delta_yaw_deg=50.0)
    m2 = GroupTrajectoryMember(robot_id="R2", delta_yaw_deg=-20.0)
    group = GroupTrajectory("grp_yaw", "偏航测试群组", "traj_yaw", members=(m1, m2))

    res = compile_group_trajectory(group, ref)
    assert res[0].sampled_points[0].yaw_deg == pytest.approx(-160.0, abs=1e-9)
    assert res[1].sampled_points[1].yaw_deg == pytest.approx(170.0, abs=1e-9)


def test_06_zero_offset_matches_reference_geometry():
    """6. 零偏移时，输出位置、朝向及弧长与参考轨迹完全一致。"""
    ref = _make_straight_x_asset("traj_06")
    m1 = GroupTrajectoryMember(robot_id="R_Zero1", offset_x_m=0.0, offset_y_m=0.0, delta_yaw_deg=0.0)
    m2 = GroupTrajectoryMember(robot_id="R_Zero2", offset_x_m=0.0, offset_y_m=0.0, delta_yaw_deg=0.0)
    group = GroupTrajectory("grp_06", "零偏移群组", "traj_06", members=(m1, m2))

    res = compile_group_trajectory(group, ref)
    for member_res in res:
        assert member_res.length_m == pytest.approx(ref.length_m)
        for out_pt, ref_pt in zip(member_res.sampled_points, ref.sampled_points):
            assert out_pt.x_m == pytest.approx(ref_pt.x_m)
            assert out_pt.y_m == pytest.approx(ref_pt.y_m)
            assert out_pt.yaw_deg == pytest.approx(ref_pt.yaw_deg)
            assert out_pt.s_m == pytest.approx(ref_pt.s_m)


def test_07_three_or_more_members_all_generated():
    """7. 两个以上成员的实际轨迹均正确生成且顺序严格对应。"""
    ref = _make_straight_x_asset("traj_07")
    members = [
        GroupTrajectoryMember(robot_id="Lead", offset_x_m=1.0, offset_y_m=0.0),
        GroupTrajectoryMember(robot_id="Wing_Left", offset_x_m=-1.0, offset_y_m=1.0),
        GroupTrajectoryMember(robot_id="Wing_Right", offset_x_m=-1.0, offset_y_m=-1.0),
    ]
    group = GroupTrajectory("grp_07", "三机编队", "traj_07", members=members)

    res = compile_group_trajectory(group, ref)
    assert len(res) == 3
    assert [m.robot_id for m in res] == ["Lead", "Wing_Left", "Wing_Right"]


def test_08_independent_arc_length_calculation():
    """8. 不同成员输出的 s_m 独立重新计算，且终点 s_m 等于实际 length_m。"""
    ref = _make_straight_x_asset("traj_08")
    m1 = GroupTrajectoryMember(robot_id="R1", offset_x_m=2.0)
    m2 = GroupTrajectoryMember(robot_id="R2", offset_x_m=-2.0)
    group = GroupTrajectory("grp_08", "弧长独立测试", "traj_08", members=(m1, m2))

    res = compile_group_trajectory(group, ref)
    for m_res in res:
        pts = m_res.sampled_points
        assert pts[0].s_m == pytest.approx(0.0)
        assert pts[-1].s_m == pytest.approx(m_res.length_m)
        # 验证单调非递减
        for i in range(1, len(pts)):
            assert pts[i].s_m >= pts[i - 1].s_m


def test_09_curved_path_arc_length_variation():
    """9. 非零横向偏移导致曲线路径实际长度改变（内圈变短，外圈变长）。"""
    # 构造向左转弯的 90 度圆弧轨迹（圆心位于 (0, 10)，半径 R=10）
    # yaw 从 0 度匀速增加到 90 度
    num_pts = 100
    r_center = 10.0
    pts = []
    for i in range(num_pts):
        phi = (math.pi / 2.0) * (i / (num_pts - 1))  # 0 -> pi/2
        x = r_center * math.sin(phi)
        y = r_center * (1.0 - math.cos(phi))
        yaw = math.degrees(phi)
        s = r_center * phi
        pts.append(TrajectoryPoint(x_m=x, y_m=y, yaw_deg=yaw, s_m=s))

    ref = TrajectoryAsset(
        trajectory_id="traj_curve",
        name="左转弯参考弧线",
        coordinate_frame="stage_world",
        control_points=[(0.0, 0.0), (10.0, 10.0)],
        sampled_points=pts,
        length_m=pts[-1].s_m,
    )

    # R_Inner: offset_y_m = +2.0（向左侧法线，即圆心方向，内圈半径为 8.0m）
    # R_Outer: offset_y_m = -2.0（向右侧，远离圆心方向，外圈半径为 12.0m）
    m_inner = GroupTrajectoryMember(robot_id="R_Inner", offset_y_m=2.0)
    m_outer = GroupTrajectoryMember(robot_id="R_Outer", offset_y_m=-2.0)
    group = GroupTrajectory("grp_curve", "转弯编队", "traj_curve", members=(m_inner, m_outer))

    res = compile_group_trajectory(group, ref)
    traj_inner = res[0]
    traj_outer = res[1]

    expected_inner_len = 8.0 * (math.pi / 2.0)   # ≈ 12.566m
    expected_ref_len = 10.0 * (math.pi / 2.0)    # ≈ 15.708m
    expected_outer_len = 12.0 * (math.pi / 2.0)  # ≈ 18.850m

    assert traj_inner.length_m == pytest.approx(expected_inner_len, rel=1e-2)
    assert ref.length_m == pytest.approx(expected_ref_len, rel=1e-2)
    assert traj_outer.length_m == pytest.approx(expected_outer_len, rel=1e-2)

    # 严苛验证：内圈长度 < 参考轨迹长度 < 外圈长度
    assert traj_inner.length_m < ref.length_m < traj_outer.length_m


def test_10_consecutive_identical_points_maintain_non_decreasing_arc_length():
    """10. 连续重合采样点产生 ds=0，弧长保持非递减，不人为制造虚假距离。"""
    pts = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
        TrajectoryPoint(x_m=1.0, y_m=0.0, yaw_deg=0.0, s_m=1.0),
        TrajectoryPoint(x_m=1.0, y_m=0.0, yaw_deg=0.0, s_m=1.0),  # 重合停顿点
        TrajectoryPoint(x_m=3.0, y_m=0.0, yaw_deg=0.0, s_m=3.0),
    ]
    ref = TrajectoryAsset(
        trajectory_id="traj_stall",
        name="包含停顿点的轨迹",
        control_points=[(0.0, 0.0), (3.0, 0.0)],
        sampled_points=pts,
        length_m=3.0,
    )
    m1 = GroupTrajectoryMember(robot_id="R1", offset_x_m=0.5, offset_y_m=0.5)
    m2 = GroupTrajectoryMember(robot_id="R2", offset_x_m=-0.5, offset_y_m=-0.5)
    group = GroupTrajectory("grp_stall", "停顿群组", "traj_stall", members=(m1, m2))

    res = compile_group_trajectory(group, ref)
    for m_res in res:
        pts_res = m_res.sampled_points
        assert pts_res[2].s_m == pytest.approx(pts_res[1].s_m)
        assert pts_res[-1].s_m == pytest.approx(3.0)


def test_11_reject_mismatched_reference_trajectory_id():
    """11. 参考轨迹 ID 不一致时明确拒绝计算。"""
    ref = _make_straight_x_asset("traj_A")
    m1 = GroupTrajectoryMember(robot_id="R1")
    m2 = GroupTrajectoryMember(robot_id="R2")
    group = GroupTrajectory("grp_mismatch", "不匹配群组", "traj_B", members=(m1, m2))

    with pytest.raises(ValueError, match="群组引用的参考轨迹 ID .* 不一致"):
        compile_group_trajectory(group, ref)


def test_12_reject_mismatched_coordinate_frame():
    """12. 坐标系不一致时明确拒绝计算。"""
    ref = _make_straight_x_asset("traj_12")
    ref.coordinate_frame = "stage_world"
    m1 = GroupTrajectoryMember(robot_id="R1")
    m2 = GroupTrajectoryMember(robot_id="R2")
    group = GroupTrajectory("grp_12", "坐标系群组", "traj_12", coordinate_frame="robot_local", members=(m1, m2))

    with pytest.raises(ValueError, match="坐标系不一致"):
        compile_group_trajectory(group, ref)


def test_13_reject_insufficient_sampled_points_and_uncommittable_group():
    """13. 参考轨迹采样点不足或群组未达提交门槛时拒绝计算。"""
    ref_empty_points = TrajectoryAsset(
        trajectory_id="traj_13",
        name="无点素材",
        control_points=[(0.0, 0.0)],
        sampled_points=[],
        length_m=0.0,
    )
    m1 = GroupTrajectoryMember(robot_id="R1")
    m2 = GroupTrajectoryMember(robot_id="R2")
    group = GroupTrajectory("grp_13", "有效群组", "traj_13", members=(m1, m2))

    with pytest.raises(ValueError, match="参考轨迹采样点不足"):
        compile_group_trajectory(group, ref_empty_points)

    # 单机群组未达到可提交门槛
    ref_valid = _make_straight_x_asset("traj_13b")
    group_single = GroupTrajectory("grp_13b", "单机群组", "traj_13b", members=(m1,))
    with pytest.raises(ValueError, match="群组轨迹尚未达到可提交门槛"):
        compile_group_trajectory(group_single, ref_valid)


def test_14_reject_nan_inf_and_negative_reference_length():
    """14. 包含非有限数或长度为 0 的参考轨迹被拒绝。"""
    ref_zero_len = TrajectoryAsset(
        trajectory_id="traj_14",
        name="零长素材",
        control_points=[(0.0, 0.0), (0.0, 0.0)],
        sampled_points=[
            TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
            TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
        ],
        length_m=0.0,
    )
    m1 = GroupTrajectoryMember(robot_id="R1")
    m2 = GroupTrajectoryMember(robot_id="R2")
    group = GroupTrajectory("grp_14", "群组", "traj_14", members=(m1, m2))

    with pytest.raises(ValueError, match="参考轨迹物理长度必须大于 0"):
        compile_group_trajectory(group, ref_zero_len)


def test_15_original_reference_asset_and_group_immutable():
    """15. 原始参考资产与群组对象在计算前后完全保持不变。"""
    ref = _make_straight_x_asset("traj_15")
    ref_dict_before = ref.to_dict()

    m1 = GroupTrajectoryMember(robot_id="R1", offset_x_m=1.0, offset_y_m=0.5)
    m2 = GroupTrajectoryMember(robot_id="R2", offset_x_m=-1.0, offset_y_m=-0.5)
    group = GroupTrajectory("grp_15", "不可变测试", "traj_15", members=(m1, m2))
    group_dict_before = group.to_dict()

    compile_group_trajectory(group, ref)

    assert ref.to_dict() == ref_dict_before
    assert group.to_dict() == group_dict_before


def test_16_output_member_order_preserved():
    """16. 输出结果成员顺序与 GroupTrajectory.members 严格一致。"""
    ref = _make_straight_x_asset("traj_16")
    ids = ["R_Delta", "R_Beta", "R_Alpha", "R_Gamma"]
    members = [GroupTrajectoryMember(robot_id=rid, offset_x_m=float(i)) for i, rid in enumerate(ids)]
    group = GroupTrajectory("grp_16", "排序测试", "traj_16", members=members)

    res = compile_group_trajectory(group, ref)
    assert [m.robot_id for m in res] == ids


def test_17_member_trajectory_serialization_roundtrip():
    """17. GroupMemberTrajectory 序列化与反序列化往返一致。"""
    ref = _make_straight_x_asset("traj_17")
    m1 = GroupTrajectoryMember(robot_id="R1", offset_x_m=1.0, offset_y_m=0.5, delta_yaw_deg=15.0)
    m2 = GroupTrajectoryMember(robot_id="R2", offset_x_m=-1.0, offset_y_m=-0.5, delta_yaw_deg=-15.0)
    group = GroupTrajectory("grp_17", "序列化测试", "traj_17", members=(m1, m2))

    res = compile_group_trajectory(group, ref)
    item = res[0]

    d = item.to_dict()
    assert d["robot_id"] == "R1"
    assert d["reference_trajectory_id"] == "traj_17"
    assert d["coordinate_frame"] == "stage_world"
    assert len(d["sampled_points"]) == 3
    assert d["length_m"] == pytest.approx(4.0)

    restored = GroupMemberTrajectory.from_dict(d)
    assert restored.robot_id == item.robot_id
    assert restored.reference_trajectory_id == item.reference_trajectory_id
    assert restored.length_m == item.length_m
    assert len(restored.sampled_points) == len(item.sampled_points)
    assert restored.to_dict() == d
