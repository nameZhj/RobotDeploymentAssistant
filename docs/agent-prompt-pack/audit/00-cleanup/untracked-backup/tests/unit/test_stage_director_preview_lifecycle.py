"""
@file: tests/unit/test_stage_director_preview_lifecycle.py
@brief: 3D 视口相机轨道控制、重置视角、焦点跟踪及性能监控生命周期测试
@exports: test_camera_controls_and_focus, test_performance_monitor_benchmark
"""
import sys
import pytest
from PySide6.QtWidgets import QApplication
from src.ui.stage3d.preview_performance_monitor import PreviewPerformanceMonitor
from src.ui.stage3d.stage_viewport_3d import StageViewport3D


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_camera_controls_and_focus(qapp):
    """测试相机重置视角、焦点聚集目标机器人与地面网格开关"""
    vp = StageViewport3D()
    vp.resize(800, 600)

    vp._target_x = 10.0
    vp.reset_camera()
    assert vp._target_x == 0.0
    assert vp._target_y == 0.0
    assert vp._yaw_deg == -45.0
    assert vp._pitch_deg == -30.0

    vp.focus_robot("Robot_1")
    assert vp._target_x == -2.0
    assert vp._target_y == 0.0

    vp.set_grid_visible(False)
    assert vp._grid_visible is False


def test_performance_monitor_benchmark():
    """测试渲染性能监控器正确统计帧延迟与 FPS"""
    monitor = PreviewPerformanceMonitor()
    for _ in range(30):
        monitor.record_sampling_time(0.5)
        monitor.record_frame(16.6)  # ~60 FPS

    report = monitor.generate_report()
    assert report.sample_count == 30
    assert report.avg_fps > 55.0
    assert report.avg_frame_time_ms > 0.0
    assert report.backend == "QPainter (CPU Software Rasterizer)"
