"""
@file: tests/unit/test_task04b_trajectory_edit_and_save.py
@brief: 任务 04B 轨迹编辑、持久化重载、引用保护、右键/工具栏事件与往返精度测试
@exports: test_01 到 test_12 完整功能与异常测试用例
"""
import copy
import math
import sys
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from src.infrastructure.storage.choreo_sqlite_store import ChoreoSqliteStore
from src.ui.choreo_page.choreo_toolbar import ChoreoToolbar
from src.ui.choreo_page.stage_canvas_2d import StageCanvas2D


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def temp_store(tmp_path):
    db_file = tmp_path / "test_studio_data_04b.db"
    return ChoreoSqliteStore(db_path=str(db_file))


@pytest.fixture
def canvas(qapp, temp_store):
    widget = StageCanvas2D(store=temp_store)
    widget.resize(800, 600)
    return widget


def _make_mouse_event(event_type, point: QPointF, button=Qt.LeftButton, modifiers=Qt.NoModifier):
    return QMouseEvent(
        event_type, point, point, point, button, button if event_type == QEvent.MouseButtonPress else Qt.NoButton,
        modifiers
    )


def test_01_robot_id_persisted_in_store_and_restored_on_reopening(canvas, temp_store):
    """1. 明确 robot_id 持久化位置：存储至 trajectories.robot_group，画布重启重载不丢失绑定"""
    canvas.select_robot("B")  # 选中 B 机器人 (pos: 2.0, 0.0)
    canvas.set_draw_mode("DRAW_TRAJECTORY")
    canvas._active_waypoints = [(2.0, 0.0), (3.0, 1.0), (4.0, 0.0)]
    assert canvas.finish_trajectory() is True

    # 保存至 SQLite
    traj_id = canvas._completed_trajectories[0]["id"]
    saved_ok = canvas.save_current_trajectory(traj_id)
    assert saved_ok is True

    # 直接核实 SQLite 物理表中 robot_group 字段存储为 "B"
    with temp_store.get_connection() as conn:
        row = conn.execute("SELECT robot_group, asset_json FROM trajectories WHERE traj_id = ?", (traj_id,)).fetchone()
        assert row is not None
        assert row["robot_group"] == "B"

    # 模拟画布关闭并创建新画布实例加载数据库
    new_canvas = StageCanvas2D(store=temp_store)
    new_canvas.resize(800, 600)
    count = new_canvas.load_trajectories_from_store()

    assert count == 1
    loaded_item = new_canvas._completed_trajectories[0]
    assert loaded_item["id"] == traj_id
    assert loaded_item["robot_id"] == "B"
    assert loaded_item["waypoints"] == [(2.0, 0.0), (3.0, 1.0), (4.0, 0.0)]


def test_02_yaw_angle_is_non_monotonic_and_normalized(canvas):
    """2. 核实偏航角测试：偏航角反映切线朝向而非单调量，必须非单调波动并规范化在 [-180, 180)"""
    canvas.select_robot("A")
    # S 型转弯折线：左转后又右转
    canvas._active_waypoints = [(-2.0, 0.0), (-1.0, 2.0), (0.0, -1.0), (1.0, 2.0)]
    assert canvas.finish_trajectory() is True

    asset = canvas._completed_trajectories[0]["asset"]
    yaws = [p.yaw_deg for p in asset.sampled_points]

    # 验证偏航角全量处于规范化区间 [-180.0, 180.0)
    for y in yaws:
        assert math.isfinite(y)
        assert -180.0 <= y < 180.0

    # 验证偏航角随路径转弯呈现非单调波动（存在增大和减小的拐点）
    diffs = [yaws[i] - yaws[i - 1] for i in range(1, len(yaws))]
    has_increasing = any(d > 0.5 for d in diffs)
    has_decreasing = any(d < -0.5 for d in diffs)
    assert has_increasing and has_decreasing, "偏航角必须随 S 型弯道呈现非单调波动"

    # 作为对比：只有空间累计弧长 s_m 严格保持单调递增
    s_vals = [p.s_m for p in asset.sampled_points]
    assert s_vals[0] == 0.0
    for i in range(1, len(s_vals)):
        assert s_vals[i] >= s_vals[i - 1]


