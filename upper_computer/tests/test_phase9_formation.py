# @file: tests/test_phase9_formation.py
# @brief: Phase 9 verification for formation template generation, 2-Opt pairing, potential field solver, and timeline commit.
# @exports: test_formation_planning_page_end_to_end

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.event_bus import StudioEventBus
from src.persistence import StudioDatabase
from src.persistence.seed_builtin_data import ensure_seeded
from src.services.studio_state_service import StudioStateService
from src.ui.formation import FormationPlanningPage


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_formation_planning_page_end_to_end(tmp_path) -> None:
    _app()
    db = StudioDatabase(tmp_path / "p9.db")
    ensure_seeded(db)
    state = StudioStateService(db=db, bus=StudioEventBus())
    state.load_demo_swarm_preset()
    page = FormationPlanningPage(state)

    page.ctrl_dock.kind_sel.set_current_data("circle")
    page.generate_targets()
    assert len(page.canvas.targets) == len(state.tracks)

    res = page.solve_paths()
    assert res.converged
    assert len(res.simplified_knots) == len(state.tracks)

    before_blocks = len(state.blocks)
    grp = page.commit_to_library()
    assert grp.id is not None
    assert len(state.blocks) == before_blocks + len(state.tracks)

    # Verify map overlay binding and TEB speed sync path (offline returns 0 safely)
    from src.domain.map_entities import PcdMapEntity
    from PySide6.QtGui import QImage
    png_p = tmp_path / "grid.png"
    img = QImage(32, 32, QImage.Format.Format_RGBA8888)
    img.fill(0)
    img.save(str(png_p))
    saved_m = state.map_repo.upsert_map(PcdMapEntity(name="test_map", grid_png_path=str(png_p), resolution=0.05))
    state.scene.active_map_id = saved_m.id
    state.scene_repo.update_scene(state.scene)
    state.reload_all()
    page.canvas._sync_active_map()
    assert page.canvas._grid_img is not None
    assert page.sync_teb_max_speed(0.8) == 0
