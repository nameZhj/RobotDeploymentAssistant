"""
@file: tests/unit/test_f04_trajectory_and_anchor.py
@brief: 轨迹点解析、平滑插值、草图笔与起点锚定定律单元测试
@exports: test_trajectory_parse_and_interpolation, test_sketch_manager, test_anchor_law_full_chain
"""
import pytest
from src.domain.trajectory.anchor_pose_resolver import AnchorPoseResolver, sample_robot_world_pose_at
from src.domain.trajectory.trajectory_compiler import StageSketchManager, TrajectoryCompiler


def test_trajectory_parse_and_interpolation() -> None:
    raw_str = (
        "0.0,0.0,0.0,0.0\n"
        "1.5,2.0,1.0,30.0\n"
        "3.0,4.0,2.0,60.0"
    )
    parsed = TrajectoryCompiler.parse_trajectory_data(raw_str)
    assert len(parsed) == 3
    assert parsed[1] == (1.5, 2.0, 1.0, 30.0)

    serialized = TrajectoryCompiler.serialize_trajectory_data(parsed)
    assert "1.50,2.0000,1.0000,30.00" in serialized

    # 测试 uniform 与 linear 样条插值
    wps = [(0.0, 0.0), (2.0, 1.0), (4.0, 0.0), (6.0, 2.0)]
    pts_uniform, dur_uniform = TrajectoryCompiler.compile_waypoints(
        wps, mode="uniform", max_acc=1.5, v_max=1.2, end_turn=True, end_turn_yaw=90.0
    )
    assert len(pts_uniform) > len(wps)
    assert dur_uniform > 0.0
    assert abs(pts_uniform[-1][3] - 90.0) < 1e-2

    pts_linear, dur_linear = TrajectoryCompiler.compile_waypoints(
        wps, mode="linear", hold_direction=True, hold_direction_yaw=180.0
    )
    assert len(pts_linear) > len(wps)
    for p in pts_linear:
        assert abs(p[3] - 180.0) < 1e-4

    # 测试轨迹反转
    rev_str = TrajectoryCompiler.reverse_trajectory(raw_str)
    rev_pts = TrajectoryCompiler.parse_trajectory_data(rev_str)
    assert len(rev_pts) == 3
    assert abs(rev_pts[0][1] - 4.0) < 1e-4
    assert abs(rev_pts[-1][1] - 0.0) < 1e-4


def test_sketch_manager() -> None:
    mgr = StageSketchManager()
    mgr.begin_stroke()
    mgr.add_point(0.0, 0.0)
    mgr.add_point(1.0, 2.0)
    mgr.add_point(3.0, 4.0)
    mgr.end_stroke()

    assert len(mgr.get_all_strokes()) == 1
    assert len(mgr.get_all_strokes()[0]) == 3

    mgr.add_stroke([(10.0, 10.0), (12.0, 12.0)])
    assert len(mgr.get_all_strokes()) == 2

    # 单步撤销 (Ctrl+Z)
    popped = mgr.undo_stroke()
    assert popped is not None
    assert len(mgr.get_all_strokes()) == 1

    # 清空草图
    mgr.clear_sketches()
    assert len(mgr.get_all_strokes()) == 0