def test_03_right_click_finishes_active_trajectory(canvas):
    """3.1 右键完成交互测试：绘制中右键点击直接结束绘制并生成样条"""
    canvas.select_robot("A")
    canvas.set_draw_mode("DRAW_TRAJECTORY")
    canvas._active_waypoints = [(-2.0, 0.0), (-1.0, 1.0)]

    right_click = _make_mouse_event(QEvent.MouseButtonPress, QPointF(350.0, 250.0), Qt.RightButton)
    canvas.mousePressEvent(right_click)

    assert len(canvas._active_waypoints) == 0
    assert len(canvas._completed_trajectories) == 1
    assert canvas._completed_trajectories[0]["robot_id"] == "A"


def test_04_toolbar_finish_signal_completes_trajectory(canvas):
    """3.2 工具栏完成事件测试：点击工具栏完成按钮触发画布轨迹结算"""
    toolbar = ChoreoToolbar()
    toolbar.finishRequested.connect(canvas.finish_trajectory)

    canvas.select_robot("A")
    canvas.set_draw_mode("DRAW_TRAJECTORY")
    canvas._active_waypoints = [(-2.0, 0.0), (0.0, 1.0)]

    toolbar.btn_finish.click()

    assert len(canvas._active_waypoints) == 0
    assert len(canvas._completed_trajectories) == 1


def test_05_toolbar_clear_signal_cancels_draft_without_saving(canvas):
    """3.3 工具栏清空事件测试：点击工具栏清空按钮触发取消并丢弃草稿"""
    toolbar = ChoreoToolbar()
    toolbar.clearRequested.connect(canvas.clear_active_trajectory)

    canvas.select_robot("A")
    canvas.set_draw_mode("DRAW_TRAJECTORY")
    canvas._active_waypoints = [(-2.0, 0.0), (0.0, 1.0)]

    toolbar.btn_clear.click()

    assert len(canvas._active_waypoints) == 0
    assert len(canvas._completed_trajectories) == 0


def test_06_trajectory_save_and_reload_fidelity(canvas, temp_store):
    """4. 轨迹保存后重新加载一致性验证：控制点、样条点、长度、时长完全无损还原"""
    canvas.select_robot("A")
    orig_wps = [(-2.0, 0.0), (-1.0, 1.5), (0.0, 0.0)]
    canvas._active_waypoints = list(orig_wps)
    assert canvas.finish_trajectory() is True

    orig_traj = canvas._completed_trajectories[0]
    canvas.save_current_trajectory(orig_traj["id"])

    # 清空画布后从数据库重新读取
    canvas.clear_all()
    assert len(canvas._completed_trajectories) == 0

    reloaded_count = canvas.load_trajectories_from_store()
    assert reloaded_count == 1
    reloaded_traj = canvas._completed_trajectories[0]

    assert reloaded_traj["id"] == orig_traj["id"]
    assert reloaded_traj["name"] == orig_traj["name"]
    assert reloaded_traj["waypoints"] == orig_wps
    assert len(reloaded_traj["spline_points"]) == len(orig_traj["spline_points"])
    assert reloaded_traj["length"] == pytest.approx(orig_traj["length"], abs=1e-3)
    assert reloaded_traj["duration"] == pytest.approx(orig_traj["duration"], abs=1e-2)


def test_07_coordinate_transformation_precision_under_zoom_and_pan(canvas):
    """5. 缩放与平移变换下的坐标往返精度测试：往返误差必须低于 1e-3 米与 0.05 像素"""
    test_scales = [5.0, 15.0, 20.0, 50.0, 100.0, 120.0]
    test_offsets = [(-300.0, -150.0), (0.0, 0.0), (250.0, 400.0)]
    test_screen_points = [QPointF(50.0, 50.0), QPointF(400.0, 300.0), QPointF(780.0, 550.0)]

    for scale in test_scales:
        for ox, oy in test_offsets:
            canvas._scale = scale
            canvas._offset_x = ox
            canvas._offset_y = oy

            # 屏幕点 -> 舞台点 -> 屏幕点
            for pt in test_screen_points:
                wx, wy = canvas.screen_to_stage(pt)
                scr = canvas.stage_to_screen(wx, wy)
                assert scr.x() == pytest.approx(pt.x(), abs=0.05)
                assert scr.y() == pytest.approx(pt.y(), abs=0.05)

            # 舞台坐标 -> 屏幕点 -> 舞台坐标
            for x_m, y_m in [(-12.345, 6.789), (0.0, 0.0), (18.5, -9.2)]:
                scr_pt = canvas.stage_to_screen(x_m, y_m)
                rx, ry = canvas.screen_to_stage(scr_pt)
                assert rx == pytest.approx(x_m, abs=1e-3)
                assert ry == pytest.approx(y_m, abs=1e-3)


