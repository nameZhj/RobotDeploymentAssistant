# @file: tests/test_phase6_shell.py
# @brief: Tests verifying UniUniAppShell 32px header, 28px statusbar, 6-page routing, and playback clock.
# @exports: test_shell_geometry_and_page_routing

from __future__ import annotations

import os
import pathlib
import pytest
from PySide6.QtWidgets import QApplication

from src.ui.windows.main_studio_window import MainStudioWindow


@pytest.fixture(scope="module")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def test_shell_geometry_and_page_routing(qt_app, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RDA_WORKSPACE_ROOT", str(tmp_path))
    from src.core.paths import get_paths
    get_paths(reset=True)

    win = MainStudioWindow()
    assert win.titlebar.height() == 32
    assert win.statusbar.height() == 28
    assert win.stack.count() == 6

    win.switch_page("formation")
    assert win.titlebar._tab_buttons["formation"].isChecked()
    win.switch_page("network")
    assert win.titlebar._tab_buttons["network"].isChecked()

    win.playback.seek(5.5)
    assert abs(win.state.playhead_s - 5.5) < 1e-6
    assert "00:05.50" in win.statusbar.lbl_timecode.text()
    win.close()
    monkeypatch.undo()
    get_paths(reset=True)
