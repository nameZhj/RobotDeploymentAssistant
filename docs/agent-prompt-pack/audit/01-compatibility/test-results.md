# Prompt 01 历史兼容性基线与回归测试审计报告

> 执行时间：2026-11-12  
> 执行范围：2026-10-01 前全项目 13 核心功能族自动化契约测试与回归验证

---

## 1. 测试套件执行汇总

| 测试套件 | 执行范围 | 用例数 | 结果 | 耗时 |
|---|---|---|---|---|
| **历史兼容性契约套件 (`tests/compatibility/`)** | 8 大契约模块 (首页、API、串口、SSH/SFTP、License、地图、3D、窗口) | 20 | **20 PASSED (100%)** | 1.08s |
| **全量单元与集成测试 (`tests/`)** | 全工程所有单元测试与集成测试 | 376 | **376 PASSED (100%)** | 9.31s |
| **端到端流程与契约校验 (`tests/verify_choreo_e2e.py`)** | 10 项端到端流程与历史契约 | 10 | **10 PASSED (100%)** | 1.80s |

---

## 2. 覆盖的 13 核心旧功能族验证状态

1. **Flask Web 启动与主页加载**：[PASS] `test_homepage_renders_200`, `test_static_asset_serving`
2. **主页舞台编导入口**：[PASS] `test_homepage_has_single_studio_button`, `test_open_studio_api_success`
3. **机器人设备状态与发现**：[PASS] `test_api_status_contract`
4. **远程控制/遥控命令**：[PASS] `test_fake_serial_open_and_write`
5. **串口与通信协议**：[PASS] `test_serial_dance_parser_syntax`, `test_serial_port_detection`
6. **SSH/SFTP 连接与传输**：[PASS] `test_ssh_credentials_and_connect_mock`, `test_sftp_upload_missing_file`
7. **License/授权校验**：[PASS] `test_license_parser_valid_content`, `test_license_parser_mismatched_machine_id`, `test_license_empty_content`
8. **地图 PCD 解析与坐标转换**：[PASS] `test_pcd_loader_ascii_format`, `test_pcd_loader_rejects_missing_file`
9. **URDF/STL 机器人模型载入**：[PASS] `test_preview_manager_builtin_models`, `test_legacy_g1_urdf_models_exist`
10. **原有 3D 舞蹈/运动预览**：[PASS] `test_preview_manager_model_info`, `test_legacy_preview_manager_loaded`
11. **设备部署与任务流程**：[PASS] `test_legacy_dance_zip_update_no_file`, `test_legacy_dance_zip_update_valid_zip`
12. **用户数据与 SQLite 持久化**：[PASS] `test_p1_domain_and_storage.py`
13. **桌面窗口生命周期与异常恢复**：[PASS] `test_studio_manager_launch_and_close`, `test_studio_window_singleton_lifecycle`

---

## 3. 硬件/环境限制声明 [OBSERVED / UNKNOWN]

- **真机硬件在线通信与串口物理握手**：[NOT RUN / UNKNOWN] 当前无真实 Unitree G1 实体机器人和真实 USB-Serial 转接模块接入，所有物理通信均通过 Fake Transport 契约测试验证。
