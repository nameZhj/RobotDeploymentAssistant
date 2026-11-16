# @file: src/math/__init__.py
# @brief: Mathematical kernels for 2D/3D splines, arc-length lookup, S-curve timing, and 50 FPS sampling.
# @exports: catmull_rom_point_2d, build_arc_length_table_2d, sample_spline_equal_distance_2d, compute_min_execution_time, build_smooth_profile, sample_trajectory_50fps, evaluate_trajectory_pose

from src.math.catmull_rom_spline import (
    ArcLengthTable,
    build_arc_length_table_2d,
    catmull_rom_derivative_2d,
    catmull_rom_point_2d,
    catmull_rom_point_3d,
    sample_spline_equal_distance_2d,
    u_from_s,
)
from src.math.s_curve_profile import SmoothProfile, build_smooth_profile, compute_min_execution_time
from src.math.trajectory_sampler import TrajectoryMetrics, evaluate_trajectory_pose, sample_trajectory_50fps
from src.math.vec_math import compute_polyline_length, interpolate_angle, normalize_angle, segments_intersect

__all__ = [
    "ArcLengthTable",
    "catmull_rom_point_2d",
    "catmull_rom_derivative_2d",
    "catmull_rom_point_3d",
    "build_arc_length_table_2d",
    "u_from_s",
    "sample_spline_equal_distance_2d",
    "SmoothProfile",
    "compute_min_execution_time",
    "build_smooth_profile",
    "TrajectoryMetrics",
    "sample_trajectory_50fps",
    "evaluate_trajectory_pose",
    "compute_polyline_length",
    "interpolate_angle",
    "normalize_angle",
    "segments_intersect",
]
