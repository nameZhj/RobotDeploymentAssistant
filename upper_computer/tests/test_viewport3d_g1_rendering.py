# @file: tests/test_viewport3d_g1_rendering.py
# @brief: Verification tests for URDF/g1.py parsing, smooth STL normals, URDF+1A materials, gait/NPZ grounding, and StageViewport3D rendering.

from __future__ import annotations

import os
import time
import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from src.core.event_bus import StudioEventBus
from src.core.paths import get_paths
from src.domain.track_entities import TrackEntity
from src.persistence import StudioDatabase
from src.persistence.seed_builtin_data import ensure_seeded
from src.services.studio_state_service import StudioStateService
from src.ui.monitoring.performance_monitor_page import PerformanceMonitorPage
from src.services.playback_coordinator import PlaybackCoordinator
from src.viewport3d.dance_motion_player import DanceMotionPlayer, procedural_gait_angles
from src.viewport3d.g1_kinematics_chain import get_g1_kinematics
from src.viewport3d.robot_render_style import draw_robot_id_labels, robot_link_material, robot_link_style
from src.viewport3d.stage_viewport_3d import StageViewport3D
from src.viewport3d.stl_vbo_cache import StlVboCache


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_urdf_and_g1_py_init_state_grounding() -> None:
    kin = get_g1_kinematics()
    assert len(kin.revolute_joint_names) == 29
    assert kin.revolute_joint_names == kin.joint_sdk_names
    assert len(kin.visuals) == 35
    assert abs(kin.default_root_z - 0.76) < 1e-4

    # Natural standing pose from g1.py must land cleanly near z = 0 without sinking or floating
    foot_min_z = kin.compute_foot_min_z(kin.default_root_z, kin.default_joint_angles)
    assert -0.015 <= foot_min_z <= 0.025

    grounded_z = kin.ground_root_z(kin.default_root_z, kin.default_joint_angles)
    assert abs(kin.compute_foot_min_z(grounded_z, kin.default_joint_angles) - 0.002) < 1e-4


def test_stl_smooth_normals_and_official_materials_1a() -> None:
    kin = get_g1_kinematics()
    cache = StlVboCache(get_paths().g1_urdf_dir)
    for rel in ("meshes/pelvis.STL", "meshes/torso_link.STL", "meshes/left_rubber_hand.STL"):
        mesh = cache.get_mesh(rel)
        assert mesh is not None and mesh.vertex_count > 100
        assert mesh.vertices.shape == (mesh.vertex_count, 3)
        assert mesh.normals.shape == (mesh.vertex_count, 3)
        assert np.all(np.isfinite(mesh.normals))
        lens = np.linalg.norm(mesh.normals, axis=1)
        assert np.all(np.abs(lens - 1.0) < 1e-3)

    # 1A rule: torso white aluminum, pelvis dark charcoal, rubber_hand dark matte rubber, collision red
    torso_mat = robot_link_material(kin, "meshes/torso_link.STL", colliding=False)
    pelvis_mat = robot_link_material(kin, "meshes/pelvis.STL", colliding=False)
    hand_mat = robot_link_material(kin, "meshes/left_rubber_hand.STL", colliding=False)
    coll_mat = robot_link_material(kin, "meshes/torso_link.STL", colliding=True)

    assert torso_mat[0][0] > 0.70 and torso_mat[1] > 0.45  # satin silver-grey aluminum
    assert pelvis_mat[0][0] < 0.25                         # dark charcoal inner link
    assert hand_mat[0][0] < 0.22 and hand_mat[2] > 0.75    # matte dark rubber hand
    assert coll_mat[0][0] > 0.85 and coll_mat[0][1] < 0.35 # collision red alert

    # Track colors must NEVER taint robot chassis diffuse material in fixed-function fallback either
    r_a, _, _ = robot_link_style(kin, "meshes/torso_link.STL", (1.0, 0.0, 0.0), False)
    r_b, _, _ = robot_link_style(kin, "meshes/torso_link.STL", (0.0, 1.0, 0.0), False)
    assert r_a == r_b


