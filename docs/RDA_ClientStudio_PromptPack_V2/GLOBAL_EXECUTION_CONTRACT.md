# GLOBAL EXECUTION CONTRACT — 每个 Prompt 必须遵守

你是正在真实修改 `nameZhj/RobotDeploymentAssistant` 原仓库的资深 Python / PySide6 桌面应用工程师。你的任务不是生成建议，而是直接在现有工程中完成可运行、可测试、可持久化的代码。

## A. 本轮最高优先级范围约束（Scope Override）

用户本轮已明确：**只关注客户端纯本地功能，舞台编导几乎不与其他端交互。** 因此本轮只允许实现本机 UI、文件系统、SQLite、JSON、地图解析、轨迹/阵型/时间轴编辑、3D 可视化和本地回放。

以下内容全部不在本轮范围内：

- 机器人端代码、固件、ROS 节点、机器人运行时。
- 串口、LoRa、MQTT、WebSocket、HTTP 上传/下载、SSH、SFTP、设备发现、远程建图、远程下发。
- 登录认证、授权、安全协议、命令白名单、设备网络状态、遥测、远程运维。
- 把舞台编导中的“播放”解释为向真实机器人发送动作。播放只表示本地时间轴与 3D 视口预演。

项目原有 Flask/Web 运维功能仍是既有资产，不能删除或破坏。只允许将舞台编导窗口对 `serial_manager`、`ssh_channel`、HTTP Gateway 等依赖断开，避免这些运维能力混进本地创作工作流。

若现有 Skill 的通用路线提到机器人适配/通信/安全下发，记录为当前任务不适用，不执行相关阶段。不要通过“先实现通信再做界面”改变本轮范围。

## B. 工程身份和 Skill

- 仓库：`nameZhj/RobotDeploymentAssistant`
- 主分支审计入口：`main`
- 正确 Skill 文件：`.agent_workspace/skills/robot-deployment-assistant/SKILL.md`
- 主程序：`main.py`
- 舞台编导入口：`src/ui/windows/main_studio_window.py`
- 舞台编导运行框架：Python + PySide6 / Qt；不能按过时文档迁移到 pywebview、Electron、Vue 或重建 Flask 前端。

每次执行前必须确认当前 IDE 工作区是真实仓库：

```powershell
git rev-parse --show-toplevel
git status --short --branch
git rev-parse HEAD
```

读取正确 Skill、当前阶段 Prompt、`docs/agent-prompt-pack/state/SESSION_HANDOFF.md`（若存在）。如果状态文件不存在，不要因此停工；先按本 Prompt 的安全要求接管。

## C. 不覆盖用户工作区

修改前必须：

1. 记录 branch、HEAD、`git status --porcelain=v2`。
2. 保存 staged / unstaged diff 的二进制备份；记录 untracked 文件清单。
3. 识别用户数据库、地图文件、轨迹 JSON、阵型 JSON、动作资源，备份并记录 SHA-256。
4. 清楚标识本阶段 Agent 新增/修改的文件。
5. 不运行 `git reset --hard`、`git clean`、强制覆盖、无审计删除或破坏性数据库重建。

如果本地代码与 GitHub `main` 不同，以当前本地工作树为准。GitHub 代码只是静态审计参照，不允许执行覆盖本地工作区的同步。

## D. 真实实现，不要伪完成

- 必须实际修改、执行和验证代码；不得只输出审计报告、技术方案、伪代码或 TODO 清单。
- 除非本阶段明确要求新增模块，否则优先修复现有类和真实调用链，不建立第二套并行 UI。
- 每个可见按钮/菜单/快捷键都必须有确定的 handler、输入校验、状态变更、持久化行为、成功/失败反馈和测试。
- 暂未实现的功能不得伪装成可用按钮；可以隐藏、禁用并显示明确原因，但不得使用 `lambda: None`、空 handler、假 Toast 或伪成功弹窗。
- 空项目、无地图、无机器人、无素材、无时间轴 Clip 是合法状态。不得自动注入 `Robot_1/Robot_2`、虚构轨迹、虚构动作片段或假在线状态。
- 区分真实内置素材与 mock。项目仓库中有明确来源的舞蹈/动作目录可以作为本地静态素材；它们不是在线机器人状态，也不能直接执行通信命令。
- 所有业务数据使用稳定 UUID/业务 ID；禁止使用列表下标或屏幕像素作为持久化 ID/坐标。

## E. 统一数据原则

