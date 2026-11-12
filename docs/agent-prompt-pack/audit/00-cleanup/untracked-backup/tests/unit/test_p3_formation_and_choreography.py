"""
@file: tests/unit/test_p3_formation_and_choreography.py
@brief: P3 机器人阵型设计、真实动作素材校验与时间轴拖放编排自动化测试集
@exports: 测试用例集合
"""
import glob
import json
import math
import os
import numpy as np
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QMimeData
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from src.application.stage_director.group_trajectory_controller import GroupTrajectoryController
from src.application.stage_director.timeline_choreo_controller import TimelineChoreoController
from src.domain.simulation.stage_performance_sampler import StagePerformanceSampler
from src.domain.timeline.timeline_clip_asset import TrackLayerType
from src.domain.trajectory.formation_matrix_planner import FormationMatrixPlanner
from src.domain.trajectory.group_trajectory import GroupTrajectory, GroupTrajectoryMember
from src.domain.trajectory.group_trajectory_compiler import GroupTrajectoryCompiler
from src.domain.trajectory.group_trajectory_safety import GroupTrajectorySafetyValidator
from src.domain.trajectory.trajectory_asset import TrajectoryAsset, TrajectoryPoint
from src.infrastructure.storage.choreo_sqlite_store import ChoreoSqliteStore
from src.infrastructure.storage.group_trajectory_sqlite_adapter import GroupTrajectorySqliteAdapter
from src.infrastructure.storage.show_project_repository import ShowProjectRepository
from src.infrastructure.storage.trajectory_sqlite_adapter import TrajectorySqliteAdapter
from src.ui.choreo_page.dual_layer_timeline_canvas import DualLayerTimelineCanvas
from src.ui.choreo_page.group_member_edit_panel import GroupMemberEditPanel
from src.ui.choreo_page.group_trajectory_workspace import GroupTrajectoryWorkspace


@pytest.fixture
def p3_env(tmp_path):
    db_file = str(tmp_path / "studio_p3_test.db")
    store = ChoreoSqliteStore(db_file)
    repo = ShowProjectRepository(db_file)
    return {"db_file": db_file, "store": store, "repo": repo, "tmp_path": tmp_path}


def test_01_formation_geometric_layouts():
    line = FormationMatrixPlanner.generate_line_formation(num_robots=4, spacing=1.5, center_x=0.0, center_y=0.0)
    assert len(line) == 4
    assert line[0][1] == line[1][1] == line[2][1] == line[3][1] == 0.0
    assert pytest.approx(line[1][0] - line[0][0], abs=1e-3) == 1.5

    col = FormationMatrixPlanner.generate_column_formation(num_robots=3, spacing=2.0, center_x=0.0, center_y=0.0)
    assert len(col) == 3
    assert col[0][0] == col[1][0] == col[2][0] == 0.0
    assert pytest.approx(col[0][1] - col[1][1], abs=1e-3) == 2.0

    grid = FormationMatrixPlanner.generate_grid_formation(num_robots=4, rows=2, cols=2, spacing=1.0)
    assert len(grid) == 4
    assert pytest.approx(grid[1][0] - grid[0][0], abs=1e-3) == 1.0

    circle = FormationMatrixPlanner.generate_circle_formation(num_robots=6, radius_m=3.0, center_x=0.0, center_y=0.0)
    assert len(circle) == 6
    for x, y, _ in circle:
        assert pytest.approx(math.hypot(x, y), abs=1e-3) == 3.0


def test_02_formation_edge_cases_and_assignment():
    single = FormationMatrixPlanner.generate_line_formation(num_robots=1, spacing=1.0)
    assert len(single) == 1

    starts = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
    targets = [(2.1, 0.0), (0.1, 0.0), (1.1, 0.0)]
    mapping = FormationMatrixPlanner.assign_targets_optimal(starts, targets)
    assert len(mapping) == 3
    assert mapping[0] == 1 and mapping[1] == 2 and mapping[2] == 0

    swapped = FormationMatrixPlanner.swap_robot_targets(mapping, 0, 1)
    assert swapped[0] == 2 and swapped[1] == 1

    pts = [(0.0, 0.0), (0.5, 0.0), (2.0, 0.0)]
    assert pytest.approx(FormationMatrixPlanner.compute_min_pairwise_distance(pts), abs=1e-3) == 0.5