def test_08_edit_mode_selection_and_control_point_dragging(canvas):
    """6. 任务 04B 轨迹选择与控制点拖拽：实时重算样条与全长"""
    canvas.select_robot("A")
    canvas._active_waypoints = [(-2.0, 0.0), (-1.0, 1.0), (0.0, 0.0)]
    assert canvas.finish_trajectory() is True
    traj_id = canvas._completed_trajectories[0]["id"]
    old_len = canvas._completed_trajectories[0]["length"]

    # 选中轨迹进入编辑模式
    assert canvas.select_trajectory(traj_id) is True
    assert canvas._selected_trajectory_id == traj_id

    # 模拟按下控制点 P2 (-1.0, 1.0)
    p2_screen = canvas.stage_to_screen(-1.0, 1.0)
    canvas.mousePressEvent(_make_mouse_event(QEvent.MouseButtonPress, p2_screen, Qt.LeftButton))
    assert canvas._dragging_point_idx == 1

    # 拖拽移动到 (-1.0, 3.0) 对应的屏幕位置
    new_screen = canvas.stage_to_screen(-1.0, 3.0)
    canvas.mouseMoveEvent(_make_mouse_event(QEvent.MouseMove, new_screen, Qt.NoButton))
    canvas.mouseReleaseEvent(_make_mouse_event(QEvent.MouseButtonRelease, new_screen, Qt.LeftButton))

    # 验证控制点已更新且样条重新计算
    updated_item = canvas._completed_trajectories[0]
    assert updated_item["waypoints"][1] == (-1.0, 3.0)
    assert updated_item["length"] > old_len


def test_09_cancel_edit_restores_unmodified_state(canvas):
    """7. 任务 04B 取消编辑：丢弃拖拽修改，完整还原未保存前的原始状态"""
    canvas.select_robot("A")
    canvas._active_waypoints = [(-2.0, 0.0), (-1.0, 1.0), (0.0, 0.0)]
    assert canvas.finish_trajectory() is True
    traj_id = canvas._completed_trajectories[0]["id"]

    canvas.select_trajectory(traj_id)
    # 修改控制点
    canvas.insert_waypoint_to_trajectory(traj_id, 1, (-1.5, 2.0))
    assert len(canvas._completed_trajectories[0]["waypoints"]) == 4

    # 按 Esc 取消编辑
    canvas.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))

    # 验证还原为 3 个原始控制点
    restored = canvas._completed_trajectories[0]
    assert len(restored["waypoints"]) == 3
    assert restored["waypoints"] == [(-2.0, 0.0), (-1.0, 1.0), (0.0, 0.0)]
    assert canvas._selected_trajectory_id is None


def test_10_insert_and_delete_waypoint_with_boundary_checks(canvas):
    """8. 任务 04B 插入与删除控制点：严格拦截少于 2 点的非法删除"""
    canvas.select_robot("A")
    canvas._active_waypoints = [(-2.0, 0.0), (-1.0, 1.0), (0.0, 0.0)]
    assert canvas.finish_trajectory() is True
    traj_id = canvas._completed_trajectories[0]["id"]

    # 插入点
    assert canvas.insert_waypoint_to_trajectory(traj_id, 2, (-0.5, 0.5)) is True
    assert len(canvas._completed_trajectories[0]["waypoints"]) == 4

    # 删除点（合法）
    assert canvas.delete_waypoint_from_trajectory(traj_id, 2) is True
    assert len(canvas._completed_trajectories[0]["waypoints"]) == 3

    assert canvas.delete_waypoint_from_trajectory(traj_id, 1) is True
    assert len(canvas._completed_trajectories[0]["waypoints"]) == 2

    # 尝试删除使点数少于 2 点 -> 必须被拦截阻止
    errors = []
    canvas.validationFailed.connect(lambda err: errors.append(err))
    assert canvas.delete_waypoint_from_trajectory(traj_id, 0) is False
    assert len(canvas._completed_trajectories[0]["waypoints"]) == 2
    assert len(errors) == 1
    assert "至少需要保留 2 个控制点" in errors[0]


