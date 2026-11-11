"""
@file: tests/unit/test_step06_g1_stl_and_fk.py
@brief: Step 06 G1 真实 URDF 解析、165个STL网格双档LOD缓存与60Hz正向运动学单元测试
@exports: test_urdf_and_stl_cache_generation, test_fk_rodrigues_and_orthogonality, test_performance_sampler_walk_and_dance, test_virtual_show_player_60hz
"""
import os
from pathlib import Path
import numpy as np
import pytest
from src.domain.kinematics.g1_stl_mesh_cache import G1StlMeshCache, parse_stl_file
from src.domain.kinematics.g1_urdf_mesh_loader import G1UrdfMeshLoader
from src.domain.kinematics.urdf_fk_solver import ForwardKinematicsSolver, solve_full_body_fk
from src.domain.kinematics.performance_sampler import StagePerformanceSampler
from src.application.virtual_show_player import VirtualShowPlayer


def test_urdf_and_stl_cache_generation() -> None:
    urdf_23 = "assets/models/g1_description/g1_description/g1_23dof.urdf"
    urdf_29 = "assets/models/g1_description/g1_description/g1_29dof.urdf"
    assert os.path.exists(urdf_23) and os.path.exists(urdf_29)

    links, joints = G1UrdfMeshLoader.parse_urdf(urdf_23)
    assert len(links) >= 30 and len(joints) >= 30
    assert "pelvis" in links and "torso_link" in links
    assert "left_knee_joint" in joints and joints["left_knee_joint"].child == "left_knee_link"

    mesh_dir = "assets/models/g1_description/g1_description/meshes"
    stl_files = list(Path(mesh_dir).glob("*.stl"))
    assert len(stl_files) == 165

    pelvis_stl = os.path.join(mesh_dir, "pelvis.stl")
    assert os.path.exists(pelvis_stl)
    v_pro, n_pro = parse_stl_file(pelvis_stl, lod_mode="PRO")
    assert v_pro.ndim == 3 and v_pro.shape[1:] == (3, 3)
    assert len(v_pro) > 500

    v_eco, n_eco = parse_stl_file(pelvis_stl, lod_mode="ECO")
    assert len(v_eco) <= 120
    assert len(v_eco) < len(v_pro)

    cache_dir = os.path.join(".agent_workspace", "cache_lod_test")
    cache = G1StlMeshCache.load_all_meshes(mesh_dir=mesh_dir, lod_mode="ECO", cache_dir=cache_dir, max_files=5)
    assert len(cache) >= 5
    for stem, (verts, norms) in cache.items():
        assert len(verts) <= 120


def test_fk_rodrigues_and_orthogonality() -> None:
    solver = ForwardKinematicsSolver()
    q_dict = {
        "left_hip_pitch_joint": -0.35, "left_knee_joint": 0.70,
        "right_hip_pitch_joint": 0.35, "right_knee_joint": 0.0,
        "waist_yaw_joint": 0.20, "left_shoulder_pitch_joint": -0.50
    }
    res = solver.solve_full_body_fk(base_xyz=(2.0, 3.0, 0.75), base_yaw=30.0, joint_angles_dict=q_dict)
    matrices = res["link_world_matrices"]
    coords = res["joint_coords"]

    assert "pelvis" in matrices
    assert "torso_link" in matrices
    assert "left_knee_link" in matrices
    assert "left_knee_joint" in coords

    pelvis_mat = matrices["pelvis"]
    assert np.allclose(pelvis_mat[:3, 3], np.array([2.0, 3.0, 0.75], dtype=np.float32), atol=1e-3)

    for link_name in ["pelvis", "torso_link", "left_hip_pitch_link", "left_knee_link"]:
        mat = matrices[link_name]
        rot = mat[:3, :3]
        assert np.allclose(rot @ rot.T, np.eye(3), atol=1e-3)
        assert abs(float(np.linalg.det(rot)) - 1.0) < 1e-3

    standalone_res = solve_full_body_fk(base_xyz=(0.0, 0.0, 0.75), base_yaw=0.0, joint_angles_dict={})
    assert "pelvis" in standalone_res["link_world_matrices"]


def test_performance_sampler_walk_and_dance() -> None:
    sampler = StagePerformanceSampler()

    walk_q, z_off = sampler.generate_walk_gait(t_sec=0.25, v=1.2, omega=0.0)
    assert abs(walk_q["left_hip_pitch_joint"]) > 0.05
    assert "left_knee_joint" in walk_q
    assert z_off <= 0.0

    dances = ["POPPING1", "POPPING2", "POPPING3", "芭蕾", "查尔斯顿舞2", "螳螂拳", "爱情鸟", "G1_DANCE_01"]
    for d in dances:
        dq = sampler.generate_dance_angles(d, local_t=0.5)
        assert len(dq) >= 2

    init_pts = [{"robot_id": 1, "x": 0.0, "y": 0.0, "yaw": 0.0}]
    track_state = [
        {"robot_id": 1, "no": 100001, "type": "trajectory", "start_time": 0.0, "end_time": 5.0, "ignored": 0},
        {"robot_id": 1, "name": "螳螂拳", "type": "active", "start_time": 2.0, "end_time": 4.0, "ignored": 0}
    ]
    traj_map = {100001: "0.00,0.0000,0.0000,0.00\n5.00,5.0000,0.0000,0.00"}

    st_walk_and_dance = sampler.sample_robot_full_state(
        robot_id=1, t_sec=3.0, init_points=init_pts, track_state=track_state, traj_map=traj_map
    )
    assert st_walk_and_dance["is_moving"] is True
    assert st_walk_and_dance["active_action"] == "螳螂拳"
    q = st_walk_and_dance["joint_angles"]
    assert "left_hip_pitch_joint" in q
    assert "right_shoulder_pitch_joint" in q
    assert len(st_walk_and_dance["link_matrices"]) >= 20


def test_virtual_show_player_60hz() -> None:
    player = VirtualShowPlayer()
    init_pts = [
        {"robot_id": 1, "x": 0.0, "y": 0.0, "yaw": 0.0},
        {"robot_id": 2, "x": 3.0, "y": 3.0, "yaw": 90.0}
    ]
    track_state = [
        {"robot_id": 1, "no": 100001, "type": "trajectory", "start_time": 0.0, "end_time": 4.0, "ignored": 0},
        {"robot_id": 2, "name": "爱情鸟", "type": "active", "start_time": 1.0, "end_time": 3.0, "ignored": 0}
    ]
    traj_map = {100001: "0.00,0.0000,0.0000,0.00\n4.00,4.0000,0.0000,0.00"}

    player.load_scene(init_pts, track_state, traj_map, duration_ms=5000)
    assert player.get_current_time_ms() == 0

    ticks = []
    player.add_tick_listener(lambda t, s: ticks.append(t))

    player.play()
    assert player.is_playing() is True

    player.set_speed(1.5)
    assert player.get_speed() == 1.5

    st_step = player.step(16)  # 60Hz step
    assert player.get_current_time_ms() == 16
    assert 1 in st_step and 2 in st_step
    assert len(ticks) == 1

    st_seek = player.seek(2000)
    assert player.get_current_time_ms() == 2000
    assert st_seek[1]["world_pos"][0] > 1.0
    assert st_seek[2]["active_action"] == "爱情鸟"

    player.pause()
    assert player.is_playing() is False
    player.stop()
    assert player.get_current_time_ms() == 0

