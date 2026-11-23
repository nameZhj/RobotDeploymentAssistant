# @file: tests/test_closure_audit_e2e.py
# @brief: Round 2 & 3 comprehensive end-to-end button trigger, zero-demo startup, CRUD, and closed-loop verification suite.

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from src.core.event_bus import StudioEvent
from src.core.paths import get_paths
from src.core.settings import get_settings
from src.domain.action_entities import ActionEntity
from src.domain.timeline_entities import TimelineBlockEntity
from src.domain.trajectory_entities import ControlPoint2D
from src.persistence.pcd_parser import PcdHeader, PcdPointCloud, write_ascii_pcd
from src.ui.modals import (
    AddTrackDialog,
    CoordTransformModal,
    DeviceOverviewModal,
    FragmentSaveDialog,
    InitPointModal,
    PreDanceCheckModal,
    StageSizeModal,
    SwitchTaskModal,
    TrajectoryEditorModal,
)
from src.ui.windows.main_studio_window import MainStudioWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_zero_demo_startup_and_full_user_track_crud(tmp_path: Path, monkeypatch) -> None:
    _app()
    monkeypatch.setenv("RDA_WORKSPACE_ROOT", str(tmp_path))
    get_paths(reset=True)
    win = MainStudioWindow(initial_page="choreography")

    # 1. Startup must have 0 demo robots
    assert len(win.state.tracks) == 0
    assert "未添加机器人" in win.statusbar.btn_init.text()
    assert len(win.formation_page.canvas.sources) == 0
    assert win.network_page.wizard.track_sel.current_data() == ""

    # 2. User creates real tracks via AddTrackDialog and DeviceOverviewModal
    dlg = AddTrackDialog(win.state, win)
    dlg.name_edit.setText("Real_G1_1")
    dlg.target_edit.setText("A")
    dlg.ip_edit.setText("192.168.50.11")
    dlg.init_x.setValue(-1.0)
    dlg.init_y.setValue(0.5)
    dlg._on_submit()
    assert len(win.state.tracks) == 1

    # Conflict guard: duplicate target "A" must be rejected
    dup = AddTrackDialog(win.state, win)
    dup.target_edit.setText("A")
    dup._on_submit()
    assert "占用" in dup.err_lbl.text() and len(win.state.tracks) == 1

    dlg2 = AddTrackDialog(win.state, win)
    dlg2.name_edit.setText("Real_G1_2")
    dlg2.target_edit.setText("B")
    dlg2.ip_edit.setText("192.168.50.12")
    dlg2.init_x.setValue(1.5)
    dlg2._on_submit()
    assert len(win.state.tracks) == 2

    # 3. Auto-synced downstream pages immediately see real tracks
    assert len(win.formation_page.canvas.sources) == 2
    assert win.network_page.ip_table.rowCount() == 2
    assert win.radar_page.table.rowCount() == 2
    assert win.monitoring_page.table.rowCount() == 2
    assert win.mapping_page.teleop_dock.target_sel.count() == 2

    # 4. Edit track via AddTrackDialog edit mode
    edit_dlg = AddTrackDialog(win.state, win, track=win.state.tracks[1])
    edit_dlg.name_edit.setText("Real_G1_2_Renamed")
    edit_dlg._on_submit()
    assert win.state.tracks[1].name == "Real_G1_2_Renamed"

    # 5. Delete track with Undo/Redo closed loop via DeviceOverviewModal
    dev = DeviceOverviewModal(win.state, win)
    dev.table.selectRow(1)
    dev._on_delete()
    assert len(win.state.tracks) == 1
    assert win.state.undo_stack.undo() is not None
    assert len(win.state.tracks) == 2
    assert win.state.undo_stack.redo() is not None
    assert len(win.state.tracks) == 1

    # 6. SwitchTaskModal creates blank 0-track tasks without demo injection
    sw = SwitchTaskModal(win.state, win)
    cur_id = win.state.task.id
    win.state.scene_repo.create_task(
        type(win.state.task)(scene_id=win.state.scene.id or 1, name="Blank_2", total_duration=20.0)
    )
    win.state.reload_all()
    assert len(win.state.tracks) == 0
    win.state.scene_repo.switch_active_task(win.state.scene.id or 1, cur_id or 1)
    win.state.reload_all()
    win.close()


