"""
@file: tests/unit/test_stage_director_eco_pro_modes.py
@brief: 3D 视口 ECO / PRO 渲染画质切换、状态保全与骨骼高光测试
@exports: test_eco_pro_painter_modes, test_viewport_mode_switch_preserves_state
"""
import sys
import pytest
from PySide6.QtWidgets import QApplication
from src.ui.stage3d.robot_avatar_3d_painter import RobotAvatar3DPainter
from src.ui.stage3d.stage_viewport_3d import StageViewport3D


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_eco_pro_painter_modes():
    """验证渲染器 ECO / PRO 模式设置与状态流转"""
    painter = RobotAvatar3DPainter(mode="ECO")
    assert painter.mode == "ECO"
    painter.set_render_mode("PRO")
    assert painter.mode == "PRO"
    painter.set_render_mode("eco")
    assert painter.mode == "ECO"


def test_viewport_mode_switch_preserves_state(qapp):
    """验证 3D 视口切换画质模式时不重置已有姿态和相机参数"""
    vp = StageViewport3D()
    vp.resize(800, 600)
    vp._target_x = 3.5
    vp._yaw_deg = -60.0

    vp.set_render_mode("PRO")
    assert vp._render_mode == "PRO"
    assert vp.avatar_painter.mode == "PRO"
    assert vp._target_x == 3.5
    assert vp._yaw_deg == -60.0
    assert len(vp._robot_poses) == 2
