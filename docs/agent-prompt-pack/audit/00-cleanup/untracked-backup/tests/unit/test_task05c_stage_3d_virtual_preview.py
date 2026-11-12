"""
@file: tests/unit/test_task05c_stage_3d_virtual_preview.py
@brief: 任务 05C 3D 虚拟预演单机/多机播放、时序插值、坐标一致性与生命周期测试
@exports: 测试用例集
"""
import math
import os
import sqlite3
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.application.services.virtual_show_player import VirtualShowPlayer
from src.application.stage_director.stage_preview_coordinator import (
    StagePreviewCoordinator,
)
from src.application.stage_director.stage_preview_engine import StagePreviewEngine
from src.domain.simulation.stage_performance_sampler import (
    AvatarSimulationState,
    StagePerformanceSampler,
)
from src.domain.timeline.timeline_clip_asset import (
    TimelineClipAsset,
    TrackLayerType,
)
from src.domain.trajectory.group_trajectory import GroupTrajectory, GroupTrajectoryMember
from src.domain.trajectory.trajectory_asset import TrajectoryAsset, TrajectoryPoint
from src.infrastructure.storage.choreo_sqlite_store import ChoreoSqliteStore
from src.infrastructure.storage.group_trajectory_sqlite_adapter import (
    GroupTrajectorySqliteAdapter,
)
from src.infrastructure.storage.timeline_clip_sqlite_adapter import (
    TimelineClipSqliteAdapter,
)
from src.infrastructure.storage.trajectory_sqlite_adapter import (
    TrajectorySqliteAdapter,
)
from src.ui.stage3d.robot_avatar_3d_painter import RobotAvatar3DPainter
from src.ui.stage3d.stage_viewport_3d import StageViewport3D
from src.ui.windows.main_studio_window import MainStudioWindow

app = QApplication.instance() or QApplication([])


@pytest.fixture
def choreo_env(tmp_path):
    db_file = str(tmp_path / "test_preview_studio.db")
    store = ChoreoSqliteStore(db_file)

    # 1. 单机轨迹素材
    pts1 = [
        TrajectoryPoint(0.0, 0.0, 0.0, 0.0),
        TrajectoryPoint(1.0, 1.0, 45.0, 1.414),
        TrajectoryPoint(2.0, 2.0, 45.0, 2.828),
    ]
    asset1 = TrajectoryAsset(
        trajectory_id="traj_single_01",
        name="单机斜线",
        control_points=[(0.0, 0.0), (2.0, 2.0)],
        sampled_points=pts1,
        length_m=2.828,
        recommended_speed_mps=1.0,
    )
    TrajectorySqliteAdapter.save_asset(store, asset1)

    # 2. 群组轨迹素材 (引用 traj_single_01)
    grp = GroupTrajectory(
        group_trajectory_id="grp_preview_01",
        name="双机梯队",
        reference_trajectory_id="traj_single_01",
        members=[
            GroupTrajectoryMember("A", offset_x_m=0.0, offset_y_m=0.5, delta_yaw_deg=0.0),
            GroupTrajectoryMember("B", offset_x_m=0.0, offset_y_m=-0.5, delta_yaw_deg=0.0),
        ],
    )
    GroupTrajectorySqliteAdapter.save_group(store, grp)

    # 3. 编排时间轴 Clip
    adapter = TimelineClipSqliteAdapter(db_file)
    adapter.save_clip(TimelineClipAsset(
        clip_id="c_act_1", robot_id="1", track_layer=TrackLayerType.ACTION,
        ref_id="550502", name="POPPING1", start_ms=0, duration_ms=3000
    ))
    adapter.save_clip(TimelineClipAsset(
        clip_id="c_trj_1", robot_id="1", track_layer=TrackLayerType.TRAJECTORY,
        ref_id="traj_single_01", name="单机斜线", start_ms=0, duration_ms=2800
    ))
    adapter.save_clip(TimelineClipAsset(
        clip_id="c_grp_2", robot_id="GROUP", track_layer=TrackLayerType.TRAJECTORY,
        ref_id="grp_preview_01", name="双机梯队", start_ms=3000, duration_ms=2800, is_group=True
    ))

    return store, db_file


