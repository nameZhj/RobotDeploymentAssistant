"""
@file: tests/unit/test_task04c_d3_formation_integration.py
@brief: 任务 04C-D3 机器人群组阵型设计与 FormationMatrixPlanner 集成单元测试
@exports: 测试用例集
"""
import os
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

from src.application.stage_director.group_trajectory_controller import (
    GroupTrajectoryController,
)
from src.domain.trajectory.formation_matrix_planner import FormationMatrixPlanner
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
    db_file = str(tmp_path / "test_formation_studio.db")
    return ChoreoSqliteStore(db_file)


def _make_ref_asset() -> TrajectoryAsset:
    pts = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
        TrajectoryPoint(x_m=5.0, y_m=0.0, yaw_deg=0.0, s_m=5.0),
    ]
    return TrajectoryAsset(
        trajectory_id="ref_f01",
        name="领航直线",
        coordinate_frame="stage_world",
        control_points=[(0.0, 0.0), (5.0, 0.0)],
        sampled_points=pts,
        length_m=5.0,
    )


def test_01_grid_formation_assigned_to_members(temp_store):
    """1. 4台机器人应用 2x2 网格方阵计算出正确相对几何偏移。"""
    ctrl = GroupTrajectoryController(temp_store)
    for i in range(1, 5):
        ctrl.add_member(f"Robot_{i}")

    ctrl.apply_grid_formation(rows=2, cols=2, spacing_m=1.2)
    members = ctrl.get_members()
    assert len(members) == 4

    # 验证中心对称排布
    xs = [m.offset_x_m for m in members]
    ys = [m.offset_y_m for m in members]
    assert min(xs) == pytest.approx(-0.6, abs=1e-3)
    assert max(xs) == pytest.approx(0.6, abs=1e-3)
    assert min(ys) == pytest.approx(-0.6, abs=1e-3)
    assert max(ys) == pytest.approx(0.6, abs=1e-3)


def test_02_formation_member_ordering_stable(temp_store):
    """2. 阵型规划后成员次序保持稳定不变。"""
    ctrl = GroupTrajectoryController(temp_store)
    ids = ["R_Alfa", "R_Bravo", "R_Charlie"]
    for rid in ids:
        ctrl.add_member(rid)

    ctrl.apply_grid_formation(rows=1, cols=3, spacing_m=1.5)
    members = ctrl.get_members()
    assert [m.robot_id for m in members] == ids


def test_03_formation_with_empty_members_raises_error(temp_store):
    """3. 未添加任何成员时调用阵型规划抛出异常。"""
    ctrl = GroupTrajectoryController(temp_store)
    with pytest.raises(ValueError, match="请先添加机器人成员"):
        ctrl.apply_grid_formation(rows=2, cols=2)


def test_04_formation_with_heading_rotation(temp_store):
    """4. 阵型规划支持整体偏角参数并正确赋值 delta_yaw_deg。"""
    ctrl = GroupTrajectoryController(temp_store)
    ctrl.add_member("R1")
    ctrl.add_member("R2")

    ctrl.apply_grid_formation(rows=1, cols=2, spacing_m=1.0, heading_deg=45.0)
    members = ctrl.get_members()
    assert members[0].delta_yaw_deg == 45.0
    assert members[1].delta_yaw_deg == 45.0


def test_05_manual_edit_after_formation_generation(temp_store):
    """5. 应用阵型后用户仍可对任意机器人的偏移参数进行二次微调。"""
    ctrl = GroupTrajectoryController(temp_store)
    ctrl.add_member("R1")
    ctrl.add_member("R2")
    ctrl.apply_grid_formation(rows=1, cols=2, spacing_m=1.0)

    ctrl.update_member_offset("R1", offset_x_m=2.5, offset_y_m=0.0, delta_yaw_deg=0.0)
    m1 = next(m for m in ctrl.get_members() if m.robot_id == "R1")
    assert m1.offset_x_m == 2.5


def test_06_formation_compile_and_safety_pipeline(temp_store):
    """6. 阵型生成偏移后能顺畅进入全局几何编译与静态安全检测。"""
    ctrl = GroupTrajectoryController(temp_store)
    ctrl.set_reference_asset(_make_ref_asset())
    for i in range(1, 4):
        ctrl.add_member(f"R{i}")

    ctrl.apply_grid_formation(rows=3, cols=1, spacing_m=1.0)
    group, trajs, report = ctrl.compile_and_validate(required_clearance_m=0.6)
    assert len(trajs) == 3
    assert report.is_safe is True
