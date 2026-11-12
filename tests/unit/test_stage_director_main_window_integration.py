"""
@file: tests/unit/test_stage_director_main_window_integration.py
@brief: MainStudioWindow 舞台主窗口左侧坞、主工具栏与 2D 画布端到端集成测试
@exports: test_main_studio_window_components_wiring
"""
import sys
import pytest
from PySide6.QtWidgets import QApplication
from src.ui.windows.main_studio_window import MainStudioWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_main_studio_window_components_wiring(qapp):
    """测试主编导窗口实例化、左侧坞与工具栏及 2D 画布的连接装配"""
    window = MainStudioWindow()
    window.resize(1200, 800)

    # 1. 验证左侧坞已成功装配在 left_dock_container 并具备多机装配能力
    assert window.stage_dock is not None
    test_robots = [{"id": "A", "name": "Robot_1", "pos": (-2.0, 0.0)}, {"id": "B", "name": "Robot_2", "pos": (2.0, 0.0)}]
    window.stage_dock.set_robots(test_robots)
    window.stage_2d.set_robots(test_robots)
    assert window.stage_dock.robot_list.count() >= 2

    # 2. 验证工具栏已装配
    assert window.toolbar is not None
    assert window.toolbar.btn_draw is not None

    # 3. 验证 2D 画布组件存在
    assert window.stage_2d is not None

    # 4. 验证互操作：切换工具栏模式同步至画布
    window.toolbar.btn_select.click()
    assert window.stage_2d._draw_mode == "SELECT"

    # 5. 验证机器人选中双向联动
    window.stage_dock.select_robot("B")
    assert window.stage_2d._selected_robot_id == "B"

    window.close()
