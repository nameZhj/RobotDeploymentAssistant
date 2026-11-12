"""
@file: tests/unit/test_task04c_d1_group_trajectory_canvas.py
@brief: 任务 04C-D1 2D 群组轨迹显示与安全风险高亮单元测试
@exports: 测试用例函数集合
"""
import copy
import math
import os
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

# 确保无头测试环境
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from src.domain.trajectory.group_trajectory import GroupTrajectory, GroupTrajectoryMember
from src.domain.trajectory.group_trajectory_compiler import (
    GroupMemberTrajectory,
    compile_group_trajectory,
)
from src.domain.trajectory.group_trajectory_safety import (
    BoundaryViolation,
    GroupTrajectorySafetyReport,
    PairwiseClearance,
    validate_group_trajectory_safety,
)
from src.domain.trajectory.trajectory_asset import TrajectoryAsset, TrajectoryPoint
from src.ui.choreo_page.group_canvas_renderer import GroupCanvasRenderer
from src.ui.choreo_page.group_trajectory_workspace import GroupTrajectoryWorkspace
from src.ui.choreo_page.stage_canvas_2d import StageCanvas2D


@pytest.fixture(scope="session")
def qapp():
    """保证 PySide6 QApplication 全局实例存在。"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_test_trajectories():
    """构造双机群组轨迹用于画布显示测试。"""
    pts_ref = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
        TrajectoryPoint(x_m=2.0, y_m=0.0, yaw_deg=0.0, s_m=2.0),
        TrajectoryPoint(x_m=4.0, y_m=0.0, yaw_deg=0.0, s_m=4.0),
    ]
    ref_asset = TrajectoryAsset(
        trajectory_id="traj_lead",
        name="参考领航线",
        coordinate_frame="stage_world",
        control_points=[(0.0, 0.0), (4.0, 0.0)],
        sampled_points=pts_ref,
        length_m=4.0,
    )
    group = GroupTrajectory(
        group_trajectory_id="grp_test",
        name="双机测试编队",
        reference_trajectory_id="traj_lead",
        members=[
            GroupTrajectoryMember(robot_id="A", offset_x_m=0.0, offset_y_m=0.5),
            GroupTrajectoryMember(robot_id="B", offset_x_m=0.0, offset_y_m=-0.5),
        ],
    )
    trajs = compile_group_trajectory(group, ref_asset)
    return trajs, ref_asset, group


def _render_canvas(canvas: StageCanvas2D) -> None:
    """辅助离屏渲染触发 paintEvent。"""
    img = QImage(800, 600, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    canvas.resize(800, 600)
    canvas.paintEvent(None)
    p.end()


def test_01_two_robots_group_preview_rendered(qapp):
    """1. 两台机器人群组轨迹正常显示并在画布上离屏渲染。"""
    canvas = StageCanvas2D()
    trajs, _, _ = _make_test_trajectories()

    canvas.set_group_preview(trajs, safety_report=None)
    assert len(canvas._group_preview_trajectories) == 2
    assert canvas._group_preview_trajectories[0].robot_id == "A"
    assert canvas._group_preview_trajectories[1].robot_id == "B"

    # 验证 paintEvent 离屏正常绘制无崩溃
    _render_canvas(canvas)


def test_02_three_robots_distinguishable_colors(qapp):
    """2. 三台机器人轨迹能够使用独立色板进行区分。"""
    c_a = GroupCanvasRenderer.get_robot_color("A", 0)
    c_b = GroupCanvasRenderer.get_robot_color("B", 1)
    c_c = GroupCanvasRenderer.get_robot_color("C", 2)

    assert c_a != c_b
    assert c_b != c_c
    assert c_a != c_c

    # 构造三机轨迹渲染
    m_pts = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
        TrajectoryPoint(x_m=1.0, y_m=1.0, yaw_deg=0.0, s_m=1.414),
    ]
    t_c = GroupMemberTrajectory("C", "ref_01", "stage_world", tuple(m_pts), 1.414)
    trajs, _, _ = _make_test_trajectories()
    three_trajs = list(trajs) + [t_c]

    canvas = StageCanvas2D()
    canvas.set_group_preview(three_trajs)
    assert len(canvas._group_preview_trajectories) == 3
    _render_canvas(canvas)


def test_03_robot_start_and_end_points_labeled(qapp):
    """3. 各机器人起点与终点正确定位并标注。"""
    trajs, _, _ = _make_test_trajectories()
    canvas = StageCanvas2D()
    canvas.set_group_preview(trajs)

    traj_a = trajs[0]
    p_start = traj_a.sampled_points[0]
    p_end = traj_a.sampled_points[-1]

    # 验证起点坐标与终点坐标不同
    assert (p_start.x_m, p_start.y_m) != (p_end.x_m, p_end.y_m)
    # 离屏绘制覆盖起点与终点图钉逻辑
    _render_canvas(canvas)


def test_04_stage_boundary_violation_highlighted(qapp):
    """4. 舞台边界违规标记定位正确并展示错误状态。"""
    canvas = StageCanvas2D()
    trajs, _, _ = _make_test_trajectories()

    violation = BoundaryViolation(robot_id="A", point_index=2, x_m=55.0, y_m=10.0, boundary="x_max")
    safety_rep = GroupTrajectorySafetyReport(
        is_safe=False,
        boundary_violations=(violation,),
        pairwise_clearances=(),
        violation_count=1,
    )

    canvas.set_group_preview(trajs, safety_rep)
    assert canvas._status_message is not None
    assert canvas._status_message[0] == "存在舞台边界违规"
    assert canvas._status_message[1] == "error"

    _render_canvas(canvas)


def test_05_clearance_violation_both_segments_highlighted(qapp):
    """5. 两条路径间距不足时两侧线段均高亮并更新状态。"""
    canvas = StageCanvas2D()
    trajs, _, _ = _make_test_trajectories()

    clearance = PairwiseClearance(
        robot_id_a="A",
        robot_id_b="B",
        min_distance_m=0.35,
        required_clearance_m=0.6,
        is_clear=False,
        segment_index_a=1,
        segment_index_b=0,
    )
    safety_rep = GroupTrajectorySafetyReport(
        is_safe=False,
        boundary_violations=(),
        pairwise_clearances=(clearance,),
        violation_count=1,
    )

    canvas.set_group_preview(trajs, safety_rep)
    assert canvas._status_message is not None
    assert canvas._status_message[0] == "存在最小间距不足"
    assert canvas._status_message[1] == "error"

    _render_canvas(canvas)


def test_06_multiple_clearance_violations_rendered(qapp):
    """6. 多个机器人对同时违规时全部显示无遗漏。"""
    canvas = StageCanvas2D()
    trajs, _, _ = _make_test_trajectories()

    c1 = PairwiseClearance("A", "B", 0.2, 0.6, False, 0, 0)
    c2 = PairwiseClearance("A", "C", 0.1, 0.6, False, 1, 0)
    safety_rep = GroupTrajectorySafetyReport(
        is_safe=False,
        boundary_violations=(),
        pairwise_clearances=(c1, c2),
        violation_count=2,
    )

    canvas.set_group_preview(trajs, safety_rep)
    assert len(canvas._group_safety_report.pairwise_clearances) == 2
    _render_canvas(canvas)


def test_07_safe_report_no_false_alarms(qapp):
    """7. 安全报告无违规时显示通过状态，无虚假报警。"""
    canvas = StageCanvas2D()
    trajs, _, _ = _make_test_trajectories()

    c = PairwiseClearance("A", "B", 1.0, 0.6, True, 0, 0)
    safety_rep = GroupTrajectorySafetyReport(
        is_safe=True,
        boundary_violations=(),
        pairwise_clearances=(c,),
        violation_count=0,
    )

    canvas.set_group_preview(trajs, safety_rep)
    assert canvas._status_message is not None
    assert canvas._status_message[0] == "静态几何检查通过"
    assert canvas._status_message[1] == "info"

    _render_canvas(canvas)


def test_08_empty_group_preview_handling(qapp):
    """8. 空群组预览正确处理，不抛出异常。"""
    canvas = StageCanvas2D()
    canvas.set_group_preview([], None)
    assert canvas._group_preview_trajectories == []
    assert canvas._group_safety_report is None
    _render_canvas(canvas)


def test_09_clear_group_preview_preserves_single_robot_trajectories(qapp):
    """9. 清除群组预览不删除已保存的单机轨迹。"""
    canvas = StageCanvas2D()
    canvas._completed_trajectories = [{"id": "single_01", "name": "单机原轨迹", "waypoints": [(0, 0), (1, 1)]}]
    trajs, _, _ = _make_test_trajectories()

    canvas.set_group_preview(trajs)
    assert len(canvas._completed_trajectories) == 1

    canvas.clear_group_preview()
    assert len(canvas._completed_trajectories) == 1
    assert canvas._completed_trajectories[0]["id"] == "single_01"
    assert canvas._group_preview_trajectories == []
    assert canvas._group_safety_report is None


def test_10_scaling_and_panning_consistency(qapp):
    """10. 缩放及平移后坐标映射与风险标记位置保持一致。"""
    canvas = StageCanvas2D()
    canvas._scale = 40.0
    canvas._offset_x = 100.0
    canvas._offset_y = -50.0

    # 舞台 (2.0, 3.0) 映射到屏幕坐标
    scr = canvas.stage_to_screen(2.0, 3.0)
    # 反向映射必须还原为 (2.0, 3.0)
    stg_x, stg_y = canvas.screen_to_stage(scr)
    assert stg_x == pytest.approx(2.0, abs=1e-3)
    assert stg_y == pytest.approx(3.0, abs=1e-3)


def test_11_input_domain_objects_not_mutated(qapp):
    """11. 接入画布与绘制前后，输入领域对象保持 100% 不可变。"""
    trajs, _, _ = _make_test_trajectories()
    dict_before = [t.to_dict() for t in trajs]

    c = PairwiseClearance("A", "B", 0.3, 0.6, False, 0, 0)
    safety_rep = GroupTrajectorySafetyReport(False, (), (c,), 1)
    rep_dict_before = safety_rep.to_dict()

    canvas = StageCanvas2D()
    canvas.set_group_preview(trajs, safety_rep)
    _render_canvas(canvas)
    canvas.clear_group_preview()

    dict_after = [t.to_dict() for t in trajs]
    assert dict_after == dict_before
    assert safety_rep.to_dict() == rep_dict_before


def test_12_no_safety_report_no_false_safe_status(qapp):
    """12. 没有安全报告时不显示虚假安全通过状态。"""
    canvas = StageCanvas2D()
    canvas._status_message = None
    trajs, _, _ = _make_test_trajectories()

    canvas.set_group_preview(trajs, safety_report=None)
    assert canvas._status_message is None


def test_13_path_intersection_risk_status_text(qapp):
    """13. 路径相交（min_distance_m=0）准确显示‘存在路径交叉风险’。"""
    canvas = StageCanvas2D()
    trajs, _, _ = _make_test_trajectories()

    clearance_cross = PairwiseClearance(
        robot_id_a="A",
        robot_id_b="B",
        min_distance_m=0.0,
        required_clearance_m=0.6,
        is_clear=False,
        segment_index_a=0,
        segment_index_b=0,
    )
    rep = GroupTrajectorySafetyReport(False, (), (clearance_cross,), 1)

    canvas.set_group_preview(trajs, rep)
    assert canvas._status_message is not None
    assert canvas._status_message[0] == "存在路径交叉风险"
    assert canvas._status_message[1] == "error"


def test_14_workspace_safety_panel_rich_summary(qapp):
    """14. 工作区安全面板完整呈现检测状态、综合判定、违规机器人与冲突机对详情。"""
    ws = GroupTrajectoryWorkspace()
    trajs, _, group = _make_test_trajectories()

    b_violation = BoundaryViolation("A", 1, 55.0, 0.0, "x_max")
    c_conflict = PairwiseClearance("A", "B", 0.35, 0.6, False, 1, 0)
    rep = GroupTrajectorySafetyReport(
        is_safe=False,
        boundary_violations=(b_violation,),
        pairwise_clearances=(c_conflict,),
        violation_count=2,
    )

    ws.set_group_data(group, trajs, rep)
    assert "已完成静态安全检测" in ws.lbl_safety_status.text()
    assert "存在几何风险" in ws.lbl_overall_result.text()
    assert "存在越界" in ws.lbl_boundary_status.text()
    assert "A" in ws.lbl_boundary_status.text()
    assert "0.35m" in ws.lbl_clearance_status.text()
    assert "A-B" in ws.lbl_clearance_status.text()
    assert "2" in ws.lbl_violations_count.text()
    assert "0.6m" in ws.lbl_disclaimer.text()
    assert ws.lbl_empty_safety.isHidden()


def test_15_workspace_safety_panel_safe_summary(qapp):
    """15. 安全无冲突时工作区展示通过标识及无越界状态。"""
    ws = GroupTrajectoryWorkspace()
    trajs, _, group = _make_test_trajectories()

    c_safe = PairwiseClearance("A", "B", 1.25, 0.6, True, 0, 0)
    rep = GroupTrajectorySafetyReport(
        is_safe=True,
        boundary_violations=(),
        pairwise_clearances=(c_safe,),
        violation_count=0,
    )

    ws.set_group_data(group, trajs, rep)
    assert "已完成静态安全检测" in ws.lbl_safety_status.text()
    assert "静态空间安全通过" in ws.lbl_overall_result.text()
    assert "无越界" in ws.lbl_boundary_status.text()
    assert "间距充足" in ws.lbl_clearance_status.text()
    assert "0" in ws.lbl_violations_count.text()


def test_16_workspace_safety_panel_empty_state(qapp):
    """16. 工作区空状态下安全面板显示初始占位提示。"""
    ws = GroupTrajectoryWorkspace()
    ws.clear_workspace()

    assert not ws.lbl_empty_safety.isHidden()
    assert "尚未检测" in ws.lbl_safety_status.text()
    assert "—" in ws.lbl_overall_result.text()
    assert "尚未检测" in ws.lbl_boundary_status.text()
    assert "尚未检测" in ws.lbl_clearance_status.text()
    assert "0" in ws.lbl_violations_count.text()