def test_01_single_robot_trajectory_playback(choreo_env):
    store, _ = choreo_env
    data = StagePreviewEngine.build_preview_tracks(store)
    assert "Robot_1" in data["robot_tracks"]
    r1_tracks = data["robot_tracks"]["Robot_1"]
    assert len(r1_tracks["trajectories"]) >= 1
    assert len(r1_tracks["actions"]) >= 1

    poses_t0 = StagePreviewEngine.interpolate_poses_at_time(data["robot_tracks"], 0)
    assert "Robot_1" in poses_t0
    assert poses_t0["Robot_1"].x == 0.0 and poses_t0["Robot_1"].y == 0.0

    poses_tmid = StagePreviewEngine.interpolate_poses_at_time(data["robot_tracks"], 1400)
    assert 0.5 < poses_tmid["Robot_1"].x < 1.5
    assert 0.5 < poses_tmid["Robot_1"].y < 1.5


def test_02_multi_robot_group_trajectory_playback(choreo_env):
    store, _ = choreo_env
    data = StagePreviewEngine.build_preview_tracks(store)
    # 群组轨迹成员 A 映射到 Robot_1, 成员 B 映射到 Robot_2
    assert "Robot_1" in data["robot_tracks"]
    assert "Robot_2" in data["robot_tracks"]

    # 在群组播放时间段 (t = 4000ms) 采样
    poses = StagePreviewEngine.interpolate_poses_at_time(data["robot_tracks"], 4000)
    p_a = poses["Robot_1"]
    p_b = poses["Robot_2"]
    # 两机因 Frenet 侧向偏移，位置绝不重合
    dist = math.hypot(p_a.x - p_b.x, p_a.y - p_b.y)
    assert dist > 0.4, f"群组机器人位置不应重叠，实测间距: {dist:.3f}m"


def test_03_playback_controls_play_pause_resume_stop():
    player = VirtualShowPlayer()
    player.set_loop(False)
    player.set_duration_ms(5000)

    # 1. 播放
    player.play()
    assert player.is_playing() is True

    # 2. 暂停
    player.seek(1500)
    player.pause()
    assert player.is_playing() is False
    assert player.get_current_time_ms() == 1500

    # 3. 继续
    player.resume()
    assert player.is_playing() is True
    assert player.get_current_time_ms() == 1500

    # 4. 停止
    player.stop()
    assert player.is_playing() is False
    assert player.get_current_time_ms() == 0
    player.cleanup()


def test_04_timeline_progress_sync_and_seek():
    player = VirtualShowPlayer()
    player.set_duration_ms(8000)
    ticks = []
    player.tick.connect(lambda t, poses: ticks.append(t))

    player.seek(3200)
    assert player.get_current_time_ms() == 3200
    assert player.get_current_time_s() == 3.2
    assert len(ticks) >= 1
    player.cleanup()


def test_05_trajectory_interpolation_continuity():
    sampler = StagePerformanceSampler()
    block = {
        "start_s": 0.0,
        "duration_s": 4.0,
        "points": [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (2.0, 2.0, 90.0)],
    }
    prev_x, prev_y = 0.0, 0.0
    for ms in range(0, 4000, 200):
        t_sec = ms / 1000.0
        x, y, yaw = sampler._interpolate_trajectory(t_sec, [block])
        step_dist = math.hypot(x - prev_x, y - prev_y)
        assert step_dist < 0.6  # 连续无跳跃
        prev_x, prev_y = x, y