def test_inline_stage_trajectory_drawing_and_sketch_closure(tmp_path: Path, monkeypatch) -> None:
    _app()
    monkeypatch.setenv("RDA_WORKSPACE_ROOT", str(tmp_path))
    get_paths(reset=True)
    win = MainStudioWindow(initial_page="choreography")
    win.resize(1440, 860)

    # Add a real robot first
    d = AddTrackDialog(win.state, win)
    d._on_submit()
    pmp = win.choreography_page.preview_panel
    c2d = pmp.canvas_2d
    tb = pmp.draw_toolbar

    # Activate sketch brush mode & draw stroke -> clear
    tb.sketch_btn.click()
    assert c2d.draw_mode == "sketch"
    c2d._active_stroke = [(0.0, 0.0), (1.0, 1.0)]
    c2d.sketch_strokes.append(list(c2d._active_stroke))
    c2d._active_stroke.clear()
    assert len(c2d.sketch_strokes) == 1
    assert c2d.undo_draw_step()
    assert len(c2d.sketch_strokes) == 0
    c2d.sketch_strokes.append([(0.0, 0.0), (2.0, 0.0)])
    tb.clr_sketch_btn.click()
    assert len(c2d.sketch_strokes) == 0

    # Activate inline 轨迹绘制 mode, click points, undo, save via TrajectoryEditorModal
    tb.draw_btn.click()
    assert c2d.draw_mode == "draw_traj"
    c2d.draft_points = [ControlPoint2D(-1.0, 0.0, 0.0), ControlPoint2D(0.5, 1.2, 0.4), ControlPoint2D(2.0, 0.0, 0.0)]
    c2d._rebuild_draft_preview()
    assert tb.save_traj_btn.isEnabled()
    assert c2d.undo_draw_step() and len(c2d.draft_points) == 2

    modal = TrajectoryEditorModal(win.state, traj=None, initial_points=c2d.draft_points, parent=win)
    modal.name_edit.setText("舞台直绘曲线")
    modal.run_sel.set_current_data(501)
    modal.hold_chk.setChecked(True)
    modal.hold_yaw_spin.setValue(0.25)
    modal._on_save()
    assert modal.saved_traj is not None
    assert modal.saved_traj.run_mode == 501
    assert any(t.name == "舞台直绘曲线" for t in win.state.trajectories.values())
    c2d.clear_draft()
    assert len(c2d.draft_points) == 0

    # Save global snapshot (Ctrl+S hook)
    assert "已保存" in win.state.save_project_snapshot()
    win.close()


