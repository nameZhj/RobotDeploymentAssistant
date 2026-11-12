"""
@file: tests/unit/test_task04a_stage_canvas_2d.py
@brief: 任务 04A 单机器人 2D 轨迹绘制、鼠标交互、校验拦截与样条资产测试
@exports: test_01 到 test_10 交互与校验测试用例
"""
import math
import sys
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QImage, QKeyEvent, QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication

from src.domain.trajectory.trajectory_asset import TrajectoryAsset
from src.domain.trajectory.trajectory_draft_validator import TrajectoryDraftValidator
from src.ui.choreo_page.map_canvas_renderer import MapCanvasRenderer
from src.ui.choreo_page.stage_canvas_2d import StageCanvas2D


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def canvas(qapp):
    widget = StageCanvas2D()
    widget.resize(800, 600)
    return widget


def _make_mouse_event(event_type, point: QPointF, button=Qt.LeftButton, modifiers=Qt.NoModifier):
    return QMouseEvent(
        event_type, point, point, point, button, button if event_type == QEvent.MouseButtonPress else Qt.NoButton,
        modifiers
    )


def test_01_mouse_click_creates_control_points_and_stage_coordinate_consistency(canvas):
    """1. 真实鼠标点击产生控制点，且屏幕坐标与舞台世界坐标严格双向一致"""
    canvas.select_robot("A")  # Robot A at (-2.0, 0.0)
    canvas.set_draw_mode("DRAW_TRAJECTORY")

    # 屏幕中心点 (400, 300) 对应舞台原点 (0, 0)
    screen_pt = QPointF(400.0, 300.0)
    wx, wy = canvas.screen_to_stage(screen_pt)
    assert wx == pytest.approx(0.0, abs=0.01)
    assert wy == pytest.approx(0.0, abs=0.01)

    # 逆向变换 stage_to_screen 严格还原
    reconstructed_screen = canvas.stage_to_screen(wx, wy)
    assert reconstructed_screen.x() == pytest.approx(screen_pt.x(), abs=0.1)
    assert reconstructed_screen.y() == pytest.approx(screen_pt.y(), abs=0.1)

    # 模拟鼠标左键点击原点附近
    points_received = []
    canvas.pointAdded.connect(lambda x, y: points_received.append((x, y)))
    canvas.mousePressEvent(_make_mouse_event(QEvent.MouseButtonPress, screen_pt, Qt.LeftButton))

    assert len(canvas._active_waypoints) == 1
    assert len(points_received) == 1
    assert points_received[0] == (wx, wy)


def test_02_mouse_move_shows_temporary_line(canvas):
    """2. 鼠标移动显示临时线段悬停坐标，离开画布时自动清空"""
    canvas.set_draw_mode("DRAW_TRAJECTORY")
    # 先点击添加一个控制点
    canvas._active_waypoints.append((-2.0, 0.0))

    # 鼠标移动到屏幕点 (450, 250)
    move_pt = QPointF(450.0, 250.0)
    canvas.mouseMoveEvent(_make_mouse_event(QEvent.MouseMove, move_pt, Qt.NoButton))
    assert canvas._hover_stage_pos is not None
    expected_x, expected_y = canvas.screen_to_stage(move_pt)
    assert canvas._hover_stage_pos == (expected_x, expected_y)

    # 鼠标离开窗口触发 leaveEvent
    canvas.leaveEvent(QEvent(QEvent.Leave))
    assert canvas._hover_stage_pos is None


