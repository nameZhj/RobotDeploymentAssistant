"""
@file: tests/unit/test_task04c_a_group_trajectory.py
@brief: 机器人群组轨迹纯领域模型、成员局部偏移、数据契约及序列化单元测试
@exports: 测试用例函数集合
"""
import math
import pytest

from src.domain.trajectory.group_trajectory import GroupTrajectory, GroupTrajectoryMember
from src.domain.trajectory.trajectory_asset import TrajectoryAsset, TrajectoryPoint, normalize_angle_deg


def test_01_create_group_trajectory_with_multiple_members():
    """1. 正常创建两个及以上机器人成员并验证字段。"""
    m1 = GroupTrajectoryMember(robot_id="Robot_1", offset_x_m=0.0, offset_y_m=0.0, delta_yaw_deg=0.0)
    m2 = GroupTrajectoryMember(robot_id="Robot_2", offset_x_m=-1.2, offset_y_m=0.8, delta_yaw_deg=-15.0)
    m3 = GroupTrajectoryMember(robot_id="Robot_3", offset_x_m=-1.2, offset_y_m=-0.8, delta_yaw_deg=15.0)

    gt = GroupTrajectory(
        group_trajectory_id="grp_traj_001",
        name="天鹅湖三人V字编队",
        reference_trajectory_id="traj_lead_001",
        coordinate_frame="stage_world",
        members=(m1, m2, m3),
    )

    assert gt.group_trajectory_id == "grp_traj_001"
    assert gt.name == "天鹅湖三人V字编队"
    assert gt.reference_trajectory_id == "traj_lead_001"
    assert gt.coordinate_frame == "stage_world"
    assert len(gt.members) == 3
    assert gt.robot_ids == ("Robot_1", "Robot_2", "Robot_3")
    assert gt.get_member("Robot_2") == m2
    assert gt.get_member("Robot_999") is None


def test_02_default_values():
    """2. 群组模型字段及默认值正确。"""
    # 成员默认值
    m_default = GroupTrajectoryMember(robot_id="Robot_Solo")
    assert m_default.robot_id == "Robot_Solo"
    assert m_default.offset_x_m == 0.0
    assert m_default.offset_y_m == 0.0
    assert m_default.delta_yaw_deg == 0.0

    # 群组默认值
    gt_default = GroupTrajectory(
        group_trajectory_id="grp_draft_01",
        name="草稿群组",
        reference_trajectory_id="traj_001",
    )
    assert gt_default.coordinate_frame == "stage_world"
    assert gt_default.members == ()
    assert gt_default.robot_ids == ()


def test_03_member_offsets_positive_negative_zero():
    """3. 成员偏移允许正数、负数和零，不擅自限制物理距离。"""
    m = GroupTrajectoryMember(
        robot_id="Robot_Wide",
        offset_x_m=-25.5,
        offset_y_m=42.125,
        delta_yaw_deg=0.0,
    )
    assert m.offset_x_m == pytest.approx(-25.5)
    assert m.offset_y_m == pytest.approx(42.125)
    assert m.delta_yaw_deg == pytest.approx(0.0)


def test_04_reject_non_finite_floats_and_invalid_types():
    """4. 非有限数及非法类型被明确拒绝。"""
    # NaN 和 Inf
    with pytest.raises(ValueError, match="禁止为 NaN 或 Infinity"):
        GroupTrajectoryMember(robot_id="R1", offset_x_m=float("nan"))

    with pytest.raises(ValueError, match="禁止为 NaN 或 Infinity"):
        GroupTrajectoryMember(robot_id="R1", offset_y_m=float("inf"))

    with pytest.raises(ValueError, match="禁止为 NaN 或 Infinity"):
        GroupTrajectoryMember(robot_id="R1", delta_yaw_deg=float("-inf"))

    # 非数字类型：字符串或布尔值
    with pytest.raises(TypeError, match="必须为浮点数或整数"):
        GroupTrajectoryMember(robot_id="R1", offset_x_m="1.5")

    with pytest.raises(TypeError, match="必须为浮点数或整数"):
        GroupTrajectoryMember(robot_id="R1", offset_y_m=True)


def test_05_yaw_angle_normalization():
    """5. 偏航角统一规范化至 [-180, 180) 区间。"""
    cases = [
        (0.0, 0.0),
        (180.0, -180.0),
        (-180.0, -180.0),
        (540.0, -180.0),
        (-540.0, -180.0),
        (360.0, 0.0),
        (720.0, 0.0),
        (-90.0, -90.0),
        (270.0, -90.0),
        (-270.0, 90.0),
        (190.0, -170.0),
        (-190.0, 170.0),
    ]
    for raw_angle, expected in cases:
        m = GroupTrajectoryMember(robot_id="R_Yaw", delta_yaw_deg=raw_angle)
        assert m.delta_yaw_deg == pytest.approx(expected, abs=1e-9), f"Failed on raw_angle={raw_angle}"