def test_11_save_storage_failure_does_not_show_success(canvas, monkeypatch):
    """9. 任务 04B 存储失败处理：底层持久化异常时严禁提示保存成功"""
    canvas.select_robot("A")
    canvas._active_waypoints = [(-2.0, 0.0), (-1.0, 1.0)]
    assert canvas.finish_trajectory() is True
    traj_id = canvas._completed_trajectories[0]["id"]

    # 模拟持久化写库抛出异常
    def mock_save_fail(*args, **kwargs):
        raise RuntimeError("模拟底层数据库 I/O 写入失败")

    monkeypatch.setattr(canvas.store, "save_trajectory_asset", mock_save_fail)

    success = canvas.save_current_trajectory(traj_id)
    assert success is False
    assert canvas._status_message is not None
    assert canvas._status_message[1] == "error"
    assert "保存失败" in canvas._status_message[0]
    assert "成功" not in canvas._status_message[0]


def test_12_delete_trajectory_protected_when_referenced_in_timeline(canvas, temp_store):
    """10. 任务 04B 引用保护：时间轴引用的轨迹禁止误删，无引用时方可物理删除"""
    canvas.select_robot("A")
    canvas._active_waypoints = [(-2.0, 0.0), (-1.0, 1.0)]
    assert canvas.finish_trajectory() is True
    traj_id = canvas._completed_trajectories[0]["id"]
    canvas.save_current_trajectory(traj_id)

    # 在 timeline_clips 中建立引用
    temp_store.save_clip("clip_test_04b", "1", "TRAJ", traj_id, 0, 2000)

    # 尝试删除被引用的轨迹，必须被拒绝拦截
    del_ok = canvas.delete_trajectory(traj_id)
    assert del_ok is False
    assert "禁止直接删除" in canvas._status_message[0]
    assert any(t["id"] == traj_id for t in canvas._completed_trajectories)

    # 解除时间轴引用后，成功删除
    temp_store.delete_clip("clip_test_04b")
    del_ok_2 = canvas.delete_trajectory(traj_id)
    assert del_ok_2 is True
    assert not any(t["id"] == traj_id for t in canvas._completed_trajectories)


def test_13_edit_referenced_trajectory_save_rejected(canvas, temp_store):
    """11. 任务 04B-R 已引用素材编辑保护：已被时间轴引用的素材默认禁止原地覆写"""
    canvas.select_robot("A")
    canvas._active_waypoints = [(-2.0, 0.0), (-1.0, 1.0)]
    assert canvas.finish_trajectory() is True
    traj_id = canvas._completed_trajectories[0]["id"]
    assert canvas.save_current_trajectory(traj_id) is True

    # 在 timeline_clips 中建立引用
    temp_store.save_clip("clip_ref_13", "1", "TRAJ", traj_id, 0, 1500)

    # 选中轨迹进行编辑修改（修改 P2 点坐标）
    assert canvas.select_trajectory(traj_id) is True
    canvas.insert_waypoint_to_trajectory(traj_id, 2, (0.0, 2.0))
    assert len(canvas._completed_trajectories[0]["waypoints"]) == 3

    # 执行保存（默认 allow_overwrite_referenced=False）必须被拒绝
    saved_ok = canvas.save_current_trajectory(traj_id)
    assert saved_ok is False
    assert "默认禁止覆盖更新" in canvas._status_message[0]
    assert "正被 1 处时间轴片段引用" in canvas._status_message[0]


