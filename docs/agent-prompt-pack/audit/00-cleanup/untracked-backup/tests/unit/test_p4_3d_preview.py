"""
@file: tests/unit/test_p4_3d_preview.py
@brief: P4 阶段自动化测试：3D 预演编译器、真实 NPZ 动作插值、边界采样与单时钟一致性
@exports: test_preview_compiler_and_validation, test_npz_keyframe_sampling, test_boundary_clamping, test_group_formation_derivation, test_clock_and_collision
"""
import math
import os
import numpy as np
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from src.application.services.virtual_show_player import VirtualShowPlayer
from src.application.stage_director.stage_preview_coordinator import StagePreviewCoordinator
from src.application.stage_director.stage_preview_engine import StagePreviewEngine
from src.domain.simulation.stage_performance_sampler import (
    AvatarSimulationState,
    StagePerformanceSampler,
)
from src.domain.timeline.timeline_clip_asset import TimelineClipAsset, TrackLayerType
from src.domain.trajectory.trajectory_asset import TrajectoryAsset, TrajectoryPoint
from src.infrastructure.storage.choreo_sqlite_store import ChoreoSqliteStore
from src.infrastructure.storage.timeline_clip_sqlite_adapter import TimelineClipSqliteAdapter
from src.infrastructure.storage.trajectory_sqlite_adapter import TrajectorySqliteAdapter
from src.ui.stage3d.stage_viewport_3d import StageViewport3D


@pytest.fixture
def test_db_env(tmp_path):
    db_file = str(tmp_path / "test_p4_studio.db")
    store = ChoreoSqliteStore(db_file)
    return store, db_file


def test_preview_compiler_and_validation(test_db_env):
    store, db_path = test_db_env
    clip_adapter = TimelineClipSqliteAdapter(db_path)

    # 1. 插入有效轨迹资产与片段
    pts = [TrajectoryPoint(s_m=0.0, x_m=0.0, y_m=0.0, yaw_deg=0.0), TrajectoryPoint(s_m=2.8, x_m=2.0, y_m=2.0, yaw_deg=45.0)]
    t_asset = TrajectoryAsset(trajectory_id="traj_p4_1", name="测试轨迹1", control_points=[(0.0, 0.0), (2.0, 2.0)], sampled_points=pts, length_m=2.8)
    TrajectorySqliteAdapter.save_asset(store, t_asset)

    c1 = TimelineClipAsset(clip_id="c_traj1", task_name="默认任务1", track_layer=TrackLayerType.TRAJECTORY,
                           robot_id="1", ref_id="traj_p4_1", start_ms=0, duration_ms=2000, name="轨迹片段1")
    clip_adapter.save_clip(c1)

    # 2. 插入有效动作片段 (引用真实的 preview/G1_KUNG_FU.npz)
    c2 = TimelineClipAsset(clip_id="c_act1", task_name="默认任务1", track_layer=TrackLayerType.ACTION,
                           robot_id="1", ref_id="act_g1_kungfu", start_ms=500, duration_ms=3000, name="G1_太极抱拳")
    clip_adapter.save_clip(c2)

    # 3. 插入缺失素材的动作片段
    c3 = TimelineClipAsset(clip_id="c_act_missing", task_name="默认任务1", track_layer=TrackLayerType.ACTION,
                           robot_id="2", ref_id="missing_act", start_ms=0, duration_ms=2000, name="缺失动作")
    clip_adapter.save_clip(c3)

    schedule = StagePreviewEngine.build_preview_tracks(store, task_name="默认任务1")
    assert "robot_tracks" in schedule
    assert "Robot_1" in schedule["robot_tracks"]
    assert "Robot_2" in schedule["robot_tracks"]
    assert schedule["duration_ms"] >= 3500

    r1_act = schedule["robot_tracks"]["Robot_1"]["actions"][0]
    assert r1_act["is_verified"] is True
    assert r1_act["npz_positions"] is not None
    assert len(r1_act["npz_positions"]) == 300

    r2_act = schedule["robot_tracks"]["Robot_2"]["actions"][0]
    assert r2_act["is_verified"] is False
    assert len(schedule["unplayable_items"]) >= 1
    assert any(u["name"] == "缺失动作" for u in schedule["unplayable_items"])