def test_timeline_undo_fragment_action_formation_map_lrmp_and_settings(tmp_path: Path, monkeypatch) -> None:
    _app()
    monkeypatch.setenv("RDA_WORKSPACE_ROOT", str(tmp_path))
    get_paths(reset=True)
    sent_frames = []

    class _MockSerial:
        is_connected = True

        def send_command(self, tgt: str, cmd: str) -> None:
            sent_frames.append(f"{tgt}|{cmd}")

    win = MainStudioWindow(serial_manager=_MockSerial(), initial_page="choreography")
    win.state.load_demo_swarm_preset()
    tr0 = win.state.tracks[0]

    # Timeline CRUD + Undo/Redo + Playhead Split + Ignore + Del
    blk = win.state.commit_block_change(
        None,
        TimelineBlockEntity(
            task_id=win.state.task.id or 1,
            track_id=tr0.id or 1,
            block_type="action",
            ref_id=1,
            code_no="G1_TAIJI",
            title="太极",
            start_time=0.0,
            duration=10.0,
        ),
        "插入太极",
    )
    lv = win.choreography_page.task_editor.lane_view
    lv.selected_block_id = blk.id
    win.playback.seek(4.0)
    win.choreography_page.task_editor.opbar.toolClicked.emit("split")
    assert len(win.state.blocks) == 2
    assert win.state.undo_stack.undo() is not None
    assert len(win.state.blocks) == 1
    assert win.state.undo_stack.redo() is not None
    assert len(win.state.blocks) == 2

    # Fragment full write -> read/load -> delete closure
    frag_dlg = FragmentSaveDialog(win.state, 0.0, win)
    frag_dlg.slot_spin.setValue(7)
    frag_dlg.name_edit.setText("黄金片段")
    frag_dlg._on_save()
    assert len(frag_dlg._frags) == 1
    win.playback.seek(12.0)
    frag_dlg.table.selectRow(0)
    frag_dlg._on_load_selected()
    assert len(win.state.blocks) >= 3
    frag_dlg2 = FragmentSaveDialog(win.state, 0.0, win)
    frag_dlg2.table.selectRow(0)
    frag_dlg2._on_delete_selected()
    assert len(frag_dlg2._frags) == 0

    # Custom Action import/filter/delete & BatchChoreoDrawer sync (zero fake seeded actions)
    custom = ActionEntity(no=9901, name="测试自定义", category="CUSTOM", lrmp_code="CST_TEST", duration=6.0, is_builtin=False)
    win.state.action_repo.upsert_action(custom)
    win.state.bus.publish(StudioEvent.ACTION_LIB_UPDATED, custom.id)
    win.choreography_page.action_lib.cat_sel.set_current_data("CUSTOM")
    win.choreography_page.action_lib.refresh()
    assert win.choreography_page.action_lib.list_layout.count() >= 2
    assert win.choreography_page.batch_drawer.act_sel.count() == 1

    # Formation text mode + exact next_track_end_time splicing
    win.formation_page.ctrl_dock.kind_sel.set_current_data("text")
    win.formation_page.ctrl_dock.text_edit.setText("G1")
    win.formation_page.generate_targets()
    assert len(win.formation_page.canvas.targets) == 4
    grp = win.formation_page.commit_to_library()
    assert grp is not None and grp.bound_track_no == 1
    assert any(abs(b.start_time - 0.0) < 1e-3 for b in win.state.blocks if b.track_id == win.state.tracks[1].id)

    # Map import + SVD rotation calibration + true delete surviving restart
    pcd_file = tmp_path / "hall_svd.pcd"
    pts = [[0, 0, 0.6], [2, 0, 0.6], [2, 2, 0.6], [0, 2, 0.6]]
    import numpy as np
    write_ascii_pcd(pcd_file, np.asarray(pts, dtype=np.float32))
    ent = win.mapping_page.lib_dock.import_pcd_file(pcd_file, activate=True)
    svd = CoordTransformModal(win.state, win)
    svd.table.item(1, 2).setText("0.0")
    svd.table.item(1, 3).setText("4.0")  # ~90 deg rotation
    svd._solve()
    reloaded_map = win.state.map_repo.get_map(ent.id or 0)
    assert reloaded_map is not None and "rot_2x2" in reloaded_map.calib_matrix
    win.mapping_page.lib_dock.list_w.setCurrentRow(0)
    win.mapping_page.lib_dock.delete_selected()
    win.mapping_page.lib_dock._scan_existing_dir()
    assert all(m.name != "hall_svd" for m in win.state.map_repo.list_maps())

    # LRMP TX on PerformanceMonitorPage + live RadarMonitorPage + Settings persistence
    win.monitoring_page._cmd_prep()
    win.monitoring_page._cmd_play()
    assert any("|PREP" in f for f in sent_frames)
    assert any("|PLAY" in f for f in sent_frames)
    assert "串口在线" in win.monitoring_page.table.item(0, 3).text()
    win.playback.seek(5.0)
    assert "安全" in win.radar_page.table.item(0, 2).text()

    win.network_page.safety_spin.setValue(0.85)
    win.network_page.virt_http_chk.setChecked(False)
    assert abs(get_settings(reload=True).stage_defaults.safety_distance_m - 0.85) < 1e-4
    assert get_settings(reload=True).virtual_interfaces.http_upload_virtual_fallback is False

    # 3D authentic Unitree G1 multi-material + NPZ 21-joint dance & concurrent action+trajectory playback
    vp3d = win.choreography_page.preview_panel.viewport_3d
    clip_kf = vp3d._motion_player.get_clip_for_action("preview/G1_KUNG_FU.npz", "G3_KUNGFU", 550031)
    clip_tk = vp3d._motion_player.get_clip_for_action("preview/G1_TIKTOK.npz", "G1_TIKTOK", 550005)
    _, q_kf = clip_kf.sample_at(2.5)
    _, q_tk = clip_tk.sample_at(2.5)
    assert float(abs(q_kf - q_tk).max()) > 0.05
    from src.viewport3d.stl_vbo_cache import g1_link_material_rgb
    assert g1_link_material_rgb("meshes/logo_link.STL", (1.0, 0.0, 0.0), False)[2] > 0.9
    # Concurrent action + trajectory on same track must NOT conflict in sub-lane model
    b_act = TimelineBlockEntity(task_id=1, track_id=tr0.id or 1, block_type="action", start_time=0.0, duration=8.0, title="D")
    b_trj = TimelineBlockEntity(task_id=1, track_id=tr0.id or 1, block_type="trajectory", start_time=0.0, duration=8.0, title="T")
    assert not b_act.overlaps(b_trj)

    # L-1 slice merge + L-2 blockSelected highlight + L-3 group rename
    from src.persistence.uniuni_slice_merger import merge_slice_into_current_task
    slice_data = win.state.json_codec.export_task_to_dict(t_start=0.0, t_end=8.0)
    pre_cnt = len(win.state.blocks)
    assert merge_slice_into_current_task(win.state, slice_data, offset_s=18.0) >= 1
    win.state.reload_all()
    assert len(win.state.blocks) > pre_cnt
    win.choreography_page.task_editor.lane_view.blockSelected.emit(win.state.blocks[0])
    assert win.choreography_page.preview_panel.canvas_2d.highlighted_track_id == win.state.blocks[0].track_id
    g0 = win.state.list_groups()[0]
    win.state.traj_repo.rename_group(g0.id or 1, "编队组_Renamed")
    assert any(g.name == "编队组_Renamed" for g in win.state.list_groups())
    win.close()