def test_06_reject_duplicate_robot_id():
    """6. 重复 robot_id 被拒绝。"""
    m1 = GroupTrajectoryMember(robot_id="Robot_1", offset_x_m=0.0, offset_y_m=0.0)
    m2 = GroupTrajectoryMember(robot_id="Robot_1", offset_x_m=1.0, offset_y_m=1.0)

    with pytest.raises(ValueError, match="群组成员 robot_id 必须唯一"):
        GroupTrajectory(
            group_trajectory_id="grp_dup",
            name="重复ID群组",
            reference_trajectory_id="traj_001",
            members=(m1, m2),
        )


def test_07_empty_group_is_draft_not_committable():
    """7. 空群组可以作为未完成草稿，但不能提交。"""
    gt_empty = GroupTrajectory(
        group_trajectory_id="grp_draft_empty",
        name="空草稿群组",
        reference_trajectory_id="traj_001",
        members=(),
    )
    assert gt_empty.is_draft() is True
    assert gt_empty.is_committable() is False
    assert gt_empty.is_submittable() is False

    with pytest.raises(ValueError, match="群组轨迹提交至少需要包含 2 个不同机器人成员"):
        gt_empty.validate_for_submission()


def test_08_single_member_cannot_be_committed():
    """8. 只有一个成员时可以作为草稿，但不能提交。"""
    m_single = GroupTrajectoryMember(robot_id="Robot_Solo")
    gt_single = GroupTrajectory(
        group_trajectory_id="grp_draft_single",
        name="单机草稿",
        reference_trajectory_id="traj_001",
        members=[m_single],
    )
    assert gt_single.is_draft() is True
    assert gt_single.is_committable() is False
    assert gt_single.is_submittable() is False

    with pytest.raises(ValueError, match="群组轨迹提交至少需要包含 2 个不同机器人成员"):
        gt_single.validate_for_submission()


def test_09_two_or_more_members_satisfies_submission_threshold():
    """9. 两个不同成员时可以满足提交数量要求。"""
    m1 = GroupTrajectoryMember(robot_id="Robot_A", offset_x_m=0.0, offset_y_m=0.5)
    m2 = GroupTrajectoryMember(robot_id="Robot_B", offset_x_m=0.0, offset_y_m=-0.5)
    gt = GroupTrajectory(
        group_trajectory_id="grp_ready",
        name="双机齐步",
        reference_trajectory_id="traj_001",
        members=[m1, m2],
    )
    assert gt.is_draft() is True
    assert gt.is_committable() is True
    assert gt.is_submittable() is True
    # 正常校验不抛出异常
    gt.validate_for_submission()


def test_10_serialization_and_deserialization_roundtrip():
    """10. 序列化与反序列化往返一致。"""
    m1 = GroupTrajectoryMember(robot_id="R1", offset_x_m=1.0, offset_y_m=2.0, delta_yaw_deg=30.0)
    m2 = GroupTrajectoryMember(robot_id="R2", offset_x_m=-1.0, offset_y_m=-2.0, delta_yaw_deg=-45.0)
    original = GroupTrajectory(
        group_trajectory_id="grp_roundtrip",
        name="往返序列化测试",
        reference_trajectory_id="traj_lead",
        coordinate_frame="stage_world",
        members=(m1, m2),
    )

    d = original.to_dict()
    assert d["group_trajectory_id"] == "grp_roundtrip"
    assert d["name"] == "往返序列化测试"
    assert d["reference_trajectory_id"] == "traj_lead"
    assert d["coordinate_frame"] == "stage_world"
    assert len(d["members"]) == 2
    assert d["members"][0] == {"robot_id": "R1", "offset_x_m": 1.0, "offset_y_m": 2.0, "delta_yaw_deg": 30.0}

    restored = GroupTrajectory.from_dict(d)
    assert restored.group_trajectory_id == original.group_trajectory_id
    assert restored.name == original.name
    assert restored.reference_trajectory_id == original.reference_trajectory_id
    assert restored.coordinate_frame == original.coordinate_frame
    assert len(restored.members) == 2
    assert restored.members[0] == m1
    assert restored.members[1] == m2
    assert restored.to_dict() == d


def test_11_member_order_preserved_across_roundtrip():
    """11. 成员顺序在往返后严格保持不变。"""
    ids_in_order = ["Robot_Echo", "Robot_Alpha", "Robot_Charlie", "Robot_Bravo"]
    members = [GroupTrajectoryMember(robot_id=rid, offset_x_m=float(i)) for i, rid in enumerate(ids_in_order)]
    gt = GroupTrajectory(
        group_trajectory_id="grp_order",
        name="保序测试",
        reference_trajectory_id="traj_order",
        members=members,
    )

    restored = GroupTrajectory.from_dict(gt.to_dict())
    assert [m.robot_id for m in restored.members] == ids_in_order
    assert list(restored.robot_ids) == ids_in_order


