"""
@file: tests/unit/test_stage_director_choreo_toolbar.py
@brief: 舞台编导主操作工具栏信号触发及模式切换状态测试
@exports: test_toolbar_mode_switch, test_toolbar_action_signals
"""
import sys
import pytest
from PySide6.QtWidgets import QApplication
from src.ui.choreo_page.choreo_toolbar import ChoreoToolbar


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def toolbar(qapp):
    widget = ChoreoToolbar()
    return widget


def test_toolbar_mode_switch(toolbar):
    """测试选择模式与绘制模式切换及信号广播"""
    emitted_modes = []
    toolbar.modeChanged.connect(lambda m: emitted_modes.append(m))

    toolbar.btn_select.click()
    assert "SELECT" in emitted_modes
    assert toolbar._current_mode == "SELECT"

    toolbar.btn_draw.click()
    assert "DRAW_TRAJECTORY" in emitted_modes
    assert toolbar._current_mode == "DRAW_TRAJECTORY"


def test_toolbar_action_signals(toolbar):
    """测试工具栏撤销、清空、完成、重置视角及急停信号触发"""
    signals_fired = []

    toolbar.undoRequested.connect(lambda: signals_fired.append("UNDO"))
    toolbar.clearRequested.connect(lambda: signals_fired.append("CLEAR"))
    toolbar.finishRequested.connect(lambda: signals_fired.append("FINISH"))
    toolbar.resetViewRequested.connect(lambda: signals_fired.append("RESET"))
    toolbar.emergencyStopRequested.connect(lambda: signals_fired.append("ESTOP"))

    toolbar.btn_undo.click()
    toolbar.btn_clear.click()
    toolbar.btn_finish.click()
    toolbar.btn_reset_view.click()
    toolbar.btn_estop.click()

    assert signals_fired == ["UNDO", "CLEAR", "FINISH", "RESET", "ESTOP"]
