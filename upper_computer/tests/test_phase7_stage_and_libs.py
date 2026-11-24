# @file: tests/test_phase7_stage_and_libs.py
# @brief: Verification tests for Phase 7 2D/3D preview panel, playback scrubber, trajectory editor modal, and right libraries.
# @exports: test_preview_panel_2d_3d_switch, test_trajectory_editor_modal_save_and_virtual_http, test_track_and_action_libraries

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.event_bus import StudioEventBus
from src.domain.trajectory_entities import ControlPoint2D
from src.persistence import StudioDatabase
from src.persistence.seed_builtin_data import ensure_seeded
from src.services.playback_coordinator import PlaybackCoordinator
from src.services.studio_state_service import StudioStateService
from src.ui.choreography import ActionLibPanel, PreviewMapPanel, TrackLibPanel
from src.ui.modals import TrajectoryEditorModal


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_preview_panel_2d_3d_switch(tmp_path) -> None:
    _app()
    db = StudioDatabase(tmp_path / "p7.db")
    ensure_seeded(db)
    state = StudioStateService(db=db, bus=StudioEventBus())
    pb = PlaybackCoordinator(state)
    panel = PreviewMapPanel(state, pb)
    assert panel.stack.currentIndex() == 0
    panel.mode_switch.set_current("3D")
    assert panel.stack.currentIndex() == 1
    panel.mode_switch.set_current("2D")
    assert panel.stack.currentIndex() == 0
    pb.seek(3.5)
    assert abs(state.playhead_s - 3.5) < 1e-4


def test_trajectory_editor_modal_save_and_virtual_http(tmp_path) -> None:
    _app()
    db = StudioDatabase(tmp_path / "p7m.db")
    ensure_seeded(db)
    state = StudioStateService(db=db, bus=StudioEventBus())
    dlg = TrajectoryEditorModal(state)
    dlg.name_edit.setText("双子星圆弧")
    dlg.traj.control_points = [ControlPoint2D(0.0, 0.0), ControlPoint2D(2.0, 1.5), ControlPoint2D(4.0, 0.0)]
    dlg._upload_http()
    assert "未配置" in dlg.http_badge.text() or "HTTP" in dlg.http_badge.text()
    dlg._on_save()
    assert dlg.saved_traj is not None
    assert dlg.saved_traj.name == "双子星圆弧"
    assert dlg.saved_traj.id in state.trajectories


def test_track_and_action_libraries(tmp_path) -> None:
    _app()
    db = StudioDatabase(tmp_path / "p7l.db")
    ensure_seeded(db)
    from backend.serial_dance_parser import DEFAULT_DANCE_GROUPS

    class _MockSerial:
        is_connected = True
        latest_dance_list_parsed = DEFAULT_DANCE_GROUPS

        def request_dance_list(self, timeout=3.0, force=True):
            return {"success": True, "groups": DEFAULT_DANCE_GROUPS}

    state = StudioStateService(db=db, bus=StudioEventBus(), serial_manager=_MockSerial())
    tlib = TrackLibPanel(state)
    alib = ActionLibPanel(state)
    assert len(state.list_groups()) >= 1
    assert alib.list_layout.count() == 2  # UEmpty + stretch when serial hasn't synced yet
    ok, cnt, _ = state.sync_actions_from_serial()
    assert ok and cnt == 33
    assert alib.list_layout.count() >= 33
    alib.search_box.setText("太极")
    assert alib.list_layout.count() >= 1 and alib.list_layout.count() <= 6
    tlib.show()
    alib.show()
    assert not tlib.isHidden() and not alib.isHidden()
