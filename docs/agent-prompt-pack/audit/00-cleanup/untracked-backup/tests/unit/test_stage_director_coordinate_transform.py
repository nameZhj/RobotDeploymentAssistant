"""
@file: tests/unit/test_stage_director_coordinate_transform.py
@brief: 舞台编导 2D 画布笛卡尔坐标系正反向转换及缩放平移数学精度测试
@exports: test_screen_to_stage_origin, test_stage_to_screen_roundtrip, test_panning_shift, test_zoom_scale
"""
import sys
import pytest
from PySide6.QtCore import QPointF
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


def test_screen_to_stage_origin(canvas):
    """验证屏幕正中心对应舞台坐标原点 (0, 0)"""
    # width=800, height=600 -> center is (400, 300)
    stage_pos = canvas.screen_to_stage((400.0, 300.0))
    assert stage_pos == (0.0, 0.0)


def test_stage_to_screen_roundtrip(canvas):
    """验证舞台坐标与屏幕坐标的正反向往返一致性"""
    test_points = [(0.0, 0.0), (1.5, 2.5), (-3.2, -1.8), (10.0, -5.0)]
    for sx, sy in test_points:
        screen_pt = canvas.stage_to_screen(sx, sy)
        recovered_stage = canvas.screen_to_stage(screen_pt)
        assert pytest.approx(recovered_stage[0], abs=1e-2) == sx
        assert pytest.approx(recovered_stage[1], abs=1e-2) == sy


def test_panning_shift(canvas):
    """验证平移偏移 offset_x, offset_y 对视口投影的线性位移"""
    canvas._offset_x = 50.0
    canvas._offset_y = -30.0

    # New screen center: cx = 400 + 50 = 450, cy = 300 - 30 = 270
    center_stage = canvas.screen_to_stage((450.0, 270.0))
    assert center_stage == (0.0, 0.0)

    # (0, 0) stage should now map to (450, 270)
    screen_pt = canvas.stage_to_screen(0.0, 0.0)
    assert screen_pt.x() == 450.0
    assert screen_pt.y() == 270.0


def test_zoom_scale(canvas):
    """验证缩放 scale 改变时舞台坐标计算的一致性与保真度"""
    canvas._scale = 40.0  # 40 px / m
    screen_pt = canvas.stage_to_screen(2.0, 3.0)
    # cx = 400, cy = 300 -> sx = 400 + 2*40 = 480, sy = 300 - 3*40 = 180
    assert screen_pt.x() == 480.0
    assert screen_pt.y() == 180.0

    recovered = canvas.screen_to_stage(screen_pt)
    assert recovered == (2.0, 3.0)
