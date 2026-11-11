"""
@file: tests/unit/test_f01_dance_bridge_and_store.py
@brief: 动态舞蹈桥接器与舞台编排 SQLite 持久化存储单元测试
@exports: test_dynamic_dance_bridge_sync, test_choreo_scene_store_flow, test_trajectory_rules_and_delete_guard
"""
import pytest
from src.application.choreo.dynamic_dance_bridge import DynamicDanceBridge
from src.infrastructure.storage.choreo_scene_store import ChoreoSceneStore


def test_dynamic_dance_bridge_sync() -> None:
    bridge = DynamicDanceBridge()
    notified_batches = []

    def on_actions_updated(actions):
        notified_batches.append(actions)

    bridge.register_listener(on_actions_updated)
    initial_actions = bridge.get_action_library()
    assert len(initial_actions) > 0
    assert initial_actions[0].no >= 550001
    assert hasattr(initial_actions[0], "allow_move")

    custom_yaml = """
CUSTOM_SALUTE: [L1, UP] # 军礼致意
SWARM_WAVE: [R1, RIGHT] # 集群波浪律动
GROUND_BREAK: [L2, DOWN] # 街舞地板托马斯
"""
    updated_actions = bridge.sync_from_yaml_text(custom_yaml)
    assert len(updated_actions) == 3
    assert len(notified_batches) >= 1
    aliases = [a.alias for a in updated_actions]
    assert "CUSTOM_SALUTE" in aliases
    assert "SWARM_WAVE" in aliases
    assert "GROUND_BREAK" in aliases

    first = updated_actions[0]
    assert first.name == "军礼致意"
    assert first.cmd == "DANCE,CUSTOM_SALUTE"
    assert first.to_dict()["allowStretch"] is False

    bridge.unregister_listener(on_actions_updated)


def test_choreo_scene_store_flow(tmp_path) -> None:
    db_file = tmp_path / "test_studio.db"
    store = ChoreoSceneStore(db_path=str(db_file))

    scene_data = {
        "scene_id": "stage_alpha",
        "name": "国家大剧院舞台",
        "music_path": "assets/audio/march.mp3",
        "music_title": "钢铁洪流进行曲",
        "bpm": 128.0,
        "stage_width": 16.0,
        "stage_height": 12.0,
        "calibration_matrix": {"R": [[1, 0], [0, 1]], "t": [0, 0]},
        "is_enabled": 1
    }
    store.upsert_scene(scene_data)
    loaded_scene = store.get_scene("stage_alpha")
    assert loaded_scene is not None
    assert loaded_scene["name"] == "国家大剧院舞台"
    assert loaded_scene["bpm"] == 128.0
    assert loaded_scene["calibration_matrix"]["t"] == [0, 0]

    tracks_data = [
        {"track_id": 1, "robot_id": 1, "sn": "SN001", "alias": "领舞G1", "lora_id": "A"},
        {"track_id": 2, "robot_id": 2, "sn": "SN002", "alias": "伴舞G1", "lora_id": "B"}
    ]
    store.save_tracks("stage_alpha", tracks_data)
    loaded_tracks = store.get_tracks("stage_alpha")
    assert len(loaded_tracks) == 2
    assert loaded_tracks[0]["alias"] == "领舞G1"

    init_pts = [
        {"robot_id": 1, "x": -2.0, "y": 0.0, "yaw": 90.0},
        {"robot_id": 2, "x": 2.0, "y": 0.0, "yaw": 90.0}
    ]
    store.save_init_points("stage_alpha", group_id=1, group_name="开场站位", points=init_pts)
    loaded_pts = store.get_init_points("stage_alpha", group_id=1)
    assert len(loaded_pts) == 2
    assert loaded_pts[0]["x"] == -2.0


def test_trajectory_rules_and_delete_guard(tmp_path) -> None:
    db_file = tmp_path / "test_rules.db"
    store = ChoreoSceneStore(db_path=str(db_file))
    sid = "scene_beta"
    store.upsert_scene({"scene_id": sid, "name": "测试舞台"})

    g1_id = store.add_trajectory_group(sid, name="1号机专属轨迹组", track_id=1)
    g2_id = store.add_trajectory_group(sid, name="2号机专属轨迹组", track_id=2)
    assert g1_id > 0
    assert g2_id > 0

    no_1 = store.add_trajectory({
        "name": "入场走位",
        "group_id": g1_id,
        "time": 4.5,
        "trajectory_point_data": "0,0,0,0\n1,1,1,45"
    })
    no_2 = store.add_trajectory({
        "name": "回退走位",
        "group_id": g1_id,
        "time": 3.0,
    })
    no_3 = store.add_trajectory({
        "name": "2号机侧移",
        "group_id": g2_id,
        "time": 2.5,
    })

    assert no_1 == 100001
    assert no_2 == 100002
    assert no_3 == 200001

    blocks = [
        {
            "block_id": "blk_traj_1",
            "scene_id": sid,
            "robot_id": 1,
            "type": "trajectory",
            "no": no_1,
            "start_time": 0.0,
            "end_time": 4.5,
            "time": 4.5
        },
        {
            "block_id": "blk_act_1",
            "scene_id": sid,
            "robot_id": 1,
            "type": "active",
            "no": 550001,
            "start_time": 4.5,
            "end_time": 9.5,
            "time": 5.0
        }
    ]
    store.save_track_state(sid, blocks)
    loaded_blocks = store.get_track_state(sid, robot_id=1)
    assert len(loaded_blocks) == 2

    with pytest.raises(ValueError, match="正在被时间轴"):
        store.delete_trajectory(no_1)

    assert store.delete_trajectory(no_2) is True
    remaining_trajs = store.get_trajectories(g1_id)
    assert len(remaining_trajs) == 1
    assert remaining_trajs[0]["no"] == no_1

    exported = store.export_timeline(sid)
    assert "scene" in exported
    assert "tracks" in exported
    assert len(exported["blocks"]) == 2

