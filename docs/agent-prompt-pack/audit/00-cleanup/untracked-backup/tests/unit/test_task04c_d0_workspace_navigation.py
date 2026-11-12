"""
@file: tests/unit/test_task04c_d0_workspace_navigation.py
@brief: 任务 04C-D0 群组轨迹工作区入口与界面导航单元测试
@exports: 测试用例函数集合
"""
import os
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from src.application.studio_controller import StudioController
from src.domain.trajectory.group_trajectory import GroupTrajectory, GroupTrajectoryMember
from src.domain.trajectory.group_trajectory_compiler import GroupMemberTrajectory
from src.domain.trajectory.group_trajectory_safety import GroupTrajectorySafetyReport
from src.domain.trajectory.trajectory_asset import TrajectoryPoint
from src.ui.choreo_page.group_trajectory_workspace import GroupTrajectoryWorkspace
from src.ui.windows.main_studio_window import MainStudioWindow


@pytest.fixture(scope="session")
def qapp():
    """保证 PySide6 QApplication 全局实例存在。"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def studio_window(qapp):
    """创建 MainStudioWindow 测试实例。"""
    ctrl = StudioController()
    win = MainStudioWindow(controller=ctrl)
    win.show()
    yield win
    win.close()


def test_01_group_trajectory_entry_visible(studio_window):
    """1. 群组轨迹入口在主编排工作区左侧区域清晰可见。"""
    assert hasattr(studio_window, "btn_group_trajectory")
    btn = studio_window.btn_group_trajectory
    assert "群组轨迹" in btn.text()
    assert btn.parent() is not None


def test_02_click_entry_switches_to_group_workspace(studio_window):
    """2. 点击入口成功进入群组轨迹工作区页面。"""
    assert studio_window.current_workspace_index() == 0
    studio_window.btn_group_trajectory.click()
    assert studio_window.current_workspace_index() == 1
    assert isinstance(studio_window.workspace_stack.currentWidget(), GroupTrajectoryWorkspace)


def test_03_group_workspace_title_correct(studio_window):
    """3. 页面标题正确展示群组轨迹。"""
    studio_window.enter_group_trajectory_workspace()
    ws = studio_window.group_workspace
    assert "群组轨迹" in ws.lbl_title.text()


def test_04_click_back_button_returns_to_single_choreo(studio_window):
    """4. 返回按钮成功回到单机器人编排界面。"""
    studio_window.enter_group_trajectory_workspace()
    assert studio_window.current_workspace_index() == 1

    studio_window.group_workspace.btn_back.click()
    assert studio_window.current_workspace_index() == 0
    assert studio_window.workspace_stack.currentWidget() == studio_window.single_choreo_widget


def test_05_single_robot_state_preserved_across_navigation(studio_window):
    """5. 返回后单机画布状态、未保存控制点与轨迹数据不丢失。"""
    stage_2d = studio_window.stage_2d
    stage_2d._active_waypoints = [(1.5, 2.5), (3.0, 4.0)]
    stage_2d._selected_robot_id = "B"
    test_traj = {"id": "test_t1", "name": "测试轨迹", "waypoints": [(0.0, 0.0), (1.0, 1.0)]}
    stage_2d._completed_trajectories.append(test_traj)

    # 切入群组工作区
    studio_window.enter_group_trajectory_workspace()
    assert studio_window.current_workspace_index() == 1

    # 切回单机工作区
    studio_window.exit_group_trajectory_workspace()
    assert studio_window.current_workspace_index() == 0
    assert stage_2d._active_waypoints == [(1.5, 2.5), (3.0, 4.0)]
    assert stage_2d._selected_robot_id == "B"
    assert len(stage_2d._completed_trajectories) == 1
    assert stage_2d._completed_trajectories[0]["id"] == "test_t1"


def test_06_repeated_navigation_no_recreation(studio_window):
    """6. 页面重复进入不会重复创建不必要的窗口，维持单实例。"""
    ws_instance = studio_window.group_workspace
    assert studio_window.workspace_stack.count() == 2

    for _ in range(10):
        studio_window.enter_group_trajectory_workspace()
        studio_window.exit_group_trajectory_workspace()

    assert studio_window.workspace_stack.count() == 2
    assert studio_window.group_workspace is ws_instance


def test_07_no_duplicate_signal_connections(studio_window):
    """7. 连续多次切换不会重复触发多次返回调用。"""
    call_count = 0

    def on_back():
        nonlocal call_count
        call_count += 1

    studio_window.group_workspace.backRequested.connect(on_back)

    studio_window.enter_group_trajectory_workspace()
    studio_window.group_workspace.btn_back.click()
    assert call_count == 1

    studio_window.enter_group_trajectory_workspace()
    studio_window.group_workspace.btn_back.click()
    assert call_count == 2


def test_08_no_fake_robots_in_clean_workspace(studio_window):
    """8. 新页面初始状态没有虚构机器人数据。"""
    ws = studio_window.group_workspace
    assert ws.list_members.count() == 0
    assert ws._current_group is None
    assert ws._member_trajectories == []
    assert ws._safety_report is None


def test_09_empty_states_displayed_properly(studio_window):
    """9. 空状态在未注入数据时正常呈现。"""
    studio_window.enter_group_trajectory_workspace()
    ws = studio_window.group_workspace
    assert "尚未选择机器人" in ws.lbl_selected_robot.text()
    assert not ws.lbl_empty_members.isHidden()
    assert not ws.lbl_empty_safety.isHidden()
    assert "尚未检测" in ws.lbl_boundary_status.text()
    assert "尚未检测" in ws.lbl_clearance_status.text()


def test_10_no_lingering_timers_or_threads(studio_window):
    """10. 切换后工作区无失控的后台线程或定时器。"""
    studio_window.enter_group_trajectory_workspace()
    studio_window.exit_group_trajectory_workspace()
    assert not hasattr(studio_window.group_workspace, "_worker_thread")


def test_11_single_robot_canvas_features_no_regression(studio_window):
    """11. 原有单机器人 2D 页面功能不发生回归。"""
    stage_2d = studio_window.stage_2d
    stage_2d.set_draw_mode("DRAW_TRAJECTORY")
    assert stage_2d._draw_mode == "DRAW_TRAJECTORY"
    stage_2d.select_robot("A")
    assert stage_2d._selected_robot_id == "A"


def test_12_ui_styling_consistent_with_studio_theme(studio_window):
    """12. UI 样式与现有 Studio 深色主题完全契合。"""
    ws = studio_window.group_workspace
    style = ws.styleSheet()
    assert "#0b0f19" in style
    assert "#0f172a" in style
    assert "#1e293b" in style
    assert "#38bdf8" in style


def test_13_group_data_injection_and_clear(studio_window):
    """13. 数据注入接口正常更新群组成员、画布预览并可一键恢复空状态。"""
    studio_window.enter_group_trajectory_workspace()
    ws = studio_window.group_workspace
    group = GroupTrajectory(
        group_trajectory_id="grp_001",
        name="编队A",
        reference_trajectory_id="ref_traj_01",
        members=[
            GroupTrajectoryMember(robot_id="A", offset_x_m=0.0, offset_y_m=0.5),
            GroupTrajectoryMember(robot_id="B", offset_x_m=0.0, offset_y_m=-0.5),
        ],
    )
    m_pts = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
        TrajectoryPoint(x_m=2.0, y_m=0.0, yaw_deg=0.0, s_m=2.0),
    ]
    trajs = [
        GroupMemberTrajectory("A", "ref_01", "stage_world", tuple(m_pts), 2.0),
        GroupMemberTrajectory("B", "ref_01", "stage_world", tuple(m_pts), 2.0),
    ]
    report = GroupTrajectorySafetyReport(is_safe=True, boundary_violations=(), pairwise_clearances=(), violation_count=0)

    ws.set_group_data(group, trajs, report)
    assert ws.list_members.count() == 2
    assert ws.lbl_empty_members.isHidden()
    assert "编队A" in ws.lbl_selected_robot.text()
    assert "正常" in ws.lbl_boundary_status.text()

    # 清空恢复
    ws.clear_workspace()
    assert ws.list_members.count() == 0
    assert not ws.lbl_empty_members.isHidden()
    assert "尚未选择机器人" in ws.lbl_selected_robot.text()
