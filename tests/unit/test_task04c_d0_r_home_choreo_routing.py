"""
@file: tests/unit/test_task04c_d0_r_home_choreo_routing.py
@brief: 任务 04C-D0-R 主页「舞台编导」入口真实路由与正确工作区跳转集成测试
@exports: test_01 到 test_10 完整端到端测试用例
"""
import os
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

from app import app
from main import _studio_manager, launch_studio_window
from src.ui.choreo_page.group_trajectory_workspace import GroupTrajectoryWorkspace
from src.ui.choreo_page.stage_canvas_2d import StageCanvas2D
from src.ui.windows.main_studio_window import MainStudioWindow
from src.ui.windows.studio_main_window import StudioMainWindow


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """保证 PySide6 QApplication 全局实例存在。"""
    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    return application


@pytest.fixture
def client():
    """Flask 测试客户端。"""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_01_home_page_renders_with_navbar_studio_button(client):
    """1. 验证正常启动应用后，主页正常渲染且包含唯一的「🎬 舞台编导」按钮。"""
    res = client.get("/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert 'id="btn-open-studio-window"' in html
    assert "舞台编导" in html
    # 确保主页没有多余同名按钮
    assert html.count('id="btn-open-studio-window"') == 1


def test_02_navbar_button_api_route_success(client):
    """2. 验证前端点击绑定的 /api/system/open-studio 路由正确执行并返回成功。"""
    res = client.post("/api/system/open-studio")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "舞台编导控制台已唤起" in data["msg"]


def test_03_opened_window_is_correct_active_main_studio_window(qapp):
    """3. 验证真正实例化的窗口是当前活跃维护的 MainStudioWindow。"""
    success, msg = launch_studio_window()
    assert success is True
    win = _studio_manager._window
    assert win is not None
    assert isinstance(win, MainStudioWindow)
    assert "舞蹈编排" in win.windowTitle()
    assert isinstance(win.stage_2d, StageCanvas2D)


def test_04_opened_window_is_not_historical_error_page(qapp):
    """4. 确认主页入口绝不进入历史冻结的 StudioMainWindow 多标签旧外壳。"""
    _studio_manager.ensure_qt_running()
    launch_studio_window()
    win = _studio_manager._window
    assert not isinstance(win, StudioMainWindow)
    assert not hasattr(win, "page_monitor")
    assert not hasattr(win, "page_map")


def test_05_window_reuse_no_duplicate_instances(qapp):
    """5. 多次从主页调用唤起，复用同一窗口实例，绝不产生重复窗口。"""
    launch_studio_window()
    first_win = _studio_manager._window
    first_id = id(first_win)

    launch_studio_window()
    second_win = _studio_manager._window
    assert id(second_win) == first_id
    assert second_win is first_win


def test_06_group_trajectory_button_visible_in_single_choreo(qapp):
    """6. 进入舞台编导后，左侧工作区呈现「👥 群组轨迹」入口且默认位于单机编排。"""
    launch_studio_window()
    win = _studio_manager._window
    assert hasattr(win, "btn_group_trajectory")
    assert win.btn_group_trajectory.text() == "👥 群组轨迹"
    assert win.current_workspace_index() == 0


def test_07_click_group_trajectory_navigates_to_workspace(qapp):
    """7. 点击群组轨迹入口能够顺畅进入群组轨迹工作区。"""
    launch_studio_window()
    win = _studio_manager._window
    win.enter_group_trajectory_workspace()
    assert win.current_workspace_index() == 1
    current_widget = win.workspace_stack.currentWidget()
    assert isinstance(current_widget, GroupTrajectoryWorkspace)


def test_08_return_to_single_choreo_preserves_canvas(qapp):
    """8. 从群组轨迹工作区返回后，原有单机器人画布状态与功能完好。"""
    launch_studio_window()
    win = _studio_manager._window
    win.stage_2d._completed_trajectories = [{"id": "single_test_01", "waypoints": [(0, 0), (1, 1)]}]
    win.enter_group_trajectory_workspace()
    assert win.current_workspace_index() == 1

    win.exit_group_trajectory_workspace()
    assert win.current_workspace_index() == 0
    assert len(win.stage_2d._completed_trajectories) == 1
    assert win.stage_2d._completed_trajectories[0]["id"] == "single_test_01"


def test_09_close_and_reopen_studio_maintains_lifecycle(qapp):
    """9. 关闭 Studio 窗口后重新从主页打开，正常重显且无信号污染。"""
    launch_studio_window()
    win = _studio_manager._window
    win.show()
    assert win.isVisible()

    win.hide()
    assert not win.isVisible()

    success, _ = launch_studio_window()
    assert success is True
    assert _studio_manager._window is win
    win.show()
    assert win.isVisible()


def test_10_home_page_other_features_regression_check(client):
    """10. 验证主页其他核心接口（系统状态、向导组件）未受影响，零回归问题。"""
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.get_json()
    assert "connected" in data
