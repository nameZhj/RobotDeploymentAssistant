import io
import os
import sys
import zipfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app

class TestDanceUpload(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_folder_upload_packaging(self):
        # 模拟上传文件夹中的多个动作文件与配置文件
        data = {
            'dest_path': '/secure/config_vsis',
            'paths': ['mimic_exp2/dance_cmu_83_58.vsis', 'mimic_exp2/config.yaml'],
            'files': [
                (io.BytesIO(b'dummy vsis binary content 12345'), 'dance_cmu_83_58.vsis'),
                (io.BytesIO(b'dummy config yaml content'), 'config.yaml')
            ]
        }
        res = self.client.post('/api/dance/update', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 200)
        res_json = res.get_json()
        print('Folder upload response:', res_json)
        self.assertTrue(res_json.get('success'))
        self.assertTrue('task_id' in res_json)

if __name__ == '__main__':
    unittest.main()
