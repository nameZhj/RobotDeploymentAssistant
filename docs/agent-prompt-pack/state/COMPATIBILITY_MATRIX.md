# 历史功能兼容性与行为契约保护矩阵 (2026-10-01 保护边界)

> 最后更新：2026-11-12  
> 状态：全量 13 功能族已验证并建立自动化回归保障

---

## 1. 保护原则与契约边界

依据 `.agents/skills/robot-deployment-assistant/SKILL.md`：
- Git 记录中 **2026-10-01（含）之前** 已经正确实现的功能必须保持行为兼容。
- 允许修改旧文件以适配架构演进，但必须维护既有接口、数据格式、通信协议和用户工作流。

---

## 2. 13 核心旧功能族兼容性矩阵

| ID | 业务域 / 旧功能族 | 最早证据提交 (2026-10-01 前) | 主要入口文件 | 核心实现文件 | 外部依赖 | 输入契约 | 输出契约 | 当前状态 | 自动化回归测试 | 兼容风险与防范措施 |
|---|---|---|---|---|---|---|---|---|---|---|
| **LEGACY-001** | Flask Web 启动与主页加载 | `55a4c89` (2026-09-09) | `app.py::index` | `web/index.html` | Flask 3.1.3 | HTTP GET `/` | 200 OK + HTML | **PASS** | `test_homepage_renders_200`, `test_static_asset_serving` | 低；已配置无缓存防抖 |
| **LEGACY-002** | 主页舞台编导入口链路 | `55a4c89` (2026-09-09) | `navbar.html` | `app.py::open_studio_route` | PySide6 | POST `/api/system/open-studio` | JSON `success: true` | **PASS** | `test_homepage_has_single_studio_button`, `test_open_studio_api_success` | 低；已验证单例复用 |
| **LEGACY-003** | 机器人设备状态与发现 | `eacb1f6` (2026-09-02) | `app.py::get_status` | `backend/network_manager.py` | Socket, SSH | GET `/api/status` | JSON 状态报文 | **PASS** | `test_api_status_contract` | 低；离线回退保护 |
| **LEGACY-004** | 远程控制/遥控命令下发 | `eacb1f6` (2026-09-02) | `app.py::send_serial_cmd` | `backend/serial_manager.py` | PySerial | JSON `target`, `command` | 字节帧发送成功 | **PASS** | `test_fake_serial_open_and_write` | 低；Fake Transport 隔离 |
| **LEGACY-005** | 串口与通信协议解析 | `0bbc74a` (2026-08-31) | `backend/serial_manager.py` | `serial_dance_parser.py` | PySerial | 串口 YAML/字符串 | 动作组结构化列表 | **PASS** | `test_serial_dance_parser_syntax`, `test_serial_port_detection` | 低；语法解析已固化 |
| **LEGACY-006** | SSH/SFTP 运维与文件传输 | `eacb1f6` (2026-09-02) | `backend/ssh_client.py` | `backend/ssh_client.py` | Paramiko | IP, 端口, 用户名, 密码 | 连接建立/文件上传 | **PASS** | `test_ssh_credentials_and_connect_mock`, `test_sftp_upload_missing_file` | 低；无生产凭据泄露 |
| **LEGACY-007** | License 授权与机器码匹配 | `41f4ba1` (2026-08-28) | `backend/license_parser.py` | `backend/license_service.py` | Base64, JSON | License JSON/B64 | 授权有效性与机器码匹配 | **PASS** | `test_license_parser_valid_content`, `test_license_parser_mismatched_machine_id` | 低；加密算法严格保持 |
| **LEGACY-008** | 地图 PCD 解析与坐标转换 | `be5eba7` (2026-08-25) | `src/core/pcd_loader.py` | `src/core/pcd_loader.py` | NumPy | PCD 文件路径 (ASCII) | 点云坐标数组与边界 | **PASS** | `test_pcd_loader_ascii_format`, `test_pcd_loader_rejects_missing_file` | 低；无 C++ 扩展依赖 |
| **LEGACY-009** | URDF/STL 机器人模型载入 | `a5973d4` (2026-09-11) | `backend/preview_manager.py` | `assets/models/g1_avatar/` | URDF/XML | URDF 路径 | 刚体链接与关节字典 | **PASS** | `test_preview_manager_builtin_models`, `test_legacy_g1_urdf_models_exist` | 低；资产只读保护 |
| **LEGACY-010** | 原有 3D 舞蹈/运动预览 | `efbab2c` (2026-09-10) | `backend/preview_manager.py` | `preview/` | Three.js / Web | 舞蹈 NPZ/ZIP | 关节姿态关键帧流 | **PASS** | `test_preview_manager_model_info`, `test_legacy_preview_manager_loaded` | 低；单例缓存优化 |
| **LEGACY-011** | 设备部署向导与升级任务 | `41f4ba1` (2026-08-28) | `app.py::update_dance` | `backend/dance_updater.py` | ZipFile | 包含动作文件的 ZIP | `task_id` 与执行状态 | **PASS** | `test_legacy_dance_zip_update_no_file`, `test_legacy_dance_zip_update_valid_zip` | 低；临时目录安全解压 |
| **LEGACY-012** | 用户数据与 SQLite 持久化 | `be5eba7` (2026-08-25) | `src/core/storage_manager.py` | `data/choreo_database.db` | SQLite 3 | 场景、轨迹、阵型对象 | 数据库事务写入与原子快照 | **PASS** | `test_p1_domain_and_storage.py` | 低；已消除多库表冲突 |
| **LEGACY-013** | 桌面窗口生命周期与异常恢复 | `be5eba7` (2026-08-25) | `main.py::StudioWindowManager` | `MainStudioWindow` | PySide6 | 窗口唤起/关闭事件 | 安全销毁与无崩溃二次唤起 | **PASS** | `test_studio_manager_launch_and_close`, `test_studio_window_singleton_lifecycle` | 低；已验证生命周期安全 |
