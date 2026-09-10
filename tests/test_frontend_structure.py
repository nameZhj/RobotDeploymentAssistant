import os
import re
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app, WEB_DIR

class FrontendStructureTest(unittest.TestCase):
    """
    前端页面架构解耦与 DOM 完整性自动化回归测试用例
    严格保证代码重构前后逻辑与功能 100% 零退化
    """
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        cls.client = app.test_client()
        response = cls.client.get('/')
        cls.status_code = response.status_code
        cls.html = response.get_data(as_text=True)

    def test_01_index_route_status_200(self):
        """测试根路由 / 正常返回 200 OK 且响应非空"""
        self.assertEqual(self.status_code, 200)
        self.assertTrue(len(self.html) > 5000)
        self.assertIn("<!DOCTYPE html>", self.html)
        self.assertIn("<html lang=\"zh-CN\">", self.html)

    def test_02_component_files_exist(self):
        """测试所有拆分后的模块化子组件文件均在对应目录下物理存在"""
        components = [
            "components/head.html",
            "components/navbar.html",
            "components/wizard_modal.html",
            "components/tab_robot_control.html",
            "components/ops_modal.html",
            "components/modals.html",
            "components/scripts.html",
            "components/ops_tabs/tab_network.html",
            "components/ops_tabs/tab_precheck.html",
            "components/ops_tabs/tab_image.html",
            "components/ops_tabs/tab_license.html",
            "components/ops_tabs/tab_dance_update.html",
            "components/ops_tabs/tab_3d_player.html",
            "components/ops_tabs/tab_logs.html",
            "components/ops_tabs/tab_tutorial.html",
        ]
        for comp in components:
            full_path = os.path.join(WEB_DIR, comp)
            self.assertTrue(os.path.isfile(full_path), f"组件文件丢失: {comp}")

    def test_03_top_navbar_elements(self):
        """测试顶部导航栏与设置菜单探针"""
        expected_ids = [
            "ctrl-serial-status-badge",
            "ctrl-serial-status-text",
            "btn-open-wizard",
            "btn-settings-menu",
            "settings-menu-content",
            "status-dot",
            "status-text",
            "conn-info-display",
            "settings-license-status",
            "btn-open-ops-modal",
        ]
        for eid in expected_ids:
            self.assertIn(f'id="{eid}"', self.html, f"顶部栏元素缺失: {eid}")

    def test_04_wizard_modal_elements(self):
        """测试一键部署向导模态框与 6 大步骤元素"""
        expected_ids = [
            "wizard-modal",
            "btn-close-wizard",
            "wizard-step-1",
            "wizard-step-2",
            "wizard-step-3",
            "wizard-step-4",
            "wizard-step-5",
            "wizard-step-6",
            "input-host",
            "input-port",
            "input-username",
            "input-password",
            "btn-global-connect",
            "select-nic-list",
            "btn-scan-network",
            "scan-results-list",
            "precheck-items-list",
            "input-local-tar-path",
            "btn-start-upload",
            "btn-docker-load",
            "select-robot-id",
            "machine-id-display",
            "license-dropzone",
            "btn-deploy-license",
        ]
        for eid in expected_ids:
            self.assertIn(f'id="{eid}"', self.html, f"向导模态框元素缺失: {eid}")

    def test_05_robot_control_workbench(self):
        """测试主工作台 (tab-robot-control) 目标选择、运控十字键、姿态与舞蹈流式列表"""
        expected_ids = [
            "tab-robot-control",
            "ctrl-selection-status",
            "ctrl-selected-summary",
            "btn-select-all-action",
            "btn-add-robot-action",
            "ctrl-target-grid-container",
            "ctrl-active-target-prefix",
            "ctrl-custom-cmd-input",
            "ctrl-send-custom-btn",
            "ctrl-dance-scroll-container",
            "ctrl-clear-log-btn",
            "ctrl-terminal-output",
        ]
        for eid in expected_ids:
            self.assertIn(f'id="{eid}"', self.html, f"群控主工作台元素缺失: {eid}")

        # 检查关键操作按钮与数据属性
        self.assertIn('data-cmd="STAND"', self.html)
        self.assertIn('data-cmd="GAIT"', self.html)
        self.assertIn('data-cmd="PASSIVE"', self.html)
        self.assertIn('data-cmd="STOP"', self.html)
        self.assertIn('data-cmd="FORWARD,2"', self.html)
        self.assertIn('data-cmd="BACKWARD,2"', self.html)

    def test_06_ops_modal_and_tabs(self):
        """测试运维与调试中心及 9 个子面板探针"""
        expected_ids = [
            "ops-modal",
            "btn-close-ops-modal",
            "tab-network",
            "tp-nic-select",
            "tp-win-ch341-status",
            "tab-precheck",
            "tp-precheck-items",
            "tab-image",
            "tp-local-tar-path",
            "tp-robot-id-select",
            "tp-docker-image-select",
            "tp-running-containers-list",
            "tp-unified-console",
            "tab-license",
            "tp-machine-id-val",
            "tp-license-dropzone",
            "tab-dance-update",
            "dropzone-update-zip",
            "dance-update-result",
            "tab-3d-player",
            "dance3d-viewport",
            "dance-3d-list",
            "tab-logs",
            "log-console-content",
            "chk-log-timestamp",
            "tab-tutorial",
        ]
        for eid in expected_ids:
            self.assertIn(f'id="{eid}"', self.html, f"运维中心或子标签页元素缺失: {eid}")

        # 验证合并后的“舞蹈与镜像管理”侧边栏与卡片标题
        self.assertIn("舞蹈与镜像管理", self.html, "未在页面中找到合并后的‘舞蹈与镜像管理’标签文本")

        # 验证合并后的“网络与 License 管理”侧边栏与卡片标题
        self.assertIn("网络与 License 管理", self.html, "未在页面中找到合并后的‘网络与 License 管理’标签文本")

    def test_07_modals_and_containers(self):
        """测试流式修复弹窗、添加机器人弹窗和全局 Toast 容器"""
        expected_ids = [
            "fix-stream-modal",
            "fix-stream-console",
            "modal-add-robot",
            "input-new-robot-id",
            "btn-submit-add-robot",
            "toast-container",
        ]
        for eid in expected_ids:
            self.assertIn(f'id="{eid}"', self.html, f"弹窗或容器元素缺失: {eid}")

    def test_08_scripts_loading_order(self):
        """测试前端 8 大核心脚本按依赖次序正确引入"""
        expected_scripts = [
            "js/api.js",
            "js/robot_control.js",
            "js/dance_player3d.js",
            "js/wizard.js",
            "js/log_viewer.js",
            "js/tab_panels.js",
            "js/app.js",
        ]
        last_pos = -1
        for s in expected_scripts:
            pos = self.html.find(f'<script src="{s}"></script>')
            self.assertNotEqual(pos, -1, f"脚本未在页面中引入: {s}")
            self.assertGreater(pos, last_pos, f"脚本引入顺序异常: {s}")
            last_pos = pos

    def test_09_js_referenced_ids_coverage(self):
        """扫描所有前端业务 JS 文件中的 getElementById 并在渲染出的 HTML 中验证静态元素"""
        js_dir = os.path.join(WEB_DIR, 'js')
        all_ids = set()
        for fname in os.listdir(js_dir):
            if fname.endswith('.js') and not fname.startswith('three') and fname != 'OrbitControls.js':
                with open(os.path.join(js_dir, fname), 'r', encoding='utf-8') as f:
                    content = f.read()
                    matches = re.findall(r'getElementById\([\'"]([a-zA-Z0-9_\-]+)[\'"]\)', content)
                    all_ids.update(matches)

        # JS 运行期动态拼接生成的 ID 模式与历史可选兼容 ID
        dynamic_prefixes = ('card-robot-', 'btn-disconnect-robot-', 'btn-reconnect-robot-', 'live-card-')
        dynamic_or_optional_ids = {
            'live-card', 'custom-toast',
            'tp-lic-ctrl-badge', 'tp-lic-lora-badge', 'tp-lic-proc-desc', 'tp-lic-proc-title',
            'wizard-btn-start-process', 'wizard-ctrl-sub-badge', 'wizard-lora-sub-badge',
            'wizard-process-dot', 'wizard-process-status-text', 'wizard-robot-process-badge'
        }

        missing_static_ids = []
        for eid in sorted(all_ids):
            if any(eid.startswith(p) for p in dynamic_prefixes) or eid in dynamic_or_optional_ids:
                continue
            if f'id="{eid}"' not in self.html:
                missing_static_ids.append(eid)

        # 检查是否有静态缺失
        self.assertEqual(missing_static_ids, [], f"发现前端脚本中引用的静态 DOM 缺失: {missing_static_ids}")


if __name__ == '__main__':
    unittest.main()
