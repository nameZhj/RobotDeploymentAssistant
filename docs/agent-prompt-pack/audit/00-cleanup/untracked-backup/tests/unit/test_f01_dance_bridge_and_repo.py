"""
@file: tests/unit/test_f01_dance_bridge_and_repo.py
@brief: 动态舞蹈桥接服务与舞台编排 SQLite 仓储引擎单元测试
@exports: test_dance_library_bridge_dynamic_and_intersect, test_choreo_repo_trajectories_and_protection, test_choreo_repo_fragments_and_tracks
"""
import pytest
from backend.serial_manager import serial_manager
from src.application.services.dance_library_bridge import DanceLibraryBridge
from src.infrastructure.storage.choreo_repository import ChoreoRepository


def test_dance_library_bridge_dynamic_and_intersect() -> None:
    bridge = DanceLibraryBridge()

    # 1. 动态注入非固定数量的 YAML 动作
    yaml_text = """
SOLO_KICK: [L1, UP] # 独舞飞踢
G1_CHEST_POP: [L1, DOWN] # 胸部震动
SYNC_SPIN: [R1, RIGHT] # 集群旋转
"""
    serial_manager.set_dance_list_raw(yaml_text)
    actions = bridge.get_dynamic_actions()
    assert len(actions) == 3
    aliases = [a["code_alias"] for a in actions]
    assert "SOLO_KICK" in aliases
    assert "G1_CHEST_POP" in aliases
    assert "SYNC_SPIN" in aliases

    # 关键词过滤与分组前缀过滤
    filtered_kw = bridge.get_dynamic_actions(filter_keyword="飞踢")
    assert len(filtered_kw) == 1
    assert filtered_kw[0]["code_alias"] == "SOLO_KICK"

    filtered_grp = bridge.get_dynamic_actions(group_prefix="G1")
    assert len(filtered_grp) >= 2

    # 2. 多机动作交集过滤
    robot1_yaml = """
COMMON_WAVE: [L1, UP] # 共同波浪
ROBOT1_SPECIAL: [L1, DOWN] # 1号独有
SYNC_FINALE: [R1, A] # 终场动作
"""
    robot2_yaml = """
COMMON_WAVE: [L1, UP] # 共同波浪
ROBOT2_SPECIAL: [L2, B] # 2号独有
SYNC_FINALE: [R1, A] # 终场动作
"""
    common_actions = bridge.get_multi_robot_common_actions([robot1_yaml, robot2_yaml])
    common_aliases = [a["code_alias"] for a in common_actions]
    assert "COMMON_WAVE" in common_aliases
    assert "SYNC_FINALE" in common_aliases
    assert "ROBOT1_SPECIAL" not in common_aliases
    assert "ROBOT2_SPECIAL" not in common_aliases


def test_choreo_repo_trajectories_and_protection(tmp_path) -> None:
    db_file = tmp_path / "test_choreo_repo.db"
    repo = ChoreoRepository(db_path=str(db_file))
    sid = "scene_show_1"
    repo.upsert_scene({"scene_id": sid, "name": "演播厅舞台", "bpm": 120.0})

    # 创建分别绑定轨道 1 和轨道 2 的轨迹分组
    g1 = repo.add_trajectory_group(sid, "1号机轨迹组", track_id=1)
    g2 = repo.add_trajectory_group(sid, "2号机轨迹组", track_id=2)

    # 验证 100001, 100002, 200001 编号生成
    no_1 = repo.add_trajectory({"group_id": g1, "name": "上台1", "trajectory_point_data": "0,0,0,0\n1,1,1,0"})
    no_2 = repo.add_trajectory({"group_id": g1, "name": "上台2"})
    no_3 = repo.add_trajectory({"group_id": g2, "name": "2号机走位"})

    assert no_1 == 100001
    assert no_2 == 100002
    assert no_3 == 200001

    # 在 track_state 中引用 100001
    repo.save_track_state(sid, [
        {"block_id": "blk_1", "robot_id": 1, "type": "trajectory", "no": no_1, "start_time": 0.0, "end_time": 2.0, "time": 2.0}
    ])

    # 验证删除引用保护
    ok, ref_cnt, msg = repo.delete_trajectory(no_1, force=False)
    assert ok is False
    assert ref_cnt == 1
    assert "禁止删除" in msg

    # 未被引用的 100002 可直接删除
    ok_free, ref_free, _ = repo.delete_trajectory(no_2, force=False)
    assert ok_free is True
    assert ref_free == 0

    # 强制删除 100001 并级联清理时间轴块
    ok_force, ref_force, _ = repo.delete_trajectory(no_1, force=True)
    assert ok_force is True
    assert ref_force == 1
    remaining_blocks = repo.get_track_state(sid, robot_id=1)
    assert len(remaining_blocks) == 0


def test_choreo_repo_fragments_and_tracks(tmp_path) -> None:
    db_file = tmp_path / "test_frag_repo.db"
    repo = ChoreoRepository(db_path=str(db_file))
    sid = "scene_frag_1"

    # 保存机群轨道与 lora_id A/B 映射
    tracks = [
        {"track_id": 1, "robot_id": 1, "alias": "左翼G1", "lora_id": "A"},
        {"track_id": 2, "robot_id": 2, "alias": "右翼G1", "lora_id": "B"}
    ]
    repo.save_tracks(sid, tracks)
    loaded_tracks = repo.get_tracks(sid)
    assert len(loaded_tracks) == 2
    assert loaded_tracks[0]["lora_id"] == "A"
    assert loaded_tracks[1]["lora_id"] == "B"

    # 01~99 片段保存与读取
    blocks_data = [{"block_id": "b1", "type": "active", "no": 550001, "start_time": 0.0, "end_time": 4.0, "time": 4.0}]
    assert repo.save_fragment(1, "前奏齐舞", blocks_data) is True
    assert repo.save_fragment(99, "终场谢幕", blocks_data) is True

    with pytest.raises(ValueError, match="01~99"):
        repo.save_fragment(0, "非法编号", blocks_data)
    with pytest.raises(ValueError, match="01~99"):
        repo.save_fragment(100, "非法编号", blocks_data)

    frag1 = repo.get_fragment(1)
    assert frag1 is not None
    assert frag1["name"] == "前奏齐舞"
    assert len(frag1["blocks"]) == 1

