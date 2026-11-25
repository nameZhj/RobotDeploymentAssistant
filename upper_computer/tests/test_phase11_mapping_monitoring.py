# @file: tests/test_phase11_mapping_monitoring.py
# @brief: Verification tests for Page 3 PCD upload/push/teleop SLAM and Page 4 unified live show monitor.
# @exports: test_navigation_map_page_upload_teleop_and_delete, test_performance_monitor_live_pose_and_controls

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time
import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.event_bus import StudioEventBus
from src.core.settings import get_settings, save_settings
from src.domain.track_entities import TrackEntity
from src.persistence import StudioDatabase
from src.persistence.pcd_parser import write_ascii_pcd
from src.persistence.seed_builtin_data import ensure_seeded
from src.services.playback_coordinator import PlaybackCoordinator
from src.services.studio_state_service import StudioStateService
from src.ui.common.async_task import wait_for_all_tasks
from src.ui.mapping import NavigationMapPage
from src.ui.monitoring import PerformanceMonitorPage


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_navigation_map_page_upload_teleop_and_delete(tmp_path, monkeypatch) -> None:
    _app()
    monkeypatch.setenv("RDA_WORKSPACE_ROOT", str(tmp_path / "ws"))
    from src.core.paths import get_paths
    get_paths(reset=True)

    # Start real LowerComputerHttpServer to verify real nav, SSE stream, cloud pull & local PCD upload
    lower_root = pathlib.Path(__file__).resolve().parents[2] / "lower_computer"
    orig_path = list(sys.path)
    saved_src = {k: v for k, v in sys.modules.items() if k == "src" or k.startswith("src.")}
    for k in list(saved_src):
        del sys.modules[k]
    sys.path.insert(0, str(lower_root))
    from src.api.http_server import LowerComputerHttpServer
    from src.api.routes import LowerComputerContext
    from src.config.ros_env_config import RosEnvConfig
    from src.ros_bridge.navctl_runner import NavctlRunner
    from src.ros_bridge.ros_topic_service_bridge import RosTopicServiceBridge
    for k in list(sys.modules):
        if k == "src" or k.startswith("src."):
            del sys.modules[k]
    sys.modules.update(saved_src)
    sys.path[:] = orig_path

    rmaps = tmp_path / "rmaps"
    rmaps.mkdir(parents=True, exist_ok=True)
    write_ascii_pcd(rmaps / "robot_real.pcd", np.array([[0, 0, 0.5], [1.5, 0.5, 0.8]], dtype=np.float32))
    l_cfg = RosEnvConfig(maps_dir=rmaps, cache_dir=tmp_path / "lcache")
    l_nav = NavctlRunner(cmd_runner=lambda a, _t: subprocess.CompletedProcess(a, 0, "ok", ""), exists_checker=lambda _p: True)
    l_ros = RosTopicServiceBridge(cfg=l_cfg, master_checker=lambda: True, shell_runner=lambda _c, _t: (0, "ok", ""))
    l_ctx = LowerComputerContext(cfg=l_cfg, navctl=l_nav, ros_bridge=l_ros)
    l_ctx.slam_tap.push_points_list([(0.0, 0.0, 0.5), (1.0, 1.0, 0.8)])
    l_ctx.slam_tap.push_external_frame(pose={"x": 0.4, "y": -0.2, "yaw": 0.1}, nav_status="MOVING", global_path=[[0.4, -0.2], [2.0, 1.0]])
    l_srv = LowerComputerHttpServer(l_ctx, host="127.0.0.1", port=0)
    l_port = l_srv.start()

    cfg_u = get_settings(reload=True)
    cfg_u.virtual_interfaces.http_default_port = l_port
    save_settings(cfg_u)

    db = StudioDatabase(tmp_path / "p11.db")
    ensure_seeded(db)
    state = StudioStateService(db=db, bus=StudioEventBus())
    state.upsert_track_validated(TrackEntity(task_id=state.task.id or 1, track_no=1, name="G1-A", target_id="A", robot_ip="127.0.0.1"))
    page = NavigationMapPage(state)
    try:
        # 1. Local user PCD upload must remain fully functional
        pcd = write_ascii_pcd(tmp_path / "stage_test.pcd", np.array([[0, 0, 0.5], [1, 1, 0.8]], dtype=np.float32))
        saved = page.lib_dock.import_pcd_file(pcd, activate=True)
        assert state.scene.active_map_id == saved.id

        # 2. Interactive navigation buttons run on background threads and return TaskHandles
        h = page._run_discovery()
        assert h is not None and h.wait(10.0) and h.result is not None and h.result.ok
        h = page._send_initialpose(0.1, 0.2, 0.0)
        assert h is not None and h.wait(10.0) and h.result.ok
        h = page._send_nav_goal(2.0, 1.0, 0.0)
        assert h is not None and h.wait(10.0) and h.result.ok
        h = page._cancel_nav()
        assert h is not None and h.wait(10.0) and h.result.ok
        # Remote PCD pull chains listing -> download -> import across two background tasks
        h = page.lib_dock.sync_remote_pcd_dialog()
        assert h is not None
        wait_for_all_tasks(timeout_s=20.0)
        for idx in range(page.lib_dock.list_w.count()):
            if "stage_test" in page.lib_dock.list_w.item(idx).text():
                page.lib_dock.list_w.setCurrentRow(idx)
                break
        h = page.lib_dock.push_selected_to_robot(restart_localization=False)
        assert h is not None and h.wait(20.0) and h.result.ok
        assert (rmaps / "stage_test.pcd").exists()

        h = page.teleop_dock._on_start()
        assert h is not None and h.wait(10.0)
        assert h.result[0] is True
        h = page.teleop_dock._step_move(1.0, 0.0, 0.0)
        if h is not None:
            assert h.wait(10.0)
        h = page.teleop_dock.save_and_register_map()
        assert h is not None and h.wait(20.0)
        slam_ent = h.result
        assert slam_ent is not None and slam_ent.id is not None
        h = page.teleop_dock._on_stop()
        assert h is not None and h.wait(10.0)
        t0 = time.monotonic()
        page.sync_active_robot_stream()
        time.sleep(0.25)
        _app().processEvents()
        page.live_worker.stop_stream()
        assert (time.monotonic() - t0) < 1.0
    finally:
        l_ros.stop_cmd_vel()
        l_srv.stop()
        get_paths(reset=True)


