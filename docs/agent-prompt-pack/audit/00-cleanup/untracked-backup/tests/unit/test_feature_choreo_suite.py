"""
@file: tests/unit/test_feature_choreo_suite.py
@brief: 编排端到端垂直增量功能套件（轨迹、阵型、素材、时间轴、3D编译与群组安全）
@exports: test_01_trajectory_compile_and_anchor, test_02_formation_geometry_and_members, test_03_asset_registry_full_catalog, test_04_timeline_lrmp_compilation, test_05_stage_preview_engine_tracks, test_06_group_trajectory_safety_pipeline
"""
import pytest
from src.core.asset_registry import asset_registry
from src.core.formation_calc import FormationCalculator
from src.core.lrmp_compiler import lrmp_compiler
from src.core.models import ControlPoint, FormationModel, TrajectoryModel
from src.domain.trajectory.trajectory_compiler import TrajectoryCompiler
from src.domain.trajectory.group_trajectory import GroupTrajectory, GroupTrajectoryMember
from src.domain.trajectory.group_trajectory_compiler import GroupTrajectoryCompiler
from src.domain.trajectory.group_trajectory_safety import GroupTrajectorySafetyValidator
from src.application.stage_director.stage_preview_engine import StagePreviewEngine
from src.infrastructure.storage.choreo_sqlite_store import ChoreoSqliteStore


def test_01_trajectory_compile_and_anchor():
    """验证 2D 轨迹样条编译与弧长插值全流程。"""
    wps = [(0.0, 0.0), (2.0, 1.0), (4.0, 0.0)]
    pts, dur = TrajectoryCompiler.compile_waypoints(
        wps, mode="uniform", max_acc=1.5, v_max=1.0, end_turn=True, end_turn_yaw=0.0
    )
    assert len(pts) > 10
    assert dur > 0.0
    assert pts[0][0] == 0.0
    assert abs(pts[-1][1] - 4.0) < 0.2


def test_02_formation_geometry_and_members():
    """验证四类阵型几何计算与成员坐标展开。"""
    r_ids = ["A", "B", "C", "D"]
    # 1. 横排 (row)
    line_members = FormationCalculator.calculate_offsets("row", r_ids, spacing=1.2)
    assert len(line_members) == 4
    assert line_members[0]["robot_id"] == "A"
    # 2. 间距安全校验
    is_safe, warnings = FormationCalculator.check_safety_distances(line_members, safe_distance=0.5)
    assert is_safe is True
    assert len(warnings) == 0


def test_03_asset_registry_full_catalog():
    """验证统一素材中心真实目录：舞蹈、基础动作与本地持久化素材。"""
    asset_registry.reload()
    dances = asset_registry.get_dances()
    actions = asset_registry.get_actions()
    assert len(dances) == 33
    assert len(actions) == 11
    # 检索能力
    act_stand = asset_registry.get_asset("act_STAND")
    assert act_stand is not None
    assert act_stand["alias"] == "STAND"


def test_04_timeline_lrmp_compilation(tmp_path):
    """验证时间轴动作块到 LRMP 指令帧的序列化编译。"""
    tracks = [{"track_id": 1, "robot_id": 1, "lora_id": "A"}]
    clips = [
        {"clip_id": "c1", "robot_id": 1, "layer": "active", "name": "STAND", "start_time": 0.0, "duration": 2.0, "cmd": "STAND"},
        {"clip_id": "c2", "robot_id": 1, "layer": "trajectory", "name": "traj_01", "start_time": 2.0, "duration": 3.0, "cmd": "traj_01"},
    ]
    proj_path = lrmp_compiler.save_project("test_proj_01", "集成测试工程", tracks, clips)
    assert proj_path is not None


def test_05_stage_preview_engine_tracks():
    """验证 3D 虚拟预演编译引擎能够为所有机器人生成时空连续姿态。"""
    store = ChoreoSqliteStore()
    preview_data = StagePreviewEngine.build_preview_tracks(store)
    assert "robot_tracks" in preview_data
    assert "duration_ms" in preview_data
    assert "trajectory_lines" in preview_data


def test_06_group_trajectory_safety_pipeline():
    """验证多机群组轨迹 Frenet 局部展开至全局几何坐标并执行安全距离筛查。"""
    from src.domain.trajectory.trajectory_asset import TrajectoryAsset, TrajectoryPoint
    from src.domain.trajectory.group_trajectory_safety import validate_group_trajectory_safety

    ref_asset = TrajectoryAsset(
        trajectory_id="traj_ref_01",
        name="参考直线",
        control_points=[(0.0, 0.0), (5.0, 0.0)],
        sampled_points=[TrajectoryPoint(x_m=float(i), y_m=0.0, yaw_deg=0.0, s_m=float(i)) for i in range(6)],
        length_m=5.0,
    )
    group = GroupTrajectory(
        group_trajectory_id="grp_test_01",
        name="测试巡游组",
        reference_trajectory_id="traj_ref_01",
        members=(
            GroupTrajectoryMember(robot_id="A", offset_x_m=0.0, offset_y_m=-0.8),
            GroupTrajectoryMember(robot_id="B", offset_x_m=0.0, offset_y_m=0.8),
        ),
    )
    # 编译展开
    compiled = GroupTrajectoryCompiler.compile(group, ref_asset)
    assert len(compiled) == 2
    # 安全检测
    report = validate_group_trajectory_safety(compiled, required_clearance_m=0.6)
    assert report.is_safe is True
