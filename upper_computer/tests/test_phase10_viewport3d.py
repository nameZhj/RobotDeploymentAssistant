# @file: tests/test_phase10_viewport3d.py
# @brief: Phase 10 verification for G1 URDF FK chain, STL loading, G1_dance.csv motion player, and StageViewport3D.
# @exports: test_g1_urdf_fk_and_stl_loading, test_dance_motion_player_samples_g1_csv, test_stage_viewport_3d_widget

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.event_bus import StudioEventBus
from src.core.paths import get_paths
from src.persistence import StudioDatabase
from src.persistence.seed_builtin_data import ensure_seeded
from src.services.studio_state_service import StudioStateService
from src.viewport3d import (
    DanceMotionPlayer,
    StageViewport3D,
    StlVboCache,
    get_g1_kinematics,
    procedural_gait_angles,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_g1_urdf_fk_and_stl_loading() -> None:
    chain = get_g1_kinematics()
    assert len(chain.revolute_joint_names) == 29
    z, joints = procedural_gait_angles(1.2, 0.8)
    parts = chain.solve_fk(1.5, -0.5, 0.4, z, joints)
    assert len(parts) >= 20
    cache = StlVboCache(get_paths().g1_urdf_dir)
    loaded = [cache.get_mesh(rel) for rel, _ in parts[:10]]
    assert all(m is not None and m.vertex_count > 0 for m in loaded)


def test_dance_motion_player_samples_g1_csv() -> None:
    player = DanceMotionPlayer()
    clip = player.get_clip("assets/motions/G1_dance.csv")
    assert clip.duration > 5.0
    z, q = clip.sample_at(2.5)
    assert 0.3 <= z <= 1.2
    assert q.shape == (29,)


def test_stage_viewport_3d_widget(tmp_path) -> None:
    _app()
    db = StudioDatabase(tmp_path / "vp3d.db")
    ensure_seeded(db)
    state = StudioStateService(db=db, bus=StudioEventBus())
    vp = StageViewport3D(state)
    vp.resize(640, 480)
    vp.reset_view("top")
    assert abs(vp.camera.pitch_deg - 88.0) < 1e-3
    vp.reset_view("iso")
    assert abs(vp.camera.yaw_deg - (-45.0)) < 1e-3
