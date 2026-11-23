# @file: tests/test_phase13_user_reqs.py
# @brief: End-to-end verification of robot drag init pose, trajectory visibility/multi-binding, serial-only actions, rigid timeline clamping, and robot collision prevention.
# @exports: test_robot_drag_and_volume_collision_guard, test_trajectory_visibility_and_multi_robot_bind, test_serial_only_actions_and_rigid_timeline_collision

from __future__ import annotations

import math
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from backend.serial_dance_parser import DEFAULT_DANCE_GROUPS
from src.core.event_bus import StudioEventBus
from src.core.paths import get_paths
from src.domain.timeline_entities import TimelineBlockEntity
from src.domain.trajectory_entities import ControlPoint2D, TrajectoryEntity
from src.persistence import StudioDatabase, get_database
from src.persistence.seed_builtin_data import ensure_seeded
from src.services.playback_coordinator import PlaybackCoordinator
from src.services.studio_state_service import StudioStateService
from src.ui.choreography.stage_painters import world_to_screen
from src.ui.choreography.timeline_collision_clamp import (
    clamp_move_start,
    clamp_resize_duration,
    resolve_non_overlapping_slot,
)
from src.ui.choreography.track_lib_row import BindRobotsDialog, TrajectoryRowWidget
from src.ui.modals import AddTrackDialog, InitPointModal
from src.ui.windows.main_studio_window import MainStudioWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_robot_drag_and_volume_collision_guard(tmp_path: Path, monkeypatch) -> None:
    _app()
    monkeypatch.setenv("RDA_WORKSPACE_ROOT", str(tmp_path))
    get_paths(reset=True)
    get_database(reset=True)
    win = MainStudioWindow(initial_page="choreography")
    win.resize(1280, 820)

    # 1. Add first robot at (0.0, 0.0)
    d1 = AddTrackDialog(win.state, win)
    d1.init_x.setValue(0.0)
    d1.init_y.setValue(0.0)
    d1._on_submit()
    assert len(win.state.tracks) == 1

    # 2. Blocking guard: same or <0.60m init position must prompt and refuse adding robot
    d_bad = AddTrackDialog(win.state, win)
    d_bad.init_x.setValue(0.2)
    d_bad.init_y.setValue(0.1)
    d_bad._on_submit()
    assert "碰撞" in d_bad.err_lbl.text()
    assert len(win.state.tracks) == 1

    # 3. Add second robot cleanly at (2.0, 0.0)
    d2 = AddTrackDialog(win.state, win)
    d2.init_x.setValue(2.0)
    d2.init_y.setValue(0.0)
    d2._on_submit()
    assert len(win.state.tracks) == 2

    # 4. InitPointModal rejects batch colliding coordinates
    ipm = InitPointModal(win.state, win)
    ipm.table.item(1, 2).setText("0.10")
    ipm.table.item(1, 3).setText("0.00")
    ipm._apply()
    assert "碰撞" in ipm.err_lbl.text()
    assert abs(win.state.tracks[1].init_x - 2.0) < 1e-3

    # 5. Drag selected robot on 2D map toward (0,0): rigid volume collision pushes it >= 0.60m away
    c2d = win.choreography_page.preview_panel.canvas_2d
    c2d.resize(800, 480)
    origin = c2d._origin_px()
    p_sc = world_to_screen(2.0, 0.0, origin, c2d.ppm)
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, p_sc, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    )
    c2d.mousePressEvent(press)
    assert c2d.highlighted_track_id == win.state.tracks[1].id

    drag_sc = world_to_screen(0.1, 0.0, origin, c2d.ppm)
    move = QMouseEvent(
        QMouseEvent.Type.MouseMove, drag_sc, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    )
    c2d.mouseMoveEvent(move)
    rel = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease, drag_sc, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier
    )
    c2d.mouseReleaseEvent(rel)
    dist = math.hypot(win.state.tracks[1].init_x - win.state.tracks[0].init_x, win.state.tracks[1].init_y - win.state.tracks[0].init_y)
    assert dist >= 0.59
    win.close()