def test_npz_keyframe_sampling():
    sampler = StagePerformanceSampler()
    # 模拟真实 G1_KUNG_FU NPZ 动作块
    npz_data = np.load("preview/G1_KUNG_FU.npz", allow_pickle=False)
    positions = npz_data["positions"]

    action_blocks = [{
        "name": "G1_太极抱拳",
        "start_s": 1.0,
        "duration_s": 6.0,
        "is_verified": True,
        "npz_positions": positions,
        "fps": 50.0,
    }]
    trajectory_blocks = [{
        "name": "直线行进",
        "start_s": 0.0,
        "duration_s": 10.0,
        "points": [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)],
    }]

    # 1. 动作开始时刻 t = 1.0s (第 0 帧)
    pose_1s = sampler.sample_robot_pose("Robot_1", 1.0, trajectory_blocks, action_blocks)
    assert pose_1s.pose_status == "NORMAL"
    assert pose_1s.keyframe_positions is not None
    assert "pelvis" in pose_1s.keyframe_positions
    pelvis_pos_0 = pose_1s.keyframe_positions["pelvis"]
    # 机器人世界 X 此时为 1.0m，pelvis 本地原点为 0.0 -> 世界坐标应为 1.0
    assert abs(pelvis_pos_0[0] - 1.0) < 1e-2

    # 2. 关键帧线性插值 (t = 1.01s, 对应第 0.5 帧)
    pose_half = sampler.sample_robot_pose("Robot_1", 1.01, trajectory_blocks, action_blocks)
    assert pose_half.pose_status == "NORMAL"
    assert pose_half.keyframe_positions is not None
    for link, p in pose_half.keyframe_positions.items():
        assert not math.isnan(p[0]) and not math.isnan(p[1]) and not math.isnan(p[2])

    # 3. 动作前与动作后采样
    pose_before = sampler.sample_robot_pose("Robot_1", 0.5, trajectory_blocks, action_blocks)
    assert pose_before.pose_status == "STAND_FALLBACK"
    assert pose_before.keyframe_positions is None

    pose_after = sampler.sample_robot_pose("Robot_1", 8.0, trajectory_blocks, action_blocks)
    assert pose_after.pose_status == "STAND_FALLBACK"


def test_boundary_clamping():
    sampler = StagePerformanceSampler()
    trajectory_blocks = [{
        "name": "单段轨迹",
        "start_s": 2.0,
        "duration_s": 4.0,
        "points": [(1.0, 1.0, 0.0), (5.0, 5.0, 45.0)],
    }]

    # 轨迹开始前：严格保持首帧坐标，禁止瞬移回 (0, 0)
    p_before = sampler.sample_robot_pose("Robot_1", 0.0, trajectory_blocks, [])
    assert abs(p_before.x - 1.0) < 1e-3 and abs(p_before.y - 1.0) < 1e-3

    # 轨迹结束后：严格保持末帧坐标，禁止跳回原点
    p_after = sampler.sample_robot_pose("Robot_1", 10.0, trajectory_blocks, [])
    assert abs(p_after.x - 5.0) < 1e-3 and abs(p_after.y - 5.0) < 1e-3
    assert abs(p_after.yaw_deg - 45.0) < 1e-3


