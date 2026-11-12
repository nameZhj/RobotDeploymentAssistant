"""
@file: tests/unit/test_stage_director_2d_canvas.py
@brief: 2D 舞台交互画布样条拟合、控制点撤销、轨迹结算及地图加载测试
@exports: test_waypoint_and_spline_fitting, test_finish_trajectory, test_undo_and_clear, test_load_map, test_robot_selection
"""
import sys
import pytest
from PySide6.QtWidgets import QApplication
from src.ui.choreo_page.stage_canvas_2d import StageCanvas2D


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def canvas(qapp):
    widget = StageCanvas2D()
    widget.resize(800, 600)
    return widget


def test_waypoint_and_spline_fitting(canvas):
    """测试添加轨迹点并验证向心样条曲线的实时平滑拟合"""
    canvas._active_waypoints.append((0.0, 0.0))
    canvas._recompute_spline()
    assert len(canvas._live_spline_points) == 1

    canvas._active_waypoints.append((2.0, 3.0))
    canvas._active_waypoints.append((4.0, 1.0))
    canvas._recompute_spline()
    assert len(canvas._live_spline_points) > 10
    assert canvas._live_spline_points[0] == (0.0, 0.0)


def test_finish_trajectory(canvas):
    """测试完成当前轨迹时发射 trajectoryFinished 信号及数据结构完整性"""
    received_payload = {}

    def on_finished(data):
        received_payload.update(data)

    canvas.trajectoryFinished.connect(on_finished)
    canvas._active_waypoints.extend([(0.0, 0.0), (1.0, 2.0), (3.0, 0.0)])
    canvas._recompute_spline()
    canvas.finish_trajectory()

    assert "id" in received_payload
    assert "waypoints" in received_payload
    assert len(received_payload["waypoints"]) == 3
    assert "spline_points" in received_payload
    assert len(received_payload["spline_points"]) > 10
    assert received_payload["length"] > 0.0
    assert received_payload["duration"] > 0.0
    assert len(canvas._active_waypoints) == 0
    assert len(canvas._completed_trajectories) == 1


def test_undo_and_clear(canvas):
    """测试撤销上一个控制点以及清空画布轨迹"""
    canvas._active_waypoints.extend([(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)])
    canvas.undo_waypoint()
    assert len(canvas._active_waypoints) == 2
    assert canvas._active_waypoints[-1] == (1.0, 1.0)

    canvas.clear_active_trajectory()
    assert len(canvas._active_waypoints) == 0
    assert len(canvas._live_spline_points) == 0


def test_load_map(canvas):
    """测试默认 PCD 地图解析、占据栅格投射及元数据信号发射"""
    loaded_meta = {}

    def on_map_loaded(meta):
        loaded_meta.update(meta)

    canvas.mapLoaded.connect(on_map_loaded)
    canvas.load_map(None)  # None loads default stage points

    assert canvas._grid_image is not None
    assert canvas._grid_image.width() > 0
    assert canvas._grid_info is not None
    assert "resolution" in canvas._grid_info
    assert loaded_meta.get("status") == "已加载 (Loaded)"


def test_robot_selection(canvas):
    """测试机器人站位节点选中与信号广播"""
    selected_ids = []
    canvas.robotSelected.connect(lambda rid: selected_ids.append(rid))

    canvas.select_robot("B")
    assert canvas._selected_robot_id == "B"
    assert selected_ids == ["B"]
