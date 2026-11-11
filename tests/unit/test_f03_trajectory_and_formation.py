"""
@file: tests/unit/test_f03_trajectory_and_formation.py
@brief: Plan F-03 轨迹编译、起点锚定定律与方阵字符队形规划器单元测试
@exports: test_trajectory_compiler_and_sketch, test_anchor_law_and_motion, test_formation_planner
"""
import math
import pytest
from src.domain.trajectory.trajectory_compiler import (
    TrajectoryCompiler,
    StageSketchManager,
    SketchStrokeManager,
    reverse_trajectory_points
)
from src.domain.trajectory.anchor_resolver import (
    AnchorResolver,
    resolve_anchor_pose_at,
    sample_robot_motion_at
)
from src.domain.trajectory.formation_matrix_planner import (
    FormationMatrixPlanner,
    formation_matrix_planner
)


def test_trajectory_compiler_and_sketch():
    data_str = "0.00,0.0000,0.0000,0.00\n1.00,1.0000,0.0000,0.00\n2.00,2.0000,0.0000,0.00"
    pts = TrajectoryCompiler.parse_trajectory_data(data_str)
    assert len(pts) == 3
    assert pts[-1][1] == 2.0

    reversed_data = reverse_trajectory_points(data_str)
    rev_pts = TrajectoryCompiler.parse_trajectory_data(reversed_data)
    assert len(rev_pts) == 3
    assert rev_pts[0][1] == 2.0
    assert rev_pts[-1][1] == 0.0

    wpts = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0)]
    compiled, dur = TrajectoryCompiler.compile_waypoints(
        wpts, mode="uniform", max_acc=1.5, v_max=1.0, end_turn=True, end_turn_yaw=90.0
    )
    assert len(compiled) > 10
    assert dur > 0.0
    assert abs(compiled[-1][3] - 90.0) < 5.0

    sketch = SketchStrokeManager()
    sketch.begin_stroke()
    sketch.add_point(1.0, 2.0)
    sketch.add_point(2.0, 3.0)
    sketch.end_stroke()
    assert len(sketch.get_all_strokes()) == 1

    sketch.add_stroke([(3.0, 4.0), (5.0, 6.0)])
    assert len(sketch.get_all_strokes()) == 2
    popped = sketch.undo_stroke()
    assert len(popped) == 2
    assert len(sketch.get_all_strokes()) == 1
    sketch.clear_sketches()
    assert len(sketch.get_all_strokes()) == 0


def test_anchor_law_and_motion():
    init_pts = [
        {"robot_id": 1, "x": 0.0, "y": 0.0, "yaw": 0.0},
        {"robot_id": 2, "x": 10.0, "y": 10.0, "yaw": 90.0}
    ]
    traj_map = {
        101: "0.00,0.0000,0.0000,0.00\n2.00,2.0000,0.0000,0.00",
        102: "0.00,2.0000,0.0000,0.00\n2.00,2.0000,3.0000,90.00"
    }
    track_state = [
        {"robot_id": 1, "no": 101, "type": "trajectory", "start_time": 0.0, "end_time": 2.0, "ignored": 0},
        {"robot_id": 1, "no": 999, "type": "active", "start_time": 2.0, "end_time": 4.0, "ignored": 0},
        {"robot_id": 1, "no": 102, "type": "trajectory", "start_time": 4.0, "end_time": 6.0, "ignored": 0}
    ]

    p_init = resolve_anchor_pose_at(robot_id=1, t_sec=0.0, init_points=init_pts, track_state=[], traj_dict_map=traj_map)
    assert p_init == (0.0, 0.0, 0.0)

    p_after_t1 = resolve_anchor_pose_at(robot_id=1, t_sec=3.0, init_points=init_pts, track_state=track_state, traj_dict_map=traj_map)
    assert p_after_t1 == (2.0, 0.0, 0.0)

    p_after_t2 = resolve_anchor_pose_at(robot_id=1, t_sec=7.0, init_points=init_pts, track_state=track_state, traj_dict_map=traj_map)
    assert p_after_t2 == (2.0, 3.0, 90.0)

    motion_still = sample_robot_motion_at(robot_id=1, t_sec=3.0, init_points=init_pts, track_state=track_state, traj_dict_map=traj_map)
    assert motion_still["is_moving"] is False
    assert motion_still["v"] == 0.0
    assert motion_still["x"] == 2.0

    motion_moving = sample_robot_motion_at(robot_id=1, t_sec=1.0, init_points=init_pts, track_state=track_state, traj_dict_map=traj_map)
    assert motion_moving["is_moving"] is True
    assert motion_moving["v"] > 0.0
    assert 0.0 < motion_moving["x"] < 2.0


def test_formation_planner():
    grid = FormationMatrixPlanner.generate_grid_formation(
        num_robots=9, rows=3, cols=3, spacing=1.5, center_x=1.0, center_y=2.0, heading_deg=45.0
    )
    assert len(grid) == 9
    assert grid[0][2] == 45.0
    min_d = FormationMatrixPlanner.compute_min_pairwise_distance(grid)
    assert abs(min_d - 1.5) < 1e-3

    single_dots = FormationMatrixPlanner.extract_char_dot_matrix(
        text="A", mode="single", font_size_m=3.0, num_points=12
    )
    assert len(single_dots) == 12

    seq_dots = FormationMatrixPlanner.extract_char_dot_matrix(
        text="AB", mode="sequential", font_size_m=3.0, num_points=8
    )
    assert len(seq_dots) == 2
    assert len(seq_dots[0]) == 8
    assert len(seq_dots[1]) == 8

    sim_dots = FormationMatrixPlanner.extract_char_dot_matrix(
        text="AB", mode="simultaneous", font_size_m=3.0, spacing_m=1.0, num_points=8
    )
    assert len(sim_dots) == 16

    starts = [(0.0, 0.0), (10.0, 10.0)]
    targets = [(10.2, 9.8), (0.1, 0.2)]
    mapping = FormationMatrixPlanner.assign_targets_greedy(starts, targets)
    assert mapping[0] == 1
    assert mapping[1] == 0

    swapped = FormationMatrixPlanner.swap_robot_targets(mapping, 0, 1)
    assert swapped[0] == 0
    assert swapped[1] == 1

    trans_trajs = FormationMatrixPlanner.generate_formation_transition_trajectories(
        current_poses=[(0.0, 0.0, 0.0), (1.0, 1.0, 0.0)],
        target_poses=[(2.0, 2.0, 90.0), (3.0, 3.0, 180.0)],
        max_acc=1.5,
        v_max=1.0
    )
    assert 0 in trans_trajs and 1 in trans_trajs
    assert len(trans_trajs[0]) > 5

    stages = FormationMatrixPlanner.plan_multi_word_sequence(
        text="HI",
        initial_poses=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0), (3.0, 0.0, 0.0)],
        font_size_m=4.0,
        dwell_time=2.0,
        max_acc=1.5,
        v_max=1.2,
        end_turn_yaw=90.0
    )
    assert len(stages) == 2
    assert stages[0]["char"] == "H"
    assert stages[1]["char"] == "I"
    assert stages[0]["duration"] > 0.0
    assert stages[0]["min_distance"] > 0.0
    assert len(stages[0]["trajectories"]) == 4

