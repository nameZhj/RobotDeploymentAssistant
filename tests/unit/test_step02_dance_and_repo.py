"""
@file: tests/unit/test_step02_dance_and_repo.py
@brief: Step 02 动态动作库桥接与 SQLite 8表仓储能力单元测试
@exports: test_dynamic_actions_expansion, test_multi_robot_common_actions, test_trajectory_numbering_law, test_trajectory_delete_protection, test_track_state_rw
"""
import os
import tempfile
import pytest
from backend.serial_manager import serial_manager
from src.application.services.dance_library_bridge import dance_library_bridge
from src.infrastructure.storage.studio_repository import StudioRepository

SAMPLE_YAML_1 = """
dance_map:
  # Group 1: select key L1
  G1_CUSTOM_DANCE_A: [L1, UP] # 自定义魔性舞蹈A
  G1_CUSTOM_DANCE_B: [L1, DOWN] # 摇摆律动B
  G1_COMMON_DANCE:   [L1, LEFT] # 多机公约动作
"""

SAMPLE_YAML_2 = """
dance_map:
  # Group 1: select key L1
  G1_CUSTOM_DANCE_C: [L1, RIGHT] # 独立动作C
  G1_COMMON_DANCE:   [L1, LEFT] # 多机公约动作
"""


def test_dynamic_actions_expansion():
    """验证动态注入任意数量动作 YAML 后，动作库无上限动态扩展且字段规范完整"""
    serial_manager.latest_dance_list_parsed = []
    serial_manager.set_dance_list_raw(SAMPLE_YAML_1)
    actions = dance_library_bridge.list_available_actions()
    assert len(actions) == 3

    aliases = [a["lora_alias"] for a in actions]
    assert "G1_CUSTOM_DANCE_A" in aliases
    assert "G1_COMMON_DANCE" in aliases

    first = actions[0]
    required_keys = {"id", "no", "name", "lora_alias", "key_combo", "type", "time", "transition", "allow_stretch", "allow_move"}
    assert required_keys.issubset(first.keys())
    assert first["no"] >= 550000


def test_multi_robot_common_actions():
    """验证多机动作公约交集提取算法"""
    common = dance_library_bridge.get_common_actions_for_robots([SAMPLE_YAML_1, SAMPLE_YAML_2])
    assert len(common) == 1
    assert common[0]["lora_alias"] == "G1_COMMON_DANCE"


def test_trajectory_numbering_law():
    """验证轨迹编号铁律：track_id=1 产生 100001/100002，track_id=2 产生 200001"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_studio.db")
        repo = StudioRepository(db_path)

        g1 = repo.create_trajectory_group("轨道1编导组", track_id=1)
        g2 = repo.create_trajectory_group("轨道2编导组", track_id=2)

        pts = "0,-3.0,-2.5,1.57\n0,-2.92,-1.3,0.61\n0,-2.24,-0.82,0.03"
        t1 = repo.create_trajectory(g1, "轨迹1A", pts, time_dur=3.5, max_acc=1.5)
        t2 = repo.create_trajectory(g1, "轨迹1B", pts, time_dur=4.0)
        t3 = repo.create_trajectory(g2, "轨迹2A", pts, time_dur=5.0)

        assert t1["no"] == 100001
        assert t2["no"] == 100002
        assert t3["no"] == 200001
        assert t1["trajectory_point_data"] == pts
        assert t1["max_acc"] == 1.5


def test_trajectory_delete_protection():
    """验证轨迹删除引用保护：被时间轴引用且非 force 时拒绝删除，force=True 时连带清除"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_studio.db")
        repo = StudioRepository(db_path)

        g1 = repo.create_trajectory_group("轨道1编导组", track_id=1)
        t1 = repo.create_trajectory(g1, "爱情鸟上场", "0,0,0,0\n0,1,1,0", time_dur=3.0)
        traj_no = t1["no"]

        # 在 track_state 中引用该轨迹
        repo.save_track_state_block({
            "id": "block_traj_1001",
            "robot_id": 1,
            "group_id": g1,
            "no": traj_no,
            "type": "trajectory",
            "name": "爱情鸟上场",
            "start_time": 0.0,
            "end_time": 3.0,
            "time": 3.0
        })

        # 保护机制：被引用拒绝删除
        ok, count, msg = repo.delete_trajectory(traj_no, force=False)
        assert not ok
        assert count == 1
        assert "拒绝删除" in msg

        # 强制删除
        ok_force, count_force, msg_force = repo.delete_trajectory(traj_no, force=True)
        assert ok_force
        assert count_force == 1
        # 验证已从数据库删除
        assert len(repo.get_track_state(robot_id=1)) == 0


def test_track_state_rw():
    """验证双子层 track_state 时间轴块保存与按机位读取"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_studio.db")
        repo = StudioRepository(db_path)

        b1 = {
            "id": "track_1_act_1",
            "robot_id": 1,
            "no": 550502,
            "type": "action",
            "name": "POPPING1",
            "start_time": 0.0,
            "end_time": 12.0,
            "time": 12.0
        }
        b2 = {
            "id": "track_2_traj_1",
            "robot_id": 2,
            "no": 200001,
            "type": "trajectory",
            "name": "走位2",
            "start_time": 5.0,
            "end_time": 9.0,
            "time": 4.0
        }

        repo.save_track_state_block(b1)
        repo.save_track_state_block(b2)

        r1_blocks = repo.get_track_state(robot_id=1)
        assert len(r1_blocks) == 1
        assert r1_blocks[0]["name"] == "POPPING1"
        assert r1_blocks[0]["type"] == "action"

        all_blocks = repo.get_track_state()
        assert len(all_blocks) == 2