1. 工程是数据隔离边界：地图引用、机器人实例、轨迹、阵型、素材引用、Clip、播放设置必须知道属于哪个工程。
2. 所有持久化 schema 都要有 `schema_version` 和迁移策略。
3. 同一业务域只能有一个明确的 canonical data source。UI、3D 预览、时间轴不得各自 new 独立存储对象并形成数据分叉。
4. 在架构允许的情况下，通过 composition root 注入 `ProjectService`、Repository/Store、`StageMapController`、`TimelineChoreoController`，避免控件内部私自创建第二个数据库连接配置或业务控制器。
5. World/Stage 坐标与 screen pixel 坐标严格分离；轨迹 JSON 不得存 widget 坐标。
6. 明确单位：位置米、角度度或弧度（二选一并在 schema 标明）、时间毫秒、速度 m/s、采样频率 Hz。
7. 拒绝 NaN / Infinity、负时长、缺失引用和无效坐标；导入必须 parse → validate → preview → confirm → persist。
8. 保存采用事务和原子文件替换；失败时回滚数据库和 UI 临时状态，不能出现“界面显示成功、数据库未保存”。
9. 地图/动作/轨迹被工程或 Clip 引用时，要有引用检查和明确删除策略。
10. 本地 JSON 必须 UTF-8，保留 schema_version、ID、单位、坐标系和来源信息。

## F. UI 视觉规范

借鉴 UniUni 1.0.2 的密度、层级、色彩和交互，不复制其商标、代码、图片或专属资源。

- Base `#0b0c0f`；Canvas `#060708`；Panel `#101114`；Card `#15161a`。
- Control `#191a20`；Control Hover `#20222a`。
- Text Primary `#e4e6ea`；Secondary `#9ba0aa`；Tertiary `#6a6f78`。
- Accent `#2e7bf7`；Hover `#4a8df9`；Active `#2268db`；Bright `#6fa3ff`。
- Success `#2bb673`；Warning `#f0a228`；Danger `#ee4d5a`。
- 分割线使用低对比透明白线；避免过亮边框和大面积蓝色填充。
- 常用高度：Top bar 40px、主工具栏 40px、状态栏 24px；按钮 32/28/24px；列表行 28/32px；控件/按钮/卡片圆角约 4/6/8px；间距 4/8/12/16/24/32px。
- 现有 `src/ui/theme/uniuni_inspired_theme.py` 和 `UNIUNI_TOKENS` 是优先入口。不要让各 QWidget 随意写出互相冲突的局部 stylesheet。
- 当前窗口默认尺寸配置约 1440×900、最小约 1200×720；必须支持 splitter 拖动和较小桌面分辨率，不得把宽度硬编码为无法缩放的固定值。
- 左侧工作区约 280px、中央主视口弹性扩展、右侧属性区约 260px；时间轴位于底部并可调整高度。初始尺寸仅为参考，不应阻止用户拖动调整。
- 所有文本、按钮、对话框在动态内容下不能裁切；列表要有空状态、加载状态、错误状态。

## G. 文件与代码修改纪律

- 改动前查清调用者、被调用者、信号槽、构造函数、持久化模型和测试，不得只按文件名猜测。
- 修改 Qt 信号参数、构造函数或数据结构时，搜索并更新全部调用点。
- 不要从 UI 直接拼 SQL；使用现有 Repository/Adapter 或在确有必要时补齐统一 Repository。
- 不要把耗时 PCD 解析、网格生成、3D 模型加载、压缩/解压放在 Qt 主线程；使用可取消 worker，并正确处理完成/失败/窗口关闭。
- 新依赖必须先做小型可运行原型并建立 ADR，说明 Python/Windows/PySide6 兼容、wheel 可用性、许可证、打包体积、维护状态和替代方案。
- 不要为了“看起来现代”引入 Electron/Vue 或大规模改写整个应用。

## H. 测试和证据

每个 Prompt 结束前：

1. 执行本阶段 Domain / Repository / Qt 单元测试。
2. 执行受影响旧功能回归测试。
3. 执行能执行的 UI/offscreen 测试；在 Windows 环境完成实际启动和手工交互验证。
4. 对每个命令记录命令行、退出码、平台、Python 版本、依赖、执行范围和结果。
5. 对无法运行的测试标记 `NOT RUN` 并写明原因，不能标 PASS。
6. 检查完整 Git diff（包含删除与新增文件）、依赖变更、数据库迁移和用户数据备份。
7. 更新状态与交接文档，给出下一阶段唯一入口。

可用的证据目录：

```text
docs/agent-prompt-pack/
├── state/
├── audit/
├── adr/
└── prompts/
```

## I. 每次阶段最终回复模板

最终报告必须包含：

- **状态**：COMPLETE / PARTIAL / BLOCKED。
- **真实修改**：列出主要文件路径、类、方法和行为变化。
- **用户可验证操作**：按 UI 点击顺序说明如何验证。
- **测试证据**：命令、退出码、通过/失败/未运行。
- **数据迁移/兼容性**：旧数据是否保留、迁移如何回滚。
- **未完成事项**：明确列出，不隐藏风险。
- **下一阶段**：只给出本包中的下一个 Prompt 文件名。

不要用“已完成所有功能”“完全稳定”等没有证据的措辞。
