import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app
from backend.drivers import ch341_manager, CH341Manager, commands
from backend.deployment_core import deployment_core


class TestDriverManager(unittest.TestCase):
    """测试驱动与下位机注入公共管理模块"""

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_commands_integrity(self):
        """测试下位机注入命令与脚本模板的完整性与基本格式"""
        self.assertTrue(len(commands.CH341_DEV_PROBE_CMD) > 0)
        self.assertIn("ttyCH34", commands.CH341_DEV_PROBE_CMD)
        self.assertTrue(len(commands.CH341_LSMOD_CMD) > 0)
        self.assertTrue(len(commands.CH341_MODINFO_CMD) > 0)
        self.assertTrue(len(commands.CH341_MODPROBE_CMD) > 0)

        # 检查编译流水线 7 个阶段
        self.assertEqual(len(commands.CH341_LINUX_BUILD_PIPELINE), 7)
        for title, cmd in commands.CH341_LINUX_BUILD_PIPELINE:
            self.assertTrue(len(title) > 0)
            self.assertTrue(len(cmd) > 0)

        # 检查 udev 规则与权限命令
        self.assertTrue(commands.UDEV_RULES_PATH.startswith("/etc/udev/rules.d/"))
        self.assertIn("1a86", commands.UDEV_RULES_CONTENT)
        self.assertIn("0666", commands.UDEV_RULES_CONTENT)
        self.assertIn("reload-rules", commands.UDEV_RELOAD_CMD)
        self.assertIn("dialout", commands.USER_GROUPS_CMD)

        # 检查 C++ 补丁
        self.assertIn("TryOpenDevice", commands.BULLETPROOF_SERIAL_CPP_PATCH)
        self.assertIn("OpenSerial", commands.BULLETPROOF_SERIAL_CPP_PATCH)
        self.assertIn("/dev/ttyCH341USB", commands.BULLETPROOF_SERIAL_CPP_PATCH)

        # 检查 run_bg.sh 脚本
        self.assertTrue(commands.RUN_BG_SCRIPT_TEMPLATE.startswith("#!/bin/bash"))
        self.assertIn("launch_lora_daemon", commands.RUN_BG_SCRIPT_TEMPLATE)
        self.assertIn("lora_recv_group", commands.RUN_BG_SCRIPT_TEMPLATE)
        self.assertIn("pidof", commands.RUN_BG_SCRIPT_TEMPLATE)

    def test_find_windows_driver_path(self):
        """测试在工作目录中定位 CH341SER.EXE"""
        mgr = CH341Manager()
        path = mgr.find_windows_driver_path()
        self.assertIsNotNone(path)
        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.lower().endswith("ch341ser.exe"))

    def test_check_windows_driver(self):
        """测试 Windows 上位机串口驱动检测返回值结构"""
        mgr = CH341Manager()
        res = mgr.check_windows_driver()
        self.assertIsInstance(res, dict)
        self.assertIn("has_driver", res)
        self.assertIn("ports", res)
        self.assertIn("count", res)
        self.assertIn("msg", res)
        self.assertIsInstance(res["ports"], list)

    def test_install_windows_driver(self):
        """测试 Windows 驱动安装器触发逻辑"""
        mgr = CH341Manager()
        with patch('ctypes.windll.shell32.ShellExecuteW') as mock_shell:
            mock_shell.return_value = 42  # > 32 表示成功弹出 UAC 提权
            res = mgr.install_windows_driver()
            self.assertTrue(res.get("success"))
            self.assertIn("安装", res.get("msg"))

    def test_check_linux_driver_status(self):
        """测试下位机 Linux 驱动状态探测逻辑"""
        mgr = CH341Manager()
        mock_ssh = MagicMock()

        # 场景 1: 已有 /dev/ttyCH341USB0 设备节点
        mock_ssh.execute_command.side_effect = [
            (0, "/dev/ttyCH341USB0\n", ""),
            (0, "ch341 20480 0\n", ""),
            (0, "filename: ch341.ko\n", ""),
        ]
        has_drv, desc = mgr.check_linux_driver_status(mock_ssh)
        self.assertTrue(has_drv)
        self.assertIn("ttyCH341USB0", desc)

        # 场景 2: 未探测到设备但有内核模块
        mock_ssh.execute_command.side_effect = [
            (1, "", "No such file"),
            (0, "ch341 20480 0\n", ""),
            (0, "filename: ch341.ko\n", ""),
        ]
        has_drv, desc = mgr.check_linux_driver_status(mock_ssh)
        self.assertTrue(has_drv)

        # 场景 3: 完全无驱动
        mock_ssh.execute_command.side_effect = [
            (1, "", "No such file"),
            (1, "", ""),
            (1, "", ""),
        ]
        has_drv, desc = mgr.check_linux_driver_status(mock_ssh)
        self.assertFalse(has_drv)

    def test_compile_and_install_linux_driver(self):
        """测试下位机 Linux 驱动编译流水线"""
        mgr = CH341Manager()
        mock_ssh = MagicMock()

        # 场景 1: 已经存在驱动，直接幂等返回
        with patch.object(mgr, 'check_linux_driver_status', return_value=(True, "ch341 exists")):
            ok = mgr.compile_and_install_linux_driver(mock_ssh)
            self.assertTrue(ok)
            mock_ssh.execute_command_stream.assert_not_called()

        # 场景 2: 驱动不存在，执行流水线
        with patch.object(mgr, 'check_linux_driver_status', return_value=(False, "")):
            mock_ssh.execute_command_stream.return_value = 0
            mock_ssh.execute_command.return_value = (0, "/dev/ttyCH341USB0", "")
            ok = mgr.compile_and_install_linux_driver(mock_ssh)
            self.assertTrue(ok)
            self.assertEqual(mock_ssh.execute_command_stream.call_count, len(commands.CH341_LINUX_BUILD_PIPELINE))

    def test_setup_udev_and_permissions(self):
        """测试 udev 规则写入与权限放行公共方法"""
        mgr = CH341Manager()
        mock_ssh = MagicMock()
        mock_ssh.write_remote_text_file.return_value = (True, "OK")
        mock_ssh.execute_command.return_value = (0, "", "")

        ok = mgr.setup_udev_and_permissions(mock_ssh)
        self.assertTrue(ok)
        mock_ssh.write_remote_text_file.assert_called_with(commands.UDEV_RULES_CONTENT, commands.UDEV_RULES_PATH, sudo=True)
        self.assertTrue(mock_ssh.execute_command.called)

    def test_disable_usb_reset(self):
        """测试关闭 USB 破坏性复位"""
        mgr = CH341Manager()
        mock_ssh = MagicMock()
        mock_ssh.execute_command.return_value = (0, "", "")

        ok = mgr.disable_usb_reset(mock_ssh)
        self.assertTrue(ok)
        mock_ssh.execute_command.assert_called_with(commands.YAML_DISABLE_USB_RESET_CMD, sudo=True)

    def test_patch_and_recompile_lora_serial(self):
        """测试 C++ 热补丁注入与编译"""
        mgr = CH341Manager()
        mock_ssh = MagicMock()

        # 源码缺少 TryOpenDevice，需注入补丁
        old_cpp = "int OpenSerial(const std::string &device, int baud, int e22_settle_ms, int usb_reset_timeout_ms) { return 0; }"
        mock_ssh.execute_command.side_effect = [
            (0, old_cpp, ""),  # cat lora_serial.cpp
            (0, "", ""),       # docker cp
            (0, "", ""),       # cp sync
        ]
        mock_ssh.execute_command_stream.return_value = 0
        mock_ssh.write_remote_text_file.return_value = (True, "OK")

        ok = mgr.patch_and_recompile_lora_serial(mock_ssh)
        self.assertTrue(ok)
        self.assertTrue(mock_ssh.write_remote_text_file.called)
        written_content = mock_ssh.write_remote_text_file.call_args[0][0]
        self.assertIn("TryOpenDevice", written_content)

    def test_deploy_run_bg_script(self):
        """测试 run_bg.sh 部署与赋权"""
        mgr = CH341Manager()
        mock_ssh = MagicMock()
        mock_ssh.write_remote_text_file.return_value = (True, "OK")
        mock_ssh.execute_command.return_value = (0, "", "")

        ok = mgr.deploy_run_bg_script(mock_ssh)
        self.assertTrue(ok)
        mock_ssh.write_remote_text_file.assert_called_with(commands.RUN_BG_SCRIPT_TEMPLATE, commands.RUN_BG_REMOTE_PATH, sudo=True)
        mock_ssh.execute_command.assert_called_with(commands.RUN_BG_SYNC_AND_CHMOD_CMD, sudo=True)

    def test_deployment_core_integration(self):
        """测试 DeploymentCore 对 ch341_manager 的代理调用及系统 API"""
        with patch.object(ch341_manager, 'check_windows_driver', return_value={"has_driver": True, "ports": [], "count": 0, "msg": "OK"}):
            res = deployment_core.check_windows_ch341()
            self.assertTrue(res["has_driver"])

            # 测试 API 端点
            api_res = self.client.get('/api/system/check_windows_ch341')
            self.assertEqual(api_res.status_code, 200)
            self.assertTrue(api_res.get_json().get("data", {}).get("has_driver"))

        with patch.object(ch341_manager, 'install_windows_driver', return_value={"success": True, "msg": "Installed"}):
            res = deployment_core.install_windows_ch341()
            self.assertTrue(res["success"])

            # 测试 API 端点
            api_res = self.client.post('/api/system/install_windows_ch341')
            self.assertEqual(api_res.status_code, 200)
            self.assertTrue(api_res.get_json().get("success"))


if __name__ == '__main__':
    unittest.main()
