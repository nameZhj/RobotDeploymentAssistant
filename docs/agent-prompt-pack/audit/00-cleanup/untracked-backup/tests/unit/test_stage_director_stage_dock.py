"""
@file: tests/unit/test_stage_director_stage_dock.py
@brief: 舞台左侧信息坞场景元数据更新、多机列表同步及位姿展示测试
@exports: test_dock_initialization, test_update_scene_info, test_set_robots_and_selection, test_readonly_lock_hint
"""
import sys
import pytest
from PySide6.QtWidgets import QApplication
from src.ui.choreo_page.stage_dock_left_panel import StageDockLeftPanel


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def dock(qapp):
    widget = StageDockLeftPanel()
    widget.resize(280, 600)
    return widget


def test_dock_initialization(dock):
    """测试左侧坞各区域组件正常初始化"""
    assert dock.lbl_scene_name is not None
    assert dock.robot_list is not None
    assert dock.lbl_pose_robot is not None


def test_update_scene_info(dock):
    """测试场景元数据更新并反映至 UI 标签"""
    info = {
        "name": "测试数字大舞台",
        "map_file": "stage_v1.pcd",
        "dimensions": "15.0m × 15.0m",
        "resolution": 0.05,
        "origin": "(1.0, 2.0)",
        "status": "就绪 (Ready)"
    }
    dock.update_scene_info(info)
    assert dock.lbl_scene_name.text() == "测试数字大舞台"
    assert dock.lbl_map_file.text() == "stage_v1.pcd"
    assert dock.lbl_dimensions.text() == "15.0m × 15.0m"
    assert dock.lbl_status.text() == "就绪 (Ready)"


def test_set_robots_and_selection(dock):
    """测试多机器人站位数据同步与列表切换响应"""
    selected_signals = []
    dock.robotSelected.connect(lambda rid: selected_signals.append(rid))

    robots = [
        {"id": "A", "name": "Robot_1", "model": "G1", "pos": (-2.0, 1.0), "yaw_deg": 45.0},
        {"id": "B", "name": "Robot_2", "model": "G1", "pos": (3.0, -1.0), "yaw_deg": 180.0},
    ]
    dock.set_robots(robots)
    assert dock.robot_list.count() == 2

    dock.select_robot("B")
    assert "B" in selected_signals
    assert dock.lbl_pose_x.text() == "3.00 m"
    assert dock.lbl_pose_y.text() == "-1.00 m"
    assert dock.lbl_pose_yaw.text() == "180.0°"


def test_readonly_lock_hint(dock):
    """验证 Phase 03 位姿展示区域具备防写库只读提示"""
    assert dock.lbl_pose_x.text() is not None
    labels = dock.findChildren(type(dock.lbl_pose_x))
    has_lock_text = any("只读监视" in lbl.text() for lbl in labels)
    assert has_lock_text
