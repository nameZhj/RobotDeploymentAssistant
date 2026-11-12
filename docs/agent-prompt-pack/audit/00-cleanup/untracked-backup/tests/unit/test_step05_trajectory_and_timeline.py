"""
@file: tests/unit/test_step05_trajectory_and_timeline.py
@brief: Step 05 轨迹编译器、起点锚定定律、双子层时间轴顺延与队形变换单元测试
@exports: test_anchor_pose_law, test_timeline_auto_shift_and_constraints, test_ugc_five_guardrails, test_formation_matrix_and_char_planner, test_timeline_range_io_and_undo_redo
"""
import numpy as np
import pytest
from src.domain.trajectory.spline_builder import SplineTrajectoryBuilder, resolve_anchor_pose
from src.domain.trajectory.ugc_guard_validator import UgcGuardValidator
from src.domain.trajectory.formation_matrix_planner import FormationMatrixPlanner
from src.domain.timeline.timeline_sequencer import TimelineBlock, TimelineSequencerEngine


def test_anchor_pose_law() -> None:
    init_pts = [
        {"robot_id": 1, "x": 1.0, "y": 2.0, "yaw": 10.0},
        {"robot_id": 2, "x": -5.0, "y": 3.0, "yaw": 180.0}
    ]
    traj_map = {
        100001: "0.00,1.0000,2.0000,10.00\n2.00,3.0000,4.0000,45.00",
        100002: "0.00,3.0000,4.0000,45.00\n3.00,6.0000,8.0000,90.00"
    }
    track_state = [
        {"robot_id": 1, "no": 100001, "type": "trajectory", "start_time": 0.0, "end_time": 2.0, "ignored": 0},
        {"robot_id": 1, "no": 550001, "type": "active", "start_time": 2.0, "end_time": 5.0, "ignored": 0},
        {"robot_id": 1, "no": 100002, "type": "trajectory", "start_time": 5.0, "end_time": 8.0, "ignored": 0}
    ]

    p_init = resolve_anchor_pose(robot_id=1, target_time_s=0.0, init_points=init_pts, track_state=[], traj_map=traj_map)
    assert p_init == (1.0, 2.0, 10.0)

    p_mid = resolve_anchor_pose(robot_id=1, target_time_s=4.0, init_points=init_pts, track_state=track_state, traj_map=traj_map)
    assert p_mid == (3.0, 4.0, 45.0)

    p_late = resolve_anchor_pose(robot_id=1, target_time_s=10.0, init_points=init_pts, track_state=track_state, traj_map=traj_map)
    assert p_late == (6.0, 8.0, 90.0)

    p2 = resolve_anchor_pose(robot_id=2, target_time_s=3.0, init_points=init_pts, track_state=track_state, traj_map=traj_map)
    assert p2 == (-5.0, 3.0, 180.0)


def test_timeline_auto_shift_and_constraints() -> None:
    engine = TimelineSequencerEngine()
    b1 = engine.insert_active_block(robot_id=1, no=550001, time=3.0, start_time=1.0, name="舞步1")
    b2 = engine.insert_active_block(robot_id=1, no=550002, time=3.0, start_time=4.0, name="舞步2")
    assert b1.start_time == 1.0 and b1.end_time == 4.0
    assert b2.start_time == 4.0 and b2.end_time == 7.0

    with pytest.raises(ValueError, match="不匹配"):
        engine.insert_trajectory_block(robot_id=1, group_bound_track_id=2, no=200001, time=2.0, start_time=3.0)

    traj = engine.insert_trajectory_block(robot_id=1, group_bound_track_id=1, no=100001, time=2.0, start_time=3.0, name="绿轨")
    assert traj.start_time == 3.0 and traj.end_time == 5.0
    b2_updated = next(b for b in engine.blocks if b.block_id == b2.block_id)
    assert b2_updated.start_time == 5.0 and b2_updated.end_time == 8.0

    b1.allow_move = False
    engine.validate_conflicts()
    assert b1.conflict is True
    assert traj.conflict is True

    with pytest.raises(ValueError, match="禁止拉伸"):
        engine.stretch_block(b1.block_id, new_duration_s=5.0)


