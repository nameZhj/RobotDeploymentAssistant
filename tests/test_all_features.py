import io
import os
import sys
import zipfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app
from backend.serial_manager import SerialManager

class ComprehensiveSystemTest(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_zip_upload(self):
        from unittest.mock import patch
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('dance_test.vsis', b'dummy vsis binary')
            zf.writestr('config.yaml', b'dance_map:\n  TEST: [L1, X]\n')
        buf.seek(0)

        data = {
            'dest_path': '/secure/config_vsis',
            'zip_file': (buf, 'dance_pack_test.zip')
        }
        with patch('backend.dance_updater.dance_updater.deploy_zip_package') as mock_up:
            mock_up.return_value = (True, "更新成功")
            res = self.client.post('/api/dance/update', data=data, content_type='multipart/form-data')
            self.assertEqual(res.status_code, 200)
            res_json = res.get_json()
            self.assertTrue(res_json.get('success'))
            self.assertEqual(res_json.get('filename'), 'dance_pack_test.zip')

    def test_folder_upload(self):
        from unittest.mock import patch
        data = {
            'dest_path': '/secure/config_vsis',
            'paths': ['mimic_exp2/dance1.vsis', 'mimic_exp2/config.yaml'],
            'files': [
                (io.BytesIO(b'vsis model 1'), 'dance1.vsis'),
                (io.BytesIO(b'yaml config'), 'config.yaml')
            ]
        }
        with patch('backend.dance_updater.dance_updater.deploy_zip_package') as mock_up:
            mock_up.return_value = (True, "更新成功")
            res = self.client.post('/api/dance/update', data=data, content_type='multipart/form-data')
            self.assertEqual(res.status_code, 200)
            res_json = res.get_json()
            self.assertTrue(res_json.get('success'))

    def test_local_folder_path_upload(self):
        from unittest.mock import patch
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = os.path.join(tmpdir, "dance_local.vsis")
            with open(f1, "w") as f:
                f.write("dummy vsis model data")
            data = {
                'dest_path': '/secure/config_vsis',
                'local_path': tmpdir
            }
            with patch('backend.dance_updater.dance_updater.deploy_zip_package') as mock_up:
                mock_up.return_value = (True, "更新成功")
                res = self.client.post('/api/dance/update', data=data)
                self.assertEqual(res.status_code, 200)
                res_json = res.get_json()
                self.assertTrue(res_json.get('success'))
                self.assertTrue('task_id' in res_json)

    def test_check_robot_env_api(self):
        from unittest.mock import patch
        with patch('backend.deployment_core.deployment_core.run_environment_precheck') as mock_chk:
            mock_chk.return_value = {"all_passed": True, "items": {}}
            res = self.client.post('/api/robot/check_env')
            self.assertEqual(res.status_code, 200)
            res_json = res.get_json()
            self.assertTrue(res_json.get('success'))
            self.assertTrue('task_id' in res_json)
        self.assertEqual(res.status_code, 200)
        res_json = res.get_json()
        self.assertTrue(res_json.get('success'))
        self.assertTrue('task_id' in res_json)

    def test_robot_process_apis(self):
        from unittest.mock import patch
        # 1. 进程状态查询
        with patch('backend.deployment_core.deployment_core.get_robot_process_status') as mock_status:
            mock_status.return_value = {
                "connected": True,
                "g1_ctrl_running": True,
                "g1_ctrl_ready": True,
                "g1_ctrl_starting": False,
                "lora_recv_running": True,
                "all_running": True
            }
            res = self.client.get('/api/robot/process_status')
            self.assertEqual(res.status_code, 200)
            res_json = res.get_json()
            self.assertTrue('g1_ctrl_running' in res_json)
            self.assertTrue('lora_recv_running' in res_json)

        # 2. 启动机载程序 (Mock 隔离，严禁在自动化测试中操作真实机器人)
        with patch('backend.deployment_core.deployment_core.start_robot_processes') as mock_start:
            mock_start.return_value = (True, "启动成功")
            res = self.client.post('/api/robot/start_processes')
            self.assertEqual(res.status_code, 200)
            res_json = res.get_json()
            self.assertTrue(res_json.get('success'))
            self.assertTrue('task_id' in res_json)

        # 3. 停止机载程序 (Mock 隔离)
        with patch('backend.deployment_core.deployment_core.stop_robot_processes') as mock_stop:
            mock_stop.return_value = (True, "停止成功")
            res = self.client.post('/api/robot/stop_processes')
            self.assertEqual(res.status_code, 200)

    def test_serial_parser(self):
        from backend.serial_manager import parse_dance_map_yaml
        sample_yaml = """
dance_map:
  # Group 1: select key L1

  G1_TURN_JUMP:    [L1, DOWN]     # 转身跳跃 RL_Mimic_CMU_83_58
  G1_FRONT_FLIP:   [L1, RIGHT]    # 前空翻 RL_Mimic_CMU_85_07
  G1_SIDE_FLIP:    [L1, A]        # 侧空翻 RL_Mimic_CMU_90_08
"""
        groups = parse_dance_map_yaml(sample_yaml)
        self.assertEqual(len(groups), 1)
        items = groups[0]['items']
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]['alias'], 'G1_TURN_JUMP')
        self.assertEqual(items[0]['name'], '转身跳跃')
        self.assertEqual(items[0]['select_key'], 'L1')
        self.assertEqual(items[0]['action_key'], 'DOWN')


if __name__ == '__main__':
    unittest.main()
