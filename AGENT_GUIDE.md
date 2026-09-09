# VSISLAB 机器人部署与群控系统 - AI Agent 开发与维护指南 (AGENT_GUIDE.md)

> **定位说明**：本文档专供后续接入本项目的 AI Coding Agent 阅读。它系统化归纳了本仓库的架构全景、组件索引、数据协议与修改守则，便于 Agent 在极短上下文开销下完成精准定位、安全修改与自动化闭环验证。

---

## 1. 系统全景与技术栈 (Architecture Overview)

本项目是针对 **宇树 (Unitree) G1 / Go2** 人形与四足机器人的商业化部署助手与无线多机群控调度系统。

```mermaid
graph TD
    A[前端 UI 界面: Jinja2 + Vanilla JS/CSS] <-->|REST API + SSE 任务流| B[Flask 后端网关: app.py]
    B <-->|串口驱动 CH341| C[USB-LoRa 广播发射器]
    B <-->|Paramiko SSH / SFTP| D[机器人宿主机 Ubuntu]
    C -.->|无线广播 TARGET|COMMAND\n| E[机器人端 lora_recv 进程]
    D -->|Docker 固化容器| F[vsis_g1: 运控与跳舞程序 g1_ctrl_vsis]
    E -->|本地 FIFO / Socket| F
```

### 核心技术栈
- **后端框架**：Python 3.10+ / Flask / Flask-CORS / Paramiko (SSH/SFTP) / PySerial / PyInstaller
- **前端架构**：服务端 Jinja2 模块化拼装 (`render_template`) + 原生 Vanilla JS (ES6) + 原生 CSS (暗黑科技风格) + Three.js (3D 动作骨骼预览)
- **桌面端封装**：`main.py` 通过 `pywebview` 唤起原生 Windows 窗口（若不可用自动降级至系统浏览器）
- **打包机制**：`build_package.py` 一键构建独立单文件 EXE (`dist/VSISLAB机器人部署助手.exe`)

---

## 2. 前端组件化架构与文件索引 (Frontend Component Index)

重构后，前端已从单体 1,661 行解耦为高内聚的组件树。修改任何 UI 时，**严禁修改不存在的单体 HTML，请按以下索引精准定位修改子组件**：

```
web/
├── index.html                   # 主模板入口 (极简结构，负责按需 include 各子组件)
├── components/                  # 核心组件目录
│   ├── head.html                # 页面 Head (Meta, CSS, Three.js 脚本与 fallback)
│   ├── navbar.html              # 顶部导航栏 (Logo, LoRa 连接徽章, 向导按钮, 综合设置菜单)
│   ├── wizard_modal.html        # 6 步一键自动化部署向导独立模态窗
│   ├── tab_robot_control.html   # 首页主工作台: 机器人编队卡片流, 姿态网格, 十字移动键, 舞蹈流式列表, TX 终端
│   ├── ops_modal.html           # 运维与调试中心外层模态弹窗 (左侧导航栏 + 包含 9 个子面板)
│   ├── ops_tabs/                # 运维中心 9 大功能子标签页
│   │   ├── tab_network.html     # 设备发现、Windows 以太网卡直连 (192.168.123.200) 与 CH341 驱动
│   │   ├── tab_precheck.html    # 机器人宿主机环境指标深度预检与修复
│   │   ├── tab_image.html       # Docker 镜像 SFTP 上传、docker load、容器启动与机载程序状态
│   │   ├── tab_license.html     # 64 位硬件机器码读取与 License 拖拽导入
│   │   ├── tab_dance_update.html# 舞蹈动作包 (.zip / 文件夹) 上传热覆盖与自动重启
│   │   ├── tab_3d_player.html   # Three.js 50fps 机器人 3D 骨骼物理仿真与 NPZ 动作库
│   │   ├── tab_logs.html        # 实时日志监视器 (容器、LoRa、运控、内核 dmesg) 与智能诊断
│   │   ├── tab_manual.html      # 远程 Bash 手动命令行控制台
│   │   └── tab_tutorial.html    # 物理遥控器图解与现场指令操作规范表
│   ├── modals.html              # 驱动修复流式日志弹窗, 添加机器人 ID 弹窗, 全局 Toast 容器
│   └── scripts.html             # 前端所有底层业务脚本引用 (依赖次序敏感)
├── css/
│   └── style.css                # 全局样式系统 (暗黑科技风格、CSS 变量、流式布局)
└── js/                          # 前端业务控制器 (详见下节)
```