def test_03_real_preview_npz_motion_assets_verification():
    npz_files = sorted(glob.glob("preview/*.npz"))
    assert len(npz_files) >= 6, "必须存在至少 6 个预览 NPZ 动作文件"

    for fpath in npz_files:
        data = np.load(fpath, allow_pickle=False)
        assert "positions" in data and "fps" in data
        pos = data["positions"]
        assert pos.ndim == 3 and pos.shape[1] == 21 and pos.shape[2] == 3
        assert not np.isnan(pos).any() and not np.isinf(pos).any()
        assert float(data["fps"]) == 50.0
        assert pos.shape[0] >= 200


def test_04_timeline_drag_drop_actions_and_trajectories(p3_env):
    ctrl = TimelineChoreoController(p3_env["db_file"], task_name="大秀任务1")

    act_data = {"asset_type": "ACTION", "asset_id": "act_g1_kungfu", "name": "G1_太极抱拳", "duration_ms": 6000}
    ok, msg, clip = ctrl.create_clip_from_dropped_asset(act_data, target_track_id="1", target_sub_layer=TrackLayerType.ACTION, start_ms=0)
    assert ok is True and clip.robot_id == "1" and clip.duration_ms == 6000

    grp_data = {"asset_type": "GROUP_TRAJECTORY", "asset_id": "grp_matrix_01", "name": "方阵群轨", "duration_ms": 5000}
    ok_g, _, clip_g = ctrl.create_clip_from_dropped_asset(grp_data, target_track_id="GROUP", target_sub_layer=TrackLayerType.TRAJECTORY, start_ms=1000)
    assert ok_g is True and clip_g.robot_id == "GROUP" and clip_g.is_group is True

    ok_bad, msg_bad, _ = ctrl.create_clip_from_dropped_asset(grp_data, target_track_id="1", target_sub_layer=TrackLayerType.TRAJECTORY, start_ms=0)
    assert ok_bad is False and "群组轨迹素材必须放置于群组轨道" in msg_bad

    assert ctrl.move_clip(clip.clip_id, 500) is True
    assert ctrl.get_clip(clip.clip_id).start_ms == 500
    assert ctrl.resize_clip(clip.clip_id, 8000) is True
    assert ctrl.get_clip(clip.clip_id).duration_ms == 8000

    new_ctrl = TimelineChoreoController(p3_env["db_file"], task_name="大秀任务1")
    reloaded_clips = new_ctrl.list_clips()
    assert len(reloaded_clips) == 2
    r_act = next(c for c in reloaded_clips if c.clip_id == clip.clip_id)
    assert r_act.start_ms == 500 and r_act.duration_ms == 8000


