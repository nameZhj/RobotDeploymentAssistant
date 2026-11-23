# @file: tests/test_phase4_math_algorithms.py
# @brief: Tests for Phase 4 Catmull-Rom 2000-sample arc table, S-curve, 2-opt, potential-field solver & collision worker.
# @exports: test_arc_length_and_scurve_50fps, test_2opt_assignment_and_formations, test_potential_field_8_robots_collision_free, test_timeline_collision_worker

from __future__ import annotations

import math

from src.algorithms import (
    PotentialFieldParams,
    assign_targets_2opt,
    count_path_crossings,
    detect_timeline_collisions,
    generate_formation,
    generate_scatter_positions,
    solve_swarm_potential_field,
)
from src.domain.timeline_entities import TimelineBlockEntity
from src.domain.track_entities import TrackEntity
from src.domain.trajectory_entities import ControlPoint2D, TrajectoryEntity
from src.math import (
    compute_min_execution_time,
    evaluate_trajectory_pose,
    sample_spline_equal_distance_2d,
    sample_trajectory_50fps,
)


def test_arc_length_and_scurve_50fps() -> None:
    pts = [(0.0, 0.0), (1.0, 2.0), (3.0, 2.0), (4.0, 0.0)]
    eq = sample_spline_equal_distance_2d(pts, samples=101)
    assert len(eq) == 101
    steps = [math.hypot(eq[i][0] - eq[i - 1][0], eq[i][1] - eq[i - 1][1]) for i in range(1, len(eq))]
    assert max(steps) - min(steps) < 5e-3

    traj = TrajectoryEntity(
        id=1,
        name="Curve",
        duration=4.0,
        control_points=[ControlPoint2D(x, y) for x, y in pts],
        end_turn=True,
        end_yaw=1.57,
    )
    arr, metrics = sample_trajectory_50fps(traj, fps=50)
    assert metrics.sample_count >= 200
    assert round(compute_min_execution_time(metrics.arc_length, 1.5, 3.0), 3) == metrics.min_execution_time
    pose_end = evaluate_trajectory_pose(arr, 4.0)
    assert abs(pose_end[2] - 1.57) < 0.02


def test_2opt_assignment_and_formations() -> None:
    starts = generate_formation("line", 6, spacing=1.0, center=(0.0, -2.0))
    goals = list(reversed(generate_formation("wedge", 6, spacing=1.0, center=(0.0, 2.0))))
    assign = assign_targets_2opt(starts, goals)
    assert len(set(assign)) == 6
    assert count_path_crossings(starts, goals, assign) == 0
    scatter = generate_scatter_positions(10)
    assert len(scatter) == 10


def test_potential_field_8_robots_collision_free() -> None:
    # 8 robots arranged on a circle swapping to exact opposite antipodal points (worst-case head-on crossing)
    starts = generate_formation("circle", 8, radius=3.0)
    targets = [(-x, -y) for x, y in starts]
    forced_antipodal = list(range(8))
    res = solve_swarm_potential_field(
        starts,
        targets,
        assignment=forced_antipodal,
        params=PotentialFieldParams(safety_dist=0.60, rdp_epsilon=0.03),
    )
    assert res.min_distance >= 0.58
    assert len(res.simplified_knots) == 8
    for i in range(8):
        end_pt = res.raw_paths[i][-1]
        assert math.hypot(end_pt[0] - targets[i][0], end_pt[1] - targets[i][1]) < 0.05


def test_timeline_collision_worker() -> None:
    t1 = TrackEntity(id=1, track_no=1, name="G1-01")
    t2 = TrackEntity(id=2, track_no=2, name="G1-02")
    tr1 = TrajectoryEntity(
        id=10,
        duration=4.0,
        interpolation_mode="linear",
        control_points=[ControlPoint2D(-2.0, 0.0), ControlPoint2D(2.0, 0.0)],
    )
    tr2 = TrajectoryEntity(
        id=11,
        duration=4.0,
        interpolation_mode="linear",
        control_points=[ControlPoint2D(2.0, 0.0), ControlPoint2D(-2.0, 0.0)],
    )
    blocks = [
        TimelineBlockEntity(id=1, task_id=1, track_id=1, block_type="trajectory", ref_id=10, start_time=0.0, duration=4.0),
        TimelineBlockEntity(id=2, task_id=1, track_id=2, block_type="trajectory", ref_id=11, start_time=0.0, duration=4.0),
    ]
    intervals = detect_timeline_collisions([t1, t2], blocks, {10: tr1, 11: tr2}, safety_dist=0.60)
    assert len(intervals) >= 1
    assert any(iv.start < 2.1 and iv.end > 1.9 and iv.min_dist < 0.2 for iv in intervals)