---

## 3. 前端控制器与 DOM 绑定映射表 (JS Controllers & DOM Mapping)

每个子组件均由特定的 JavaScript 模块进行事件监听与状态驱动，修改 DOM 时务必保证对应的 ID 存在：

| 组件文件 | 对应 JS 控制器 | 核心 DOM ID 探针 | 关键职责 |
| :--- | :--- | :--- | :--- |
| `navbar.html` | `app.js` / `robot_control.js` | `#ctrl-serial-status-badge`, `#status-dot`, `#btn-open-wizard`, `#btn-open-ops-modal` | 串口状态药丸展示、SSH 连接状态、打开向导与设置菜单 |
| `wizard_modal.html` | `wizard.js` | `#wizard-modal`, `#wizard-step-[1-6]`, `#btn-global-connect`, `#license-dropzone` | 引导用户逐步完成机器人网络、环境、镜像、自启动和 License 导入 |
| `tab_robot_control.html` | `robot_control.js` | `#ctrl-target-grid-container`, `#ctrl-dance-scroll-container`, `#ctrl-terminal-output` | 多机编队多选 (Ctrl+左键)、W/A/S/D 移动 (5Hz 持续长按)、舞蹈按钮流式自适应、TX 监视器 |
| `tab_network.html` | `tab_panels.js` (`TabNetwork`) | `#tp-nic-select`, `#btn-scan-network`, `#tp-scan-results` | Windows 本机网卡切换静态 IP、CH341 串口驱动安装、网段扫描 |
| `tab_precheck.html` | `tab_panels.js` (`TabPrecheck`) | `#tp-precheck-items`, `#btn-tp-fix-ch341` | 检查宿主机 Docker、驱动、权限并提供一键修复 |
| `tab_image.html` | `tab_panels.js` (`TabImage`) | `#tp-local-tar-path`, `#tp-robot-id-select`, `#tp-running-containers-list` | SFTP 大文件上传、`docker load`、写入自启动与启动 `vsis_g1` |
| `tab_license.html` | `tab_panels.js` (`TabLicense`) | `#tp-machine-id-val`, `#tp-license-dropzone`, `#tp-deploy-btn` | 读取 64 位 Machine ID、拖拽校验 License 并生效 |
| `tab_dance_update.html` | `tab_panels.js` (`TabDanceUpdate`) | `#dropzone-update-zip`, `#dance-update-result` | 导入新动作包解压至 `/secure/config_vsis` 并热重启 |
| `tab_3d_player.html` | `dance_player3d.js` | `#dance3d-viewport`, `#dance-3d-list`, `#btn-dance-play` | Three.js 骨骼仿真渲染、动作帧播放与 NPZ 本地解析 |
| `tab_logs.html` | `log_viewer.js` | `#select-log-container`, `#log-console-content`, `#chk-log-timestamp` | 实时拉取并格式化高亮机器人运行日志、每行时间戳解析对齐与开关 |
| `tab_manual.html` | `manual_mode.js` | `#manual-cmd-list`, `#manual-console-output` | 常用运维脚本一键执行与自定义 Bash 命令执行 |

---

## 4. 后端接口与核心通信协议 (Backend & Protocols)

