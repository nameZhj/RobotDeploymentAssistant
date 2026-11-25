# 仓库结构、分区契约与运行入口

> 何时阅读：定位任何文件、新增模块或启动服务/测试前必读。
> 前置文档：[README.md](README.md)。
> 要点速览：1) 根目录固定三文件夹契约，禁建根级杂项文件；2) 上下位机顶层包名同为 `src`，严格隔离禁互导；3) 区分历史基线保护区与新 `src/` 架构区。

---

## 1. 仓库根目录三分区契约

仓库根目录固定仅包含三个同级业务目录：`upper_computer/`、`lower_computer/`、`ai_execution_plan/`（加 `.git` 与 `.gitignore`）。
- **MUST NOT** 在仓库根目录新增业务目录或根级说明文件（如禁止新增根目录 `AGENTS.md`）。

| 目录 | 责任边界 | 核心入口/关键文件 |
|---|---|---|
| `upper_computer/` | 上位机：Flask 运维后台 + PySide6 编导工作台 | `main.py`（桌面+Web 集成启动）、`app.py`（纯 Web/Flask 入口） |
| `lower_computer/` | 下位机：ROS 1.17.4 桥接、任务链执行、HTTP/LoRa 代理 | `main.py`（`--port 8090`、`--use-navctl-shell`、LoRa 参数） |
| `ai_execution_plan/` | AI 规范、全局符号索引、双端门禁审计与自动化验证 | `verify_deep_closure.py`、`run_all_validation.ps1`、`test_dual_computer_e2e.py` |

---

## 2. 双端内部目录与 `src` 分层职责

### 上位机 `upper_computer/`
- **历史基线区（受 `a5973d4` 保护）**：`app.py`（1337 行，82 个路由）、`main.py`、`backend/`（运维、SSH、LoRa/串口、ZIP/NPZ、HTTP 桥等旧服务）、`web/`（前端静态与模板）、基线 Web/安全测试（`test_all_features.py`、`test_robot_id_and_target.py`）。
- **新架构区（`upper_computer/src/`）**：
  - `core/`：工作区路径（`paths.py`）、YAML 配置（`settings.py`）、日志（`logger.py`）、事件总线（`event_bus.py`）、撤销栈（`undo_stack.py`）。
  - `domain/`：舞台、场景、任务、轨道、轨迹、动作、时间线块、PCD 地图等纯领域实体。
  - `math/`：2D/3D Catmull-Rom 样条、7 段 S 曲线加减速、50FPS 采样、Kabsch SVD 刚体配准。
  - `algorithms/`：队形生成、2-Opt 目标分配、势场避障规划、散点过渡、空间哈希与时间线碰撞检测。
  - `persistence/`：SQLite 10 表引擎（`db_engine.py`, `schema_ddl.py`）、各实体仓储、PCD 解析与栅格生成、UniUni JSON 编解码。
  - `protocol/`：LRMP V1.0-R3 编解码与状态机、Wi-Fi HTTP 客户端（`RobotHttpClient`）、Webhook 回调监听（`HttpCallbackListener`）、SLAM 建图客户端。
  - `services/`：`StudioStateService`、`PlaybackCoordinator` 及 HTTP 调度操作封装（`studio_http_ops.py`）。
  - `ui/`：`choreography`、`common`（`async_task.py`）、`design_system`、`formation`、`mapping`、`modals`、`monitoring`、`shell`、`theme`、`windows`。
  - `viewport3d/`：Unitree G1 29-DOF 运动学链、STL VBO 缓存、3D OpenGL 舞台视口与轨道相机。
- **配置与文档**：`configs/`（`app_settings.yaml`, `lrmp_protocol.yaml`；`user_settings.yaml` 已 gitignore）、`docs/`、`scripts/verify_hygiene.py`、`tests/`（10 个核心测试 + `conftest.py`）。

### 下位机 `lower_computer/`
- `src/config/`：实机 ROS 环境常量（`ros_env_config.py`）与机载配置文件读取（`robot_config_reader.py`）。
- `src/commands/`：`ControlArbiter` 控制权互斥、已知运控执行、复杂动作 `RESERVED_SLOT`、`LoraWifiAgent`、`LoraSerialDaemon`、`SystemOpsService`。
- `src/ros_bridge/`：`NavctlRunner`、动态话题发现、实时 SLAM tap、ROS 话题/TF/服务桥接与深度诊断。
- `src/task_chain/`：到点驱动的任务链状态机与执行器（`TaskChainExecutor`）及真实 HTTP Webhook 回调派发（`WebhookDispatcher`）。
- `src/api/`：`LowerComputerHttpServer` 与 REST 路由分发（`routes.py`, `slam_routes.py`, `system_routes.py`）。
- 参考文件：`lower_computer/下位机ros信息`；测试：`lower_computer/tests/test_lower_computer.py`。

---

## 3. 运行期产物目录（Gitignored）

- 运行期与用户状态 **MUST** 写入 `.agent_workspace/runtime/`（含 `uniuni_studio.db`、日志与用户覆写配置）、`upper_computer/temp_uploads/`、`upper_computer/data/`、`lower_computer/runtime_cache/`。
- **MUST NOT** 在 `upper_computer/` 或 `lower_computer/` 根目录创建 `runtime/`、`cache/`、`installer/`，或提交 `*.db`、`*.pcd`、日志及本地设置文件。

---

## 4. 启动方式与关键避坑

- **启动入口**：
  - 上位机：`ai_execution_plan/start_upper_computer.bat`，或 `cd upper_computer` 后执行 `python main.py` / `python app.py`。
  - 下位机：`ai_execution_plan/start_lower_computer.bat`，或 `cd lower_computer` 后执行 `python main.py --port 8090`（支持 `--use-navctl-shell` 与 LoRa 串口参数）。
  - 运行依赖：Python 3.12、pytest 9.x、PySide6 6.8–6.12；桌面 UI 测试需环境变量 `QT_QPA_PLATFORM=offscreen`。
- **双 `src` 包名冲突**：上下位机顶层包名均叫 `src`。上位机代码 **MUST NOT** 直接导入下位机 `src`（反之亦然）；跨端测试须按 [test_dual_computer_e2e.py](../test_dual_computer_e2e.py) 切换 `sys.path` 与 `sys.modules["src*"]`。
- **过期文档警告**：`upper_computer/README.md` 中的 `src/{core,infrastructure,domain,application,ui}` 与 `scripts/verify_guardrails.py` 为过期残留描述，**MUST NOT** 采信。

## 自检清单

- [ ] 新模块放在正确的 `upper_computer/src/` 或 `lower_computer/src/` 分层目录，未污染根目录
- [ ] 未发生上位机与下位机 `src` 包之间的直接 cross-import
- [ ] 所有运行期数据均指向 `.agent_workspace/runtime/` 或指定忽略目录
