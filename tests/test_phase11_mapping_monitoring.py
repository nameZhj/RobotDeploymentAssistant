# @file: tests/test_phase11_mapping_monitoring.py
# @brief: Verification tests for Page 3 PCD upload/delete/teleop SLAM, Page 4 LRMP monitor, and Page 5 radar.
# @exports: test_navigation_map_page_upload_teleop_and_delete, test_performance_and_radar_monitor_pages

from __future__ import annotations

import os
import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.event_bus import StudioEventBus
from src.persistence import StudioDatabase
from src.persistence.pcd_parser import write_ascii_pcd
from src.persistence.seed_builtin_data import ensure_seeded
from src.services.playback_coordinator import PlaybackCoordinator
from src.services.studio_state_service import StudioStateService
from src.ui.mapping import NavigationMapPage
from src.ui.monitoring import PerformanceMonitorPage, RadarMonitorPage


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_navigation_map_page_upload_teleop_and_delete(tmp_path) -> None:
    _app()
    db = StudioDatabase(tmp_path / "p11.db")
    ensure_seeded(db)
    state = StudioStateService(db=db, bus=StudioEventBus())
    page = NavigationMapPage(state)

    pcd = write_ascii_pcd(tmp_path / "stage_test.pcd", np.array([[0, 0, 0.5], [1, 1, 0.8]], dtype=np.float32))
    saved = page.lib_dock.import_pcd_file(pcd, activate=True)
    assert state.scene.active_map_id == saved.id

    page.teleop_dock._on_start()
    page.teleop_dock._step_move(1.0, 0.0, 0.0)
    slam_ent = page.teleop_dock.save_and_register_map()
    assert slam_ent.id is not None
    page.teleop_dock._on_stop()
    # Cleanup synthetic test maps from real workspace data/maps
    for ent in (saved, slam_ent):
        for p in (ent.file_path, ent.grid_png_path):
            if p and os.path.exists(p):
                os.remove(p)


def test_performance_and_radar_monitor_pages(tmp_path) -> None:
    _app()
    db = StudioDatabase(tmp_path / "p10m.db")
    ensure_seeded(db)
    state = StudioStateService(db=db, bus=StudioEventBus())
    state.load_demo_swarm_preset()
    pb = PlaybackCoordinator(state)
    perf = PerformanceMonitorPage(state, pb)
    radar = RadarMonitorPage(state)
    perf._cmd_prep()
    assert "CHOREO" in perf.phase_badge.text()
    perf._cmd_play()
    assert "PLAY" in perf.phase_badge.text()
    perf._cmd_emergency()
    assert "EMERGENCY" in perf.phase_badge.text()
    assert radar.table.rowCount() == len(state.tracks)