### 4.1 LoRa 串口群控协议规范 (Serial Command Protocol)
- **物理介质**：USB 转 TTL / CH340 / CH341 串口适配器，默认波特率 `9600` 或 `115200`。
- **寻址格式**：
  $$\text{TARGET} \mid \text{COMMAND} \backslash\text{n}$$
  - `TARGET`：目标机器人机身标识。
    - **单机受控**：`A|COMMAND\n`
    - **多机/全选编队**：采用逗号 `,` 隔开对应机器人标识（如 `A,B|COMMAND\n`、`A,B,C|COMMAND\n`），**全选时不再发送 ALL，多选也不必循环多次下发，统一以逗号隔开一次性下发**。
    - **广播保留字**：`ALL` 仅保留用于系统级广播查询（如 `ALL|GETDANCELIST\n`）或极端情况下的全网紧急停机。**严禁用户将单机 ID 命名为 ALL**。
  - `COMMAND`：控制动作字或参数。
- **常用核心指令集**：
  - `TARGET|STAND\n`：进入 FixStand 站立状态（按键映射：1）
  - `TARGET|GAIT\n`：激活 RL_MJAMP 步态（按键映射：2）
  - `TARGET|PASSIVE\n`：趴下卸力保护（按键映射：0）
  - `TARGET|STOP\n`：步态复位 / 软停（按键映射：X，发送 GAIT 保持平衡）
  - `TARGET|FORWARD,2\n` / `TARGET|BACKWARD,2\n`：前后移动
  - `TARGET|MOVE_LEFT,2\n` / `TARGET|MOVE_RIGHT,2\n`：左右平移
  - `TARGET|TURN_LEFT,1\n` / `TARGET|TURN_RIGHT,1\n`：原地旋转
  - `TARGET|DANCE,<ALIAS>\n`：触发特定舞蹈动作（如 `TARGET|DANCE,G1_TIKTOK\n`）
  - `ALL|GETDANCELIST\n`：串口请求机器人回传动作配置列表

### 4.2 机器人宿主机固化规范
- **Robot ID 存放路径**：`/home/ubuntu/vsis_mimic_deploy/group/lora_robot_id.txt`
- **自启动挂载脚本**：`/docker_config/custom_startup.sh`
- **机载主程序启动链**：`/home/ubuntu/vsis_mimic_deploy/run_bg.sh` -> 启动 `g1_ctrl_vsis` 与 `lora_recv`

### 4.3 驱动与下位机注入公共架构 (backend.drivers)
为了避免在业务代码中硬编码底层 Shell 指令与配置字符串，系统将所有注入到下位机的命令、C++ 容灾热补丁及守护脚本抽取至独立模块统一分类管理：
- `backend/drivers/commands.py`：
  - **Linux 驱动探测与加载**：`CH341_DEV_PROBE_CMD`, `CH341_ALL_SERIAL_DEVS_CMD`, `CH341_LSMOD_CMD`, `CH341_MODINFO_CMD`, `CH341_MODPROBE_CMD`
  - **Linux 驱动在线编译流水线**：`CH341_LINUX_BUILD_PIPELINE`（包含 7 阶段标准构建流程）
  - **udev 规则与权限**：`UDEV_RULES_PATH`, `UDEV_RULES_CONTENT`, `UDEV_RELOAD_CMD`, `USER_GROUPS_CMD`, `CHMOD_DEV_NODES_CMD`
  - **YAML 配置加固**：`YAML_DISABLE_USB_RESET_CMD`
  - **C++ 多端口自适应热补丁**：`LORA_SERIAL_SRC_REMOTE_PATH`, `BULLETPROOF_SERIAL_CPP_PATCH`, `LORA_SERIAL_RECOMPILE_CMD`
  - **开机与保活守护脚本**：`RUN_BG_REMOTE_PATH`, `RUN_BG_SCRIPT_TEMPLATE`, `RUN_BG_SYNC_AND_CHMOD_CMD`, `START_LORA_DAEMON_CONTAINER_CMD`
  - **Windows 驱动文件名**：`WINDOWS_DRIVER_FILENAMES`
