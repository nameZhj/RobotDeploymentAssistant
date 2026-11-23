# @file: src/viewport3d/__init__.py
# @brief: Public exports for Unitree G1 29-DOF kinematics, STL caching, motion playback, and 3D OpenGL viewport.
# @exports: DanceMotionClip, DanceMotionPlayer, G1KinematicsChain, OrbitCamera, StageViewport3D, StlVboCache, get_g1_kinematics, procedural_gait_angles

from src.viewport3d.dance_motion_player import DanceMotionClip, DanceMotionPlayer, procedural_gait_angles
from src.viewport3d.g1_kinematics_chain import G1KinematicsChain, get_g1_kinematics
from src.viewport3d.orbit_camera import OrbitCamera
from src.viewport3d.stage_viewport_3d import StageViewport3D
from src.viewport3d.stl_vbo_cache import StlVboCache

__all__ = [
    "DanceMotionClip",
    "DanceMotionPlayer",
    "G1KinematicsChain",
    "OrbitCamera",
    "StageViewport3D",
    "StlVboCache",
    "get_g1_kinematics",
    "procedural_gait_angles",
]