def test_03_cancel_trajectory_discards_active_without_saving(canvas):
    """3. 取消退出 (Esc/clear) 立即丢弃草稿，严禁保存任何轨迹记录"""
    canvas.set_draw_mode("DRAW_TRAJECTORY")
    canvas._active_waypoints.extend([(-2.0, 0.0), (-1.0, 1.0)])
    canvas._hover_stage_pos = (0.0, 2.0)
    assert len(canvas._completed_trajectories) == 0

    cancelled_signals = []
    canvas.trajectoryCancelled.connect(lambda: cancelled_signals.append(True))

    # 按 Esc 键取消
    canvas.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))

    assert len(canvas._active_waypoints) == 0
    assert len(canvas._live_spline_points) == 0
    assert canvas._hover_stage_pos is None
    assert len(canvas._completed_trajectories) == 0
    assert len(cancelled_signals) == 1


def test_04_mode_isolation_prevents_misclick(canvas):
    """4. 绘制模式与选择模式严格隔离防误触：SELECT 模式不落点，DRAW 模式不误选"""
    canvas.select_robot("A")
    canvas.set_draw_mode("SELECT")
    assert canvas.cursor().shape() == Qt.PointingHandCursor

    # 在 SELECT 模式下点击空白区域，不应添加任何控制点
    canvas.mousePressEvent(_make_mouse_event(QEvent.MouseButtonPress, QPointF(300.0, 200.0), Qt.LeftButton))
    assert len(canvas._active_waypoints) == 0

    # 在 SELECT 模式下点击 Robot B 所在坐标 (2.0, 0.0)
    screen_b = canvas.stage_to_screen(2.0, 0.0)
    canvas.mousePressEvent(_make_mouse_event(QEvent.MouseButtonPress, screen_b, Qt.LeftButton))
    assert canvas._selected_robot_id == "B"

    # 切换回 DRAW_TRAJECTORY 模式，光标恢复为十字且开始接收控制点
    canvas.set_draw_mode("DRAW_TRAJECTORY")
    assert canvas.cursor().shape() == Qt.CrossCursor
    canvas.mousePressEvent(_make_mouse_event(QEvent.MouseButtonPress, screen_b, Qt.LeftButton))
    assert len(canvas._active_waypoints) == 1


def test_05_validation_insufficient_points_rejected_with_warning(canvas):
    """5. 控制点不足校验：少于 2 个控制点时拒绝完成并提示，不生成假轨迹"""
    canvas.select_robot("A")
    canvas._active_waypoints.append((-2.0, 0.0))

    errors_caught = []
    canvas.validationFailed.connect(lambda msg: errors_caught.append(msg))

    result = canvas.finish_trajectory()
    assert result is False
    assert len(canvas._completed_trajectories) == 0
    assert len(errors_caught) == 1
    assert "至少需要 2 个控制点" in errors_caught[0]


def test_06_validation_non_finite_and_out_of_bounds_rejected(canvas):
    """6. 坐标数值有效性校验：非有限数、超出舞台工作区或重复点均被有效拦截"""
    # 6.1 非有限浮点数
    valid, err = TrajectoryDraftValidator.validate([(-2.0, 0.0), (float("nan"), 1.0)], "A")
    assert valid is False
    assert "坐标非法" in err

    # 6.2 超出舞台边界 (±50m)
    valid, err = TrajectoryDraftValidator.validate([(-2.0, 0.0), (80.0, 0.0)], "A")
    assert valid is False
    assert "超出舞台有效工作区" in err

    # 6.3 连续两点过近重叠
    valid, err = TrajectoryDraftValidator.validate([(-2.0, 0.0), (-2.0001, 0.0001)], "A")
    assert valid is False
    assert "重叠或间距过小" in err


def test_07_validation_robot_start_anchor_deviation_check(canvas):
    """7. 轨迹起点与机器人初始位姿锚定校验：起点偏差过大时拦截"""
    canvas.select_robot("A")  # Robot A pos is (-2.0, 0.0)
    # 起点放在 (8.0, 8.0)，与 (-2, 0) 距离远超 3m 允许范围
    canvas._active_waypoints = [(8.0, 8.0), (9.0, 9.0)]

    errors = []
    canvas.validationFailed.connect(lambda err: errors.append(err))
    success = canvas.finish_trajectory()

    assert success is False
    assert len(errors) == 1
    assert "站位偏差过大" in errors[0]
    assert len(canvas._completed_trajectories) == 0


