# @file: tests/test_task_chain_and_ui.py
# @brief: Verifies pure-name Task Chain presentation, 70:30 viewport ratio, stop-to-origin, and LoRa Wi-Fi binding.
# @exports: test_task_chain_pure_name_format_and_70_30_viewport, test_stop_to_origin_resets_robots_and_lora_binding

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from backend.g1_wifi_service import G1WifiService
from src.core.paths import get_paths
from src.domain.timeline_entities import TimelineBlockEntity
from src.domain.trajectory_entities import ControlPoint2D, TrajectoryEntity
from src.persistence import get_database
from src.services.g1_wifi_provisioner import G1WifiProvisioner
from src.services.task_chain_normalizer import (
    active_chain_node_label,
    format_track_chain_summary,
    sequence_track_chain,
)
from src.ui.modals import AddTrackDialog
from src.ui.windows.main_studio_window import MainStudioWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_task_chain_pure_name_format_and_70_30_viewport(tmp_path: Path, monkeypatch) -> None:
    app = _app()
    monkeypatch.setenv("RDA_WORKSPACE_ROOT", str(tmp_path))
    get_paths(reset=True)
    get_database(reset=True)
    win = MainStudioWindow(initial_page="choreography")
    win.resize(1440, 900)
    win.show()
    app.processEvents()
    page = win.choreography_page

    # 1. Verify 70% : 30% viewport stretch & initial size proportion automatically on show
    sizes = page.left_split.sizes()
    assert sizes[0] > 0 and sizes[1] > 0
    ratio = sizes[0] / float(sizes[0] + sizes[1])
    assert abs(ratio - 0.70) < 0.03

    # 2. Verify pure-name Task Chain format: "导航到点1 - 太极 - 街舞 - 导航到点2" (no "步骤", no seconds)
    dlg = AddTrackDialog(win.state, win)
    dlg.target_edit.setText("A")
    dlg.init_x.setValue(-1.0)
    dlg.init_y.setValue(0.0)
    dlg._on_submit()
    tr = win.state.tracks[0]

    blocks = [
        TimelineBlockEntity(task_id=1, track_id=tr.id or 1, block_type="trajectory", title="导航到点1", start_time=0.0, duration=4.0),
        TimelineBlockEntity(task_id=1, track_id=tr.id or 1, block_type="action", title="太极", start_time=4.0, duration=5.0),
        TimelineBlockEntity(task_id=1, track_id=tr.id or 1, block_type="action", title="街舞", start_time=9.0, duration=5.0),
        TimelineBlockEntity(task_id=1, track_id=tr.id or 1, block_type="trajectory", title="导航到点2", start_time=14.0, duration=4.0),
    ]
    seq = sequence_track_chain(blocks, tr.id or 1)
    assert len(seq) == 4
    summary = format_track_chain_summary(seq, tr.id or 1)
    assert summary == "导航到点1 - 太极 - 街舞 - 导航到点2"
    assert "步骤" not in summary and "s" not in summary

    for b in seq:
        win.state.scene_repo.upsert_block(b)
    win.state.reload_all()

    # Check header & progress bar display pure chain names without seconds or step numbers
    page.task_editor.header.refresh()
    assert "任务链 4 项" in page.task_editor.header.dur_badge.text()
    win.playback.seek(0.0)
    assert page.preview_panel.progress_bar.time_lbl.text() == "原点待命"
    win.playback.seek(5.0)
    assert page.preview_panel.progress_bar.time_lbl.text() == "太极"
    assert active_chain_node_label(win.state.blocks, 10.0) == "街舞"
    win.close()


def test_stop_to_origin_resets_robots_and_lora_binding(tmp_path: Path, monkeypatch) -> None:
    _app()
    monkeypatch.setenv("RDA_WORKSPACE_ROOT", str(tmp_path))
    get_paths(reset=True)
    get_database(reset=True)
    win = MainStudioWindow(initial_page="choreography")
    dlg = AddTrackDialog(win.state, win)
    dlg.target_edit.setText("A")
    dlg.init_x.setValue(-2.0)
    dlg.init_y.setValue(1.0)
    dlg._on_submit()
    tr = win.state.tracks[0]

    grp = win.state.list_groups()[0]
    traj = win.state.traj_repo.upsert_trajectory(
        TrajectoryEntity(
            group_id=grp.id or 1, no=100001, name="导航到点1", duration=5.0,
            control_points=[ControlPoint2D(-2.0, 1.0), ControlPoint2D(3.0, 2.0)],
        )
    )
    win.state.scene_repo.upsert_block(
        TimelineBlockEntity(
            task_id=win.state.task.id or 1, track_id=tr.id or 1,
            block_type="trajectory", ref_id=traj.id or 0, title="导航到点1", start_time=0.0, duration=5.0,
        )
    )
    win.state.reload_all()

    # Move halfway along trajectory
    win.playback.seek(3.0)
    px, py, _ = win.state.evaluate_robot_pose(tr, win.state.playhead_s)
    assert px > -1.5

    # Click stop button -> returns immediately to origin (-2.0, 1.0)
    win.choreography_page.preview_panel.progress_bar.stop_btn.click()
    assert abs(win.state.playhead_s) < 1e-6
    ox, oy, _ = win.state.evaluate_robot_pose(tr, win.state.playhead_s)
    assert abs(ox - (-2.0)) < 1e-4 and abs(oy - 1.0) < 1e-4

    # Verify LoRa channel binding for Wi-Fi provisioning
    prov = G1WifiProvisioner(win.state, wifi_service=G1WifiService(lora_port="COM13"))
    bind_res = prov.bind_lora_port("COM13", 9600)
    assert bind_res["ok"] and bind_res["transport"] == "LoRa" and bind_res["lora_port"] == "COM13"
    win.close()
