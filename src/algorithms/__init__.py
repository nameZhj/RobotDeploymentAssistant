# @file: src/algorithms/__init__.py
# @brief: Swarm formation, 2-opt assignment, potential-field solver, and timeline collision detection exports.
# @exports: generate_formation, assign_targets_2opt, count_path_crossings, generate_scatter_positions, PotentialFieldParams, SwarmSimulationResult, solve_swarm_potential_field, rdp_simplify, CollisionInterval, detect_timeline_collisions

from src.algorithms.formation_generators import generate_formation
from src.algorithms.potential_field_solver import (
    PotentialFieldParams,
    SwarmSimulationResult,
    compute_segment_times,
    rdp_simplify,
    solve_swarm_potential_field,
)
from src.algorithms.scatter_stage import CROSSING_THRESHOLD, generate_scatter_positions
from src.algorithms.spatial_hash_grid import SpatialHashGrid
from src.algorithms.target_assignment import assign_targets_2opt, count_path_crossings
from src.algorithms.timeline_collision_worker import CollisionInterval, detect_timeline_collisions

__all__ = [
    "generate_formation",
    "assign_targets_2opt",
    "count_path_crossings",
    "CROSSING_THRESHOLD",
    "generate_scatter_positions",
    "SpatialHashGrid",
    "PotentialFieldParams",
    "SwarmSimulationResult",
    "rdp_simplify",
    "compute_segment_times",
    "solve_swarm_potential_field",
    "CollisionInterval",
    "detect_timeline_collisions",
]