def test_trajectory_visibility_and_multi_robot_bind(tmp_path: Path, monkeypatch) -> None:
    _app()
    monkeypatch.setenv("RDA_WORKSPACE_ROOT", str(tmp_path))
    get_paths(reset=True)
    get_database(reset=True)
    win = MainStudioWindow(initial_page="choreography")
    win.state.load_demo_swarm_preset()

    gid = win.state.list_groups()[0].id or 1
    tr = win.state.traj_repo.upsert_trajectory(
        TrajectoryEntity(
            group_id=gid, no=100001, name="双向编队弧线", duration=6.0,
            control_points=[ControlPoint2D(0.0, 0.0), ControlPoint2D(2.0, 1.0)],
        )
    )
    win.state.reload_all()
    win.choreography_page.track_lib.refresh()
    assert tr.visible_on_map is True

    # Toggle visibility checkbox in TrackLibPanel row -> persists across reload
    row_widgets = win.choreography_page.track_lib.findChildren(TrajectoryRowWidget)
    assert len(row_widgets) == 1
    row_widgets[0].vis_chk.setChecked(False)
    assert win.state.trajectories[tr.id].visible_on_map is False

    # Bind trajectory to multiple robots (tracks 1 and 2) via BindRobotsDialog + state helper
    dlg = BindRobotsDialog(win.state.trajectories[tr.id], win.state.tracks, win)
    dlg._checks[1].setChecked(True)
    dlg._checks[2].setChecked(True)
    assert dlg.selected_track_nos() == [1, 2]
    added = win.state.bind_trajectory_tracks(tr.id or 0, dlg.selected_track_nos(), sync_to_timeline=True)
    assert added == 2
    assert win.state.trajectories[tr.id].bound_track_nos == [1, 2]
    assert sum(1 for b in win.state.blocks if b.block_type == "trajectory" and b.ref_id == tr.id) == 2
    win.close()


def test_serial_only_actions_and_rigid_timeline_collision(tmp_path: Path) -> None:
    _app()
    db = StudioDatabase(tmp_path / "p13.db")
    ensure_seeded(db)

    class _SerialStub:
        def __init__(self, connected: bool, groups):
            self.is_connected = connected
            self.latest_dance_list_parsed = groups

        def request_dance_list(self, timeout=3.0, force=True):
            return {"success": self.is_connected, "groups": self.latest_dance_list_parsed}

    # Disconnected with empty cache -> strictly 0 actions
    st_off = StudioStateService(db=db, bus=StudioEventBus(), serial_manager=_SerialStub(False, []))
    assert len(st_off.action_repo.list_actions()) == 0
    ok, cnt, _ = st_off.sync_actions_from_serial()
    assert not ok and cnt == 0

    # Connected -> receives real serial groups
    st_on = StudioStateService(db=db, bus=StudioEventBus(), serial_manager=_SerialStub(True, DEFAULT_DANCE_GROUPS[:1]))
    ok2, cnt2, _ = st_on.sync_actions_from_serial()
    assert ok2 and cnt2 == len(DEFAULT_DANCE_GROUPS[0]["items"])

    # Rigid-body timeline collision clamping: same-type blocks cannot overlap during move, resize, or drop
    fixed = TimelineBlockEntity(id=1, track_id=1, block_type="action", start_time=5.0, duration=4.0)  # [5, 9]
    assert clamp_move_start(6.0, 3.0, 1.0, [fixed]) == 2.0
    assert clamp_move_start(7.0, 3.0, 11.0, [fixed]) == 9.0
    assert clamp_resize_duration(2.0, 8.0, [fixed]) == 3.0
    assert resolve_non_overlapping_slot(6.0, 2.0, [fixed]) == 9.0
