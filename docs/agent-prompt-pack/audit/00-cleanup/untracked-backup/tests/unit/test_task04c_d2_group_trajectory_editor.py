"""
@file: tests/unit/test_task04c_d2_group_trajectory_editor.py
@brief: 任务 04C-D2 群组成员管理与轨迹局部偏移编辑单元测试
@exports: 测试用例集
"""
import os
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

from src.application.stage_director.group_trajectory_controller import (
    GroupTrajectoryController,
)
from src.domain.trajectory.trajectory_asset import TrajectoryAsset, TrajectoryPoint
from src.infrastructure.storage.choreo_sqlite_store import ChoreoSqliteStore
from src.ui.choreo_page.group_trajectory_workspace import GroupTrajectoryWorkspace


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def temp_store(tmp_path):
    db_file = str(tmp_path / "test_editor_studio.db")
    return ChoreoSqliteStore(db_file)


def _make_sample_ref_asset() -> TrajectoryAsset:
    pts = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
        TrajectoryPoint(x_m=2.0, y_m=0.0, yaw_deg=0.0, s_m=2.0),
        TrajectoryPoint(x_m=4.0, y_m=0.0, yaw_deg=0.0, s_m=4.0),
    ]
    return TrajectoryAsset(
        trajectory_id="ref_traj_01",
        name="参考主轨迹",
        coordinate_frame="stage_world",
        control_points=[(0.0, 0.0), (4.0, 0.0)],
        sampled_points=pts,
        length_m=4.0,
    )


def test_01_set_and_get_reference_trajectory(temp_store):
    """1. 能够正确设置与读取当前单机器人参考轨迹。"""
    ctrl = GroupTrajectoryController(temp_store)
    assert ctrl.get_reference_trajectory() is None

    asset = _make_sample_ref_asset()
    ctrl.set_reference_asset(asset)
    assert ctrl.get_reference_trajectory() is asset
    assert ctrl.get_reference_trajectory().trajectory_id == "ref_traj_01"


def test_02_add_member_success(temp_store):
    """2. 正常添加机器人成员并配置初始局部偏移。"""
    ctrl = GroupTrajectoryController(temp_store)
    m1 = ctrl.add_member("Robot_1", offset_x_m=0.5, offset_y_m=1.0, delta_yaw_deg=10.0)
    assert m1.robot_id == "Robot_1"
    assert m1.offset_x_m == 0.5
    assert m1.offset_y_m == 1.0
    assert m1.delta_yaw_deg == 10.0
    assert len(ctrl.get_members()) == 1


def test_03_prevent_duplicate_member_id(temp_store):
    """3. 严格阻止重复添加相同 robot_id 的机器人。"""
    ctrl = GroupTrajectoryController(temp_store)
    ctrl.add_member("Robot_A")
    with pytest.raises(ValueError, match="禁止重复添加"):
        ctrl.add_member("Robot_A")
    assert len(ctrl.get_members()) == 1


def test_04_remove_member(temp_store):
    """4. 能够按 ID 移除指定机器人成员。"""
    ctrl = GroupTrajectoryController(temp_store)
    ctrl.add_member("Robot_1")
    ctrl.add_member("Robot_2")
    assert len(ctrl.get_members()) == 2

    removed = ctrl.remove_member("Robot_1")
    assert removed is True
    members = ctrl.get_members()
    assert len(members) == 1
    assert members[0].robot_id == "Robot_2"


def test_05_update_member_offsets_and_yaw_normalization(temp_store):
    """5. 修改成员偏移参数并验证角度自动规范化到 [-180, 180)。"""
    ctrl = GroupTrajectoryController(temp_store)
    ctrl.add_member("Robot_1", 0.0, 0.0, 0.0)

    updated = ctrl.update_member_offset("Robot_1", offset_x_m=-1.5, offset_y_m=2.0, delta_yaw_deg=190.0)
    assert updated.offset_x_m == -1.5
    assert updated.offset_y_m == 2.0
    # 190° 规范化为 -170°
    assert updated.delta_yaw_deg == -170.0


def test_06_compile_fails_without_reference(temp_store):
    """6. 没有选择参考轨迹时拒绝编译。"""
    ctrl = GroupTrajectoryController(temp_store)
    ctrl.add_member("Robot_1")
    ctrl.add_member("Robot_2")
    with pytest.raises(ValueError, match="尚未选择参考轨迹"):
        ctrl.compile_and_validate()


def test_07_compile_fails_with_insufficient_members(temp_store):
    """7. 成员少于 2 台机器人时拒绝生成群组轨迹。"""
    ctrl = GroupTrajectoryController(temp_store)
    ctrl.set_reference_asset(_make_sample_ref_asset())
    ctrl.add_member("Robot_1")
    with pytest.raises(ValueError, match="至少需要 2 台机器人"):
        ctrl.compile_and_validate()


def test_08_compile_and_validate_success(temp_store):
    """8. 成功聚合参考线与成员偏移生成全局轨迹与安全报告。"""
    ctrl = GroupTrajectoryController(temp_store)
    ctrl.set_reference_asset(_make_sample_ref_asset())
    ctrl.add_member("Robot_1", offset_x_m=0.0, offset_y_m=0.5)
    ctrl.add_member("Robot_2", offset_x_m=0.0, offset_y_m=-0.5)

    group, trajs, report = ctrl.compile_and_validate(name="双机测试编队")
    assert len(trajs) == 2
    assert trajs[0].robot_id == "Robot_1"
    assert trajs[1].robot_id == "Robot_2"
    assert report is not None
    assert isinstance(report.violation_count, int)


def test_09_workspace_ui_preview_pipeline(qapp, temp_store):
    """9. 验证工作区 UI 面板能够直接驱动生成预览并注入画布。"""
    ws = GroupTrajectoryWorkspace()
    ws.group_controller.store = temp_store
    ref = _make_sample_ref_asset()
    ws.group_controller.set_reference_asset(ref)
    ws.edit_panel.set_selected_reference(ref)

    ws.group_controller.add_member("R1", 0.0, 0.4)
    ws.group_controller.add_member("R2", 0.0, -0.4)
    ws.edit_panel.set_members(ws.group_controller.get_members())

    ws.generate_group_preview()
    assert len(ws.canvas_2d._group_preview_trajectories) == 2
    assert ws.canvas_2d._group_safety_report is not None
