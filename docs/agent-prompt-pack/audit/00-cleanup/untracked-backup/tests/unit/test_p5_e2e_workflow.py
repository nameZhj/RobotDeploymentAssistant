"""
@file: tests/unit/test_p5_e2e_workflow.py
@brief: P5 阶段端到端全业务闭环集成测试：地图生命周期、群组阵型、时间轴与 3D 预演
@exports: test_e2e_scenario_a_map, test_e2e_scenario_bc_formation_and_group, test_e2e_scenario_de_timeline_3d
"""
import math
import os
import numpy as np
import pytest

from src.application.services.virtual_show_player import VirtualShowPlayer
from src.application.stage_director.stage_map_controller import StageMapController
from src.application.stage_director.stage_preview_coordinator import StagePreviewCoordinator
from src.application.stage_director.stage_preview_engine import StagePreviewEngine
from src.domain.project.show_project import Formation, Robot, ShowProject
from src.domain.simulation.stage_performance_sampler import StagePerformanceSampler
from src.domain.timeline.timeline_clip_asset import TimelineClipAsset, TrackLayerType
from src.domain.trajectory.formation_matrix_planner import FormationMatrixPlanner
from src.domain.trajectory.group_trajectory import GroupTrajectory, GroupTrajectoryMember
from src.domain.trajectory.group_trajectory_compiler import GroupTrajectoryCompiler
from src.domain.trajectory.group_trajectory_safety import GroupTrajectorySafetyValidator
from src.domain.trajectory.trajectory_asset import TrajectoryAsset, TrajectoryPoint
from src.infrastructure.storage.choreo_sqlite_store import ChoreoSqliteStore
from src.infrastructure.storage.group_trajectory_sqlite_adapter import GroupTrajectorySqliteAdapter
from src.infrastructure.storage.show_project_repository import ShowProjectRepository
from src.infrastructure.storage.stage_map_sqlite_adapter import StageMapSqliteAdapter
from src.infrastructure.storage.timeline_clip_sqlite_adapter import TimelineClipSqliteAdapter
from src.infrastructure.storage.trajectory_sqlite_adapter import TrajectorySqliteAdapter


@pytest.fixture
def e2e_env(tmp_path):
    db_file = str(tmp_path / "e2e_studio.db")
    map_dir = str(tmp_path / "maps")
    os.makedirs(map_dir, exist_ok=True)
    store = ChoreoSqliteStore(db_file)
    repo = ShowProjectRepository(db_file)
    map_ctrl = StageMapController(db_path=db_file, map_dir=map_dir)
    return {
        "store": store, "repo": repo, "map_ctrl": map_ctrl,
        "db_file": db_file, "map_dir": map_dir, "tmp_path": tmp_path,
    }


def test_e2e_scenario_a_map(e2e_env):
    map_ctrl = e2e_env["map_ctrl"]
    tmp_path = e2e_env["tmp_path"]

    # 1. 创建合法 ASCII PCD 地图文件并导入
    pcd_content = "VERSION .7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\nWIDTH 3\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS 3\nDATA ascii\n0.0 0.0 0.0\n1.0 1.0 0.5\n2.0 0.0 0.0\n"
    src_pcd = str(tmp_path / "valid_stage.pcd")
    with open(src_pcd, "w", encoding="utf-8") as f:
        f.write(pcd_content)

    asset = map_ctrl.import_pcd_file(src_pcd, custom_name="演播主舞台")
    assert asset is not None
    map_id = asset.map_id

    # 2. 建立工程引用该地图
    proj = ShowProject(project_id="proj_e2e", name="全链路测试工程", current_map_id=map_id)
    e2e_env["repo"].save_project(proj)

    # 3. 校验被引用的地图严禁物理删除
    ok_in_use, msg_in_use = map_ctrl.delete_map(map_id)
    assert ok_in_use is False
    assert "无法直接删除" in msg_in_use

    # 4. 解除工程引用后，安全删除成功
    proj.current_map_id = ""
    e2e_env["repo"].save_project(proj)
    success, del_msg = map_ctrl.delete_map(map_id)
    assert success is True


def test_e2e_scenario_bc_formation_and_group(e2e_env):
    store = e2e_env["store"]
    # 1. 阵型计算：生成 2x2 网格阵型 (Grid) 与 3机圆阵 (Circle)
    grid_coords = FormationMatrixPlanner.generate_grid_formation(num_robots=4, rows=2, cols=2, spacing=1.5)
    assert len(grid_coords) == 4
    circle_coords = FormationMatrixPlanner.generate_circle_formation(num_robots=3, radius_m=2.5)
    assert len(circle_coords) == 3

    # 2. 创建基准曲线轨迹 (S形曲线样条)
    pts = [
        TrajectoryPoint(s_m=0.0, x_m=0.0, y_m=0.0, yaw_deg=0.0),
        TrajectoryPoint(s_m=2.5, x_m=2.0, y_m=1.0, yaw_deg=30.0),
        TrajectoryPoint(s_m=5.0, x_m=4.0, y_m=0.0, yaw_deg=-30.0),
        TrajectoryPoint(s_m=7.5, x_m=6.0, y_m=0.0, yaw_deg=0.0),
    ]
    base_traj = TrajectoryAsset(
        trajectory_id="base_s_curve", name="S形基准线",
        control_points=[(0.0, 0.0), (2.0, 1.0), (4.0, 0.0), (6.0, 0.0)],
        sampled_points=pts, length_m=7.5
    )
    TrajectorySqliteAdapter.save_asset(store, base_traj)

    # 3. 建立群组成员并派生成员轨迹 (横向双机伴飞)
    m1 = GroupTrajectoryMember("Robot_1", offset_x_m=0.0, offset_y_m=1.0, delta_yaw_deg=0.0)
    m2 = GroupTrajectoryMember("Robot_2", offset_x_m=0.0, offset_y_m=-1.0, delta_yaw_deg=0.0)
    grp = GroupTrajectory("grp_fly_pair", "双机伴飞群组", "base_s_curve", members=(m1, m2))
    GroupTrajectorySqliteAdapter.save_group(store, grp)

    compiled = GroupTrajectoryCompiler.compile(grp, base_traj)
    assert len(compiled) == 2
    assert compiled[0].robot_id == "Robot_1"
    assert compiled[1].robot_id == "Robot_2"

    # 4. 几何安全检测验证：两机曲线间距均大于安全阈值 0.65m，无碰撞
    report = GroupTrajectorySafetyValidator.validate(compiled, required_clearance_m=0.65)
    assert report.is_safe is True
    assert report.violation_count == 0
    assert len(report.pairwise_clearances) == 1
    assert report.pairwise_clearances[0].min_distance_m >= 1.0
    assert report.pairwise_clearances[0].is_clear is True


