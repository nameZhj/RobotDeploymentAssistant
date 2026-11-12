"""
@file: tests/compatibility/test_robot_transport_contracts.py
@brief: 机器人串口/LoRa 传输层契约与通信协议回归测试 (2026-10-01 前基线)
@exports: test_serial_dance_parser_syntax, test_fake_serial_open_and_write, test_serial_port_detection
"""
from unittest.mock import MagicMock, patch
import pytest
from backend.serial_manager import SerialManager, parse_dance_map_yaml


def test_serial_dance_parser_syntax():
    """验证串口舞蹈指令解析器能正确识别各种注释与快捷键格式。"""
    raw_yaml = """
# Group 1: select key L1
dance_map:
  G1_WAVE:         [L1, A]        # 招手舞 RL_Wave_v1
  G1_SALUTE:       [L1, B]        # 敬礼动作
# Group 2: select key R1
  G2_MOONWALK:     [R1, UP]       # 太空漫步
"""
    groups = parse_dance_map_yaml(raw_yaml)
    assert len(groups) == 2
    g1 = groups[0]
    assert g1["group_id"] == "G1"
    assert len(g1["items"]) == 2
    assert g1["items"][0]["alias"] == "G1_WAVE"
    assert g1["items"][0]["name"] == "招手舞"
    assert g1["items"][0]["cmd"] == "DANCE,G1_WAVE"

    g2 = groups[1]
    assert g2["group_id"] == "G2"
    assert g2["items"][0]["alias"] == "G2_MOONWALK"
    assert g2["items"][0]["name"] == "太空漫步"


def test_fake_serial_open_and_write():
    """通过 Fake Serial 验证串口打开、发送报文与关闭流程。"""
    mgr = SerialManager()

    fake_serial = MagicMock()
    fake_serial.is_open = True
    fake_serial.in_waiting = 0
    fake_serial.write = MagicMock(return_value=12)

    with patch("serial.Serial", return_value=fake_serial):
        res = mgr.connect_port("COM99", baudrate=115200)
        assert res["success"] is True
        assert mgr.current_port == "COM99"

        # 发送原始控制指令
        send_res = mgr.send_raw("DANCE,G1_WAVE")
        assert send_res["success"] is True
        fake_serial.write.assert_called_with(b"DANCE,G1_WAVE\n")

        # 断开端口
        close_res = mgr.disconnect()
        assert close_res["success"] is True
        assert mgr.ser is None


def test_serial_port_detection():
    """验证 list_ports 对常见 CH340/CH341 芯片的识别与排序能力。"""
    mgr = SerialManager()

    p1 = MagicMock()
    p1.device = "COM1"
    p1.description = "Standard Serial Port"
    p1.hwid = "PCI\\VEN_8086"

    p2 = MagicMock()
    p2.device = "COM3"
    p2.description = "USB-SERIAL CH340"
    p2.hwid = "USB\\VID_1A86&PID_7523"

    with patch("serial.tools.list_ports.comports", return_value=[p1, p2]):
        ports = mgr.list_ports()
        assert len(ports) == 2
        # CH340 设备应该优先排在最前
        assert ports[0]["port"] == "COM3"
        assert ports[0]["is_ch341"] is True
        assert ports[1]["port"] == "COM1"
        assert ports[1]["is_ch341"] is False