def test_12_reject_missing_fields_and_corrupt_data():
    """12. 缺失必需字段、错误类型和损坏数据被明确拒绝。"""
    valid_dict = {
        "group_trajectory_id": "grp_valid",
        "name": "有效群组",
        "reference_trajectory_id": "traj_001",
        "members": [{"robot_id": "R1", "offset_x_m": 0.0, "offset_y_m": 0.0, "delta_yaw_deg": 0.0}],
    }

    # 缺失必需字段
    for field in ("group_trajectory_id", "name", "reference_trajectory_id", "members"):
        corrupt = dict(valid_dict)
        del corrupt[field]
        with pytest.raises(KeyError, match=f"缺少必需字段: '{field}'"):
            GroupTrajectory.from_dict(corrupt)

    # 成员缺失字段
    corrupt_member = {
        "group_trajectory_id": "grp_valid",
        "name": "有效群组",
        "reference_trajectory_id": "traj_001",
        "members": [{"robot_id": "R1", "offset_x_m": 0.0}],
    }
    with pytest.raises(KeyError, match="缺少必需字段: 'offset_y_m'"):
        GroupTrajectory.from_dict(corrupt_member)

    # 纯空白字符串
    with pytest.raises(ValueError, match="必须为非空且非纯空白字符串"):
        GroupTrajectory(group_trajectory_id="  ", name="群组", reference_trajectory_id="traj_001")

    with pytest.raises(ValueError, match="必须为非空且非纯空白字符串"):
        GroupTrajectory(group_trajectory_id="grp_1", name="   ", reference_trajectory_id="traj_001")

    with pytest.raises(ValueError, match="必须为非空且非纯空白字符串"):
        GroupTrajectory(group_trajectory_id="grp_1", name="群组", reference_trajectory_id="   ")

    with pytest.raises(ValueError, match="必须为非空且非纯空白字符串"):
        GroupTrajectoryMember(robot_id="   ")

    # 非字典输入
    with pytest.raises(TypeError, match="必须为 dict"):
        GroupTrajectory.from_dict("not_a_dict")

    with pytest.raises(TypeError, match="必须为 dict"):
        GroupTrajectoryMember.from_dict([1, 2, 3])


def test_13_instances_isolation_no_data_pollution():
    """13. 不同 GroupTrajectory 之间的数据互不污染。"""
    m1 = GroupTrajectoryMember(robot_id="R1", offset_x_m=0.0)
    m2 = GroupTrajectoryMember(robot_id="R2", offset_x_m=1.0)
    m_list = [m1, m2]

    gt1 = GroupTrajectory(group_trajectory_id="g1", name="群1", reference_trajectory_id="t1", members=m_list)
    gt2 = GroupTrajectory(group_trajectory_id="g2", name="群2", reference_trajectory_id="t2", members=m_list)

    # 修改传入的外部列表，不影响 gt1 与 gt2 内部不可变元组
    m_list.append(GroupTrajectoryMember(robot_id="R3", offset_x_m=2.0))
    assert len(gt1.members) == 2
    assert len(gt2.members) == 2

    # 修改导出的字典，不影响领域模型内部状态
    d1 = gt1.to_dict()
    d1["members"].clear()
    assert len(gt1.members) == 2

    # 默认元组独立，不发生共享实例篡改
    gt_empty1 = GroupTrajectory(group_trajectory_id="e1", name="空1", reference_trajectory_id="t1")
    gt_empty2 = GroupTrajectory(group_trajectory_id="e2", name="空2", reference_trajectory_id="t2")
    assert gt_empty1.members == ()
    assert gt_empty2.members == ()


def test_14_trajectory_asset_unaffected():
    """14. 原有 TrajectoryAsset 领域模型不受影响且契约保持解耦。"""
    pts = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
        TrajectoryPoint(x_m=5.0, y_m=0.0, yaw_deg=0.0, s_m=5.0),
    ]
    ref_asset = TrajectoryAsset(
        trajectory_id="lead_path_100",
        name="领头轨迹",
        coordinate_frame="stage_world",
        control_points=[(0.0, 0.0), (5.0, 0.0)],
        sampled_points=pts,
        length_m=5.0,
    )
    assert ref_asset.is_committable() is True

    # 群组轨迹只引用其 trajectory_id，不嵌入整份 asset，也不污染 TrajectoryAsset
    gt = GroupTrajectory(
        group_trajectory_id="grp_lead_100",
        name="领头参考编队",
        reference_trajectory_id=ref_asset.trajectory_id,
        members=[
            GroupTrajectoryMember(robot_id="Lead_Bot", offset_x_m=0.0, offset_y_m=0.0),
            GroupTrajectoryMember(robot_id="Wing_Bot", offset_x_m=-1.0, offset_y_m=1.0),
        ],
    )
    assert gt.reference_trajectory_id == "lead_path_100"
    assert gt.is_committable() is True
    assert not hasattr(ref_asset, "group_trajectory_id")
    assert not hasattr(ref_asset, "members")
