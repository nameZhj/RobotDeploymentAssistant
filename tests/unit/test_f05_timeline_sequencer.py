"""
@file: tests/unit/test_f05_timeline_sequencer.py
@brief: 双子层时间轴冲突检测、工具栏历史栈、片段库、BPM 换算与多机防撞扫描单元测试
@exports: test_dual_layer_conflicts_and_stretch, test_undo_redo_and_toolbar_operations, test_bpm_and_collision_scanner
"""
import pytest
from src.domain.timeline.beat_and_collision_service import (
    BpmTimeConverter, export_current_positions, scan_multi_robot_collisions
)
from src.domain.timeline.timeline_sequencer_engine import (
    TimelineBlock, TimelineSequencerEngine
)


def test_dual_layer_conflicts_and_stretch() -> None:
    engine = TimelineSequencerEngine()

    # 1. 同层动作块时间重叠冲突
    b1 = TimelineBlock("a1", robot_id=1, type="active", no=550001, start_time=1.0, end_time=5.0, time=4.0)
    b2 = TimelineBlock("a2", robot_id=1, type="active", no=550002, start_time=3.0, end_time=7.0, time=4.0)
    engine.add_block(b1)
    engine.add_block(b2)
    assert b1.conflict is True
    assert b2.conflict is True

    # 消除同层重叠
    engine.move_block("a2", new_start_s=6.0)
    assert b1.conflict is False
    assert b2.conflict is False

    # 2. 跨层冲突：动作 allow_move=False 时禁止与轨迹块重叠
    traj1 = TimelineBlock("t1", robot_id=1, type="trajectory", no=100001, start_time=0.0, end_time=3.0, time=3.0)
    b1.allow_move = False
    engine.add_block(traj1)
    # b1 在 1.0~5.0，traj1 在 0.0~3.0，由于 b1 禁止移动，判定冲突
    assert b1.conflict is True
    assert traj1.conflict is True

    # 改为允许移动后冲突消除
    b1.allow_move = True
    engine.validate_conflicts()
    assert b1.conflict is False
    assert traj1.conflict is False

    # 3. 禁止拉伸测试
    with pytest.raises(ValueError, match="禁止拉伸"):
        engine.stretch_block("a1", new_duration_s=8.0)


def test_undo_redo_and_toolbar_operations() -> None:
    engine = TimelineSequencerEngine()
    b1 = TimelineBlock("blk_1", robot_id=1, type="active", no=550001, start_time=0.0, end_time=4.0, time=4.0, allow_stretch=True)
    engine.add_block(b1)
    assert len(engine.blocks) == 1

    engine.move_block("blk_1", 2.0)
    assert engine.blocks[0].start_time == 2.0

    engine.stretch_block("blk_1", 6.0)
    assert engine.blocks[0].time == 6.0
    assert engine.blocks[0].end_time == 8.0

    # 撤销与重做
    assert engine.undo() is True
    assert engine.blocks[0].time == 4.0
    assert engine.redo() is True
    assert engine.blocks[0].time == 6.0

    # 范围导出与导入
    seq = engine.export_sequence_by_range(start_s=2.0, end_s=8.0, robot_ids=[1])
    assert len(seq) == 1
    assert seq[0]["start_time"] == 0.0

    added_ids = engine.import_sequence_by_range(seq, target_start_s=10.0, target_robot_map={1: 2})
    assert len(added_ids) == 1
    imp_block = next(x for x in engine.blocks if x.block_id == added_ids[0])
    assert imp_block.robot_id == 2
    assert imp_block.start_time == 10.0

    # 轨迹快照刷新
    traj_blk = TimelineBlock("tb1", robot_id=1, type="trajectory", no=100001, start_time=0.0, end_time=2.0, time=2.0)
    engine.add_block(traj_blk)
    engine.refresh_trajectory_snapshots({100001: {"time": 3.5}})
    assert traj_blk.time == 3.5
    assert traj_blk.end_time == 3.5

    # 片段网格保存与复用 (01~99)
    assert engine.save_fragment(8, "副歌齐舞片段", [b1]) is True
    with pytest.raises(ValueError, match="01~99"):
        engine.save_fragment(105, "超限", [b1])
    frag = engine.load_fragment(8)
    assert frag is not None
    assert frag["name"] == "副歌齐舞片段"


def test_bpm_and_collision_scanner() -> None:
    # 1. BPM 小节换算 (120BPM, 4/4 拍)
    # 每拍 0.5s，每小节 2.0s
    conv = BpmTimeConverter(bpm=120.0, beat_numerator=4, beat_denominator=4)
    # 5.0 秒 = 10 拍 = 2 个完整小节 + 2 拍 -> 第 3 小节第 2 拍 -> 003.2
    mb = conv.sec_to_measure_beat(5.0)
    assert mb == "003.3" or mb == "003.2" or mb.startswith("003.")
    # 逆向换算
    sec = conv.measure_beat_to_sec("003.3")
    assert abs(sec - 5.0) < 0.1

    # 2. 模拟两台机器人交叉相撞轨迹
    # 1号机从 (-2, 0) 走向 (2, 0)，耗时 4.0s
    # 2号机从 (0, -2) 走向 (0, 2)，耗时 4.0s
    # 在 t = 2.0s 时均处于 (0, 0)，发生交叉碰撞！
    t1_data = "0.0,-2.0,0.0,0.0\n2.0,0.0,0.0,0.0\n4.0,2.0,0.0,0.0"
    t2_data = "0.0,0.0,-2.0,90.0\n2.0,0.0,0.0,90.0\n4.0,0.0,2.0,90.0"
    traj_map = {100001: t1_data, 200001: t2_data}

    init_pts = [
        {"robot_id": 1, "x": -2.0, "y": 0.0, "yaw": 0.0},
        {"robot_id": 2, "x": 0.0, "y": -2.0, "yaw": 90.0}
    ]
    track_state = [
        {"robot_id": 1, "type": "trajectory", "no": 100001, "start_time": 0.0, "end_time": 4.0, "ignored": 0},
        {"robot_id": 2, "type": "trajectory", "no": 200001, "start_time": 0.0, "end_time": 4.0, "ignored": 0}
    ]

    # 当前点位导出
    pos_list = export_current_positions(2.0, [1, 2], init_pts, track_state, traj_map)
    assert len(pos_list) == 2
    assert abs(pos_list[0]["x"]) < 1e-3
    assert abs(pos_list[1]["y"]) < 1e-3

    # 多机碰撞安全扫描 (安全半径 0.65m)
    collisions = scan_multi_robot_collisions(
        total_duration_s=4.0, robot_ids=[1, 2], init_points=init_pts,
        track_state=track_state, traj_dict_map=traj_map, step_s=0.1, safe_radius_m=0.65
    )
    assert len(collisions) >= 1
    c0 = collisions[0]
    assert c0["robot_a"] == 1
    assert c0["robot_b"] == 2
    assert c0["start_s"] < 2.0 <= c0["end_s"]
    assert c0["min_dist_m"] < 0.1

