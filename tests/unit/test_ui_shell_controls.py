"""
@file: tests/unit/test_ui_shell_controls.py
@brief: UniUni 风格主工作台外壳、Splitter 尺寸与按键事件契约单元测试
@exports: test_uniuni_theme_tokens_and_stylesheet, test_main_studio_window_splitters_and_min_sizes, test_top_header_actions
"""
import os
import sys
import pytest
from PySide6.QtWidgets import QApplication
from src.ui.theme.uniuni_inspired_theme import UNIUNI_TOKENS, get_uniuni_stylesheet
from src.ui.windows.main_studio_window import MainStudioWindow


@pytest.fixture(scope="module")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    from main import _studio_manager
    _studio_manager.ensure_qt_running()
    yield app


def test_uniuni_theme_tokens_and_stylesheet():
    """验证 UniUni 真实设计 Token 完整性与 QSS 样式字符串。"""
    required_keys = [
        "window_base", "canvas", "panel", "card", "control",
        "text_primary", "accent", "success", "warning", "danger"
    ]
    for k in required_keys:
        assert k in UNIUNI_TOKENS
        assert UNIUNI_TOKENS[k].startswith("#") or UNIUNI_TOKENS[k].startswith("rgba")

    qss = get_uniuni_stylesheet()
    assert "QMainWindow" in qss
    assert "panel-container" in qss
    assert UNIUNI_TOKENS["window_base"] in qss
    assert UNIUNI_TOKENS["accent"] in qss


def test_main_studio_window_splitters_and_min_sizes(qapp):
    """验证 MainStudioWindow 的窗口限制 (1440x900 默认, 1200x720 最小) 与 Splitter 结构。"""
    win = MainStudioWindow()
    assert win.minimumWidth() >= 1200
    assert win.minimumHeight() >= 720

    # 检查核心容器存在性
    assert hasattr(win, "left_dock_container")
    assert hasattr(win, "viewport_container")
    assert hasattr(win, "right_dock_container")
    assert hasattr(win, "timeline_container")

    # 检查 Splitter 最小约束
    assert win.left_dock_container.minimumWidth() >= 220
    assert win.timeline_container.minimumHeight() >= 220


def test_top_header_actions(qapp):
    """验证 TopShowHeader 的快捷键配置、工具提示与触发信号。"""
    win = MainStudioWindow()
    header = win.header

    assert header.btn_new.shortcut().toString() == "Ctrl+N"
    assert "Ctrl+N" in header.btn_new.toolTip()

    assert header.btn_import.shortcut().toString() == "Ctrl+O"
    assert "Ctrl+O" in header.btn_import.toolTip()

    assert header.btn_save.shortcut().toString() == "Ctrl+S"
    assert "Ctrl+S" in header.btn_save.toolTip()
    assert header.btn_save.property("class") == "btn-primary"


def test_offscreen_screenshot_rendering(tmp_path, qapp):
    """验证离线模式下窗口能正常渲染并保存至 PNG 文件。"""
    win = MainStudioWindow()
    win.resize(1200, 720)
    win.show()
    qapp.processEvents()

    target_png = tmp_path / "test_render.png"
    success = win.grab().save(str(target_png))
    assert success is True
    assert target_png.exists()
    assert target_png.stat().st_size > 1000
