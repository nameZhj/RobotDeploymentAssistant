"""
@file: tests/unit/test_step03_lrmp_lora_bridge.py
@brief: Step 03 LRMP V1.0-R3 协议、ControlArbiter 状态机与物理 LoRa 桥接单元测试
@exports: test_expand_targets_all_blocking, test_control_arbiter_three_states, test_move_mapping_and_timeout, test_hardware_emergency, test_button_mask_whitelist, test_src_id_logging
"""
import os
import time
from unittest.mock import MagicMock
import pytest
from backend.serial_manager import serial_manager
from src.domain.lrmp.control_arbiter import ControlArbiter
from src.infrastructure.lrmp.lrmp_protocol_engine import LrmpProtocolEngine
from src.infrastructure.serial.lora_lrmp_bridge import LoraLrmpBridge


def test_expand_targets_all_blocking():
    """验证目标展开与 ALL 广播拦截规则"""
    engine = LrmpProtocolEngine()
    # 1. 唯一允许 ALL 广播的是 DISCOVER
    assert engine.expand_targets("ALL", "DISCOVER") == ["ALL"]

    # 2. 其它指令无已知目标时拦截 ALL
    with pytest.raises(ValueError, match="严禁非 DISCOVER 指令进行 ALL 广播"):
        engine.expand_targets("ALL", "STAND")

    # 3. 提供已知机群时自动将 ALL 展开为定向机群
    targets = engine.expand_targets("ALL", "STAND", known_targets=["A", "B", "C"])
    assert targets == ["A", "B", "C"]

    # 4. 多选目标拆分
    assert engine.expand_targets("A, B, D", "MOVE") == ["A", "B", "D"]


def test_control_arbiter_three_states():
    """验证 FREE / MANUAL / CHOREO 互斥与停动保权、拒绝 RELEASE 保护"""
    arb = ControlArbiter()
    # 1. 初始为 FREE，运动指令自动获取 MANUAL
    ok, st, _ = arb.handle_command("A", "STAND")
    assert ok and st == "MANUAL"

    # 2. MANUAL 态下拒绝 PREP 编排
    ok, st, _ = arb.handle_command("A", "PREP")
    assert not ok and st == "MANUAL"

    # 3. STOP 停动保权（保持 MANUAL）
    new_st, _ = arb.handle_stop("A")
    assert new_st == "MANUAL"

    # 4. RELEASE 释放 MANUAL 回 FREE
    ok, st, _ = arb.handle_command("A", "RELEASE")
    assert ok and st == "FREE"

    # 5. FREE 下 PREP 自动进入 CHOREO
    ok, st, _ = arb.handle_command("A", "PREP")
    assert ok and st == "CHOREO"

    # 6. CHOREO 下严词拒绝 RELEASE
    ok, st, msg = arb.handle_command("A", "RELEASE")
    assert not ok
    assert st == "CHOREO"
    assert "严词拒绝" in msg

    # 7. CHOREO 下 STOP 安全中断编排回 FREE
    new_st, _ = arb.handle_stop("A")
    assert new_st == "FREE"


def test_move_mapping_and_timeout():
    """验证通用 MOVE 映射与超时清零保护"""
    bridge = LoraLrmpBridge()
    sent_cmds = []
    serial_manager.send_command = MagicMock(side_effect=lambda t, c: sent_cmds.append((t, c)) or {"success": True})

    # 1. 超界校验
    ok, err = bridge.send_move_command("A", forward=1.5, left=0.0, turn=0.0, t=1.0)
    assert not ok and "超出" in err

    # 2. 正常前进映射
    ok, _ = bridge.send_move_command("A", forward=0.8, left=0.1, turn=0.0, t=0.1)
    assert ok
    assert ("A", "FORWARD,0.1") in sent_cmds

    # 3. 等待超时清零自动下发 STOP
    time.sleep(0.18)
    assert ("A", "STOP") in sent_cmds


def test_hardware_emergency():
    """验证硬急停触发 ALL|EMERGENCY 与多机定向 STOP"""
    bridge = LoraLrmpBridge()
    sent_cmds = []
    serial_manager.send_command = MagicMock(side_effect=lambda t, c: sent_cmds.append((t, c)) or {"success": True})

    ok, msg = bridge.trigger_hardware_emergency(known_targets=["A", "B"])
    assert ok
    assert ("ALL", "EMERGENCY") in sent_cmds
    assert ("A", "STOP") in sent_cmds
    assert ("B", "STOP") in sent_cmds


def test_button_mask_whitelist():
    """验证 BUTTON / MASK 高级特权指令白名单校验"""
    bridge = LoraLrmpBridge()
    serial_manager.send_command = MagicMock(return_value={"success": True})

    # 1. 非管理员拒绝
    ok, msg = bridge.send_button_command("A", "L1", "SELECT", is_admin=False)
    assert not ok and "未获管理员授权" in msg

    # 2. 非法按键名拒绝
    ok, msg = bridge.send_button_command("A", "L1", "INVALID_KEY", is_admin=True)
    assert not ok and "不在白名单中" in msg

    # 3. 合法按键放行
    ok, _ = bridge.send_button_command("A", "L1", "START", is_admin=True)
    assert ok


def test_src_id_logging():
    """验证通信帧记录真实 SRC_ID 审计日志"""
    engine = LrmpProtocolEngine()
    frame = engine.build_frame("REQ", src_id="GW_8C2F", dst_id="CTRL", payload="STATUS,NET")
    assert "GW_8C2F" in frame
    parsed = engine.parse_frame(frame)
    assert parsed["src_id"] == "GW_8C2F"
    assert parsed["dst_id"] == "CTRL"

    # 校验日志文件中存在真实 SRC_ID
    log_file = os.path.join("runtime", "logs", "comm_frames.log")
    assert os.path.exists(log_file)
    with open(log_file, "r", encoding="utf-8") as f:
        content = f.read()
    assert "SRC=GW_8C2F" in content

