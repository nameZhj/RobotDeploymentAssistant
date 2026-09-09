import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app
from backend.deployment_core import validate_robot_id, deployment_core
from backend.serial_manager import serial_manager


class TestRobotIdAndTargetControl(unittest.TestCase):
    """测试多机目标控制逗号分隔规范与 Robot ID 全局安全校验逻辑"""

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_validate_robot_id_valid_cases(self):
        """测试合法 Robot ID 命名格式"""
        valid_cases = [
            ("A", "A"),
            ("b", "B"),
            ("R1", "R1"),
            ("r2", "R2"),
            ("G1_02", "G1_02"),
            ("robot-1", "ROBOT-1"),
            ("g1_unitree_01", "G1_UNITREE_01"),
            ("99", "99"),
            ("  c  ", "C"),
            ("A_B-C", "A_B-C"),
        ]
        for raw, expected in valid_cases:
            ok, clean_id, err = validate_robot_id(raw)
            self.assertTrue(ok, f"合法 ID [{raw}] 校验失败: {err}")
            self.assertEqual(clean_id, expected)
            self.assertEqual(err, "")

    def test_validate_robot_id_forbidden_and_injection_cases(self):
        """测试非法字符、广播保留字及安全注入字符拦截"""
        invalid_cases = [
            # 空值
            (None, "不能为空"),
            ("", "不能为空"),
            ("   ", "不能为空"),
            # 保留字
            ("ALL", "保留关键字"),
            ("all", "保留关键字"),
            ("All", "保留关键字"),
            # 逗号与竖线 (协议分隔符)
            ("A,B", "逗号"),
            (",A", "逗号"),
            ("A,", "逗号"),
            ("A|B", "竖线"),
            ("A|STAND", "竖线"),
            # 命令注入字符
            ("A; rm -rf /", "不合法"),
            ("A && reboot", "不合法"),
            ("A & B", "不合法"),
            ("A | cat", "竖线"),
            ("A`whoami`", "不合法"),
            ("A$(id)", "不合法"),
            ("A$FOO", "不合法"),
            ("A' OR '1'='1", "不合法"),
            ('A" OR "1"="1', "不合法"),
            ("A/B", "不合法"),
            ("A\\B", "不合法"),
            ("A\nB", "不合法"),
            ("A\rB", "不合法"),
            ("A\tB", "不合法"),
            ("A B", "不合法"),
            ("A*B", "不合法"),
            ("A?B", "不合法"),
            # 超过 20 位长度
            ("A" * 21, "不合法"),
        ]
        for raw, expected_keyword in invalid_cases:
            ok, clean_id, err = validate_robot_id(raw)
            self.assertFalse(ok, f"非法 ID [{raw}] 未被拦截！返回了 clean_id={clean_id}")
            self.assertIn(expected_keyword, err, f"错误提示 [{err}] 未包含预期关键字 [{expected_keyword}]")

    def test_deployment_core_configure_autostart_validation(self):
        """测试 DeploymentCore.configure_autostart_and_robot_id 对非法 ID 的拦截"""
        # 逗号拦截
        res_comma = deployment_core.configure_autostart_and_robot_id("A,B")
        self.assertFalse(res_comma["success"])
        self.assertIn("逗号", res_comma["msg"])

        # 注入字符拦截
        res_inject = deployment_core.configure_autostart_and_robot_id("A; rm -rf /")
        self.assertFalse(res_inject["success"])
        self.assertIn("不合法", res_inject["msg"])

        # ALL 拦截
        res_all = deployment_core.configure_autostart_and_robot_id("ALL")
        self.assertFalse(res_all["success"])
        self.assertIn("保留关键字", res_all["msg"])

    def test_api_container_autostart_validation(self):
        """测试 /api/container/autostart 端点校验"""
        # 测试含有注入字符的非法请求
        resp = self.client.post('/api/container/autostart', json={"robot_id": "A,B"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data.get("success"))
        self.assertIn("逗号", data.get("msg", ""))

        # 测试合法请求
        with patch('backend.deployment_core.deployment_core.configure_autostart_and_robot_id') as mock_cfg:
            mock_cfg.return_value = {"success": True, "robot_id": "R1", "msg": "OK"}
            resp_ok = self.client.post('/api/container/autostart', json={"robot_id": "r1"})
            self.assertEqual(resp_ok.status_code, 200)
            data_ok = resp_ok.get_json()
            self.assertTrue(data_ok.get("success"))
            self.assertEqual(data_ok.get("robot_id"), "R1")

    def test_serial_send_multi_target_format(self):
        """测试串口指令发送接口接受逗号隔开的多机目标 (如 A,B|STAND)"""
        with patch.object(serial_manager, 'send_command') as mock_send:
            mock_send.return_value = {"success": True, "target": "A,B", "command": "STAND", "msg": "OK"}
            
            # 客户端发送 A,B 多选目标
            res = self.client.post('/api/serial/send', json={
                "target": "A,B",
                "command": "STAND"
            })
            self.assertEqual(res.status_code, 200)
            mock_send.assert_called_with("A,B", "STAND")

            # 客户端发送 A,B,C 全选多机目标
            mock_send.return_value = {"success": True, "target": "A,B,C", "command": "GAIT", "msg": "OK"}
            res_all = self.client.post('/api/serial/send', json={
                "target": "A,B,C",
                "command": "GAIT"
            })
            self.assertEqual(res_all.status_code, 200)
            mock_send.assert_called_with("A,B,C", "GAIT")


if __name__ == '__main__':
    unittest.main()