def test_procedural_gait_and_npz_csv_compatibility(tmp_path) -> None:
    kin = get_g1_kinematics()
    for speed in (0.0, 0.35, 1.0):
        for t in (0.0, 0.25, 0.65):
            rz, q = procedural_gait_angles(t, speed)
            assert q.shape == (29,) and np.all(np.isfinite(q))
            assert np.all(q >= kin.joint_limits[:, 0] - 1e-4)
            assert np.all(q <= kin.joint_limits[:, 1] + 1e-4)
            fmin = kin.compute_foot_min_z(rz, q)
            assert abs(fmin - 0.002) < 1e-3

    player = DanceMotionPlayer()
    # 21-joint preview NPZ dance
    clip_tiktok = player.get_clip(player.resolve_dance_file("TIKTOK"))
    rz, q, rq = clip_tiktok.sample_pose_at(1.2)
    assert q.shape == (29,) and 0.45 <= rz <= 1.25 and rq is None
    assert abs(kin.compute_foot_min_z(rz, q)) < 0.08

    # 36-col G1_dance.csv mocap
    clip_csv = player.get_clip(str(get_paths().g1_dance_csv))
    rz_c, q_c, rq_c = clip_csv.sample_pose_at(0.5)
    assert q_c.shape == (29,) and rq_c is not None and rq_c.shape == (4,)

    # 29-DOF joint_pos NPZ with reversed joint_names order
    custom_npz = tmp_path / "custom_29dof.npz"
    rev_names = np.array(list(reversed(kin.revolute_joint_names)))
    jp = np.zeros((10, 29), dtype=np.float32)
    jp[:, 0] = 0.42  # corresponds to last joint in revolute_joint_names (right_wrist_yaw_joint, idx=28)
    np.savez(custom_npz, fps=np.float64(50.0), joint_pos=jp, joint_names=rev_names)
    clip_29 = player.get_clip(str(custom_npz))
    _, q_29, _ = clip_29.sample_pose_at(0.05)
    assert abs(float(q_29[28]) - 0.42) < 1e-4 and abs(float(q_29[0])) < 1e-4


def test_stage_viewport_live_states_and_single_qpainter_labels(tmp_path) -> None:
    _app()
    db = StudioDatabase(tmp_path / "vp3d.db")
    ensure_seeded(db)
    state = StudioStateService(db=db, bus=StudioEventBus())
    state.upsert_track_validated(TrackEntity(task_id=state.task.id or 1, track_no=1, name="G1-A", target_id="A", init_x=0.0, init_y=0.0, color_hex="#38BDF8"))
    state.upsert_track_validated(TrackEntity(task_id=state.task.id or 1, track_no=2, name="G1-B", target_id="B", init_x=1.2, init_y=0.0, color_hex="#F59E0B"))

    # Verify all 35 URDF visual STL meshes preload smoothly with finite normals
    cache = StlVboCache(get_paths().g1_urdf_dir)
    loaded = cache.preload_all([v.mesh_rel_path for v in get_g1_kinematics().visuals])
    assert loaded == 35

    vp = StageViewport3D(state)
    vp.resize(640, 480)
    vp.set_live_robot_states({
        "A": {"pose": (0.0, 0.0, 0.0), "motion_state": "STAND", "active_dance": "", "dance_start_s": 0.0, "fault": False},
        "B": {"pose": (1.2, 0.3, 0.5), "motion_state": "GAIT", "active_dance": "TIKTOK", "dance_start_s": time.monotonic(), "fault": False},
    })
    assert vp._live_anim_timer.isActive()
    vp._live_anim_timer.stop()

    rz_a, q_a, _, tag_a = vp._resolve_live_robot_motion("A", vp._live_robot_states["A"], time.monotonic())
    rz_b, q_b, _, tag_b = vp._resolve_live_robot_motion("B", vp._live_robot_states["B"], time.monotonic() + 0.4)
    assert tag_a == "" and tag_b == "DANCE"
    assert q_a.shape == (29,) and q_b.shape == (29,)

    # Verify PerformanceMonitorPage syncs live dance callbacks into StageViewport3D
    pb = PlaybackCoordinator(state)
    perf = PerformanceMonitorPage(state, pb)
    state.callback_listener._handle_event({
        "event": "DANCE_STARTED", "target_id": "A", "alias": "TIKTOK",
        "pose": {"x": 0.2, "y": 0.1, "yaw": 0.2},
        "robot_state": {"motion_state": "DANCE", "active_dance": "TIKTOK"},
    })
    perf._on_http_callback({"target_id": "A", "payload": {"event": "DANCE_STARTED", "alias": "TIKTOK"}})
    assert perf.viewport._live_robot_states["A"]["active_dance"] == "TIKTOK"
    perf.viewport._live_anim_timer.stop()

    state.callback_listener._handle_event({
        "event": "DANCE_COMPLETED", "target_id": "A", "alias": "TIKTOK",
        "pose": {"x": 0.2, "y": 0.1, "yaw": 0.2},
        "robot_state": {"motion_state": "STAND", "active_dance": ""},
    })
    perf._on_http_callback({"target_id": "A", "payload": {"event": "DANCE_COMPLETED", "alias": "TIKTOK"}})
    assert perf.viewport._live_robot_states["A"]["active_dance"] == ""

    # Single-QPainter badge drawing must succeed cleanly on a QImage without Qt double-painter conflicts
    img = QImage(320, 240, QImage.Format.Format_ARGB32)
    img.fill(QColor(15, 20, 30))
    painter = QPainter(img)
    try:
        draw_robot_id_labels(painter, [("A", 100.0, 120.0, (0.22, 0.74, 0.97), "", False), ("B", 220.0, 140.0, (0.96, 0.62, 0.04), "DANCE", True)])
    finally:
        painter.end()
    # At least one pixel near the pill center should reflect the dark pill fill rather than raw clear
    assert img.pixelColor(100, 120) != QColor(15, 20, 30)