def test_ugc_five_guardrails() -> None:
    ok1, _ = UgcGuardValidator.check_rule1_anchor(track_id=1, first_start=(0.0, 0.0), init_pos=(0.1, 0.0), tolerance=0.20)
    assert ok1 is True
    ok1_bad, msg1 = UgcGuardValidator.check_rule1_anchor(track_id=1, first_start=(0.0, 0.0), init_pos=(1.0, 1.0), tolerance=0.20)
    assert ok1_bad is False and "起点锚定失败" in msg1

    segs = [{"points": [(0.0, 0.0), (1.0, 0.0)]}, {"points": [(1.05, 0.0), (2.0, 0.0)]}]
    ok2, _ = UgcGuardValidator.check_rule2_continuity(track_id=1, segments=segs, tolerance=0.20)
    assert ok2 is True

    segs_broken = [{"points": [(0.0, 0.0), (1.0, 0.0)]}, {"points": [(1.5, 0.0), (2.0, 0.0)]}]
    ok2_bad, err2 = UgcGuardValidator.check_rule2_continuity(track_id=1, segments=segs_broken, tolerance=0.20)
    assert ok2_bad is False and err2["gap_m"] == 0.5

    grid = np.zeros((20, 20), dtype=np.uint8)
    grid[5, 5] = 100
    grid_info = {"origin_x": 0.0, "origin_y": 0.0, "resolution": 0.1}
    ok3, cols = UgcGuardValidator.check_rule3_wall_collision([(0.55, 0.55)], grid, grid_info)
    assert ok3 is False and len(cols) == 1

    ok4_bad, v_errs = UgcGuardValidator.check_rule4_kinematics([{"t": 1.0, "v": 2.5, "omega": 1.0}], max_v=2.0)
    assert ok4_bad is False and len(v_errs) == 1

    tracks_data = {
        1: [{"start_s": 0.0, "duration_s": 2.0, "sampled_points": [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}]}],
        2: [{"start_s": 0.0, "duration_s": 2.0, "sampled_points": [{"x": 0.3, "y": 0.0}, {"x": 1.2, "y": 0.0}]}]
    }
    alerts = UgcGuardValidator.check_rule5_swarm_collision(tracks_data, {1: (0.0, 0.0), 2: (0.3, 0.0)}, dt=0.05, safe_dist=0.65)
    assert len(alerts) > 0


def test_formation_matrix_and_char_planner() -> None:
    grid = FormationMatrixPlanner.generate_grid_formation(num_robots=16, rows=4, cols=4, spacing=1.2)
    assert len(grid) == 16
    assert grid[0][0] < grid[1][0]

    grid_144 = FormationMatrixPlanner.generate_grid_formation(num_robots=200, rows=12, cols=12)
    assert len(grid_144) == 144

    dots_single = FormationMatrixPlanner.extract_char_dot_matrix("G", mode="single", num_points=12)
    assert len(dots_single) == 12

    dots_seq = FormationMatrixPlanner.extract_char_dot_matrix("AB", mode="sequential", num_points=8)
    assert len(dots_seq) == 2 and len(dots_seq[0]) == 8

    dots_sim = FormationMatrixPlanner.extract_char_dot_matrix("AB", mode="simultaneous", num_points=8)
    assert len(dots_sim) == 16

    min_d = FormationMatrixPlanner.compute_min_pairwise_distance(dots_single)
    assert min_d > 0.0 and min_d != float("inf")

    mapping = FormationMatrixPlanner.assign_targets_optimal([(0.0, 0.0), (10.0, 0.0)], [(0.1, 0.0), (9.9, 0.0)])
    assert mapping[0] == 0 and mapping[1] == 1

    swapped = FormationMatrixPlanner.swap_robot_targets(mapping, 0, 1)
    assert swapped[0] == 1 and swapped[1] == 0


def test_timeline_range_io_and_undo_redo() -> None:
    engine = TimelineSequencerEngine()
    b1 = engine.insert_active_block(robot_id=1, no=550001, time=4.0, start_time=0.0, name="舞步A", allow_stretch=True)

    engine.move_block(b1.block_id, new_start_s=2.0)
    assert b1.start_time == 2.0
    engine.stretch_block(b1.block_id, new_duration_s=6.0)
    assert b1.time == 6.0 and b1.end_time == 8.0

    assert engine.undo() is True
    assert engine.blocks[0].time == 4.0
    assert engine.redo() is True
    assert engine.blocks[0].time == 6.0

    seq = engine.export_sequence_by_range(start_s=2.0, end_s=8.0, robot_ids=[1])
    assert len(seq) == 1 and seq[0]["start_time"] == 0.0

    added = engine.import_sequence_by_range(seq, target_start_s=10.0, target_robot_map={1: 2})
    assert len(added) == 1
    imp_blk = next(b for b in engine.blocks if b.block_id == added[0])
    assert imp_blk.robot_id == 2 and imp_blk.start_time == 10.0

    assert engine.save_fragment(5, "测试片段", [b1]) is True
    with pytest.raises(ValueError, match="01~99"):
        engine.save_fragment(105, "越界", [b1])
    frag = engine.load_fragment(5)
    assert frag["name"] == "测试片段"

    mb = engine.sec_to_measure_beat(4.5, bpm=120.0, numerator=4)
    assert mb == "003.2"
    sec = engine.measure_beat_to_sec("003.2", bpm=120.0, numerator=4)
    assert abs(sec - 4.5) < 0.01