def test_08_successful_draw_generates_smooth_spline_and_trajectory_asset(canvas):
    """8. 成功完成绘制：生成平滑 Catmull-Rom 样条，组装统一 TrajectoryAsset 并绑定 robot_id"""
    canvas.select_robot("A")
    # 起点在 (-2.0, 0.0) 附近
    wps = [(-2.0, 0.0), (-1.0, 1.0), (0.0, 0.5), (1.0, -0.5)]
    canvas._active_waypoints = list(wps)
    canvas._recompute_spline()

    finished_payload = {}
    canvas.trajectoryFinished.connect(lambda data: finished_payload.update(data))

    ok = canvas.finish_trajectory()
    assert ok is True
    assert len(canvas._completed_trajectories) == 1
    assert len(canvas._active_waypoints) == 0

    # 验证载荷字典
    assert finished_payload["robot_id"] == "A"
    assert finished_payload["waypoints"] == wps
    assert len(finished_payload["spline_points"]) > 20
    assert finished_payload["length"] > 0.0
    assert finished_payload["duration"] > 0.0

    # 验证内嵌领域资产 TrajectoryAsset
    asset: TrajectoryAsset = finished_payload["asset"]
    assert isinstance(asset, TrajectoryAsset)
    assert asset.trajectory_id.startswith("traj_A_")
    assert asset.coordinate_frame == "stage_world"
    assert asset.control_points == wps
    assert len(asset.sampled_points) == len(finished_payload["spline_points"])
    # 验证采样点的物理量纲与单调性
    assert asset.sampled_points[0].s_m == 0.0
    assert asset.sampled_points[-1].s_m == pytest.approx(asset.length_m)
    for i in range(1, len(asset.sampled_points)):
        assert asset.sampled_points[i].s_m >= asset.sampled_points[i - 1].s_m
        assert math.isfinite(asset.sampled_points[i].yaw_deg)


def test_09_undo_waypoint_and_keyboard_shortcuts(canvas):
    """9. 快捷操作支持：Ctrl+Z 撤销最后一个控制点，Enter 键快捷完成"""
    canvas.select_robot("A")
    canvas.set_draw_mode("DRAW_TRAJECTORY")
    canvas._active_waypoints = [(-2.0, 0.0), (-1.0, 1.0), (0.0, 0.0)]
    canvas._recompute_spline()
    assert len(canvas._active_waypoints) == 3

    # Ctrl+Z 撤销
    canvas.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Z, Qt.ControlModifier))
    assert len(canvas._active_waypoints) == 2
    assert canvas._active_waypoints[-1] == (-1.0, 1.0)

    # Enter 快捷完成
    finished = []
    canvas.trajectoryFinished.connect(lambda d: finished.append(d))
    canvas.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
    assert len(finished) == 1
    assert len(canvas._completed_trajectories) == 1


def test_10_map_canvas_renderer_draws_hover_line_and_status_toast():
    """10. 渲染层健全性验证：临时悬停虚线段与状态胶囊绘制不崩溃"""
    img = QImage(400, 300, QImage.Format_ARGB32)
    img.fill(Qt.black)
    p = QPainter(img)

    # 验证带 hover_pos 的样条与临时虚线渲染
    wps = [(0.0, 0.0), (1.0, 1.0)]
    spline = [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)]
    hover = (2.0, 1.5)
    MapCanvasRenderer.draw_spline_trajectory(p, wps, spline, True, 200.0, 150.0, 20.0, hover)

    # 验证状态与错误胶囊渲染
    MapCanvasRenderer.draw_status_toast(p, 400, "测试信息提示", "info")
    MapCanvasRenderer.draw_status_toast(p, 400, "测试错误拦截", "error")
    p.end()

    assert img.width() == 400