def test_14_rejected_save_keeps_original_database_asset(canvas, temp_store):
    """12. 任务 04B-R 数据库数据不变性：覆写被拒绝时，SQLite 数据库中原始素材保持不变"""
    canvas.select_robot("A")
    canvas._active_waypoints = [(-2.0, 0.0), (-1.0, 1.0)]
    assert canvas.finish_trajectory() is True
    traj_id = canvas._completed_trajectories[0]["id"]
    canvas.save_current_trajectory(traj_id)

    # 获取数据库中原始 asset
    orig_asset = temp_store.load_trajectory_asset(traj_id)
    assert orig_asset.control_points == [(-2.0, 0.0), (-1.0, 1.0)]

    # 建立引用并尝试覆写
    temp_store.save_clip("clip_ref_14", "1", "TRAJ", traj_id, 0, 1500)
    canvas.select_trajectory(traj_id)
    canvas.insert_waypoint_to_trajectory(traj_id, 2, (5.0, 5.0))
    canvas.save_current_trajectory(traj_id)

    # 验证数据库中持久化资产未被篡改
    db_asset_after = temp_store.load_trajectory_asset(traj_id)
    assert db_asset_after.control_points == [(-2.0, 0.0), (-1.0, 1.0)]
    assert db_asset_after.length_m == orig_asset.length_m


def test_15_rejected_save_keeps_edit_draft_and_error_state(canvas, temp_store):
    """13. 任务 04B-R UI 状态与草稿保护：保存被拒时 UI 呈现 error 状态，且用户编辑草稿不丢失"""
    canvas.select_robot("A")
    canvas._active_waypoints = [(-2.0, 0.0), (-1.0, 1.0)]
    assert canvas.finish_trajectory() is True
    traj_id = canvas._completed_trajectories[0]["id"]
    canvas.save_current_trajectory(traj_id)

    temp_store.save_clip("clip_ref_15", "1", "TRAJ", traj_id, 0, 1500)
    canvas.select_trajectory(traj_id)
    # 编辑将 P2 移动至 (-1.0, 3.5)
    canvas._completed_trajectories[0]["waypoints"][1] = (-1.0, 3.5)

    failed_signals = []
    saved_signals = []
    canvas.validationFailed.connect(lambda msg: failed_signals.append(msg))
    canvas.trajectorySaved.connect(lambda d: saved_signals.append(d))

    ok = canvas.save_current_trajectory(traj_id)
    assert ok is False

    # 1. UI 进入 error 状态，严禁出现“成功”
    assert canvas._status_message[1] == "error"
    assert "成功" not in canvas._status_message[0]
    assert len(failed_signals) == 1
    assert len(saved_signals) == 0

    # 2. 当前编辑草稿完整保留在画布中，用户修改没有被清空
    current_item = canvas._completed_trajectories[0]
    assert current_item["waypoints"][1] == (-1.0, 3.5)

    # 3. 用户若主动放弃，按 Esc 依然能可靠还原为未修改的原始备份
    assert canvas.cancel_edit() is True
    assert canvas._completed_trajectories[0]["waypoints"][1] == (-1.0, 1.0)


def test_16_duration_semantic_estimate_distinct_from_clip_duration_ms(canvas, temp_store):
    """14. 任务 04B-R duration 数据语义：轨迹 duration 仅为估算秒数，与时间轴 Clip 的 duration_ms 解耦"""
    canvas.select_robot("A")
    # 总长约 1.414m，v=0.8 m/s -> 估算时长约 1.77s
    canvas._active_waypoints = [(-2.0, 0.0), (-1.0, 1.0)]
    assert canvas.finish_trajectory() is True
    traj_id = canvas._completed_trajectories[0]["id"]
    canvas.save_current_trajectory(traj_id)

    # 在时间轴中插入 Clip，独立设定业务播放时长 12500ms（拉伸播放）
    temp_store.save_clip("clip_semantic_16", "1", "TRAJ", traj_id, 0, 12500)

    # 编辑轨迹并强制覆盖更新（总长增加）
    canvas.select_trajectory(traj_id)
    canvas.insert_waypoint_to_trajectory(traj_id, 2, (0.0, 2.0))
    assert canvas.save_current_trajectory(traj_id, allow_overwrite_referenced=True) is True

    # 验证轨迹表中的 duration (秒)
    with temp_store.get_connection() as conn:
        row_traj = conn.execute("SELECT duration FROM trajectories WHERE traj_id = ?", (traj_id,)).fetchone()
        assert row_traj["duration"] > 2.0  # 随长度增加而更新的估算秒数

        # 验证时间轴表中的 duration_ms (毫秒) 绝对未被擅自篡改，仍然保持为 12500ms
        row_clip = conn.execute("SELECT duration_ms FROM timeline_clips WHERE clip_id = 'clip_semantic_16'").fetchone()
        assert row_clip["duration_ms"] == 12500