def test_performance_monitor_live_pose_and_controls(tmp_path) -> None:
    _app()
    db = StudioDatabase(tmp_path / "p10m.db")
    ensure_seeded(db)
    state = StudioStateService(db=db, bus=StudioEventBus())
    state.load_demo_swarm_preset()
    pb = PlaybackCoordinator(state)
    perf = PerformanceMonitorPage(state, pb)
    perf._cmd_prep()
    wait_for_all_tasks(timeout_s=30.0)
    assert "CHOREO" in perf.phase_badge.text()
    perf._cmd_play()
    wait_for_all_tasks(timeout_s=30.0)
    assert "PLAY" in perf.phase_badge.text()
    # Real callback path: lower computer webhook -> listener._handle_event merge -> 3D viewport & clearance table
    state.callback_listener._handle_event({
        "event": "STEP_PROGRESS", "target_id": "A", "title": "导航到点1",
        "pose": {"x": 1.25, "y": -0.4, "yaw": 0.3},
        "remaining_distance_m": 0.42, "localization_confidence": 0.96,
        "localization_delay_ms": 12.0, "local_nav_status": "SUCCEEDED",
        "state": {"status": "RUNNING", "target_id": "A", "current_node_title": "导航到点1"},
    })
    perf._on_http_callback({"target_id": "A", "payload": {"event": "STEP_PROGRESS", "title": "导航到点1", "remaining_distance_m": 0.42}})
    assert "A" in perf.viewport._live_robot_poses
    assert abs(perf.viewport._live_robot_poses["A"][0] - 1.25) < 1e-4
    assert "[实机]" in perf.table.item(0, 1).text()
    assert "安全" in perf.table.item(0, 2).text()
    perf._cmd_emergency()
    assert "EMERGENCY" in perf.phase_badge.text()
    assert perf.table.rowCount() == len(state.tracks)
    state.arbiter.apply_command("A", "PREP")
    state.callback_listener._handle_event({"event": "CHAIN_ABORTED", "target_id": "A", "reason": "STOP"})
    perf._on_http_callback({"target_id": "A", "payload": {"event": "CHAIN_ABORTED", "reason": "STOP"}})
    assert state.arbiter.get_state("A").value == "FREE" and "中止" in perf.phase_badge.text()
    wait_for_all_tasks(timeout_s=30.0)