def test_e2e_scenario_de_timeline_3d(e2e_env):
    store = e2e_env["store"]
    db_file = e2e_env["db_file"]
    clip_adapter = TimelineClipSqliteAdapter(db_file)

    # 0. 准备轨迹资产
    pts = [TrajectoryPoint(s_m=0.0, x_m=0.0, y_m=0.0, yaw_deg=0.0), TrajectoryPoint(s_m=5.0, x_m=5.0, y_m=0.0, yaw_deg=0.0)]
    t_asset = TrajectoryAsset(trajectory_id="base_s_curve", name="S形基准线", control_points=[(0.0, 0.0), (5.0, 0.0)], sampled_points=pts, length_m=5.0)
    TrajectorySqliteAdapter.save_asset(store, t_asset)

    m1 = GroupTrajectoryMember("Robot_1", offset_x_m=0.0, offset_y_m=1.0, delta_yaw_deg=0.0)
    m2 = GroupTrajectoryMember("Robot_2", offset_x_m=0.0, offset_y_m=-1.0, delta_yaw_deg=0.0)
    grp = GroupTrajectory("grp_fly_pair", "双机伴飞群组", "base_s_curve", members=(m1, m2))
    GroupTrajectorySqliteAdapter.save_group(store, grp)

    # 1. 拖入单机轨迹与群组轨迹片段 (单机分配给 Robot_3，避免与群组成员冲突)
    c_single = TimelineClipAsset("c_single_1", "默认任务1", "3", TrackLayerType.TRAJECTORY,
                                 ref_id="base_s_curve", name="主单机轨迹", start_ms=0, duration_ms=5000)
    clip_adapter.save_clip(c_single)

    c_grp = TimelineClipAsset("c_grp_1", "默认任务1", "GROUP", TrackLayerType.TRAJECTORY,
                              ref_id="grp_fly_pair", is_group=True, name="双机群组轨迹", start_ms=0, duration_ms=5000)
    clip_adapter.save_clip(c_grp)

    # 2. 拖入真实动作 (G1_太极抱拳式)
    c_act = TimelineClipAsset("c_act_kungfu", "默认任务1", "1", TrackLayerType.ACTION,
                              ref_id="act_g1_kungfu", name="G1_太极抱拳", start_ms=500, duration_ms=4000)
    clip_adapter.save_clip(c_act)

    # 3. 预演编译与冲突检测
    schedule = StagePreviewEngine.build_preview_tracks(store, "默认任务1")
    assert "Robot_1" in schedule["robot_tracks"]
    assert schedule["clip_count"] == 3
    assert schedule["is_valid"] is True

    # 4. 模拟时间冲突注入：在同一机器人重叠时间内插入第二段轨迹
    c_conflict = TimelineClipAsset("c_conf", "默认任务1", "1", TrackLayerType.TRAJECTORY,
                                   ref_id="base_s_curve", name="冲突轨迹", start_ms=2000, duration_ms=3000)
    clip_adapter.save_clip(c_conflict)
    sched_conflict = StagePreviewEngine.build_preview_tracks(store, "默认任务1")
    assert any("时空重叠冲突" in err for err in sched_conflict["validation_errors"])
    clip_adapter.delete_clip("c_conf")

    # 5. 60Hz 播放器推进与协调器时空快照一致性
    coordinator = StagePreviewCoordinator()
    coordinator.set_robot_tracks(schedule["robot_tracks"])

    player = VirtualShowPlayer()
    player.set_duration_ms(schedule["duration_ms"])
    player.set_loop(False)

    # 首帧静态采样 (t = 0)
    poses_t0 = coordinator.sample_at_time(0)
    assert "Robot_1" in poses_t0
    p1_0 = poses_t0["Robot_1"]
    assert p1_0.pose_status == "STAND_FALLBACK"

    # 播放至动作活跃时间段 (t = 1500ms -> 1.5s)
    poses_t15 = coordinator.sample_at_time(1500)
    p1_15 = poses_t15["Robot_1"]
    assert p1_15.pose_status == "NORMAL"
    assert p1_15.keyframe_positions is not None
    assert "pelvis" in p1_15.keyframe_positions

    # 越界钳位采样 (t = 99999ms)
    poses_end = coordinator.sample_at_time(99999)
    assert poses_end["Robot_1"].x > 0.0  # 停在最后坐标，禁止瞬移回 0
    player.cleanup()