def test_06_time_units_conversion_strict():
    # 明确时间为秒/毫秒，距离为米
    sampler = StagePerformanceSampler()
    # 轨迹弧长 10m，持续时间 5.0s
    block = {"start_s": 1.0, "duration_s": 5.0, "points": [(0.0, 0.0), (10.0, 0.0)]}
    # 播放时间 3.5s (中间时刻进度 50%) -> 坐标应为 x=5.0m
    x, y, yaw = sampler._interpolate_trajectory(3.5, [block])
    assert abs(x - 5.0) < 0.05
    assert yaw == 0.0


def test_07_coordinate_system_consistency():
    vp = StageViewport3D()
    # 测试原点投影位于视口中轴
    vp.resize(800, 600)
    proj_origin = vp._project(0.0, 0.0, 0.0)
    assert proj_origin is not None
    # 3D 深度 > 0
    assert proj_origin[2] > 0
    # X 正方向在屏幕中心右侧
    proj_x_plus = vp._project(2.0, 0.0, 0.0)
    assert proj_x_plus is not None
    assert proj_x_plus[0] > proj_origin[0]


def test_08_playback_end_handling():
    player = VirtualShowPlayer()
    player.set_loop(False)
    player.set_duration_ms(2000)
    finished = []
    player.playbackFinished.connect(lambda: finished.append(True))

    player.seek(1990)
    player.play()
    player._on_timer_tick()  # 步进超过 2000ms
    assert player.is_playing() is False
    assert player.get_current_time_ms() == 2000
    assert len(finished) == 1
    player.cleanup()


def test_09_lifecycle_no_lingering_timers_on_switch(choreo_env):
    _, db_file = choreo_env
    win = MainStudioWindow()
    win.store = ChoreoSqliteStore(db_file)
    win.show_player.play()
    assert win.show_player.is_playing() is True

    # 切换至群组工作区必须自动暂停
    win.enter_group_trajectory_workspace()
    assert win.show_player.is_playing() is False

    # 关闭窗口安全释放
    win.close()
    assert win.show_player._timer.isActive() is False


def test_10_repeated_play_no_duplicate_timers():
    player = VirtualShowPlayer()
    player.play()
    timer_id = id(player._timer)
    # 重复调用 play()
    player.play()
    player.play()
    assert id(player._timer) == timer_id
    assert player._timer.isActive() is True
    player.cleanup()
    assert player._timer.isActive() is False


def test_11_empty_state_and_missing_model_display():
    vp = StageViewport3D()
    # 点云空状态
    vp.set_point_cloud(None)
    assert len(vp._point_cloud) == 0

    # 模型缺失渲染分支
    painter = RobotAvatar3DPainter()
    # 当 is_model_missing=True 时不崩溃且正常绘制告示牌
    p = type("MockPainter", (), {
        "setPen": lambda self, *a: None, "setBrush": lambda self, *a: None,
        "drawEllipse": lambda self, *a: None, "drawRoundedRect": lambda self, *a: None,
        "drawText": lambda self, *a: None, "setFont": lambda self, *a: None,
    })()
    painter.render_robot(
        p=p, project_fn=lambda x, y, z: (100.0, 100.0, 5.0),
        base_pose=(0.0, 0.0, 0.0, 0.0), action_name="STAND", t_sec=0.0,
        is_model_missing=True
    )


def test_12_pure_virtual_safety_boundary():
    # 验证 3D 虚拟预演模块绝对不导入或调用串口硬件写操作
    import inspect
    from src.application.stage_director.stage_preview_engine import StagePreviewEngine
    src = inspect.getsource(StagePreviewEngine)
    assert "serial" not in src.lower()
    assert "lora" not in src.lower()
    assert "send_command" not in src.lower()


def test_13_pcd_map_loading_to_3d_viewport():
    vp = StageViewport3D()
    pts = [(0.0, 0.0, 0.1), (1.0, 2.0, 0.2)]
    vp.set_point_cloud(pts)
    assert len(vp._point_cloud) == 2
    vp.clear_point_cloud()
    assert len(vp._point_cloud) == 0
