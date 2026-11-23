import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.serial_manager import SerialManager

class TestSerialSyncPolicy(unittest.TestCase):
    def test_sync_policy(self):
        sm = SerialManager()
        sm.ser = MagicMock()
        sm.ser.is_open = True
        sm.current_port = "COM3"

        # 模拟 send_command
        sm.send_command = MagicMock(return_value={"success": True})

        # 1. 串口已连接时调用 auto_connect_best_port，不应触发 GETDANCELIST
        res = sm.auto_connect_best_port()
        self.assertTrue(res.get("connected"))
        sm.send_command.assert_not_called()

        # 2. 用户点击刷新，强制触发 request_dance_list(force=True) -> 触发一次 GETDANCELIST
        sm.latest_dance_list_parsed = [{"group": 1, "items": [{"alias": "G1_TEST"}]}]
        sm.request_dance_list(force=True, timeout=0.01)
        sm.send_command.assert_called_once_with("ALL", "GETDANCELIST")

        # 3. 频繁重复无 force 调用 request_dance_list -> 防抖拦截，不会再次触发 send_command
        sm.request_dance_list(force=False, timeout=0.01)
        sm.send_command.assert_called_once_with("ALL", "GETDANCELIST")

if __name__ == '__main__':
    unittest.main()
