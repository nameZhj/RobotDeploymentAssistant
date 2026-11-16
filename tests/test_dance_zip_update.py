import unittest
import os
import sys
import zipfile
import tempfile
import io
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app
from backend.dance_updater import dance_updater

class TestDanceZipUpdate(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

        # 创建临时测试 zip 压缩包
        self.temp_dir = tempfile.mkdtemp()
        self.zip_path = os.path.join(self.temp_dir, "test_dances.zip")
        with zipfile.ZipFile(self.zip_path, 'w') as zf:
            zf.writestr("model_a.vsis", "dummy vsis content A")
            zf.writestr("model_b.vsis", "dummy vsis content B")
            zf.writestr("config.yaml", "dummy: true\n")

    def tearDown(self):
        if os.path.exists(self.zip_path):
            try:
                os.remove(self.zip_path)
            except Exception:
                pass

    def test_api_update_dance_no_file(self):
        """测试未选择文件时的拦截校验"""
        resp = self.app.post("/api/dance/update", data={})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data["success"])
        self.assertIn("未检测到", data["msg"])

    def test_api_update_dance_with_zip(self):
        """测试上传真实 .zip 文件时正常生成任务 ID"""
        with open(self.zip_path, "rb") as fp:
            data = {
                "zip_file": (fp, "test_dances.zip"),
                "dest_path": "/secure/config_vsis"
            }
            resp = self.app.post("/api/dance/update", data=data, content_type="multipart/form-data")
            self.assertEqual(resp.status_code, 200)
            res_json = resp.get_json()
            self.assertTrue(res_json["success"])
            self.assertTrue(res_json["task_id"].startswith("dance_update_"))
            self.assertEqual(res_json["filename"], "test_dances.zip")


if __name__ == "__main__":
    unittest.main()