- `backend/drivers/ch341_manager.py`（单例 `ch341_manager`）：
  - `find_windows_driver_path()` / `check_windows_driver()` / `install_windows_driver()`
  - `check_linux_driver_status()` / `compile_and_install_linux_driver()`
  - `setup_udev_and_permissions()` / `disable_usb_reset()`
  - `patch_and_recompile_lora_serial()` / `deploy_run_bg_script()`
- `backend/deployment_core.py` 内部全面代理复用上述公共方法，严禁重复编写相似 Shell 与脚本拼装代码。

### 4.4 机器人命名安全规范与公共校验方法 (Robot ID Validation)
为避免在 Shell 拼装与串口下发中发生命令注入、路径穿越或协议歧义，系统强制执行全局统一的 Robot ID 校验：
- **合法字符集白名单**：仅允许 1~20 位英文字母、数字、下划线 `_` 和短横线 `-`（正则表达式：`^[A-Za-z0-9_-]{1,20}$`）。
- **严格拦截规则**：
  1. 严禁为空或纯空格；
  2. 严禁为保留关键字 `ALL`（大小写不敏感）；
  3. 严禁包含逗号 `,`（已用于群控多机分隔）与竖线 `|`（串口指令分隔符）；
  4. 严禁包含空格、引号、分号、反引号、美元符、斜杠等特殊字符。
- **公共方法索引**：
  - **前端**：`window.validateRobotId(rawId)` / `API.validateRobotId(rawId)`（定义于 `web/js/api.js`，供添加机器人、镜像容器管理、部署向导共同复用）。
  - **后端**：`backend.deployment_core.validate_robot_id(robot_id)`（供自启动配置、环境预检与 API 端点共同复用）。

---

## 5. Agent 开发维护准则与自检清单 (Rules & Checklist for Agents)

作为 Agent，在承接本项目的新需求或缺陷修复时，**必须严格遵守以下原则**：

### 5.1 不可违反的行为边界
1. **绝不退回到单体 HTML**：任何前端结构修改必须定位到 `web/components/` 或 `web/components/ops_tabs/` 对应的子组件，主入口 `web/index.html` 保持简洁的 include 结构。
2. **严禁修改既有 DOM ID**：前端各 JS 模块均采用 `document.getElementById` 直接获取元素。修改或优化样式时，**绝对不能改动或遗漏原有的 ID**。
3. **下位机指令统一管理**：严禁在控制器中直接拼接硬编码的底层 Shell 命令或脚本，必须在 `backend.drivers.commands` 中分类归档。
4. **命名统一公共校验**：涉及机器人命名的位置必须统一调用 `validateRobotId`，杜绝绕过校验。
5. **严禁在自动化执行中调用浏览器**：用户明确约束严禁启动可视化浏览器测试。必须使用 Python 自动化测试脚本通过 HTTP 请求与 DOM 树断言进行无头验证。
6. **资源与事件安全**：所有异步轮询（如串口状态、日志监控）必须在页面隐藏或组件卸载时正确清理定时器，避免内存泄漏。

### 5.2 修改后必跑的自动化验证指令
在向用户交付成果前，在命令行中执行以下回归测试套件，必须确保 100% 通过：

```bash
# 1. 目标控制逗号分隔与安全命名校验测试 (5 项测试)
python tests\test_robot_id_and_target.py

# 2. 驱动管理与下位机注入公共方法测试 (11 项测试)
python tests\test_driver_manager.py

# 3. 前端组件解耦与 DOM 探针完整性测试 (9 项测试)
python tests\test_frontend_structure.py

# 4. 系统核心功能、API 与串口解析测试 (6 项测试)
python tests\test_all_features.py

# 5. 全局全量单元测试套件 (40 项测试)
python -m unittest discover -s tests -p "test_*.py"
```

### 5.3 生产打包与构建说明
若修改了 Python 依赖或新增了打包资源，必须在 `build_package.py` 中维护 `--hidden-import`，并执行：
```powershell
python build_package.py
```
打包产物将自动输出到 `dist/VSISLAB机器人部署助手.exe`。
