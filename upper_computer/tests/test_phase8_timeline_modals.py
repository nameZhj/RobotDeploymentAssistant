# @file: tests/test_phase8_timeline_modals.py
# @brief: Phase 8 verification for timeline lane editor, block split/duplicate/overlap, batch drawer, and all modals.
# @exports: test_timeline_block_lifecycle_and_overlap, test_all_standard_modals_construct, test_choreography_page_in_main_window

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.event_bus import StudioEventBus
from src.domain.timeline_entities import TimelineBlockEntity
from src.persistence import StudioDatabase
from src.persistence.seed_builtin_data import ensure_seeded
from src.services.playback_coordinator import PlaybackCoordinator
from src.services.studio_state_service import StudioStateService
from src.ui.choreography import ChoreographyPage
from src.ui.modals import (
    AddTrackDialog,
    CoordTransformModal,
    CustomMapModal,
    DeviceOverviewModal,
    FragmentSaveDialog,
    InitPointModal,
    PreDanceCheckModal,
    StageSizeModal,
    SwitchTaskModal,
    TaskJsonViewerModal,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_timeline_block_lifecycle_and_overlap(tmp_path) -> None:
    _app()
    db = StudioDatabase(tmp_path / "p8.db")
    ensure_seeded(db)
    state = StudioStateService(db=db, bus=StudioEventBus())
    state.load_demo_swarm_preset()
    pb = PlaybackCoordinator(state)
    page = ChoreographyPage(state, pb)
    lv = page.task_editor.lane_view

    tr_id = state.tracks[0].id or 1
    b1 = state.scene_repo.upsert_block(
        TimelineBlockEntity(task_id=state.task.id or 1, track_id=tr_id, block_type="action", ref_id=1, code_no="G1_TAIJI", title="太极", start_time=0.0, duration=8.0)
    )
    state.reload_all()
    lv.selected_block_id = b1.id
    lv.duplicate_selected_block()
    assert len(state.blocks) >= 2
    assert len(lv._overlap_block_ids()) == 0

    pb.seek(3.0)
    lv.selected_block_id = b1.id
    lv.split_selected_or_at_playhead()
    assert len(state.blocks) >= 3

    lv.delete_selected_block()
    assert len(state.blocks) >= 2


def test_all_standard_modals_construct(tmp_path) -> None:
    _app()
    db = StudioDatabase(tmp_path / "p8m.db")
    ensure_seeded(db)
    state = StudioStateService(db=db, bus=StudioEventBus())

    stage_m = StageSizeModal(state)
    stage_m.width_spin.setValue(16.0)
    stage_m._on_apply()
    assert abs(state.scene.stage_width - 16.0) < 1e-4

    modals = [
        AddTrackDialog(state),
        InitPointModal(state),
        SwitchTaskModal(state),
        FragmentSaveDialog(state, 2.0),
        PreDanceCheckModal(state),
        DeviceOverviewModal(state),
        CoordTransformModal(state),
        CustomMapModal(state),
        TaskJsonViewerModal(state),
    ]
    for m in modals:
        assert m.windowTitle()


def test_choreography_page_in_main_window(tmp_path) -> None:
    _app()
    db = StudioDatabase(tmp_path / "p8c.db")
    ensure_seeded(db)
    state = StudioStateService(db=db, bus=StudioEventBus())
    pb = PlaybackCoordinator(state)
    page = ChoreographyPage(state, pb)
    page.batch_drawer._apply_batch()
    assert len(state.blocks) >= len(state.tracks)
