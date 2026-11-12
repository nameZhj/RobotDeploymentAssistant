"""
@file: tests/compatibility/test_studio_launch_contracts.py
@brief: 舞台编导 Qt 桌面窗口唤起与生命周期契约测试 (2026-10-01 前基线)
@exports: test_studio_manager_launch_and_close
"""
import os
import pytest
from main import _studio_manager, launch_studio_window
from src.ui.windows.main_studio_window import MainStudioWindow


def test_studio_manager_launch_and_close(qapp):
    """验证 StudioWindowManager 正常初始化窗口，并在关闭后能二次正常唤起。"""
    _studio_manager.ensure_qt_running()

    # 首次唤起
    launch_studio_window()
    win = _studio_manager._window
    assert win is not None
    assert isinstance(win, MainStudioWindow)
    assert "舞蹈编排" in win.windowTitle()

    # 模拟关闭窗口
    win.close()

    # 二次唤起，应当安全恢复，绝不抛出 RuntimeError
    success, msg = launch_studio_window()
    assert success is True
    assert _studio_manager._window is not None
    assert isinstance(_studio_manager._window, MainStudioWindow)