def test_05_group_trajectory_compiler_and_safety_checks():
    ref = TrajectoryAsset(
        trajectory_id="trj_ref", name="Ref", length_m=4.0,
        control_points=[(0.0, 0.0), (4.0, 0.0)],
        sampled_points=[
            TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
            TrajectoryPoint(x_m=2.0, y_m=0.0, yaw_deg=0.0, s_m=2.0),
            TrajectoryPoint(x_m=4.0, y_m=0.0, yaw_deg=0.0, s_m=4.0),
        ]
    )
    grp = GroupTrajectory(
        group_trajectory_id="grp_01", name="GroupTest", reference_trajectory_id="trj_ref",
        members=(
            GroupTrajectoryMember(robot_id="R1", offset_x_m=0.0, offset_y_m=1.0, delta_yaw_deg=0.0),
            GroupTrajectoryMember(robot_id="R2", offset_x_m=0.0, offset_y_m=-1.0, delta_yaw_deg=0.0),
        )
    )
    compiled = GroupTrajectoryCompiler.compile(grp, ref)
    assert len(compiled) == 2
    assert compiled[0].robot_id == "R1"
    assert pytest.approx(compiled[0].sampled_points[0].y_m, abs=1e-3) == 1.0
    assert compiled[1].robot_id == "R2"
    assert pytest.approx(compiled[1].sampled_points[0].y_m, abs=1e-3) == -1.0

    report = GroupTrajectorySafetyValidator.validate(compiled, stage_bounds=(-10.0, 10.0, -10.0, 10.0), required_clearance_m=0.8)
    assert report.is_safe is True
    assert len(report.boundary_violations) == 0

    report_tight = GroupTrajectorySafetyValidator.validate(compiled, stage_bounds=(-10.0, 10.0, -10.0, 10.0), required_clearance_m=2.5)
    assert report_tight.is_safe is False
    assert len(report_tight.pairwise_clearances) == 1
    assert report_tight.pairwise_clearances[0].is_clear is False


def test_06_motion_sampler_fallback_and_real_keyframe():
    sampler = StagePerformanceSampler()
    st_empty = sampler.sample_robot_pose("R1", 1.0, [], [])
    assert st_empty.pose_status == "STAND_FALLBACK"
    assert st_empty.action_name == "STAND"

    unverified_block = [{"name": "FAKE_DANCE", "start_s": 0.0, "duration_s": 3.0, "is_verified": False, "npz_positions": None}]
    st_unverified = sampler.sample_robot_pose("R1", 1.0, [], unverified_block)
    assert st_unverified.pose_status == "POSE_UNAVAILABLE"
    assert st_unverified.keyframe_positions is None

    real_data = np.load("preview/G1_KUNG_FU.npz", allow_pickle=False)
    real_block = [{"name": "G1_KUNG_FU", "start_s": 0.0, "duration_s": 6.0, "is_verified": True, "fps": float(real_data["fps"]), "npz_positions": real_data["positions"]}]
    st_real = sampler.sample_robot_pose("R1", 1.5, [], real_block)
    assert st_real.pose_status == "NORMAL"
    assert st_real.keyframe_positions is not None
    assert len(st_real.keyframe_positions) == 21
    assert "pelvis" in st_real.keyframe_positions


def test_07_timeline_controller_undo_redo(p3_env):
    ctrl = TimelineChoreoController(p3_env["db_file"], task_name="大秀任务1")
    act_data = {"asset_type": "ACTION", "asset_id": "act_g1_kungfu", "name": "G1_太极抱拳", "duration_ms": 4000}
    ok, _, clip = ctrl.create_clip_from_dropped_asset(act_data, "1", TrackLayerType.ACTION, 0)
    assert ok is True and len(ctrl.list_clips()) == 1

    ctrl.delete_clip(clip.clip_id)
    assert len(ctrl.list_clips()) == 0

    assert ctrl.undo() is True
    assert len(ctrl.list_clips()) == 1

    assert ctrl.redo() is True
    assert len(ctrl.list_clips()) == 0


def test_08_group_trajectory_controller_formations():
    ctrl = GroupTrajectoryController()
    ctrl.add_member("R1")
    ctrl.add_member("R2")
    ctrl.add_member("R3")
    ctrl.add_member("R4")

    # 1. 方阵
    ctrl.apply_grid_formation(rows=2, cols=2, spacing_m=1.5)
    members = ctrl.get_members()
    assert len(members) == 4
    assert pytest.approx(abs(members[0].offset_x_m - members[1].offset_x_m), abs=1e-3) == 1.5

    # 2. 横队
    ctrl.apply_line_formation(spacing_m=2.0)
    m_line = ctrl.get_members()
    assert all(m.offset_x_m == 0.0 for m in m_line)
    assert pytest.approx(m_line[1].offset_y_m - m_line[0].offset_y_m, abs=1e-3) == 2.0

    # 3. 纵队
    ctrl.apply_column_formation(spacing_m=1.0)
    m_col = ctrl.get_members()
    assert all(m.offset_y_m == 0.0 for m in m_col)
    assert pytest.approx(m_col[0].offset_x_m - m_col[1].offset_x_m, abs=1e-3) == 1.0

    # 4. 圆阵
    ctrl.apply_circle_formation(radius_m=3.0)
    m_circle = ctrl.get_members()
    for m in m_circle:
        assert pytest.approx(math.hypot(m.offset_x_m, m.offset_y_m), abs=1e-3) == 3.0


