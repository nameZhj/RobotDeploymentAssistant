import os
import sys
import unittest
import zipfile
import tempfile
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app import app
from backend.preview_manager import preview_manager


class TestPreviewImport(unittest.TestCase):
    """测试根目录 preview 管理、ZIP 导入、URDF 29-DoF 解析与动作播放数据生成"""

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_01_preview_dir_created(self):
        """测试根目录 preview 文件夹自动创建与存在"""
        self.assertTrue(os.path.exists(preview_manager.preview_dir))
        self.assertTrue(os.path.isdir(preview_manager.preview_dir))

    def test_02_mock_urdf_zip_import_and_parse(self):
        """测试导入包含 URDF 的 ZIP 压缩包并自动解析生成 50fps 动作"""
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "test_g1_model.zip")
            urdf_content = """<?xml version="1.0"?>
            <robot name="g1_mock">
                <link name="pelvis"/>
                <link name="waist_yaw_link"/>
                <link name="waist_roll_link"/>
                <link name="torso_link"/>
                <joint name="waist_yaw_joint" type="revolute">
                    <parent link="pelvis"/>
                    <child link="waist_yaw_link"/>
                    <origin xyz="0 0 0.05"/>
                </joint>
                <joint name="waist_roll_joint" type="revolute">
                    <parent link="waist_yaw_link"/>
                    <child link="waist_roll_link"/>
                    <origin xyz="0 0 0.04"/>
                </joint>
                <joint name="waist_pitch_joint" type="revolute">
                    <parent link="waist_roll_link"/>
                    <child link="torso_link"/>
                    <origin xyz="0 0 0.05"/>
                </joint>
            </robot>
            """
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("test_g1_model/model.urdf", urdf_content)

            res = preview_manager.import_zip(zip_path)
            self.assertTrue(res.get("success"), f"Mock ZIP 导入失败: {res.get('msg')}")
            self.assertEqual(res.get("joint_count"), 30)
            self.assertEqual(res.get("fps"), 50.0)
            self.assertEqual(res.get("total_frames"), 300)
            self.assertEqual(res.get("duration_seconds"), 6.0)

            # 验证生成的 NPZ 文件已存在于 preview 根目录
            npz_file = os.path.join(preview_manager.preview_dir, f"{res['dance_name']}.npz")
            self.assertTrue(os.path.exists(npz_file), f"生成的 NPZ 文件不存在: {npz_file}")
            preview_manager.delete_dance(res['dance_name'])

    def test_03_real_g1_rubber_hand_zip_if_exists(self):
        """若用户指定的真实微信文件存在，测试其实际导入与解析"""
        real_path = r"E:\myfile\xwechat_files\wxid_j7m2dqj20npw21_e0ac\msg\file\2026-09\g1_29dof_rubber_hand.zip"
        if os.path.exists(real_path):
            res = preview_manager.import_zip(real_path)
            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("dance_name"), "g1_29dof_rubber_hand_dance")
            self.assertEqual(res.get("joint_count"), 30)
            self.assertEqual(len(res.get("frames", [])), 300)

            # 验证解压文件夹与生成的 NPZ
            extracted_folder = os.path.join(preview_manager.preview_dir, "g1_29dof_rubber_hand")
            npz_file = os.path.join(preview_manager.preview_dir, "g1_29dof_rubber_hand_dance.npz")
            self.assertTrue(os.path.exists(extracted_folder))
            self.assertTrue(os.path.exists(npz_file))

    def test_04_api_import_zip_endpoint(self):
        """测试 POST /api/dance/import_zip 接口"""
        # 测试空路径拦截
        r1 = self.client.post("/api/dance/import_zip", json={"path": ""})
        d1 = r1.get_json()
        self.assertFalse(d1["success"])

        # 测试不存在文件拦截
        r2 = self.client.post("/api/dance/import_zip", json={"path": "not_existing.zip"})
        d2 = r2.get_json()
        self.assertFalse(d2["success"])

        # 测试真实文件导入
        real_path = r"E:\myfile\xwechat_files\wxid_j7m2dqj20npw21_e0ac\msg\file\2026-09\g1_29dof_rubber_hand.zip"
        if os.path.exists(real_path):
            r3 = self.client.post("/api/dance/import_zip", json={"path": real_path})
            d3 = r3.get_json()
            self.assertTrue(d3["success"])
            self.assertIn("g1_29dof_rubber_hand", d3["dance_name"])

            # 测试读取接口
            r_get = self.client.get(f"/api/dance/get_3d/{d3['dance_name']}")
            d_get = r_get.get_json()
            self.assertTrue(d_get["success"])
            self.assertEqual(len(d_get["frames"]), 300)

    def test_05_delete_dance_permanently(self):
        """测试删除动作后永久删除，不再自动重新生成演示动作"""
        # 创建临时动作测试删除
        test_dance_name = "test_to_delete_dance"
        npz_file = os.path.join(preview_manager.preview_dir, f"{test_dance_name}.npz")
        np.savez_compressed(npz_file, positions=np.zeros((10, 21, 3)), fps=50.0, dance_name=test_dance_name)
        self.assertTrue(os.path.exists(npz_file))

        # 执行删除
        del_res = preview_manager.delete_dance(test_dance_name)
        self.assertTrue(del_res["success"])
        self.assertFalse(os.path.exists(npz_file))

        # 再次获取列表，验证已删除项绝不会复活
        all_dances = preview_manager.list_all_dances()
        names = [d["name"] for d in all_dances]
        self.assertNotIn(test_dance_name, names)

    def test_06_merged_npz_and_zip_import(self):
        """测试 NPZ 与 ZIP 合并导入：自动识别 .npz 动捕文件并正确导入"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sample_npz = os.path.join(tmpdir, "sample_custom_mocap.npz")
            np.savez_compressed(
                sample_npz,
                positions=np.zeros((20, 21, 3)),
                fps=50.0,
                dance_name="sample_custom_mocap"
            )

            # 通过统一导入端点导入 .npz
            res = self.client.post("/api/dance/import_zip", json={"path": sample_npz})
            data = res.get_json()
            self.assertTrue(data["success"], f"NPZ 导入失败: {data.get('msg')}")
            self.assertEqual(data["dance_name"], "sample_custom_mocap")
            self.assertEqual(data["total_frames"], 20)

            # 清理导入的临时测试文件
            preview_manager.delete_dance("sample_custom_mocap")

    def test_07_robot_3d_mesh_metadata_and_static_serving(self):
        """测试 3D 机器人网格模型深度解析与静态 STL 路由访问"""
        real_path = r"E:\myfile\xwechat_files\wxid_j7m2dqj20npw21_e0ac\msg\file\2026-09\g1_29dof_rubber_hand.zip"
        if os.path.exists(real_path):
            res = preview_manager.import_zip(real_path)
            self.assertTrue(res["success"])
            self.assertIn("model_info", res)

            mi = res["model_info"]
            self.assertTrue(mi["has_robot_model"])
            self.assertEqual(mi["parts_count"], 35)
            self.assertEqual(len(mi["parts"]), 35)

            # 验证各刚体零件包含 base_pos 与 STL URL
            first_part = mi["parts"][0]
            self.assertIn("base_pos", first_part)
            self.assertIn("mesh_url", first_part)
            self.assertTrue(first_part["mesh_url"].startswith("/preview/"))

            # 测试静态资源路由能够成功拉取 STL 文件
            mesh_url = first_part["mesh_url"]
            resp = self.client.get(mesh_url)
            self.assertEqual(resp.status_code, 200)
            self.assertGreater(len(resp.data), 1000)


if __name__ == "__main__":
    unittest.main()