def test_anchor_law_full_chain() -> None:
    # 1. 初始点：1号机位于 (-3.0, 1.0, 0度)
    init_pts = [{"robot_id": 1, "x": -3.0, "y": 1.0, "yaw": 0.0}]

    # 2. 轨迹 100001: 从 (-3, 1, 0) 走位到 (2.0, 4.0, 45度)，耗时 4.0 秒
    t1_data = (
        "0.0,-3.0,1.0,0.0\n"
        "2.0,-0.5,2.5,22.5\n"
        "4.0,2.0,4.0,45.0"
    )
    # 轨迹 100002: 从 (2.0, 4.0, 45) 走位到 (5.0, 4.0, 90度)，耗时 3.0 秒
    t2_data = (
        "0.0,2.0,4.0,45.0\n"
        "1.5,3.5,4.0,67.5\n"
        "3.0,5.0,4.0,90.0"
    )
    traj_map = {100001: t1_data, 100002: t2_data}

    # 3. 时间轴排布：
    # [0.0 ~ 4.0]: 轨迹块 100001
    # [4.0 ~ 9.0]: 原地街舞动作块 (active) 550001
    # [9.0 ~ 12.0]: 轨迹块 100002
    track_state = [
        {"block_id": "b1", "robot_id": 1, "type": "trajectory", "no": 100001, "start_time": 0.0, "end_time": 4.0, "ignored": 0},
        {"block_id": "b2", "robot_id": 1, "type": "active", "no": 550001, "start_time": 4.0, "end_time": 9.0, "ignored": 0},
        {"block_id": "b3", "robot_id": 1, "type": "trajectory", "no": 100002, "start_time": 9.0, "end_time": 12.0, "ignored": 0}
    ]

    # A. t = -1.0 (开场前)：锚定在 init_points
    p_pre = sample_robot_world_pose_at(1, -1.0, init_pts, track_state, traj_map)
    assert p_pre["is_moving"] is False
    assert abs(p_pre["x"] - (-3.0)) < 1e-3
    assert abs(p_pre["y"] - 1.0) < 1e-3

    # B. t = 2.0 (轨迹1运动中)：插值位姿处于中点 (-0.5, 2.5)
    p_mid1 = sample_robot_world_pose_at(1, 2.0, init_pts, track_state, traj_map)
    assert p_mid1["is_moving"] is True
    assert p_mid1["active_traj_no"] == 100001
    assert abs(p_mid1["x"] - (-0.5)) < 1e-3
    assert abs(p_mid1["y"] - 2.5) < 1e-3

    # C. t = 6.5 (处于原地跳舞 active 块中)：
    # 严格检验锚定定律：尽管正在跳舞，但位置必须静止在前序轨迹1终点 (2.0, 4.0, 45度)！
    p_dance = sample_robot_world_pose_at(1, 6.5, init_pts, track_state, traj_map)
    assert p_dance["is_moving"] is False
    assert p_dance["active_traj_no"] is None
    assert abs(p_dance["x"] - 2.0) < 1e-3
    assert abs(p_dance["y"] - 4.0) < 1e-3
    assert abs(p_dance["yaw"] - 45.0) < 1e-3

    # D. t = 9.0 (轨迹2起点时刻)：锚点依然精确对齐在轨迹1终点 (2.0, 4.0, 45度)
    anchor_at_t9 = AnchorPoseResolver.resolve_anchor_pose(1, 9.0, init_pts, track_state, traj_map)
    assert abs(anchor_at_t9[0] - 2.0) < 1e-3
    assert abs(anchor_at_t9[1] - 4.0) < 1e-3
    assert abs(anchor_at_t9[2] - 45.0) < 1e-3

    # E. t = 10.5 (轨迹2运动中)：插值到中点 (3.5, 4.0)
    p_mid2 = sample_robot_world_pose_at(1, 10.5, init_pts, track_state, traj_map)
    assert p_mid2["is_moving"] is True
    assert p_mid2["active_traj_no"] == 100002
    assert abs(p_mid2["x"] - 3.5) < 1e-3
    assert abs(p_mid2["y"] - 4.0) < 1e-3

    # F. t = 15.0 (演播结束)：最终静止在轨迹2终点 (5.0, 4.0, 90度)
    p_end = sample_robot_world_pose_at(1, 15.0, init_pts, track_state, traj_map)
    assert p_end["is_moving"] is False
    assert abs(p_end["x"] - 5.0) < 1e-3
    assert abs(p_end["y"] - 4.0) < 1e-3
    assert abs(p_end["yaw"] - 90.0) < 1e-3