def test_09_full_gui_choreo_workflow(p3_env):
    ws = GroupTrajectoryWorkspace()
    ws.group_controller.store = p3_env["store"]
    for r in ["Robot_1", "Robot_2", "Robot_3", "Robot_4"]:
        ws.group_controller.add_member(r)

    ws.group_controller.apply_line_formation(spacing_m=1.8, heading_deg=0.0)
    assert len(ws.group_controller.get_members()) == 4

    ref = TrajectoryAsset(
        trajectory_id="trj_main_01", name="MainTrj", length_m=6.0,
        control_points=[(0.0, 0.0), (6.0, 0.0)],
        sampled_points=[
            TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
            TrajectoryPoint(x_m=6.0, y_m=0.0, yaw_deg=0.0, s_m=6.0),
        ]
    )
    TrajectorySqliteAdapter.save_asset(p3_env["store"], ref)
    ws.group_controller.set_reference_asset(ref)

    grp, _, rep = ws.group_controller.compile_and_validate("横队巡游", group_id="grp_parade_01", required_clearance_m=0.8)
    assert rep.is_safe is True
    GroupTrajectorySqliteAdapter.save_group(p3_env["store"], grp)

    reloaded_grp = GroupTrajectorySqliteAdapter.get_group(p3_env["store"], "grp_parade_01")
    assert reloaded_grp.group_trajectory_id == "grp_parade_01"
    assert len(reloaded_grp.members) == 4

    canvas = DualLayerTimelineCanvas()
    canvas.choreo_controller = TimelineChoreoController(p3_env["db_file"], task_name="大秀P3")
    canvas.load_from_store()
    assert len(canvas._blocks) == 0

    ok_g, _, clip_g = canvas.choreo_controller.create_clip_from_dropped_asset(
        {"asset_type": "GROUP_TRAJECTORY", "asset_id": "grp_parade_01", "name": "方阵巡游", "duration_ms": 6000},
        target_track_id="GROUP", target_sub_layer=TrackLayerType.TRAJECTORY, start_ms=0
    )
    assert ok_g is True

    ok_t, _, clip_t = canvas.choreo_controller.create_clip_from_dropped_asset(
        {"asset_type": "TRAJECTORY", "asset_id": "trj_main_01", "name": "单机主轨", "duration_ms": 4000},
        target_track_id="1", target_sub_layer=TrackLayerType.TRAJECTORY, start_ms=1000
    )
    assert ok_t is True

    ok_a, _, clip_a = canvas.choreo_controller.create_clip_from_dropped_asset(
        {"asset_type": "ACTION", "asset_id": "act_g1_kungfu", "name": "G1_太极抱拳", "duration_ms": 5000},
        target_track_id="1", target_sub_layer=TrackLayerType.ACTION, start_ms=2000
    )
    assert ok_a is True

    canvas.choreo_controller.move_clip(clip_a.clip_id, 2500)
    canvas.choreo_controller.resize_clip(clip_a.clip_id, 6000)
    canvas.choreo_controller.delete_clip(clip_t.clip_id)

    canvas2 = DualLayerTimelineCanvas()
    canvas2.choreo_controller = TimelineChoreoController(p3_env["db_file"], task_name="大秀P3")
    canvas2.load_from_store()
    assert len(canvas2._blocks) == 2
    b_act = next(b for b in canvas2._blocks if b.block_id == clip_a.clip_id)
    assert b_act.start_ms == 2500 and b_act.duration_ms == 6000


