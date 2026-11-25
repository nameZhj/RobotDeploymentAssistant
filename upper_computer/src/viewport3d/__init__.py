# @file: src/viewport3d/__init__.py
# @brief: Public exports for G1 29-DOF kinematics, STL/VBO cache, studio shader, live motion & 3D viewport.
# @exports: DanceMotionClip, DanceMotionPlayer, G1KinematicsChain, G1StudioShader, LiveMotionController, OrbitCamera, StageViewport3D, StlGpuVboPool, StlVboCache, get_g1_kinematics, procedural_gait_angles

from src.viewport3d.dance_motion_player import DanceMotionClip, DanceMotionPlayer, procedural_gait_angles
from src.viewport3d.g1_kinematics_chain import G1KinematicsChain, get_g1_kinematics
from src.viewport3d.g1_studio_shader import G1StudioShader
from src.viewport3d.live_motion_controller import LiveMotionController
from src.viewport3d.orbit_camera import OrbitCamera
from src.viewport3d.stage_viewport_3d import StageViewport3D
from src.viewport3d.stl_vbo_cache import StlGpuVboPool, StlVboCache

__all__ = [
    "DanceMotionClip",
    "DanceMotionPlayer",
    "G1KinematicsChain",
    "G1StudioShader",
    "LiveMotionController",
    "OrbitCamera",
    "StageViewport3D",
    "StlGpuVboPool",
    "StlVboCache",
    "get_g1_kinematics",
    "procedural_gait_angles",
]
