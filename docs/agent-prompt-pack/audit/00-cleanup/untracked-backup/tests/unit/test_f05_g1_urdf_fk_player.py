"""
@file: tests/unit/test_f05_g1_urdf_fk_player.py
@brief: Plan F-05 G1 真实 URDF、STL 网格 LOD 加载与 60Hz 走位舞蹈正向运动学播放器测试
@exports: test_g1_urdf_and_stl_loading, test_fk_orthogonality_and_blending, test_virtual_show_player
"""
import math
import os
import numpy as np
import pytest
from src.domain.kinematics.g1_urdf_mesh_loader import G1UrdfMeshLoader
from src.domain.kinematics.g1_fk_motion_blender import G1ForwardKinematics, G1MotionBlender
from src.application.virtual_show_player import VirtualShowPlayer


def test_g1_urdf_and_stl_loading():
    links, joints = G1UrdfMeshLoader.parse_urdf()
    assert len(links) >= 30
    assert len(joints) >= 30
    assert "pelvis" in links
    assert "left_knee_joint" in joints
    assert joints["left_knee_joint"].child == "left_knee_link"

    stl_path = "assets/models/g1_description/g1_description/meshes/pelvis.stl"
    assert os.path.exists(stl_path)
    verts_pro, norms_pro = G1UrdfMeshLoader.parse_stl_file(stl_path, lod_mode="PRO")
    assert verts_pro.ndim == 3 and verts_pro.shape[1] == 3 and verts_pro.shape[2] == 3
    assert len(verts_pro) > 1000

    verts_eco, _ = G1UrdfMeshLoader.parse_stl_file(stl_path, lod_mode="ECO")
    assert len(verts_eco) < len(verts_pro)

    cache_dir = os.path.join(".agent_workspace", "cache_test")
    meshes = G1UrdfMeshLoader.load_all_meshes(lod_mode="ECO", cache_dir=cache_dir, max_files=3)
    assert len(meshes) >= 1
    meshes_cached = G1UrdfMeshLoader.load_all_meshes(lod_mode="ECO", cache_dir=cache_dir, max_files=3)
    assert len(meshes_cached) == len(meshes)


def test_fk_orthogonality_and_blending():
    fk = G1ForwardKinematics()
    matrices = fk.compute_fk(
        world_pos=(1.0, 2.0, 0.75),
        yaw_deg=45.0,
        joint_angles={"left_knee_joint": 0.5, "left_hip_pitch_joint": -0.3}
    )
    assert "pelvis" in matrices
    assert "left_knee_link" in matrices

    for link_name in ["pelvis", "torso_link", "left_knee_link"]:
        mat = matrices[link_name]
        rot = mat[:3, :3]
        identity = rot @ rot.T
        assert np.allclose(identity, np.eye(3), atol=1e-3)
        assert abs(float(np.linalg.det(rot)) - 1.0) < 1e-3

    blender = G1MotionBlender()
    walk_q, z_off = blender.generate_walk_gait(t_sec=0.25, v=1.0)
    assert abs(walk_q["left_hip_pitch_joint"]) > 0.01
    assert z_off <= 0.0

    popping_q = blender.generate_dance_angles("POPPING", local_t=0.2)
    assert "left_shoulder_pitch_joint" in popping_q
    assert "waist_yaw_joint" in popping_q

    ballet_q = blender.generate_dance_angles("芭蕾", local_t=0.2)
    assert ballet_q["left_shoulder_pitch_joint"] < -0.5

    init_pts = [{"robot_id": 1, "x": 0.0, "y": 0.0, "yaw": 0.0}]
    track_state = [
        {"robot_id": 1, "no": 101, "type": "trajectory", "start_time": 0.0, "end_time": 4.0, "ignored": 0},
        {"robot_id": 1, "name": "芭蕾", "type": "active", "start_time": 1.0, "end_time": 3.0, "ignored": 0}
    ]
    traj_map = {101: "0.00,0.0000,0.0000,0.00\n4.00,4.0000,0.0000,0.00"}

    state_walk_and_dance = blender.sample_robot_full_state(1, t_sec=2.0, init_points=init_pts, track_state=track_state, traj_map=traj_map)
    assert state_walk_and_dance["is_moving"] is True
    assert state_walk_and_dance["active_action"] == "芭蕾"
    assert "left_hip_pitch_joint" in state_walk_and_dance["joint_angles"]
    assert "left_shoulder_roll_joint" in state_walk_and_dance["joint_angles"]


def test_virtual_show_player():
    player = VirtualShowPlayer()
    init_pts = [
        {"robot_id": 1, "x": 0.0, "y": 0.0, "yaw": 0.0},
        {"robot_id": 2, "x": 2.0, "y": 2.0, "yaw": 90.0}
    ]
    track_state = [
        {"robot_id": 1, "no": 101, "type": "trajectory", "start_time": 0.0, "end_time": 5.0, "ignored": 0},
        {"robot_id": 2, "name": "POPPING", "type": "active", "start_time": 0.0, "end_time": 4.0, "ignored": 0}
    ]
    traj_map = {101: "0.00,0.0000,0.0000,0.00\n5.00,5.0000,0.0000,0.00"}

    player.load_scene(init_pts, track_state, traj_map, duration_ms=6000)
    assert player.get_current_time_ms() == 0

    ticks = []
    player.add_tick_listener(lambda t, s: ticks.append(t))

    player.play()
    assert player.is_playing() is True

    player.set_speed(2.0)
    assert player.get_speed() == 2.0

    st1 = player.step(100)
    assert player.get_current_time_ms() == 100
    assert 1 in st1 and 2 in st1
    assert len(ticks) == 1

    st_seek = player.seek(2500)
    assert player.get_current_time_ms() == 2500
    assert st_seek[1]["world_pos"][0] > 1.0
    assert st_seek[2]["active_action"] == "POPPING"

    player.pause()
    assert player.is_playing() is False

    player.stop()
    assert player.get_current_time_ms() == 0