def test_group_formation_derivation(test_db_env):
    store, db_path = test_db_env
    ref_asset = TrajectoryAsset(
        trajectory_id="ref_line", name="基准直线",
        control_points=[(0.0, 0.0), (5.0, 0.0)],
        sampled_points=[TrajectoryPoint(s_m=0.0, x_m=0.0, y_m=0.0, yaw_deg=0.0), TrajectoryPoint(s_m=5.0, x_m=5.0, y_m=0.0, yaw_deg=0.0)],
        length_m=5.0
    )
    TrajectorySqliteAdapter.save_asset(store, ref_asset)

    from src.infrastructure.storage.group_trajectory_sqlite_adapter import GroupTrajectorySqliteAdapter
    from src.domain.trajectory.group_trajectory import GroupTrajectory, GroupTrajectoryMember
    m1 = GroupTrajectoryMember("Robot_1", offset_x_m=0.0, offset_y_m=0.75, delta_yaw_deg=0.0)
    m2 = GroupTrajectoryMember("Robot_2", offset_x_m=0.0, offset_y_m=-0.75, delta_yaw_deg=0.0)
    group = GroupTrajectory(
        group_trajectory_id="grp_line", name="横队编队", reference_trajectory_id="ref_line",
        members=(m1, m2)
    )
    GroupTrajectorySqliteAdapter.save_group(store, group)

    clip_adapter = TimelineClipSqliteAdapter(db_path)
    c_grp = TimelineClipAsset(clip_id="cg_1", task_name="默认任务1", track_layer=TrackLayerType.TRAJECTORY,
                              robot_id="GROUP", ref_id="grp_line", is_group=True, start_ms=0, duration_ms=5000, name="群组行进")
    clip_adapter.save_clip(c_grp)

    schedule = StagePreviewEngine.build_preview_tracks(store, task_name="默认任务1")
    assert "Robot_1" in schedule["robot_tracks"]
    assert "Robot_2" in schedule["robot_tracks"]

    r1_pts = schedule["robot_tracks"]["Robot_1"]["trajectories"][0]["points"]
    r2_pts = schedule["robot_tracks"]["Robot_2"]["trajectories"][0]["points"]
    # 验证两机器人横向间距 1.5m 派生
    assert abs(abs(r1_pts[0][1] - r2_pts[0][1]) - 1.5) < 1e-3


def test_clock_and_collision():
    coordinator = StagePreviewCoordinator()
    # 配置两台机器人，初始间距 0.5m (处于硬防撞 < 0.65m 范围内)
    tracks = {
        "Robot_1": {"trajectories": [{"start_s": 0.0, "duration_s": 5.0, "points": [(0.0, 0.0, 0.0)]}], "actions": []},
        "Robot_2": {"trajectories": [{"start_s": 0.0, "duration_s": 5.0, "points": [(0.5, 0.0, 0.0)]}], "actions": []},
    }
    coordinator.set_robot_tracks(tracks)
    poses = coordinator.sample_at_time(0)
    diag = coordinator.check_collision_status(poses)
    assert diag["status"] == "BLOCKED"
    assert len(diag["alerts"]) >= 1

    player = VirtualShowPlayer()
    player.set_duration_ms(2000)
    player.set_loop(False)
    player.seek(500)
    assert player.get_current_time_ms() == 500
    player.seek(3000)
    # 超过时长限制钳位
    assert player.get_current_time_ms() == 2000
    player.cleanup()


def test_06_viewport_first_frame_and_empty_state():
    viewport = StageViewport3D()
    viewport.clear_robot_poses()
    assert len(viewport._robot_poses) == 0

    # 1. 验证首帧点云与轨迹设置
    viewport.set_point_cloud([(0.0, 0.0, 0.0), (1.0, 1.0, 0.5)])
    assert len(viewport._point_cloud) == 2
    viewport.clear_point_cloud()
    assert len(viewport._point_cloud) == 0

    # 2. 模拟从协调器接收首帧 (t=0) 快照并在 3D 呈现
    coordinator = StagePreviewCoordinator()
    poses = coordinator.sample_at_time(0)
    viewport.set_robot_poses(poses)
    assert len(viewport._robot_poses) == 2
    assert "Robot_1" in viewport._robot_poses
    assert viewport._robot_poses["Robot_1"].x == -2.0


def test_07_playback_clock_lifecycle():
    player = VirtualShowPlayer()
    player.set_duration_ms(3000)
    player.set_speed(1.0)
    assert player.get_speed() == 1.0

    player.play()
    assert player.is_playing() is True

    player.pause()
    assert player.is_paused() is True

    player.resume()
    assert player.is_playing() is True

    player.stop()
    assert player.is_playing() is False
    assert player.get_current_time_ms() == 0

    # 验证清理定时器无残留
    player.cleanup()
    assert player._timer.isActive() is False

