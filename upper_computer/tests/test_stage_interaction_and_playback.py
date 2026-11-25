# @file: tests/test_stage_interaction_and_playback.py
# @brief: Tests trajectory draw -> select/drag recovery, zero-uni branding cleanup, and playback reset-to-origin on last block end.

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel

from src.core.settings import get_settings
from src.domain.timeline_entities import TimelineBlockEntity
from src.domain.trajectory_entities import ControlPoint2D
from src.ui.modals import AddTrackDialog
from src.ui.windows.main_studio_window import MainStudioWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_draw_to_select_recovery_and_robot_drag(tmp_path: Path, monkeypatch) -> None:
    _app()
    monkeypatch.setenv("RDA_WORKSPACE_ROOT", str(tmp_path))
    from src.core.paths import get_paths
    get_paths(reset=True)
    win = MainStudioWindow(initial_page="choreography")
    win.resize(1280, 820)

    dlg = AddTrackDialog(win.state, win)
    dlg.target_edit.setText("A")
    dlg.init_x.setValue(0.0)
    dlg.init_y.setValue(0.0)
    dlg._on_submit()

    pmp = win.choreography_page.preview_panel
    tb = pmp.draw_toolbar
    c2d = pmp.canvas_2d
    c2d.resize(600, 400)

    # 1. Enter trajectory draw mode -> Esc must restore mouse selection mode
    tb.draw_btn.click()
    assert c2d.draw_mode == "draw_traj" and tb.draw_btn.isChecked()
    c2d.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert c2d.draw_mode == "view" and tb.select_btn.isChecked() and not tb.draw_btn.isChecked()

    # 2. Enter trajectory draw mode -> clearDraftClicked must also restore mouse selection mode
    tb.draw_btn.click()
    c2d.draft_points = [ControlPoint2D(0.0, 0.0, 0.0), ControlPoint2D(1.0, 0.5, 0.0)]
    tb.clr_traj_btn.click()
    assert len(c2d.draft_points) == 0
    assert c2d.draw_mode == "view" and tb.select_btn.isChecked()

    # 3. Dragging robot visually in view mode updates its start position even after playhead moved
    win.playback.seek(2.5)
    from src.ui.choreography.stage_painters import world_to_screen
    sc = world_to_screen(0.0, 0.0, c2d._origin_px(), c2d.ppm)
    c2d.mousePressEvent(QMouseEvent(QMouseEvent.Type.MouseButtonPress, sc, sc, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    assert abs(win.state.playhead_s) < 1e-6  # Auto-snaps to initial t=0 when dragging start pose
    dst = world_to_screen(1.2, 0.8, c2d._origin_px(), c2d.ppm)
    c2d.mouseMoveEvent(QMouseEvent(QMouseEvent.Type.MouseMove, dst, dst, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    c2d.mouseReleaseEvent(QMouseEvent(QMouseEvent.Type.MouseButtonRelease, dst, dst, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    assert abs(win.state.tracks[0].init_x - 1.2) < 0.05 and abs(win.state.tracks[0].init_y - 0.8) < 0.05
    win.close()


def test_no_uni_branding_and_playback_reset_after_last_action(tmp_path: Path, monkeypatch) -> None:
    _app()
    monkeypatch.setenv("RDA_WORKSPACE_ROOT", str(tmp_path))
    from src.core.paths import get_paths
    get_paths(reset=True)
    win = MainStudioWindow(initial_page="choreography")

    # Task 2 assertions: no UniSwarm / Unitree / UniUni in title, settings, or titlebar corner
    cfg = get_settings(reload=True)
    for forbidden in ("uniswarm", "uniuni", "unitree"):
        assert forbidden not in cfg.app_title.lower()
        assert forbidden not in win.windowTitle().lower()
    titlebar_labels = [lbl.text().lower() for lbl in win.titlebar.findChildren(QLabel)]
    assert not any("uni" in t for t in titlebar_labels)

    # Task 3 assertions: empty timeline must not advance playhead into empty space
    assert win.state.effective_playback_duration() == 0.0
    win.playback.play()
    assert win.playback.is_playing is False and win.state.playhead_s == 0.0

    # Add robot + single 2.5s action while task.total_duration > 2.5s; playback must stop and reset at 2.5s
    dlg = AddTrackDialog(win.state, win)
    dlg.target_edit.setText("A")
    dlg._on_submit()
    win.state.commit_block_change(
        None,
        TimelineBlockEntity(
            task_id=win.state.task.id or 1,
            track_id=win.state.tracks[0].id or 1,
            block_type="action",
            ref_id=1,
            code_no="G1_TAIJI",
            title="太极",
            start_time=0.0,
            duration=2.5,
        ),
        "插入短动作",
    )
    assert abs(win.state.effective_playback_duration() - 2.5) < 1e-4
    win.playback.play()
    assert win.playback.is_playing is True
    win.state.playhead_s = 2.49
    win.playback._on_tick()
    assert win.playback.is_playing is False
    assert abs(win.state.playhead_s) < 1e-6
    win.close()
