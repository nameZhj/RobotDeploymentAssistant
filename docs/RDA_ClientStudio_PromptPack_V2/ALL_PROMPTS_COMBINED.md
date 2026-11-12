# RobotDeploymentAssistant Client Studio Prompt Pack V2（合并版）

> 合并版便于全文检索；实际执行仍建议每次只使用全局执行约束 + 单个阶段 Prompt。


---

<!-- SOURCE: README.md -->

# RobotDeploymentAssistant：客户端舞台编导功能 Prompt Pack V2

**版本**：2.0  
**审计基线**：GitHub `nameZhj/RobotDeploymentAssistant` 的 `main` 分支，2026-11-12 重新读取  
**目标**：把现有 PySide6 舞台编导窗口改造成真正可用的本地创作工具，而不是另起一个 Demo、只写设计文档，或只修改颜色和标题。

## 本包解决什么问题

本包针对当前仓库中已经存在的舞台编导模块编写。它不是通用软件需求模板。Prompt 直接引用现有类、构造函数、方法和调用路径，并要求 Agent 对现有代码进行增量修复和功能实现。

最终本地客户端应当支持：

1. 本地工程创建、打开、保存、另存为、导入、导出和最近工程恢复。
2. 本地 PCD 地图导入、校验、解析、管理、加载、卸载、重命名、导出、删除；同一张地图同时进入 2D 舞台和 3D 视口。
3. 单机器人/多机器人实例管理与 2D 轨迹绘制、控制点编辑、样条预览、保存、JSON 导入导出和重现。
4. 阵型模板设计、机器人成员配置、位置/朝向计算、安全间距提示、保存和应用到舞台。
5. 舞蹈/动作/轨迹/阵型素材的统一本地素材库、搜索、详情、预览和拖放。
6. 双层时间轴：按机器人/群组分轨，动作层与轨迹层分层，拖放、移动、拉伸、吸附、播放头、撤销/重做、保存。
7. 基于项目真实数据的 3D 可视化预演和确定性播放；不把可视化预演宣传成动力学仿真。
8. 统一的 UniUni 1.0.2 深色工作台观感，以及完整的交互、数据持久化和回归验收。

## 当前执行范围的特别说明

**本轮只开发舞台编导客户端的纯本地功能。** 不开发、不联调、不审查、不重构机器人端或服务端通信，不做 LoRa/串口/MQTT/HTTP 上传/SSH/SFTP/认证/授权/安全下发/远程建图/设备遥测/机器人指令派发。不得把这些内容重新引入舞台编导工作区作为本轮验收项。

项目原有 Flask Web 部署与运维功能属于既有系统，原则上保持不变。本轮只允许解除舞台编导页面对运维通信组件的耦合；不得顺带删除、重写或破坏系统其他页面已有的设备管理能力。

## 重要：Skill 路径已重新确认

项目中的 Skill 正确路径是：

`/.agent_workspace/skills/robot-deployment-assistant/SKILL.md`

不是 `/.agents/skills/...`。请 Agent 每次开始时读取正确路径。该 Skill 是工程保护规则；如其中“机器人适配、通信与安全下发”等通用长期路线与本包的当前项目范围冲突，以用户本轮明确的“只做客户端纯本地创作功能”为本轮范围约束，记录为 Scope Override，不执行通信相关阶段。

## 推荐执行顺序

按编号顺序逐个执行，一次只执行一个 Prompt：

- `P00`：接管已执行 00–05 的工作区，修复主窗口数据注入、职责边界和核心链路。
- `P01`：本地工程、项目数据模型和持久化。
- `P02`：地图管理与 PCD 工作区。
- `P03`：机器人实例管理与 2D 轨迹编辑。
- `P04`：阵型设计与舞台应用。
- `P05`：统一素材库与拖放数据契约。
- `P06`：双层时间轴、播放头、撤销重做和持久化。
- `P07`：真实 3D 可视化预演。
- `P08`：端到端集成、视觉验收、回归和发布检查。

不要跳过 P00，也不要把多个 Prompt 合并成一个大重构。每个 Prompt 必须实际修改代码、执行测试、写入证据并更新 handoff，不得只输出分析报告。

## 目录结构

```text
RDA_ClientStudio_PromptPack_V2/
├── README.md
├── PROMPT_INDEX.md
├── GLOBAL_EXECUTION_CONTRACT.md
├── PROJECT_AUDIT_BASELINE.md
├── RELEASE_ACCEPTANCE_CHECKLIST.md
├── prompts/
│   ├── P00_WORKSPACE_RECOVERY_AND_WIRING.md
│   ├── P01_LOCAL_PROJECT_AND_DATA_MODEL.md
│   ├── P02_LOCAL_MAP_AND_PCD_WORKSPACE.md
│   ├── P03_ROBOT_REGISTRY_AND_2D_TRAJECTORY.md
│   ├── P04_FORMATION_DESIGN.md
│   ├── P05_ASSET_LIBRARY_AND_DRAG_DROP_CONTRACT.md
│   ├── P06_DUAL_LAYER_TIMELINE.md
│   ├── P07_REAL_3D_PREVIEW.md
│   └── P08_END_TO_END_INTEGRATION_AND_ACCEPTANCE.md
└── references/
    └── UNIUNI_DESIGN_TOKENS.md
```

## 如何使用

1. 在 Windows 开发机打开真实 `RobotDeploymentAssistant` Git 仓库，而不是 Prompt Pack 解压目录。
2. 确认 Prompt Pack 已经放在可访问的位置；不需要把 Prompt Pack 自动复制进仓库，除非你希望自行纳入版本管理。
3. 将 `GLOBAL_EXECUTION_CONTRACT.md` 和当前阶段 Prompt 一起交给 Coding Agent，或让 Agent 明确读取这两个文件。
4. 每完成一个 Prompt，先检查 Agent 生成的 `SESSION_HANDOFF.md`、测试报告和 Git diff，再执行下一个阶段。
5. 若本地工作区与 GitHub `main` 已不同，以本地真实工作区和用户未提交修改为准；GitHub 审计只作为定位线索，不是覆盖本地代码的理由。

## 不要接受的“完成”

- 只改 CSS、颜色、标题、图标，却没有接通真实功能。
- 只新增一套平行窗口/平行数据模型，旧窗口仍然坏着。
- 使用固定 `Robot_1/Robot_2`、固定轨迹、固定时间轴 Clip 假装项目已经有数据。
- 拖拽时能看到一个色块，但保存后重启消失，或 3D 播放器读取的不是同一份 Clip。
- 地图只显示在某一视图，而 2D/3D 使用不同地图数据或不同坐标变换。
- 测试只覆盖 Domain 函数，却声称 Qt 真实交互通过。
- 以“当前环境没安装 PySide6”为由不做静态、单元和可运行的替代验证；也不得把未运行的 Qt 集成测试标成通过。
- 只交付审计报告或架构设计，没有实际实现代码。


---

<!-- SOURCE: GLOBAL_EXECUTION_CONTRACT.md -->

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


---

<!-- SOURCE: PROJECT_AUDIT_BASELINE.md -->

# 项目审计基线（GitHub main 静态代码审计）

**检查日期**：2026-11-12  
**仓库**：`nameZhj/RobotDeploymentAssistant`  
**读取来源**：GitHub `main` 分支文件；未在本次审计环境中启动 Windows Qt 应用。以下是源码观察，不是运行时验证。

## 1. Skill 路径更正

已重新成功读取：

`.agent_workspace/skills/robot-deployment-assistant/SKILL.md`

Blob SHA：`b826e79af37d65d5fe92505b6ec7cb7cf2337871`

此前检查 `.agents/skills/...` 是路径写错；不能再声称 Skill 未进入仓库。

## 2. 舞台编导实际入口

- `main.py` 的 `StudioWindowManager` 延迟创建 `QApplication`，并实例化 `src.ui.windows.main_studio_window.MainStudioWindow`。
- 舞台编导使用 PySide6，不是 `AGENT_GUIDE.md` 中所描述的 pywebview 渲染窗口。
- `AGENT_GUIDE.md` 的系统总览混合了过时/其他系统结构，执行舞台编导任务时应先以真实 import、调用栈和当前源码为准；不要直接按文档重建。

## 3. 当前确认的问题（必须在本地分支复核）

### 3.1 MainStudioWindow 的依赖未统一注入

文件：`src/ui/windows/main_studio_window.py`

- `__init__` 创建 `self.store = ChoreoSqliteStore()` 和 `self.map_controller = StageMapController(...)`。
- `_build_layout()` 创建 `LeftDockTabs(..., controller=self.controller)`，而不是显式传 `self.map_controller` 和本地 Store/Project Context。
- `_init_choreo_studio()` 创建 `StageCanvas2D(..., controller=self.controller)`，没有传 `store=self.store`。
- `LeftDockTabs.__init__` 只有 `controller` 参数；内部通过 `getattr(self.controller, "map_controller", None)` 找地图控制器。如果 `controller` 为 `None`（`main.py` 当前创建 MainStudioWindow 时没有传这个 controller），`MapManagerPanel` 会自行构造新的 `StageMapController`。
- `StageCanvas2D` 的 `self.store` 只取显式 `store` 或 `controller.store`；当前主窗口调用没有显式注入 store。

结论：主窗口创建的 `self.map_controller` 未形成明确共享链路；地图面板、画布、时间轴和预览服务的依赖来源不够明确。P00 必须修复。

### 3.2 时间轴控制器单独创建

文件：
- `src/ui/choreo_page/dual_layer_timeline_canvas.py`
- `src/application/stage_director/timeline_choreo_controller.py`
- `src/infrastructure/storage/timeline_clip_sqlite_adapter.py`

`DualLayerTimelineCanvas.__init__` 内部执行 `TimelineChoreoController()`，无法由 MainStudioWindow 传入统一 Project/Store。它当前使用默认 `data/choreo_database.db`，虽然路径与 `ChoreoSqliteStore.DEFAULT_DB_PATH` 一致，但控制器实例、任务名、项目上下文和数据生命周期都没有显式统一。

### 3.3 素材拖放的数据类型存在不匹配风险

文件：
- `src/ui/asset_library.py`
- `src/core/asset_registry.py`
- `src/ui/choreo_page/dual_layer_timeline_canvas.py`
- `src/application/stage_director/timeline_choreo_controller.py`

`AssetRegistry` 输出字段使用 `category`（`dance`、`action`、`trajectory`、`formation`）；`DraggableAssetListWidget.startDrag()` 将完整 dict 写入 MIME；时间轴控制器 `create_clip_from_dropped_asset()` 首先读取 `asset_type` 并转大写，用其判断 ACTION/DANCE/TRAJECTORY。若拖入的数据没有 `asset_type`，动作/舞蹈可能走默认轨迹分支。必须建立一个显式、版本化的 MIME/Clip 适配契约，不允许依赖偶然字段。

### 3.4 时间轴编辑状态可能与持久化状态脱节

`DualLayerTimelineCanvas.mouseMoveEvent()` 直接修改 `_dragged_block.start_ms` 或 `_resizing_block.duration_ms`；`mouseReleaseEvent()` 再调用控制器 `move_clip()` / `resize_clip()`，但当前调用方没有依据返回值进行 UI 回滚。数据库更新失败时，需要恢复旧值、提示用户并重载真实状态。

### 3.5 默认演示机器人数据

文件：
- `src/ui/stage3d/stage_viewport_3d.py`
- `src/application/services/virtual_show_player.py`
- `src/application/stage_director/stage_preview_coordinator.py`

当前 3D 视口构造时初始化 `Robot_1`、`Robot_2` 的颜色与位姿；`VirtualShowPlayer._init_default_tracks()` 初始化两台机器人轨迹和动作；`StagePreviewCoordinator` 默认 `load_defaults=True` 并生成相似数据。即使主窗口后面清空部分 UI 轨道，预览对象仍可能从内部默认值显示出来。正式空项目必须真实为空。

### 3.6 右侧面板含通信/运控功能

文件：`src/ui/choreo_page/right_dock_panel.py`

`RightDockPanel` 除对象属性 Inspector 外，还包含 HTTP 轨迹上传、通信状态、串口状态和 STAND/GAIT/STOP/PASSIVE 基础指令按钮，并调用 `robot_trajectory_http_gateway`。这与用户当前的纯本地创作范围不符。应在舞台编导窗口内替换为本地属性 Inspector / Clip 属性面板；不要删除项目其他页面的运维能力。

### 3.7 保存行为写死场景并读取 UI 私有数据

文件：`src/ui/windows/main_studio_window.py`

`_on_save_button_clicked()` 读取 `timeline_canvas._blocks`、`_tracks` 等 UI 私有字段，保存固定 `scene_001` / `主舞台默认场景`，并直接弹出“SQLite 与 data/projects/ 已同步保存”成功提示。它没有表现出明确的当前工程对象/工程选择流程；必须由 ProjectService/Use Case 接管保存行为，只有持久化真实成功后才提示成功。

### 3.8 3D 视口目前不是完整 3D 场景引擎

文件：`src/ui/stage3d/stage_viewport_3d.py`

视口继承 `QWidget`，通过 `QPainter` 和 `_project(x,y,z)` 绘制投影网格、点云、轨迹和机器人骨骼；`RobotAvatar3DPainter` 进一步用 `QPainter` 绘制骨架。该方案可以作为轻量投影预览，但不能直接称为完整 3D 场景/网格模型视口。用户需求是完整 3D 预览，因此 P07 必须评估并落地真正支持 3D 相机、点云/网格、URDF Visual Mesh 和时间轴驱动姿态的视口。

### 3.9 本地地图已有可复用基础

文件：
- `src/ui/map_manager_panel.py`
- `src/application/stage_director/stage_map_controller.py`

已经存在 `MapManagerPanel`、`StageMapController`、PCD 校验、SHA-256 判重、文件复制、SQLite 元数据、active map、地图删除保护、2D 栅格转换等实现。不要另起炉灶重写地图子系统；先查清现有 loader、数据库适配器和 UI 事件连接，再补齐真实工作流。

### 3.10 阵型与轨迹也有现存基础

- `src/ui/formation_panel.py` 已有参数化阵型、计算、安全距离检查、JSON 文件列表和保存/加载方法。
- `src/ui/choreo_page/stage_canvas_2d.py` 已有屏幕/舞台坐标转换、轨迹编辑状态、控制点编辑、保存/删除、地图栅格和群组轨迹预览接口。
- 这些模块不应被全新平行控件替换；要修复与 Project/Robot Registry 的真实数据绑定和 UI 闭环。

## 4. 主要审计入口链接

- [main.py](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/main.py)
- [MainStudioWindow](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/ui/windows/main_studio_window.py)
- [LeftDockTabs](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/ui/choreo_page/left_dock_tabs.py)
- [StageCanvas2D](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/ui/choreo_page/stage_canvas_2d.py)
- [MapManagerPanel](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/ui/map_manager_panel.py)
- [StageMapController](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/application/stage_director/stage_map_controller.py)
- [DualLayerTimelineCanvas](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/ui/choreo_page/dual_layer_timeline_canvas.py)
- [TimelineChoreoController](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/application/stage_director/timeline_choreo_controller.py)
- [AssetLibraryPanel](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/ui/asset_library.py)
- [AssetRegistry](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/core/asset_registry.py)
- [FormationPanel](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/ui/formation_panel.py)
- [StageViewport3D](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/ui/stage3d/stage_viewport_3d.py)
- [VirtualShowPlayer](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/application/services/virtual_show_player.py)
- [StagePreviewCoordinator](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/application/stage_director/stage_preview_coordinator.py)

## 5. 需要 Agent 在本地复核的事项

- GitHub `main` 代码不是用户本地 Prompt 00–05 执行后的工作区快照；本地可能有额外改动。P00 必须先比较本地差异。
- 本次未在 Windows 上启动 Qt UI，因此不能断言当前具体屏幕布局、运行时异常、PCD 加载耗时或视觉效果。
- `StageMapController`、`MapManagerPanel` 使用的 PCD Loader 具体实现和数据结构需在本地完整调用链中复核，不能仅凭类名推断等价。
- `ChoreoSqliteStore`、各 SQLite Adapter 和 `lrmp_compiler` 的历史数据结构需要通过真实数据库 schema / Git 历史 / 测试复核后迁移。
- 机器人 URDF、mesh、舞蹈帧和动作资源目录是否完整，需扫描真实仓库与用户资源后确认；不得用虚构模型/帧填充缺失资源。


---

<!-- SOURCE: PROMPT_INDEX.md -->

# Prompt Index — RDA Client Studio V2

## 阶段图

```text
P00 工作区接管与主窗口链路修复
  └── P01 本地工程与统一数据持久化
        └── P02 地图 / PCD
              └── P03 机器人实例 + 2D 轨迹
                    ├── P04 阵型设计
                    └── P05 素材库与拖放契约
                          └── P06 双层时间轴
                                └── P07 3D 预演
                                      └── P08 集成验收
```

P04 与 P05 在 P03 完成后可以分开执行，但不要并行修改同一组模型文件。P06 必须等 P05 的素材数据契约稳定。P07 必须等 P01/P02/P03/P06 的数据模型稳定。P08 最后执行。

## Prompt 清单

| 编号 | 目标 | 必须交付的真实结果 | 不允许用什么代替 |
|---|---|---|---|
| P00 | 接管现状并修复 MainStudioWindow 数据注入和职责边界 | 一套实际运行的依赖链；地图、画布、时间轴、预览不再各自 new 出互不相关的业务实例 | 新建平行窗口、只写审计报告 |
| P01 | 本地工程和数据模型 | 可创建/打开/保存/另存/导入/导出工程；项目数据重启后可恢复 | 固定 scene_001、全局默认工程、只写 SQLite 表 |
| P02 | 地图与 PCD | 地图导入管理、加载/卸载/重命名/导出/删除；2D/3D 使用同一张地图 | 只显示文件名或只在一个视图画点云 |
| P03 | 机器人与 2D 轨迹 | 项目内机器人实例、坐标转换、轨迹编辑、保存和 JSON 重现 | 固定机器人、只能画不能存、只存像素坐标 |
| P04 | 阵型 | 参数化阵型、成员表格、预览、保存/加载/应用 | 仅计算偏移、不改变舞台机器人位置 |
| P05 | 素材库 | 本地真实素材目录、元数据、搜索、详情、预览、统一 MIME schema | 依靠隐含字段/将舞蹈误判为轨迹 |
| P06 | 时间轴 | 双层轨道、拖放、编辑、撤销重做、项目级保存、播放时钟一致 | 只画块、移动仅改内存、播放器读另一份数据 |
| P07 | 3D | 真实 3D 视口、地图点云、机器人模型、轨迹/动作同步播放 | 把 QPainter 透视画布改名为“完整 3D” |
| P08 | 集成 | 端到端验收、Windows 实机截图、回归报告、问题清单 | 单元测试通过就宣称全部完成 |

## 运行方式

每轮执行：

1. 阅读 `GLOBAL_EXECUTION_CONTRACT.md`。
2. 阅读项目内 `/.agent_workspace/skills/robot-deployment-assistant/SKILL.md`。
3. 阅读本阶段 Prompt 的全部内容。
4. 先核对 `docs/agent-prompt-pack/state/SESSION_HANDOFF.md` 和 Git 工作区，再开始修改。
5. 执行本阶段全部验收，更新状态和交接文档。

## 阶段完成状态

不要凭主观判断将阶段标记为完成。仅当阶段 Prompt 中全部 Must Pass 项目有可检查的测试或运行证据时才能标记 `COMPLETE`；有任何未运行、未验证或未实现项时标记 `PARTIAL` 或 `BLOCKED`。


---

<!-- SOURCE: prompts/P00_WORKSPACE_RECOVERY_AND_WIRING.md -->

# P00 — 接管 Prompt 00–05 执行后的工作区，并修复舞台编导基础链路

**阶段目标**：先让现有舞台编导的对象依赖、数据源、信号槽和空状态真实一致。这个阶段不是重写功能，也不是重新执行旧 Prompt 00–05。它负责接管用户已经修改过的工作区，找出旧 Prompt 没有真正落地的部分，并在保护用户改动的前提下修复根因。

**执行前置**：必须同时读取 `GLOBAL_EXECUTION_CONTRACT.md` 和仓库内 `.agent_workspace/skills/robot-deployment-assistant/SKILL.md`。

## 1. 绝对要求

1. 直接在当前本地仓库工作，不得重置成 GitHub `main`，不得重新 clone 覆盖用户文件。
2. 不要把旧 Prompt 00–05 生成的所有代码一律判定为正确或错误。逐项对照代码、信号槽、数据文件、测试和 UI 操作确认。
3. 本阶段只做舞台编导客户端本地链路。移除/隔离该窗口内的机器人通信、HTTP 上传、串口指令和急停派发；不得删除其他页面的既有运维功能。
4. 本阶段必须修改代码并执行测试，不允许只提交审计报告。
5. 不要新增第二套舞台编导窗口。主入口继续是 `main.py` 中 `StudioWindowManager` 创建的 `MainStudioWindow`。

## 2. 接管和基线检查

先执行并保存完整输出：

```powershell
git rev-parse --show-toplevel
git status --short --branch
git status --porcelain=v2
git rev-parse HEAD
git diff --binary > docs/agent-prompt-pack/audit/P00_before_unstaged.patch
git diff --cached --binary > docs/agent-prompt-pack/audit/P00_before_staged.patch
```

若目录不存在，先创建。保存 untracked 文件清单、用户数据库/地图/轨迹/阵型/模型文件列表及 SHA-256。禁止使用 `git clean`、`git reset --hard`、force checkout 等破坏性命令。

重新读取以下文件的**本地版本**，不可仅依赖 GitHub 静态快照：

- `main.py`
- `src/ui/windows/main_studio_window.py`
- `src/ui/choreo_page/left_dock_tabs.py`
- `src/ui/choreo_page/stage_canvas_2d.py`
- `src/ui/map_manager_panel.py`
- `src/application/stage_director/stage_map_controller.py`
- `src/ui/choreo_page/dual_layer_timeline_canvas.py`
- `src/application/stage_director/timeline_choreo_controller.py`
- `src/infrastructure/storage/choreo_sqlite_store.py`
- `src/infrastructure/storage/timeline_clip_sqlite_adapter.py`
- `src/ui/choreo_page/right_dock_panel.py`
- `src/ui/choreo_page/choreo_toolbar.py`
- `src/ui/choreo_page/stage_overlay_controls.py`
- `src/ui/stage3d/stage_viewport_3d.py`
- `src/application/services/virtual_show_player.py`
- `src/application/stage_director/stage_preview_coordinator.py`
- `src/application/stage_director/stage_preview_engine.py`
- `src/ui/asset_library.py`
- `src/core/asset_registry.py`

对照本包 `PROJECT_AUDIT_BASELINE.md`，生成 `docs/agent-prompt-pack/audit/P00_LOCAL_RECHECK.md`。每项标记 `CONFIRMED / FIXED_ALREADY / NOT_REPRODUCED / UNKNOWN`，并附本地路径、方法名、证据。发现本地代码已修复的项目，不要重复改写。

## 3. 建立唯一的舞台编导依赖注入链

### 3.1 当前已观察到的接线问题

在 GitHub `main` 静态快照中：

- `MainStudioWindow.__init__()` 创建 `self.store = ChoreoSqliteStore()` 和 `self.map_controller = StageMapController(...)`。
- `_build_layout()` 创建 `LeftDockTabs(..., controller=self.controller)`，没有显式传入 `self.map_controller` 和 Store。
- `LeftDockTabs.__init__()` 仅接收 `controller`，再用 `getattr(self.controller, "map_controller", None)` 寻找地图控制器。
- 当 `main.py` 默认创建窗口时，`MainStudioWindow` 的 `controller` 参数没有传入；于是 `MapManagerPanel` 可能自行创建另一个 `StageMapController`。
- `StageCanvas2D` 虽然构造函数支持 `store`，但主窗口没有传 `store=self.store`。
- `DualLayerTimelineCanvas` 内部执行 `TimelineChoreoController()`，没有接收主窗口的项目/数据库上下文。

必须在本地验证以上情况后修复。

### 3.2 具体实施

建立明确的 Composition Root / `StudioRuntimeContext`（名称可调整，但只能有一个主对象），集中创建并持有：

- 当前工程会话/当前工程数据库连接配置（P01 会进一步完善 ProjectService；本阶段先提供可扩展的注入接口）。
- 当前工程的 `ChoreoSqliteStore` 或统一 Store。
- 当前工程的 `StageMapController`。
- 当前工程的 `TimelineChoreoController`。
- 当前工程的 Robot/Trajectory/Formation/Asset 查询服务（若已有服务则复用，不要复制）。

将这些对象显式注入，而非让 Widget 内部悄悄 new：

- 扩展 `LeftDockTabs.__init__`，至少显式接收 `map_controller` 和工程上下文；
- `MapManagerPanel` 使用主窗口提供的同一个 `StageMapController`；
- `StageCanvas2D(..., store=...)` 使用同一项目 Store；
- `DualLayerTimelineCanvas` 接收统一创建的 `TimelineChoreoController` 或 Store/DB path + task context；
- `StagePreviewEngine.build_preview_tracks()` 从当前工程上下文取 Store 和项目标识，不得另行打开默认数据库；
- `VirtualShowPlayer`、`StagePreviewCoordinator` 和 3D 视口从同一份 Preview Snapshot 获取数据。

必须提供自动化断言，证明：

```python
main_window.left_tabs.map_panel.controller is main_window.map_controller
main_window.stage_2d.store is main_window.store
main_window.timeline_canvas.choreo_controller 使用当前工程同一 DB path
PreviewEngine 读取的 DB path 与当前工程一致
```

上述表达是验收意图，实际测试可通过正式公开属性验证；不要依赖私有字段做生产逻辑。

### 3.3 依赖生命周期

- 主窗口只负责创建/注入服务，子控件不得持有重复的业务数据库或互相构造对方。
- 工程切换时要么通过可控的 `set_project_context()` 更新依赖，要么由主窗口安全销毁并重新创建工程作用域控件；不得留下旧 DB 连接或旧地图控制器。
- 窗口隐藏/关闭时播放器、worker、文件句柄正确停止/释放；不能因窗口重复打开造成重复 Qt 连接或定时器。
- 不要因为现有 `controller` 参数在历史页面使用而粗暴删除；确认所有调用方后保持兼容。

## 4. 空状态清理：不得显示演示机器人

逐一检查并处理：

- `StageViewport3D.__init__()` 中 `_robot_meta` 和 `_robot_poses` 默认的 `Robot_1` / `Robot_2`。
- `VirtualShowPlayer._init_default_tracks()` 的两台机器人默认轨迹与 `POPPING1`、`POPPING2`、`中华武术` 默认动作。
- `StagePreviewCoordinator.__init__(load_defaults=True)` 和 `_init_default_tracks()` 的同类默认数据。
- 其他窗口构造/刷新逻辑中任何默认机器人、默认 Clip、默认轨迹、默认在线状态。

将产品默认状态改成空数据：

- 新建项目没有机器人、地图、轨迹、动作 Clip。
- 播放器无轨道时停止/禁用播放，显示“当前工程没有可播放的时间轴内容”。
- 3D 视口无机器人时只显示地面、坐标轴、网格/已加载地图和空状态提示。
- 有合法的仓库内置舞蹈/动作素材时可展示素材库，但不能因此自动在舞台上生成机器人或时间轴 Clip。
- 测试若需要演示对象，使用明确的 test fixture，禁止在正式构造函数自动 seed。

增加测试：新建空窗口/空工程时机器人数量为 0、播放器轨道数量为 0、时间轴 Clip 数为 0；切换到 3D 视图不出现任何 Robot_1/Robot_2。

## 5. 从舞台编导窗口隔离通信和运控控件

重点审查 `RightDockPanel`、`ChoreoToolbar`、`StageOverlayControls` 和 `MainStudioWindow._wire_signals()`。

### 5.1 右侧 Dock

`RightDockPanel` 当前在 Inspector 之外包含 HTTP 轨迹上传、IP/Port、通信状态、串口状态和 STAND/GAIT/STOP/PASSIVE 基础指令。把它收敛为纯本地 Inspector：

- 选中对象类型、ID、世界坐标、角度、所属资源/轨道；
- 轨迹属性：名称、时长、点数、长度、绑定机器人；
- 阵型属性：名称、类型、中心点、成员数；
- 时间轴 Clip 属性：素材名称、Clip ID、起始时间、持续时长、轨道层；
- 无对象时显示明确空状态。

删除舞台编导窗口中 HTTP 上传、IP/Port、串口状态、通信状态和机器人指令发射 UI 及其 handler/import/信号。只在本窗口上下文内隔离，不能删除 `robot_trajectory_http_gateway`、serial manager 或其他页面的功能。

### 5.2 急停/动作派发

`MainStudioWindow._on_basic_motion()`、`_on_emergency_brake()` 和任何调用 `serial_manager.send_raw_command()` 的舞台编导连接必须从本地创作路径中断开。舞台预演播放只驱动本地时间轴/视口。

若 `ChoreoToolbar` 或 `StageOverlayControls` 仍包含急停按钮：从舞台编导创作工具栏移除；或明确禁用并显示“本地预演不控制真实设备”。不能点击后向串口发送任何数据。

对舞台编导的播放、暂停、停止、拖动播放头做测试，断言不会触发串口/HTTP/SSH。

## 6. 修复保存和时间轴编辑的假成功风险

### 6.1 保存

当前快照中 `MainStudioWindow._on_save_button_clicked()`：

- 直接访问 `timeline_canvas._blocks` 和 `_tracks`；
- 固定保存 `scene_001` / `主舞台默认场景`；
- 无条件弹出 SQLite 和 `data/projects/` 保存成功。

本阶段先拆除这种“无论实际结果如何都成功”的实现：

- 不再从 QWidget 私有绘制状态构造持久化记录；
- 由 application service/use case 从领域数据/Repository 读取并保存；
- 数据库或文件写入失败时必须显示真实错误，不显示成功；
- 在 P01 工程服务落地前，若尚不存在有效当前工程，可以禁用保存并提示“请先创建/打开本地工程”，但不得伪成功。
- `TopShowHeader` 的 New/Open/Save/Import/Export 信号逐一追踪并连接到真实动作；不能用清空画布冒充新建工程。

### 6.2 时间轴编辑

`DualLayerTimelineCanvas.mouseMoveEvent()` 当前直接修改画布内 `TimelineBlock`，释放时才持久化。检查 `TimelineChoreoController.move_clip()` / `resize_clip()` 的 bool 返回值：

- 鼠标按下时记录旧值；拖动阶段只维护 preview state；
- 鼠标释放时提交业务命令；
- 返回 False 或抛异常时回滚旧值、刷新视图、显示错误；
- 提交成功才更新选中项/脏状态；
- 禁止 UI 显示新值但 DB 仍保存旧值。

若本地已实现更完整的 Command/Undo 机制，优先复用。

## 7. 必须检查的其它信号连接

完整检查并输出一张信号槽清单：

- Header：New / Open / Save / Import / Export。
- ChoreoToolbar：新建、保存、导入轨迹、导入地图、模式切换、撤销、清除、完成轨迹、重置视图。
- StageOverlayControls：2D/3D 切换、网格、重置相机、播放、清除、模式。
- LeftDockTabs：地图加载/卸载、阵型应用、机器人选择、素材选择。
- TimelineLeftToolbar：播放、停止、撤销/重做、删除、缩放、吸附、循环。
- DualLayerTimelineCanvas：拖放、选择、移动、拉伸、删除、撤销、重做、播放头。

对每个控件记录 objectName、信号、slot、业务效果、失败反馈、测试方式。检查重连、重复 connect、lambda 捕获变量和销毁生命周期。

## 8. 本阶段验收

### Must Pass

1. `MainStudioWindow` 只存在一套当前工程的 Store、MapController、TimelineController 依赖，并且所有子组件用的是同一份上下文。
2. 空工程启动没有假机器人、假轨迹、假 Clip 和假播放内容。
3. 舞台编导不再有机器人指令派发、串口急停或 HTTP 上传入口；项目其他运维页保持完整。
4. Header 的新建/保存等按钮不再通过清空画布或伪成功弹窗冒充工程操作。
5. 时间轴持久化失败会回滚 UI 状态。
6. 关键 Qt 信号槽有自动化测试或逐项验证记录。
7. 对受影响的现有功能进行回归；未运行的 Windows Qt 项明确标记 NOT RUN。

### 用户手工验证流程

1. 启动现有主程序，从原入口打开舞台编导窗口。
2. 新建或进入空工程；确认左侧没有凭空产生机器人、地图或轨迹。
3. 切换 2D/3D；确认 3D 为空场景。
4. 点击本地播放；无 Clip 时应禁用或提示，不得发设备命令。
5. 检查右侧 Inspector 仅显示本地对象属性，不出现通信/上传/串口状态。
6. 用自动化测试模拟 SQLite 更新失败，确认时间轴恢复旧位置。

## 9. 交付文件和报告

- `docs/agent-prompt-pack/audit/P00_LOCAL_RECHECK.md`
- `docs/agent-prompt-pack/audit/P00_SIGNAL_SLOT_MATRIX.md`
- `docs/agent-prompt-pack/audit/P00_TEST_REPORT.md`
- `docs/agent-prompt-pack/state/PROJECT_STATE.md`
- `docs/agent-prompt-pack/state/ARCHITECTURE.md`
- `docs/agent-prompt-pack/state/SESSION_HANDOFF.md`
- 相关测试文件及实际代码修复。

仅当 Must Pass 全部具备证据时标记 `COMPLETE`。完成后只进入 `P01_LOCAL_PROJECT_AND_DATA_MODEL.md`。


---

<!-- SOURCE: prompts/P01_LOCAL_PROJECT_AND_DATA_MODEL.md -->

# P01 — 本地工程管理、项目隔离和统一数据持久化

**阶段目标**：把“舞台编导工程”变成真正的本地数据容器。用户可以创建、打开、保存、另存为、导入、导出工程；项目中的地图引用、机器人、轨迹、阵型、素材引用和时间轴 Clip 必须跟随工程，重启程序后可以恢复。

**前置**：P00 COMPLETE。执行前读取全局执行契约和正确 Skill。

## 1. 本阶段不能做什么

不开发任何网络上传、机器人通信、设备发现、远程项目、远程下发和运维能力。不要实现机器人命令编译/部署。也不要把 `lrmp_compiler` 当成本地工程管理器，除非代码审计能证明它本身是项目存档服务；不得因名字或历史用途猜测。

## 2. 先审计现有持久化，不得直接建第二套数据库

必须阅读并追踪：

- `src/infrastructure/storage/choreo_sqlite_store.py`
- `src/infrastructure/storage/timeline_clip_sqlite_adapter.py`
- `src/infrastructure/storage/trajectory_sqlite_adapter.py`
- `src/infrastructure/storage/stage_map_sqlite_adapter.py`
- `src/infrastructure/storage/group_trajectory_sqlite_adapter.py`
- `src/infrastructure/storage/*formation*`（存在时）
- `src/core/storage_manager.py`
- `src/core/lrmp_compiler.py`
- `src/ui/header/top_show_header.py`
- `src/ui/windows/main_studio_window.py`
- 所有现有 scene/project JSON、SQLite 表和 migration。

建立 `P01_PERSISTENCE_AUDIT.md`：数据库路径、表结构、主键、外键、Repository/Adapter、默认项目/任务行为、旧数据目录、各模块当前使用的 DB path。扫描用户当前数据文件并记录 SHA-256。不要把开发目录中的空数据库和用户真实数据库混为一谈。

当前 GitHub `main` 快照中 `ChoreoSqliteStore.DEFAULT_DB_PATH` 是 `data/choreo_database.db`；`StageMapController` 支持传 `db_path`；`TimelineChoreoController` 也支持 `db_path`。这给统一工程数据库留下了复用入口，但必须在本地检查所有 Adapter 是否都使用同一路径。

## 3. 定义工程文件格式和目录结构

提交 ADR 并选定一个权威方案：

- 推荐可移植的工程目录/压缩包格式；
- 一个工程有稳定 `project_id`；
- 工程有 `manifest.json`；
- 工程数据库与地图、轨迹、阵型等本地资源有明确归属；
- 工程导出可以包含所有引用资源，导入后不依赖原机器绝对路径。

推荐逻辑结构（可以根据当前 `storage_manager` 路径调整，但要写 ADR）：

```text
<projects_root>/
  <project-folder>/
    project.json
    project.sqlite3
    assets/
      maps/*.pcd
      trajectories/*.json
      formations/*.json
      actions/...
      audio/...
    cache/                 # 可重建缓存，不作为真源
```

工程清单至少包含：

```json
{
  "schema_version": 1,
  "project_id": "UUID",
  "name": "Project Name",
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601",
  "active_map_id": null,
  "settings": {
    "coordinate_frame": "stage_world",
    "position_unit": "m",
    "angle_unit": "deg",
    "time_unit": "ms"
  }
}
```

以上为契约示意，真实字段要与领域模型一致。禁止把屏幕像素、窗口尺寸、临时选中控件状态写进项目核心数据。可恢复的 UI 偏好可以另存 `ui_state.json`。

如果评估后选择“一个全局 DB 加 project_id”，必须保证所有表都进行项目隔离并有 migration；不允许部分表全局、部分表按项目，从而产生串项目数据。若选择“每工程一个 SQLite”，所有 Adapter 的 `db_path` 必须一致。选定后不得混搭。

## 4. 必须实现的 Application 层接口

创建或完善一个单一工程服务（例如 `ProjectService`），对 UI 提供以下操作；命名可调整，但行为必须完整：

- `create_project(name, destination?)`
- `open_project(project_id_or_path)`
- `save_project()`
- `save_project_as(destination)`
- `close_project()`
- `import_project(archive_path, destination?)`
- `export_project(project_id, archive_path, include_assets=True)`
- `rename_project(project_id, new_name)`
- `list_recent_projects()`
- `get_current_project()`
- `validate_project(path)`

返回明确的 Result/错误类型，不要靠 QMessageBox 结果作为业务成功状态。ProjectService 负责：

1. ID 和名称校验。
2. 创建目录和 canonical SQLite schema。
3. 确保项目数据与项目资源路径互相隔离。
4. 保存 manifest/数据库事务。
5. 导入工程时验证 zip 内路径，拒绝 `../`、绝对路径和越界写入。
6. 验证资源存在、hash 一致、schema_version 可识别。
7. 保存失败时保留原文件并报告原因。
8. 为关闭工程/切换工程提供 dirty-check / 未保存变更策略。

## 5. 统一数据模型

至少梳理并形成 `DATA_CONTRACTS.md`：

- `Project`
- `MapAsset`（复用 `StageMapAsset`，避免重复定义）
- `RobotInstance`（P03 实现，但 P01 先确定工程归属字段）
- `TrajectoryAsset` / `TrajectoryPoint`
- `Formation` / `FormationMember`
- `ActionAsset` / DanceAsset
- `TimelineClipAsset`
- `TimelineTrack`（轨道可以是动态视图模型，但应具有稳定 ID）

每个实体明确：ID 类型、项目 ID、名称、类型、时间/坐标单位、schema_version、文件引用、更新时间和删除/引用策略。

必须区分：

- 素材 Asset：可复用定义；
- Timeline Clip：素材在某条轨道某个时间点的实例；
- Robot Instance：当前项目中的机器人对象，不等同于物理设备在线状态；
- Robot Model：可复用模型/URDF 资源；
- 预览 Pose：由轨迹、动作、时间计算出来的瞬时派生状态，不持久化为主数据。

## 6. SQLite 统一与迁移

1. 所有当前工程的 Store/Adapter 必须接收同一 DB path 或同一 Repository。
2. `ChoreoSqliteStore`、`TimelineClipSqliteAdapter`、`StageMapSqliteAdapter`、`TrajectorySqliteAdapter` 等不能在各自代码中悄悄选择不同默认数据库。
3. 数据库 schema 版本与项目 manifest 版本分开管理；添加可重复执行的 migration。
4. 迁移先备份旧 DB，再事务迁移；失败能够恢复备份。
5. 对旧 `data/choreo_database.db`、`runtime/stage_maps`、`runtime/maps`、`storage_manager` 中的轨迹/阵型文件做只读盘点，设计用户可确认的“导入旧数据”流程。不能自动搬走、删除或重命名旧数据。
6. 若旧数据无法完整识别，保留源文件并将不可迁移项列出；不允许吞异常后显示成功。
7. 对资源文件记录 SHA-256；导出工程包时检查引用闭环。

## 7. UI：在现有 TopShowHeader 中完成真实工程操作

主要入口：`src/ui/header/top_show_header.py`、`src/ui/windows/main_studio_window.py`。

将 Header 的 New / Open / Save / Save As / Import / Export / Recent Projects 连接至 ProjectService。若当前 UI 没有 Save As 或 Recent，补齐但沿用现有视觉主题，不另做新窗口。

交互要求：

- New：询问工程名称和保存位置；创建空工程；切换到空场景。
- Open：工程列表/文件选择；显示名称、更新时间和资源摘要；确认后加载。
- Save：只有持久化成功才显示成功状态；保存过程中防止重复点击。
- Save As：复制工程数据和引用资源，生成新 project_id；不得与原项目共享可变 SQLite 文件。
- Import：导入 `.rda`/ZIP 工程包，先预览工程名、资源数、版本和校验结果。
- Export：打包 manifest、数据库和所引用资源；提供导出成功路径。
- Close/Switch：有未保存变更时提示保存/放弃/取消。
- 最近工程：记录在用户配置中，不把绝对路径写入工程内部作为唯一引用。

按钮必须有 objectName 和 UI 自动化测试定位 ID。

## 8. 接入 P00 的统一 Runtime Context

工程打开/切换后，主窗口把同一工程上下文注入：

- `ChoreoSqliteStore(db_path=current_project.db_path)`
- `StageMapController(db_path=current_project.db_path, map_dir=current_project.maps_dir)`
- `TimelineChoreoController(db_path=current_project.db_path, task_name=...)`
- 轨迹/阵型/Asset Repositories
- StagePreviewEngine

不得出现地图已经切换到新项目、时间轴仍读取旧项目 DB 的情况。

## 9. 测试和验收

### Must Pass

1. 创建 A、B 两个工程，分别建数据，切换后数据绝不串用。
2. 保存关闭重启再打开，工程元信息、地图引用、机器人/轨迹/阵型/Clip 数据一致。
3. Save As 后新旧项目各自独立修改，不互相污染。
4. 导出/导入工程包，校验资源文件 hash 一致，引用闭环。
5. 非法 ZIP 路径、损坏 SQLite、未知 schema version、缺失资源均拒绝导入，原工程不受影响。
6. 模拟保存失败，不得出现成功提示，不得丢失当前内存中的未保存修改。
7. 旧数据库迁移前后数据条数、关键字段和资源哈希一致；源备份存在。
8. `MainStudioWindow` 在新建/打开/切换工程后，地图、2D 画布、时间轴、3D 预览使用同一 project_id / DB path。

### UI 手工验收

- 新建“测试工程 A”，新增一条轨迹/阵型/Clip，保存并关闭。
- 新建“测试工程 B”，不应看到 A 的任何机器人、轨迹、阵型或 Clip。
- 重新打开 A，所有数据恢复。
- A 导出 ZIP，再导入为 C，C 与 A 内容一致但 project_id 不同。
- 在导入损坏包时确认出现明确错误，并且 C/A 原数据不改变。

## 10. 交付

- ProjectService / Repository / Schema / Migration 的真实实现。
- `DATA_CONTRACTS.md`、ADR、数据迁移报告。
- Header 工程管理 UI 与 Qt 测试。
- `P01_TEST_REPORT.md` 和更新后的 `SESSION_HANDOFF.md`。

完成后进入 P02。若 P01 尚未建立项目级 DB/资源隔离，不得进入地图/轨迹/时间轴的正式功能开发。


---

<!-- SOURCE: prompts/P02_LOCAL_MAP_AND_PCD_WORKSPACE.md -->

# P02 — 本地地图资产管理与 PCD 场地工作区

**阶段目标**：完善现有 `MapManagerPanel + StageMapController`，使地图成为当前工程可管理、可恢复、可在 2D/3D 一致显示的本地资源。

**前置**：P00、P01 COMPLETE。必须使用当前打开工程的项目 DB 和资源目录。

## 1. 先检查现有实现，优先修补而不是重写

本地逐项读取：

- `src/ui/map_manager_panel.py`
- `src/application/stage_director/stage_map_controller.py`
- `src/domain/map/stage_map_asset.py`
- `src/domain/map/grid_and_calibration.py`
- `src/domain/map/map_storage_service.py`
- `src/infrastructure/map/pcd_io_engine.py`
- `src/infrastructure/storage/stage_map_sqlite_adapter.py`
- `src/ui/choreo_page/stage_canvas_2d.py`
- `src/ui/choreo_page/map_canvas_renderer.py`
- `src/ui/stage3d/stage_viewport_3d.py`
- `src/core/storage_manager.py`

重点核对 MapManagerPanel 的 PCD loader 与 StageMapController 的 loader 是否为不同 API/不同数据结构。当前审计快照中 `StageMapController.import_pcd_file()` 使用 `PcdMapLoader`，而 `MapManagerPanel._load_selected_map()` 使用 `PcdLoader.load_pcd()` / `downsample()`；必须检查这两个类的实现，不能只根据名称推断兼容。

建立 `P02_MAP_PIPELINE_AUDIT.md`：记录导入、校验、复制、解析、数据库保存、列表刷新、加载、2D 栅格化、3D 点云显示、卸载和删除每一步具体调用的方法与数据类型。

## 2. 地图数据的权威契约

地图资产使用稳定 `map_id`，至少包含：

- `schema_version`
- `map_id`
- `project_id`
- `name`
- `file_path`（项目相对路径；绝对路径仅可作为运行时解析结果）
- `file_size_bytes`
- `point_count`
- `sha256`
- `pcd_encoding`（ASCII / binary / binary_compressed 等按实际支持范围）
- `bounds`：min/max x/y/z，单位 m
- `origin`：x/y/yaw
- `resolution`：m/cell
- `width` / `height`
- `created_at` / `updated_at`
- `is_valid` 或可计算的资源状态

点云数据统一为 `N×3` 浮点数组（如果仓库实际支持 intensity 等其他字段，应另外定义，不要丢失原始信息）。原始 PCD 文件必须保留；用于 3D 展示的下采样点云只是可重建的缓存，不能覆盖原始地图。

坐标契约必须在 2D 与 3D 两边一致：

- X/Y 是舞台世界坐标，单位米。
- Z 是高度，单位米。
- 2D 屏幕 Y 轴方向可能与世界 Y 轴相反，但只能在视图变换时转换。
- `origin`、`resolution`、栅格上下翻转和图像像素中心定义必须统一。
- 地图加载之后，2D 点击/轨迹绘制坐标必须落在正确世界坐标；3D 点云必须与 2D 同一位置/朝向。

将最终契约写入 `DATA_CONTRACTS.md`，不要在多个文件中各写一套隐含坐标变换。

## 3. 地图管理 UI

在 `MapManagerPanel` 内完善，而不是新建另一个地图管理页。左侧 Dock 的地图 Tab 必须展示项目内真实地图资产。

### 地图列表

每项至少显示：名称、点数、尺寸、更新时间、状态。状态区分：

- 已导入 / 可用
- 当前已加载
- 文件缺失
- 元数据不完整
- 校验失败
- 正在导入/解析

支持名称搜索/排序/刷新。没有地图时显示可操作空状态：“当前工程还没有地图，导入 PCD 文件以开始”。不能放入示例地图。

### 操作

必须实现并验证：

1. 导入本地 PCD。
2. 输入/修改地图显示名称。
3. 查看详情（路径、文件大小、编码、点数、边界、分辨率、hash）。
4. 预览地图范围/缩略图（可使用轻量 2D 预览图）。
5. 加载到 2D/3D 工作区。
6. 卸载当前地图。
7. 重命名。
8. 导出原始 PCD 到用户指定路径。
9. 删除地图。

删除前检查：是否是活动地图、是否被轨迹/场景/工程资源引用。禁止静默解除引用。若当前 Project 只允许删除未引用地图，则明确提示先解除引用；若提供“连同引用清理”则必须有确认和事务/备份。

### 导入流程

`选择文件 → 头部校验 → 编码/字段支持校验 → 文件 hash → 重复项检查 → 异步解析 → 展示解析摘要 → 用户确认名称 → 项目目录原子复制 → DB 元数据写入 → 地图列表刷新`。

- 重复文件必须区分“同一 PCD 文件已存在”和“允许作为副本导入”。
- 解析失败或 DB 写入失败时删除临时复制文件，不留下孤儿记录；原始源文件不动。
- 重命名不修改原始数据内容。
- 导入任务可取消；取消后不应将半截文件标为可用。
- 不允许 UI 冻结；PCD 读取、解析、下采样和 2D 栅格生成在 worker 中执行。

## 4. 2D 地图加载链路

使用当前工程唯一 `StageMapController`。`MapManagerPanel` 发出加载事件后，由应用层协调：

1. 传递 `map_id`，不要只传无法追溯的点数组。
2. 加载真实点云和元数据。
3. 使用 canonical `MapGridProcessor` 生成占据栅格。
4. 将 QImage + grid metadata + map identity 注入 `StageCanvas2D`。
5. 在视口中显示地图名称、分辨率、范围和当前坐标状态。
6. 轨迹编辑时，`screen_to_world` / `world_to_screen` 与地图 origin/resolution 一致。
7. 卸载地图必须清除 2D 视口地图缓存，但不能删除地图资产和已保存轨迹。

必须查清 `StageCanvas2D.set_grid_data()`、`load_map()`、`MapCanvasRenderer` 的实际坐标实现，消除重复转换或上下翻转两次的问题。

## 5. 3D 点云数据链路

加载同一 `map_id` 时，把点云和 metadata 传给 3D Viewport。不得另外扫描目录或从另一数据库读取地图。

- 原始点数与显示点数分开显示。
- 限制 UI 最大显示点数时，使用可重复的 voxel/downsample 策略；保存原文件原样。
- 视口可显示地图范围、原点、XYZ 轴和地面网格。
- 地图加载/卸载事件要同步 2D、3D、Inspector 与当前工程状态。
- 如果某个视图渲染失败，地图资产仍保持有效；错误应在 UI 显示，不能让地图 DB 记录被误删。

真正的高质量 3D 视口技术选型在 P07 完成；本 Prompt 只要让当前 3D 组件接收同一份地图数据并形成可验证接口。

## 6. PCD 格式与性能

1. 扫描仓库当前 loader 能力，明确支持的 `DATA` 编码、字段（x/y/z/intensity 等）、尺寸限制。
2. 对 `FIELDS`、`SIZE`、`TYPE`、`COUNT`、`WIDTH`、`HEIGHT`、`POINTS`、`DATA` 头部做严格验证。
3. 对 header 的 point count 与实际解码点数不一致情况给出错误/警告策略。
4. 处理空点云、NaN/Infinity、异常字段、截断文件、超大文件。
5. 使用 chunk / bounded memory；不得一次复制多份大数组导致内存翻倍。
6. worker 支持 progress、cancel、error；窗口退出时安全清理。
7. 下采样结果必须可追溯到源 map hash 与参数。

不要擅自宣称支持未实现的 PCD encoding。不能通过“try/except 然后返回空点数组”掩盖损坏文件。

## 7. 数据库与文件一致性

- Map metadata 和资源文件一致性要有校验服务。
- 导入顺序采用临时文件 → 验证 → 原子 rename → DB transaction；失败清理临时文件。
- 删除顺序要防止 DB 记录消失但文件仍残留或文件先删而 DB 留孤儿记录；必要时采用回收站/待清理记录。
- 工程导出时打包 map 相对路径及 hash；导入后更新路径引用，不允许引用原电脑绝对路径。
- 同一个 map_id 不得指向多个不同 hash 文件。

## 8. 测试矩阵

至少准备：合法 ASCII PCD、小型 binary PCD（若 loader 宣称支持）、空文件、头部损坏、字段缺失、点数不匹配、截断文件、NaN/Infinity、重复 hash、大文件取消。

### Must Pass

1. 导入合法 PCD 后 DB 记录和原始复制文件存在，hash 一致。
2. 重开工程后地图列表恢复。
3. 加载后 2D 和 3D 的 map_id、origin、bounds 一致。
4. 已加载地图不能被误删；卸载后按引用规则决定能否删除。
5. 导出 PCD 与源文件 SHA-256 完全一致（若导出定义为原始副本）。
6. 导入失败不产生孤儿文件/DB 记录。
7. 取消大文件导入后 UI 恢复可操作，临时文件清理。
8. 2D 世界坐标转换有单元测试，至少测试原点、边界、正负坐标与屏幕往返误差。
9. 重新打开工程和地图后数据没有串用其他工程。

## 9. 用户手工验收

- 导入一张真实 PCD，确认列表中的点数/尺寸/编码合理。
- 加载地图，观察 2D 栅格和 3D 点云是否在同一原点/方向。
- 在 2D 视图中记录地图内一个点的世界坐标；缩放/平移/切换视图后确认坐标仍一致。
- 卸载再加载，数据应恢复。
- 导出并计算 hash，与原始 PCD 比较。
- 删除仍被引用的地图，必须提示原因且数据保留。

## 10. 交付

提交代码、PCD 测试样本生成器/fixture、`P02_MAP_PIPELINE_AUDIT.md`、`P02_TEST_REPORT.md`、界面截图和更新后的 `SESSION_HANDOFF.md`。完成后进入 P03。


---

<!-- SOURCE: prompts/P03_ROBOT_REGISTRY_AND_2D_TRAJECTORY.md -->

# P03 — 工程内机器人实例管理与 2D 单机/多机轨迹工作台

**阶段目标**：将现有 `StageCanvas2D` 从“可绘制的画布控件”完善为真正的本地轨迹编辑器，并且有明确的工程机器人实例来源。轨迹支持 JSON 保存、重现和多机器人归属。

**前置**：P00、P01、P02 COMPLETE。

## 1. 先查清现有实现

检查：

- `src/ui/choreo_page/stage_canvas_2d.py`
- `src/ui/choreo_page/map_canvas_renderer.py`
- `src/ui/choreo_page/stage_dock_left_panel.py`
- `src/ui/choreo_page/left_dock_tabs.py`
- `src/domain/trajectory/trajectory_asset.py`
- `src/domain/trajectory/trajectory_draft_validator.py`
- `src/domain/trajectory/spline_builder.py`
- `src/infrastructure/storage/trajectory_sqlite_adapter.py`
- `src/infrastructure/storage/choreo_sqlite_store.py`
- `src/core/models.py`
- P01 创建的 Robot/Trajectory Repository 和 DATA_CONTRACTS。

对 `StageCanvas2D` 已存在的方法逐个建立映射：`set_robots`、`select_robot`、`get_robot_pose`、`validate_trajectory_draft`、`select_trajectory`、`cancel_edit`、`insert_waypoint_to_trajectory`、`delete_waypoint_from_trajectory`、`finish_trajectory`、`save_current_trajectory`、`delete_trajectory`、`load_trajectories_from_store`、`clear_active_trajectory`、`clear_all`、`set_grid_data`、鼠标/键盘事件。

不得删除已有能力，只能在查清行为后修复和扩展。

## 2. RobotInstance：明确是本地项目对象

目前 `StageCanvas2D.set_robots()` 支持接收 dict 列表，但必须找到真实来源；FormationPanel 现有 `_get_robot_ids()` 会退回默认 `A/B/C/D`，这不是当前项目中真实配置的机器人实例。

为当前工程建立 RobotInstance 管理能力。字段至少包括：

- `robot_id`：稳定唯一 ID（UUID 或项目稳定 ID），不是列表下标。
- `display_name`：画布显示名称。
- `model_id`：引用本地模型库中的型号；未知时允许 null。
- `color`：可视化颜色。
- `initial_pose`：x/y/z/yaw，单位 m / deg。
- `footprint_radius` 或用于视觉区分的占地参数；若用于冲突提示，必须注明是估算参数。
- `enabled`：是否参与当前场景编辑。
- `metadata`：用户可扩展的本地备注。
- `schema_version`、`project_id`。

提供本地 UI 操作：添加机器人实例、编辑名称/颜色/型号/初始位姿、复制、删除、选择。新工程默认机器人数量为 0。不得从串口/HTTP/SSH 获取设备列表，也不得伪装这些机器人在线。

如果模型库没有某型号资源，仍可让用户建立抽象 RobotInstance，但在 Inspector/3D 中明确标记“模型资源未配置”；不要绘制假模型。

## 3. 画布对象和编辑状态

把 2D 舞台交互整理为明确状态机，至少包含：

- `SELECT`：选择机器人/轨迹/控制点。
- `DRAW_TRAJECTORY`：新增轨迹控制点。
- `EDIT_TRAJECTORY`：编辑选中轨迹。
- `PAN`：平移视口。
- `PLACE_ROBOT`：放置/修改机器人初始位姿（若采用独立模式）。

每个模式下定义：鼠标左键、右键、中键、滚轮、Delete、Esc、Ctrl+Z/Ctrl+Y 行为。不能在绘制模式误选机器人，不能在平移模式添加控制点。

轨迹对象至少包含：

- `trajectory_id`
- `project_id`
- `name`
- `robot_id` 或 `target_type/group_id`
- `schema_version`
- `coordinate_frame = stage_world`
- `position_unit = m`
- `angle_unit = deg`
- `points`：按顺序保存 x/y/可选 z/heading/time 或显式的 control point 数据
- `spline_type` / sampling 参数
- `created_at` / `updated_at`

区分控制点与采样曲线：持久化控制点和曲线参数；采样点是可重建数据，除非有性能需求和版本策略，不要将屏幕像素采样数组作为主数据。

## 4. 轨迹绘制和编辑的真实行为

### 绘制

1. 用户选择目标 RobotInstance。
2. 切换 DRAW_TRAJECTORY。
3. 在舞台上点击添加控制点；画布显示编号/节点和实时预览曲线。
4. 状态栏显示当前点数、轨迹长度/估计时长（估计值必须标注）。
5. 点击 Finish 完成草稿，输入轨迹名称并保存。
6. 保存成功后进入已保存轨迹列表，自动选中该轨迹。

若没有机器人实例，绘制轨迹操作应提示先创建/选择机器人，而不是自动创建 A/B/C/D。

### 控制点编辑

- 选择已有轨迹后显示控制点。
- 拖动控制点时实时更新曲线。
- 支持选中点插入前/后、删除点、撤销、取消修改。
- 最小控制点数与轨迹合法性由 Domain Validator 决定；不足时阻止保存并显示具体原因。
- 取消编辑恢复数据库中的原始版本。
- 删除轨迹前检查时间轴 Clip/阵型/项目引用；存在引用时提示并执行明确策略。

### 多机器人

- 每条单机轨迹绑定一个真实 `robot_id`。
- 画布上同时显示项目内多个 RobotInstance 与各自轨迹，可独立选中/隐藏。
- 支持多机轨迹组（若已有 `GroupTrajectoryWorkspace`，复用其 Domain/Compiler），不复制出第二套群组数据模型。
- 多机器人轨迹编辑不得把不同机器人控制点混成一条无归属轨迹。

## 5. 世界坐标与视图交互

使用 P02 的地图 origin/resolution/calibration。当前 `StageCanvas2D.screen_to_stage()` 与 `stage_to_screen()` 基于 widget 中心、offset、scale，必须确认这套局部舞台坐标如何与地图世界坐标一致。

要求：

- 持久化数据只存米制世界坐标。
- 缩放/平移只改变 View Transform。
- 地图存在时，根据地图边界提供 Fit Map / Reset View。
- 无地图时提供合理的空舞台网格，坐标原点清晰。
- 滚轮缩放围绕鼠标位置，不应让视口突然跳向中心。
- 坐标转换可往返：world → screen → world 的误差应在测试阈值内（例如 1e-4 m，按浮点和绘制精度调整并写清）。
- 舞台坐标转换逻辑放入单独的可测试对象/工具，不在多个 paint/mouse handler 中散落重复公式。

## 6. 本地保存与 JSON 重现

实现正式 TrajectoryRepository / Service：

- 新建、更新、复制、删除轨迹。
- 查询某工程所有轨迹、按机器人筛选。
- JSON 导出单条或多条轨迹。
- JSON 导入前显示摘要，支持选择导入到当前工程的机器人。
- 导入时验证 schema_version、坐标单位、点数、ID 冲突、机器人引用。
- 提供向后兼容解析器，将旧格式转换成当前模型；原文件不覆盖。

JSON 文件示例仅用于说明，真实字段以 DATA_CONTRACTS 为准：

```json
{
  "schema_version": 1,
  "trajectory_id": "UUID",
  "project_id": "UUID",
  "name": "示例轨迹",
  "target": {"type": "robot", "robot_id": "UUID"},
  "coordinate_frame": "stage_world",
  "position_unit": "m",
  "angle_unit": "deg",
  "points": [
    {"x": 0.0, "y": 0.0, "yaw": 0.0},
    {"x": 1.0, "y": 0.5, "yaw": 30.0}
  ]
}
```

JSON 保存采用临时文件 + fsync/flush（平台能力允许时）+ atomic replace；DB 事务和文件系统操作要能处理失败回滚。

## 7. 左侧对象列表和右侧 Inspector

左侧对象/机器人面板必须展示当前工程真实 RobotInstance：

- 名称、ID、型号配置状态、颜色、初始坐标；
- 选择后同步画布选择、右侧 Inspector；
- 新增/编辑/删除入口；
- 没有机器人时显示空状态。

右侧 Inspector 随当前选择对象切换：

- Robot：ID、名称、model_id、x/y/yaw、颜色、备注。
- Trajectory：ID、名称、目标机器人、点数、长度、估计时间。
- Control Point：索引、x/y/yaw/time（可编辑字段由功能定义）。

任何编辑都通过应用服务保存，不允许 UI 直接改 JSON 文件。

## 8. 自动化测试

必须至少包括：

1. 空项目无机器人；添加后持久化、重启恢复、删除后不再出现。
2. 机器人选择同步到画布与 Inspector。
3. 绘制轨迹并保存，DB/JSON 均可恢复。
4. 编辑控制点、撤销、取消、保存后的几何数据符合预期。
5. JSON 导出再导入，控制点坐标一致。
6. 非法 JSON、未知机器人 ID、NaN、Infinity、缺字段、过少点数会被拒绝。
7. 缩放/平移前后同一世界坐标不变。
8. 两台机器人分别拥有轨迹，互不覆盖，列表筛选正确。
9. 删除被时间轴 Clip 引用的轨迹按既定策略阻止或安全处理。
10. 真实 Qt 鼠标/键盘事件测试或 Windows UI 实测覆盖核心绘制流程。

## 9. 用户手工验收

1. 新建空项目，左侧机器人列表应为空。
2. 添加两个 RobotInstance（例如 Dog-A、Dog-B），调整初始位置和朝向。
3. 分别为两个机器人绘制不同轨迹，保存。
4. 选择轨迹并拖动中间控制点，确认曲线变化；Esc 取消后恢复。
5. 导出其中一条 JSON，再导入到另一个机器人，检查坐标和归属。
6. 缩放和平移地图，轨迹与地图不发生相对漂移。
7. 关闭重开工程，机器人和轨迹全部恢复。

## 10. 交付

真实代码、机器人实例数据模型/Repository、轨迹 CRUD 与 JSON 导入导出、Qt 自动化测试、截图、`P03_TEST_REPORT.md`。完成后进入 P04。


---

<!-- SOURCE: prompts/P04_FORMATION_DESIGN.md -->

# P04 — 多机器人阵型设计、预览、保存与应用

**阶段目标**：将现有 `FormationPanel` 的计算能力接入当前工程 RobotInstance 和 StageCanvas2D，形成可交互、可持久化、可重现的阵型编辑器。

**前置**：P00–P03 COMPLETE。

## 1. 现有代码检查

重点文件：

- `src/ui/formation_panel.py`
- `src/ui/choreo_page/left_dock_tabs.py`
- `src/core/models.py`
- 阵型计算器源码（搜索 `FormationCalculator`）
- `src/ui/choreo_page/stage_canvas_2d.py`
- P01 的 Project/Formation Repository
- P03 的 RobotInstance Repository

当前 GitHub `main` 快照中 `FormationPanel._get_robot_ids()` 如果输入为空会退回 `A/B/C/D`；`_on_group_changed()` 也会把固定组别写入输入框。必须先确认本地版本并取消这种隐式假数据。阵型成员只能来自当前工程的真实 RobotInstance；用户可以在阵型编辑器临时添加/移除成员，但应用阵型时必须清楚地将其与项目机器人匹配。

## 2. 阵型模型

阵型是可复用模板/工程资源，不是运行中的机器人状态。字段至少包括：

- `formation_id`、`project_id`、`schema_version`
- `name`、`description`、`formation_type`
- `center_pose`：x/y/yaw（m/deg）
- `parameters`：spacing、rows、columns、radius、arc_angle、facing 等（仅保存当前类型使用的字段）
- `members[]`：robot_id、sequence、offset_x、offset_y、offset_yaw
- `created_at`、`updated_at`

明确区分：

- 阵型局部坐标偏移（相对于阵型中心/朝向）；
- 世界坐标成员位姿（由计算器派生）；
- 屏幕显示坐标（只由视图变换计算）。

持久化时保留局部成员偏移和中心位姿；世界坐标可缓存，但必须能重新计算。

## 3. 阵型类型和参数

至少支持仓库现有 `FormationCalculator` 已实现的所有类型；不得只在 UI 放选项却没有计算分支。若实现不足，补齐并测试以下常见类型：

- 单列/横排（Line）
- 纵列（Column）
- 矩形网格（Grid）
- 圆形/环形（Circle/Ring）
- 弧形（Arc）

每种类型定义准确参数：

- Grid：rows、columns、水平间距、垂直间距、行列排列顺序。
- Line：成员数量、成员间距、排列方向。
- Column：成员数量、纵向间距。
- Circle：半径、起始角、方向、朝向模式。
- Arc：半径、圆心角、起始角、方向。

朝向模式可包括：统一朝向、面向阵型中心、沿队形切线；只有确实实现后才能显示在 ComboBox。

成员数量不能超过工程内可选 RobotInstance；当机器人数量不足时显示明确约束，不要自动创建临时机器人。

## 4. 实时计算和可视化预览

- 用户编辑任一参数时，计算器立即更新成员局部偏移和世界位姿。
- 预览结果在 2D StageCanvas2D 中同步显示成员点、ID、朝向箭头和阵型轮廓。
- 阵型中心、朝向、成员间距变化后，画布位置实时更新。
- 选中成员时右侧 Inspector 显示 robot_id、offset、world pose。
- 无地图时仍可在空舞台网格上编辑；有地图时使用统一 world transform。
- 不要把阵型预览写入正式 RobotInstance 初始位姿，除非用户显式点击 Apply。

## 5. 安全间距提示（仅本地几何检查）

继续复用现有安全距离计算能力，但明确这是基于简化占地半径的几何间距校验，不是机器人动力学/避障保证。

- 检查所有成员两两距离。
- 使用每个 RobotInstance 的 footprint 参数；缺省值必须在 UI 中标明为“估算默认值”，不得伪装成真实尺寸。
- 输出违反间距的成员对、实际距离、阈值。
- 状态分级：正常、警告、冲突。
- 不允许因计算失败显示“安全”。
- 可一键定位画布中的冲突成员。

## 6. 保存、加载、复制、删除

- 保存到当前工程 FormationRepository。
- 保存前验证成员 ID 存在、ID 唯一、偏移有限、间距参数合法。
- 加载阵型后参数和成员选择恢复；没有成员映射时显示 unresolved member，不得悄悄丢弃。
- “复制阵型”生成新 ID。
- 删除前检查时间轴 Clip/工程引用；若被引用，提示并遵循 P01 删除策略。
- 对已有 `storage_manager.formations_dir/*.json` 文件提供兼容导入；不能自动删除或覆盖旧 JSON。
- 导入/导出格式包含 schema_version 和单位。

## 7. 应用到舞台

点击“应用到舞台”必须有真实行为：

1. 校验阵型当前成员都能匹配到 Project RobotInstance。
2. 计算每个 RobotInstance 的新 world pose。
3. 展示差异预览（可选但推荐）。
4. 用户确认后，更新本项目 RobotInstance 的位置/朝向，或建立一个阵型实例状态；具体选择写 ADR。
5. StageCanvas2D 立即刷新机器人位置和朝向。
6. 右侧 Inspector/对象列表同步。
7. Project 标记 dirty，Save 后重启可恢复。

“应用阵型”不能只发一个 `formationApplied` signal 然后更新右侧文本；必须能在主舞台看到成员位置真正变化。

## 8. 与时间轴的关系

阵型本身不等于轨迹 Clip。P06 如需阵型变化动画，应定义 `FORMATION` 类型 Clip 或生成明确的 GroupTrajectory；不得把静态阵型直接伪装成普通轨迹。

本阶段只需保证 FormationAsset 稳定 ID、工程归属、序列化格式和成员关系，供 P05/P06 使用。

## 9. UI/可用性

- 阵型参数区、成员列表/表格、校验反馈、保存阵型列表和 Apply 操作清晰分组。
- 对成员表格提供添加/移除、顺序调整和单成员偏移微调。
- 所有数值输入有单位、范围、精度和合理步进。
- 选择阵型模板后可看到预览，不需要先保存。
- 空工程无机器人时显示“先在机器人面板创建 RobotInstance”，阵型保存/应用处于合理禁用状态。
- 深色 UI 使用统一主题，不再在组件里散落大量独立颜色值。

## 10. 测试

至少测试：

1. 机器人为空时不自动生成 A/B/C/D。
2. Line/Grid/Circle/Arc 等每种类型计算点数、中心、间距和方向。
3. yaw 旋转后成员 world pose 计算正确。
4. 所有成员机器人 ID 唯一且有效。
5. 保存/加载往返数据一致。
6. JSON 导出/导入数据一致；非法数据拒绝。
7. 冲突距离阈值边界值测试。
8. Apply 后 RobotInstance 和 StageCanvas2D 位置一致。
9. 保存重开后阵型仍可加载，且项目隔离。

## 11. 用户手工验收

- 为一个有 4 个 RobotInstance 的项目分别生成 Grid、Line、Circle 阵型。
- 调整间距、中心、朝向，观察成员标记实时变化。
- 制造两个成员重叠，确认冲突提示定位到对应成员。
- 保存、关闭、重开，重新加载阵型。
- 点击应用到舞台，确认地图上的机器人标记位置发生实际变化。

## 12. 交付

Formation model/Repository/Calculator/UI 实际实现、兼容旧阵型导入、测试、截图、`P04_TEST_REPORT.md` 和 HANDOFF。完成后可进入 P05。


---

<!-- SOURCE: prompts/P05_ASSET_LIBRARY_AND_DRAG_DROP_CONTRACT.md -->

# P05 — 统一本地素材库、动作资源元数据与拖放数据契约

**阶段目标**：完善现有 `AssetLibraryPanel + AssetRegistry`，让动作/舞蹈/轨迹/阵型有稳定 ID、清晰的分类与来源，并能无歧义地拖入时间轴。此阶段不实现真实设备动作下发，只实现本地素材管理和预览所需数据。

**前置**：P00–P04 COMPLETE。

## 1. 先审计现有素材来源

阅读：

- `src/ui/asset_library.py`
- `src/core/asset_registry.py`
- `src/domain/simulation/dance_motion_library.py`
- `backend/serial_dance_parser.py`（只读取本地静态舞蹈目录/元数据的来源，不修改其设备通信逻辑）
- `src/infrastructure/storage/choreo_sqlite_store.py`
- `src/domain/trajectory/trajectory_asset.py`
- P01/P03/P04 的 Repository、资产 schema 和工程目录。

当前 GitHub `main` 静态快照中 `AssetRegistry`：

- 舞蹈来自 `DEFAULT_DANCE_GROUPS`；
- 基础动作来自 `DEFAULT_BASIC_ACTIONS`；
- 轨迹来自 `storage_manager.trajectories_dir/*.json`；
- 阵型来自 `storage_manager.formations_dir/*.json`；
- 输出以 `category` 标识类型。

`DraggableAssetListWidget.startDrag()` 将整个 dict 写入 MIME；但 `TimelineChoreoController.create_clip_from_dropped_asset()` 先读取 `asset_type`。如果没有适配，dance/action 可能被误分类成 trajectory。必须在代码中建立单一转换层，不能让时间轴再去猜字段。

## 2. 统一 Asset 模型

定义一个 canonical Asset Envelope（可用 dataclass/Pydantic/TypedDict，但必须适配项目实际依赖）：

```json
{
  "schema_version": 1,
  "asset_id": "stable-id",
  "asset_type": "DANCE",
  "name": "舞蹈/动作名称",
  "project_id": "project-id-or-null-for-bundled",
  "duration_ms": 5000,
  "source": {
    "kind": "BUNDLED|PROJECT_FILE|DATABASE",
    "ref": "resource-reference"
  },
  "preview": {
    "preview_kind": "JOINT_KEYS|TRAJECTORY|FORMATION|NONE"
  },
  "capabilities": {
    "timeline_action_layer": true,
    "timeline_trajectory_layer": false,
    "stretch_allowed": false
  },
  "metadata": {}
}
```

类型枚举至少：

- `DANCE`
- `ACTION`
- `TRAJECTORY`
- `GROUP_TRAJECTORY`
- `FORMATION`

禁止通过名称、图标、文件扩展名猜测类型。禁止 `category` 与 `asset_type` 同时作为两个独立真值。旧格式由一个 `AssetEnvelopeAdapter` 归一化。

每类素材的关键数据：

- Dance：alias、时长、可预览动作帧/动作源文件、适用 robot model。
- Action：名称、动作类型、duration、joint keyframe source 或明确 `preview_not_available`。
- Trajectory：trajectory_id、机器人目标信息、长度/时长、坐标单位、文件/DB ref。
- Group Trajectory：group_trajectory_id、成员 ID、群组轨迹数据引用。
- Formation：formation_id、成员数量、阵型类型；除非明确实现“阵型变换 Clip”，否则不直接作为普通时间轴轨迹 Clip。

## 3. 素材来源分类

区分三类：

1. **Bundled Assets**：仓库/安装包自带且有明确本地来源的静态舞蹈/动作目录。可只读，不归当前工程所有。
2. **Project Assets**：用户在当前项目创建/导入的轨迹、阵型、动作资源，归当前工程。
3. **Cached/Derived Assets**：预览帧缓存、缩略图、采样曲线，随时可重建，不作为数据真源。

AssetRegistry 不应把无法定位真实帧/模型的占位记录伪装为可预览资产。若动作仅有命令字符串而无本地关节帧，标记 `preview_not_available`；本轮不要执行该命令。命令字符串只作为历史 metadata 保存，不连接设备。

`DEFAULT_BASIC_ACTIONS` 是否保留由本地审计确定：若确实是产品内置动作定义，可保留为只读本地目录项；但不能因存在 `cmd` 字段而显示“执行”按钮，或把它们当作可供 3D 播放的真实关节动画。动作帧缺失时显示资源缺失状态。

## 4. 素材库 UI

沿用 `AssetLibraryPanel` 和左侧素材 Tab。完善：

- 顶部搜索框：名称、别名、ID、标签、动作类型。
- 分类 Tab：舞蹈、动作、单机轨迹、群组轨迹、阵型。
- 列表每项显示名称、分类、时长/成员数、来源标记、是否可预览。
- 右侧或下方详情区域：完整 metadata、资源路径/引用、模型适配、预览状态。
- 刷新按钮：仅刷新本地目录/Repository；错误时保留上次列表并显示告警。
- 空状态、无搜索结果、资源缺失、格式错误、加载中均有对应 UI。
- 项目切换后，Project Assets 只显示当前工程资源；Bundled Assets 保持只读全局资源。

所有条目使用稳定 `asset_id`，不能依赖排序后的列表下标。

## 5. 本地预览

- 若 Dance/Action 有真实 joint keyframe，显示动作缩略预览或打开预览弹窗；复用 P07 统一动作采样器。
- Trajectory 展示 2D 缩略图/控制点摘要；单击可在主舞台定位并选择该轨迹。
- Formation 显示阵型示意缩略图；单击载入阵型面板。
- 无帧数据时显示“没有本地预览帧”，不能生成随机骨架动画或伪造缩略图。
- 预览不写数据库，不改变当前项目数据；明确区分“选择素材”和“应用到工程”。

## 6. Drag & Drop：建立无歧义的单一数据流

`DraggableAssetListWidget.startDrag()` 仅调用一个统一 `serialize_asset_envelope()`，使用一个正式 MIME 类型，例如：

`application/x-rda-stage-asset+json`

旧 MIME `application/x-robo-choreo-asset`、`application/x-choreo-asset` 可在迁移期只读兼容，但新写入只使用 canonical schema。

时间轴收到 drop 后：

1. 检查 MIME 类型和 schema_version。
2. JSON parse。
3. `AssetEnvelopeAdapter.from_legacy()` 只负责兼容旧字段；不能吞异常。
4. 校验 asset_id 和 source ref 在当前工程/内置素材库中真实存在。
5. 校验素材类型与目标轨道的兼容性。
6. 生成 `TimelineClipAsset`（P06 中完善）。
7. 业务持久化成功后接受 drop；失败时拒绝并提示原因。

轨道规则：

| asset_type | ACTION 子层 | TRAJECTORY 子层 | GROUP 轨道 |
|---|---|---|---|
| DANCE | 允许 | 禁止 | 禁止，除非明确设计群组同步动作 Clip |
| ACTION | 允许 | 禁止 | 按模型/群组能力明确，不得默认允许 |
| TRAJECTORY | 禁止 | 允许 | 禁止 |
| GROUP_TRAJECTORY | 禁止 | 禁止 | 允许 |
| FORMATION | 默认禁止 | 默认禁止 | 仅在实现专属 Formation Clip 后允许 |

禁止一个 DANCE 因没有 `asset_type` 而落入 TRAJECTORY。禁止单机器人轨迹落入 GROUP，禁止群组轨迹落到个人机器人轨道。

## 7. 轨道绑定和目标解析

- `asset_id` 是素材库 ID；`ref_id` 是领域资源 ID；两者不能混用。
- 时间轴 Clip 必须保存 asset_type、asset_id/ref_id、target robot/group、duration、start_ms、layer、schema_version。
- 轨迹素材放入轨道时，根据轨迹的 target metadata 校验当前轨道是否匹配；支持用户明确重新绑定目标机器人，但必须在 drop 前/后给出预览确认。
- Dance/Action 可指定 robot model compatibility。当前 RobotInstance 的 `model_id` 不支持该动作时提示，不可静默放入。
- 资源改名不应破坏 Clip 引用；删除素材前检查是否被 Clip 引用。

## 8. 测试

至少测试：

1. Registry 四/五类素材返回稳定 ID、category/type 统一。
2. 已知内置舞蹈的真实来源 metadata 及预览能力正确。
3. 没有本地帧的动作不会显示“可预览”。
4. `DANCE` drop 到 ACTION layer 成功；drop 到 TRAJECTORY layer 失败。
5. `TRAJECTORY` drop 到 TRAJECTORY layer 成功；ACTION layer 失败。
6. `GROUP_TRAJECTORY` 只能进入 GROUP track。
7. 缺 asset_id、错误 schema_version、未知 source ref、损坏 JSON 拒绝。
8. 旧 MIME/旧 category 数据可被兼容转换，转换结果不会误分类。
9. 项目切换后素材引用不会跨工程串用。
10. 删除被 Clip 引用的资源会按约定阻止或安全解除引用。

## 9. 用户手工验收

- 打开素材库，确认分类、搜索、详情和来源标记正确。
- 选一个真实有动作帧的舞蹈进行本地预览；选一个无帧的基础动作，确认显示不可预览原因。
- 拖入舞蹈到 ACTION 子层，应生成正确的动作 Clip。
- 故意拖入轨迹到 ACTION 子层，应明确拒绝。
- 切换工程后确认只显示当前工程轨迹/阵型。

## 10. 交付

统一 Asset Envelope、Registry/Repository、UI 详情与预览、MIME 适配器、拖放测试、`P05_TEST_REPORT.md`。完成后进入 P06。


---

<!-- SOURCE: prompts/P06_DUAL_LAYER_TIMELINE.md -->

# P06 — 双层时间轴、轨道管理、Clip 编辑与本地播放调度

**阶段目标**：把现有 `DualLayerTimelineCanvas` 从“可绘制和拖动矩形块”完善为真实时间轴编辑器。动作、舞蹈、轨迹和群组轨迹来自 P05 的素材契约；Clip 保存在当前工程，并被 3D 播放器直接消费。

**前置**：P00–P05 COMPLETE。

## 1. 现有代码审计

逐项检查：

- `src/ui/choreo_page/dual_layer_timeline_canvas.py`
- `src/ui/choreo_page/timeline_left_toolbar.py`
- `src/ui/choreo_page/timeline_canvas_renderer.py`
- `src/application/stage_director/timeline_choreo_controller.py`
- `src/domain/timeline/timeline_clip_asset.py`
- `src/infrastructure/storage/timeline_clip_sqlite_adapter.py`
- `src/application/stage_director/stage_preview_engine.py`
- `src/application/services/virtual_show_player.py`
- `src/application/stage_director/stage_preview_coordinator.py`
- `src/ui/windows/main_studio_window.py`
- P01/P03/P05 的 Project、Robot、Asset、Trajectory Repository。

当前快照中 `DualLayerTimelineCanvas.__init__()` 内部直接创建 `TimelineChoreoController()`；`load_from_store()` 读取控制器的 Clip；dropEvent 将素材 dict 直接交给控制器；`TimelineChoreoController` 先读 `asset_type`；mouseMoveEvent 直接改 `TimelineBlock` 内存对象，mouseReleaseEvent 持久化但不根据 bool 结果回滚。必须修复。

## 2. Timeline Domain Model

每个 Clip 至少包括：

- `clip_id`：稳定 ID。
- `project_id`。
- `task_id` 或当前工程内部的 show/sequence ID；不能所有工程共用硬编码“默认任务1”。
- `asset_id`：素材库稳定 ID。
- `asset_type`：DANCE/ACTION/TRAJECTORY/GROUP_TRAJECTORY/FORMATION（实际允许的类型）。
- `ref_id`：底层资源 ID。
- `target_type`：robot/group。
- `target_id`：RobotInstance ID 或 Group ID。
- `track_id`：对应 TimelineTrack ID。
- `track_layer`：ACTION / TRAJECTORY。
- `start_ms`、`duration_ms`、`offset_ms`、`rate`。
- `allow_stretch`。
- `name`、`schema_version`、更新时间。

字段语义要写入 DATA_CONTRACTS。时间一律毫秒；UI 显示秒/帧只是格式化。Clip 引用资源，不复制整份 Trajectory/Action 内容。

区分 `TimelineTrack` 和 RobotInstance：轨道是编排通道，不代表在线机器人。轨道可以是机器人轨道或群组轨道。

## 3. 轨道生成和视图布局

- 根据当前工程真实 RobotInstance 动态生成轨道；用户可隐藏/展开轨道，但不能凭空 seed。
- 提供明确的 GROUP 轨道（若工程启用群组编排）。
- 每个 Robot Track 包含上层 ACTION lane 和下层 TRAJECTORY lane。
- 轨道名称、Robot ID、颜色来自 RobotInstance。
- 对没有机器人时显示空状态，并引导先添加 RobotInstance；空状态不能出现 A/B/C/D。
- 支持轨道高度/时间轴缩放，长工程横向滚动。
- 时间刻度、吸附刻度、playhead 和 Clip 绘制必须使用同一坐标换算函数。

## 4. 拖放编排

使用 P05 的 canonical `AssetEnvelope`。禁止 timeline canvas 直接解析多种隐含 dict 结构并猜测类型。

流程：

1. `dragEnterEvent` 检查 canonical MIME。
2. `dragMoveEvent` 实时显示目标轨道和 ACTION/TRAJECTORY 子层预览高亮。
3. `dropEvent` 获取轨道 ID、layer、目标时间。
4. 使用统一时间换算和 snap 规则得到 start_ms。
5. 校验目标轨道与素材类型、机器人型号、轨迹归属、群组类型兼容。
6. 生成 Clip。
7. Repository 事务保存成功后，画布新增 Clip；失败不更新画布并显示可读原因。

drop 结果消息至少区分：非法 MIME、素材不存在、项目不匹配、轨道类型不匹配、目标机器人不匹配、素材引用丢失、保存失败。

## 5. Clip 交互

### 选择

- 单击选中 Clip，显示选中边框并更新 Inspector。
- 点空白取消选择。
- 双击可打开素材详情或 Clip 属性编辑器。

### 移动

- 按下记录原始 start_ms；拖动显示临时位置。
- 按 snap_ms（默认 100ms，可在 UI 调整）吸附。
- 同一项目允许重叠的规则由业务校验明确；不能无提示覆盖其他 Clip。
- mouse release 才向 Controller 提交。
- DB 更新成功后更新正式状态；失败回滚位置并提示。

### 时长拉伸

- 只允许 `allow_stretch=True` 的 Clip。
- 最短时长由 Domain 校验；不允许低于 200ms（或产品明确值）。
- 拖动右边缘改变 duration_ms；显示吸附和时长预览。
- 持久化失败时恢复原 duration_ms。
- 对动作帧有固定时长的素材，默认不允许拉伸；要拉伸必须定义 rate/time-scale 语义，不能简单拉大矩形而仍以原速度采样。

### 删除 / 复制 / 拆分

- Delete 删除选中 Clip，确认是否影响后续动作。
- Ctrl+C/Ctrl+V 可复制（若实现），复制产生新 clip_id。
- Split 只有在定义资源 offset/时间裁剪语义后才能启用。
- 删除后资源本身仍存在；Clip 不是 Asset。

## 6. Undo / Redo

当前 `TimelineChoreoController` 有 snapshot undo/redo；需验证其数据库事务、并发和 project/task 隔离。

- 所有创建/移动/拉伸/删除操作记录可逆命令或快照。
- Undo/Redo 必须同时更新 Repository 和 UI。
- DB 事务失败时不推进 undo/redo 栈。
- undo/redo 栈只属于当前工程/当前时间轴会话；切换项目清空或切换到独立栈。
- 至少保留 50 步（或配置化）。
- Ctrl+Z / Ctrl+Y、工具栏按钮状态一致。

## 7. 播放头、时间刻度和播放器时钟

- Playhead 单一权威时间值 `current_time_ms`。
- 时间轴拖动播放头 → VirtualShowPlayer.seek → StagePreviewCoordinator/3D viewport 更新。
- 播放器 tick → TimelineCanvas 更新播放头，但必须避免 signal loop。
- 播放、暂停、停止、循环、倍速、跳转统一由一个应用服务管理。
- 使用 monotonic clock / elapsed timer 校正实际经过时间，不要仅用固定 16ms 累加而忽略 timer 误差；若仍用 fixed step，必须证明长时间播放漂移满足阈值。
- 有效总时长根据当前工程 Clips 的最大 end_ms 计算；不使用硬编码 10 秒作为工程总时长。
- 空时间轴不得进入播放状态。
- 到达末尾后按 Loop 设置回到 0 或停止；UI 状态按钮同步。

## 8. 预演数据编译

`StagePreviewEngine.build_preview_tracks()` 当前快照以默认 task_name 查询；必须改为接收当前 Project/Sequence ID。

- 只从当前工程数据库读取 Clip 和引用素材。
- 每个 Clip 解析其 Asset/Trajectory/Action 数据；资源缺失列出具体 ID。
- 输出 Preview Snapshot：`project_id`、`sequence_id`、`duration_ms`、`robot_tracks`、`trajectory_lines`、`validation_errors`、`unplayable_items`、`schema_version`。
- 不允许缺失轨迹或动作时生成默认路线/默认姿势并仍标记有效。
- 保持编译纯函数/可测试，播放时不直接从 UI 私有 `_blocks` 读取。
- 不要让 VirtualShowPlayer 和 StagePreviewCoordinator 各自编译两套不同数据；协调器应消费播放器的 pose snapshot 或同一编译结果。

## 9. 时间轴 UI 和 Inspector

- 底部时间轴区域可在 220–450px 左右调整高度，横向滚动性能可接受。
- 时间刻度、Clip、Playhead 颜色层次清晰。
- ACTION lane 与 TRAJECTORY lane 视觉区分。
- 当前选中 Clip 右侧属性 Inspector 显示素材类型、名称、目标机器人/群组、start、duration、offset、rate、stretch。
- 显示当前时间、总时长、缩放百分比、snap 状态、循环状态。
- 所有工具按钮有 toolTip、禁用条件、快捷键和测试 ID。

## 10. 测试

至少覆盖：

1. DANCE/ACTION/TRAJECTORY/GROUP_TRAJECTORY MIME type 到目标层映射。
2. 不匹配的 drop 拒绝，数据库无新记录。
3. 成功 drop 后 Clip 数据库和 UI 完全一致。
4. 移动、拉伸、删除、撤销、重做保存重启后仍一致。
5. Mock DB failure 时 UI 状态回滚。
6. 时间轴 snap 边界、负坐标、最大 duration 和水平滚动坐标换算。
7. Project A/B Clips 完全隔离。
8. 无机器人/无 Clip 时播放禁用。
9. 预览引擎读取的 Clip 与时间轴展示完全相同（数量、ID、start、duration）。
10. 播放、暂停、seek、loop、speed、stop 同步时间轴播放头和预览 Pose。
11. 60Hz 长时间播放漂移测量；写出测量时长、平均 FPS、P95 tick 间隔、最大漂移。

## 11. 用户手工验收

1. 新建项目并添加至少两台 RobotInstance。
2. 把舞蹈拖到 Robot A 的 ACTION lane，把轨迹拖到 Robot A 的 TRAJECTORY lane。
3. 把第二条轨迹拖到 Robot B 的 TRAJECTORY lane。
4. 移动/拉伸 Clip，保存，关闭重开，确认位置和时长恢复。
5. 删除一个 Clip，Undo，再 Redo，数据库和画面同步。
6. 播放、暂停、拖动 playhead、倍速、循环和停止，确认 3D 视口时间同步。
7. 切换另一个工程，确认不出现上一工程的轨道/Clip。

## 12. 交付

Timeline Domain/Controller/Adapter/UI 真实实现、统一 Preview Snapshot、测试和性能报告、`P06_TEST_REPORT.md`。完成后进入 P07。


---

<!-- SOURCE: prompts/P07_REAL_3D_PREVIEW.md -->

# P07 — 真正的 3D 舞台视口、地图点云、机器人模型与时间轴预演

**阶段目标**：将现有 `StageViewport3D` 从 QPainter 投影绘制视图升级为真正的 3D 视口；加载当前工程地图点云、机器人模型/URDF、轨迹和动作姿态，并与 P06 的时间轴播放头严格同步。

**前置**：P00–P06 COMPLETE。P01/P02/P03/P05/P06 的数据契约必须已稳定。

## 1. 明确当前基础与目标差异

检查：

- `src/ui/stage3d/stage_viewport_3d.py`
- `src/ui/stage3d/robot_avatar_3d_painter.py`
- `src/ui/stage3d/preview_performance_monitor.py`
- `src/domain/simulation/urdf_fk_solver.py`
- `src/domain/simulation/dance_motion_library.py`
- `src/domain/simulation/stage_performance_sampler.py`
- `src/application/stage_director/stage_preview_engine.py`
- `src/application/stage_director/stage_preview_coordinator.py`
- `src/application/services/virtual_show_player.py`
- `assets/models/`、URDF、mesh、舞蹈帧和动作资源目录。

当前 GitHub `main` 快照中 `StageViewport3D` 继承 `QWidget`，在 `paintEvent()` 中通过 QPainter 和 `_project()` 画投影网格、点云、轨迹和骨骼；`RobotAvatar3DPainter` 同样以 QPainter 画线段和关节点。它适合作为轻量投影，但不等同于支持网格模型、真实 3D 相机和 3D 场景对象的完整视口。

本阶段必须交付真正的 3D 相机/场景/对象渲染能力。仅提高 QPainter 细节、增加阴影或把类名改成 Renderer 均不算完成。

## 2. 3D 技术选型：先做可运行 Spike，不允许盲目添加依赖

在当前 Windows + Python + PySide6 的真实环境中，评估至少两个可嵌入 Qt 的渲染方案。可评估但不限于：

- PyVista + VTK Qt Interactor；
- pyqtgraph.opengl / Qt OpenGL widget；
- Qt3D（若当前 PySide6 发行环境确实提供并可打包）；
- 现有项目已经安装/使用的其他可行库。

为每个候选写入 ADR 对比：

- PySide6 版本兼容；
- Windows wheel 可用性和安装步骤；
- 运行时性能、点云渲染能力和 mesh 支持；
- 相机 orbit/pan/zoom 能力；
- URDF link mesh/transform 的实现复杂度；
- 与 Qt signal/slot 和线程模型的兼容；
- PyInstaller 打包大小与 DLL 依赖；
- 许可证和长期维护状态；
- 对现有 2D 主窗口的嵌入风险。

先构建一个最小独立 Spike：创建真实 QApplication、Qt 主窗口、渲染 3D 坐标轴、一个 mesh、一个点云，并验证 orbit/pan/zoom。将启动命令、环境、截图和退出码保存到 `P07_SPIKE/`。

选型后新增依赖必须固定兼容版本并更新 requirements/build configuration。禁止在未运行 Spike 的情况下宣称已验证兼容。

## 3. 统一视口接口

保持上层 `MainStudioWindow` 不感知具体图形库；通过 `StageViewport3D` 或明确定义的 Renderer Adapter 暴露统一接口：

- `set_project_context(context)`
- `set_map(map_id, points, metadata)` / `clear_map()`
- `set_robot_instances(robots)` / `clear_robots()`
- `set_robot_models(model_assets)`
- `set_trajectories(trajectory_snapshot)`
- `set_preview_snapshot(snapshot)`
- `set_playhead(time_ms)`
- `update_robot_poses(poses)` / `set_robot_poses(poses)`
- `set_grid_visible(bool)`
- `set_render_mode(mode)`（只展示实际支持的模式）
- `focus_robot(robot_id)`
- `reset_camera()`
- `capture_screenshot(path)`（用于测试证据）

对已有方法保持兼容，更新调用者和测试。禁止组件内部创建默认机器人或从默认数据库读取数据。

## 4. 真实地图点云与舞台环境

- 加载 P02 提供的原始地图点云或其派生 LOD；不能重复从文件系统私自加载第二张地图。
- 显示原点、XYZ 坐标轴、地面网格和地图边界。
- 支持点大小、点颜色、背景和可视化质量等级。
- 相机 Reset/Fit Map 自动适应地图边界；无地图时回到空舞台范围。
- 大点云需要 voxel/LOD/视锥裁剪或其它受控策略；保留原始 PCD 完整点数和 hash。
- 点云解析、LOD 生成和模型资源加载使用 worker；UI 线程只接收可显示结果。
- 加载新地图时释放旧 GPU buffer/scene actor，避免内存累积。
- 2D 和 3D 使用完全一致的 map_id、origin、单位和坐标方向。

## 5. URDF 和真实机器人 Mesh

当前 `UrdfFkSolver` 已具备 URDF Joint/Link 解析和 FK 基础，但必须检查：

- URDF 文件是否真实存在；
- `<visual>` / `<geometry>` / `<mesh>` / `<origin>` / `<material>` 解析是否实现；
- `package://`、相对路径、绝对路径如何解析；
- mesh 文件格式（STL/OBJ/DAE/GLTF 等）的实际支持情况；
- `compute_fk()` 返回 link transform 是否与视口世界坐标约定一致。

必须实现可验证的 RobotModelAsset 管理：

- `model_id`、model name、URDF path、mesh refs、link/joint 列表、scale、source hash。
- URDF 路径解析使用可配置模型根目录；拒绝不安全越界路径。
- 缺少 mesh/link/joint 时给出具体日志和模型状态。
- 不得因 URDF 缺失而静默生成“看起来像真的”模型。

3D 视口应按 URDF visual geometry 显示真实 mesh；将每个 visual origin、scale 和 link FK transform 正确组合后渲染。

如果某 RobotInstance 没有 model_id 或模型文件不存在：

- 显示明确的缺失模型图标/占位标签，说明“无模型资源”；
- 可选显示坐标点/朝向箭头作为抽象对象，但必须和真实 mesh 区分；
- 不允许把 QPainter 线条骨架描述为真实机器人 mesh。

## 6. 动作姿态和轨迹采样

复用 `StagePerformanceSampler`、`DanceMotionLibrary`、`UrdfFkSolver`。不要在 3D Viewport 中另外实现一套独立时间轴算法。

每个 Robot Pose 至少包括：

- base position x/y/z 和 yaw；
- active action/dance asset ID；
- 关节角度（单位明确）；
- 当前 Clip ID、Clip local time；
- pose status：VALID / POSE_UNAVAILABLE / MODEL_MISSING / STAND_FALLBACK（名字可按现有规范统一）。

对于每个 timeline tick：

1. 根据 P06 Preview Snapshot 和 `current_time_ms` 找到当前机器人所在轨迹段。
2. 采样 base pose，包含轨迹段衔接和 heading 插值。
3. 找到当前动作 Clip，按 Clip offset/rate 映射到动作帧时间。
4. 采样真实 joint keyframe，插值关节角度。
5. FK 计算每个 link 的 world transform。
6. 更新各机器人 mesh transform。

轨迹不应有位置突跳或角度 ±180° 跳变；heading 插值应使用 wrap-aware shortest-angle。动作 Clip 没有真实帧时不得随机生成 joint angles；显示姿态不可用并列出素材缺失。

## 7. 相机和视口交互

至少支持：

- 左键拖动 Orbit；
- 中键或 Shift+左键 Pan；
- 滚轮 Zoom；
- Home/Reset Camera；
- Fit Map；
- 双击机器人聚焦；
- 选中机器人高亮、显示名称/ID；
- 切换 Ground Grid/Point Cloud/Trajectory/Robot Model 可见性。

具体鼠标映射可按选用的渲染库适配，但必须写入帮助提示，并且和现有 2D 鼠标行为不冲突。

## 8. 3D/2D/时间轴联动

- 2D 点击机器人 → 3D 同一 robot_id 高亮并聚焦。
- 3D 点击机器人 → 2D 同一 robot_id 选中；右侧 Inspector 同步。
- 2D 轨迹变化后，3D 轨迹线刷新。
- 阵型 Apply 后，3D 机器人起始位姿刷新。
- 时间轴拖动 Playhead 后，3D 立即显示准确时刻的 Pose。
- 播放/暂停/停止/循环/倍速必须与 P06 一个时钟一致。
- 3D 视口关闭/切回 2D 时不得重复创建多个播放 Timer。
- `VirtualShowPlayer` 和 `StagePreviewCoordinator` 不得各自保留不同默认数据。建议由单一 PreviewPlaybackService 计算 Pose，并通过信号推送给两个视图。

## 9. 性能目标和降级策略

在用户真实地图/模型资源规模下测试，不允许只用 100 个点的小样本声称性能达标。

至少测量：

- 点云总点数/显示点数；
- 点云载入时间与峰值内存；
- 3D 帧率平均值、P95 frame time；
- 同屏 1/5/10 个 RobotInstance 的渲染表现；
- 动作姿态采样开销；
- 切换工程/地图后的 GPU/CPU 内存回收。

建议交付目标：普通地图下交互相机操作保持流畅；播放时稳定接近目标 30/60 FPS（按实际硬件设定）；如果无法达到，明确给出点云 LOD、模型 LOD 和预览质量设置。不要将固定 FPS 数字当作未测量的承诺。

## 10. 本阶段测试

### 自动化

1. 无地图、无机器人时场景正常且无假模型。
2. 加载 PCD 后点数、bounds、origin 正确。
3. URDF 解析的 joints/links 与原始文件一致。
4. FK 的已知关节角度结果通过数值单元测试。
5. visual mesh path 解析正确，缺文件产生 MODEL_MISSING 状态。
6. base trajectory sample 时间插值和 yaw wrap 测试正确。
7. action keyframe 插值边界和 Clip rate/offset 正确。
8. P06 playhead → Preview Pose → 3D transform 数据一致。
9. 2D 与 3D 选中状态同步。
10. 连续加载/卸载地图和模型 20 次无明显内存持续增长。

### Windows GUI

实际运行 Qt 应用并截取：

- 空舞台；
- 有地图点云；
- 有一台真实模型；
- 多台模型和轨迹；
- 动作播放中的姿态；
- 轨道相机、平移、缩放视角。

## 11. 用户手工验收

1. 打开包含 PCD 的项目，切换 3D，地图点云与 2D 方向一致。
2. 加载真实 URDF/mesh 模型，旋转相机从不同角度观察机器人结构。
3. 为 Robot A 绑定轨迹和有真实帧的舞蹈 Clip，播放时间轴。
4. 拖动 playhead，机器人 base pose 和关节姿态同步变化。
5. 暂停、单步 seek、停止、循环；姿态可重复、无随机闪动。
6. 切换 2D/3D，选中机器人和当前时间不丢失。

## 12. 交付

- 3D 技术选型 ADR 和 Spike 源码/截图。
- 真正的 3D Qt 视口实现。
- URDF Visual Mesh 解析与 RobotModelAsset。
- 轨迹/动作时序采样和统一播放服务。
- 性能数据、测试和 Windows GUI 验收截图。
- `P07_TEST_REPORT.md` 与 HANDOFF。

未完成真正 3D 场景、真实模型加载或时间轴姿态同步中的任一核心项时，只能标记 PARTIAL，不得将原 QPainter 透视视图标记为“完整 3D 已完成”。


---

<!-- SOURCE: prompts/P08_END_TO_END_INTEGRATION_AND_ACCEPTANCE.md -->

# P08 — 舞台编导端到端集成、视觉验收、性能和回归

**阶段目标**：验证前序所有功能真正组成同一个客户端工作流。修复模块集成问题、视觉问题、持久化问题和回归问题；交付可供用户验收的 Windows 运行版本证据。

**前置**：P00–P07 COMPLETE 或有逐项列明的 PARTIAL。不得通过隐藏未完成项将阶段改为 COMPLETE。

## 1. 集成审计

读取并贯通：

- `main.py` → `StudioWindowManager` → `MainStudioWindow`
- ProjectService / RuntimeContext
- `LeftDockTabs` / `MapManagerPanel` / `FormationPanel` / `AssetLibraryPanel`
- `StageCanvas2D` / `StageViewport3D`
- `DualLayerTimelineCanvas` / `TimelineChoreoController`
- PreviewPlaybackService / StagePreviewEngine / Sampler
- `RightDockPanel`（纯本地 Inspector）
- 所有 Repository / SQLite Adapter / JSON import-export。

输出 `P08_END_TO_END_DATA_FLOW.md`，用 Mermaid 画出：

1. 工程打开的数据流。
2. 地图导入与加载数据流。
3. 机器人创建与 2D 轨迹保存流。
4. 阵型 Apply 数据流。
5. 素材拖放到时间轴数据流。
6. 时间轴播放到 3D Pose 的数据流。
7. 工程导出/导入数据流。

对每条链路标明具体类/方法/信号、领域对象、Repository/DB 表和错误回滚策略。若任何 UI 控件只触发 log 或改变标签，没有持久化或状态更新，视为未完成。

## 2. 端到端验收场景

使用可重置的测试工程 `RDA_E2E_Test_Project`，不使用用户真实工程数据库。测试夹具应包含：

- 一张小型合法 PCD（fixture）。
- 两个 RobotInstance（其中至少一个绑定真实模型资源；若仓库无模型则记录阻塞）。
- 一条 Robot A 轨迹、一条 Robot B 轨迹。
- 一个 Grid 阵型和一个 Circle/Arc 阵型。
- 至少一个有真实关节关键帧的 Dance/Action Asset；若资源不存在，不得伪造，记录缺失并只执行可测试子集。

端到端执行步骤：

### Scenario A：Project lifecycle

1. 创建工程。
2. 保存。
3. 关闭工程。
4. 重新打开。
5. 检查项目 ID、数据库路径、资源相对路径和当前选中状态。

### Scenario B：Map pipeline

1. 导入 PCD。
2. 验证文件 hash 和元数据。
3. 加载到 2D 和 3D。
4. 检查两视图的原点/边界/方向。
5. 卸载再加载。

### Scenario C：Robot + Trajectory

1. 创建两台 RobotInstance。
2. 分别绘制轨迹。
3. 编辑控制点并保存。
4. JSON 导出，再导入另一个测试工程。
5. 对比世界坐标数据。

### Scenario D：Formation

1. 创建阵型。
2. 修改间距、中心和朝向。
3. 触发冲突提示。
4. Apply 到 RobotInstance。
5. 检查 2D/3D 对象同步。

### Scenario E：Asset + Timeline

1. 在本地素材库搜索一个舞蹈和一条轨迹。
2. 拖放到正确轨道/子层。
3. 尝试错误轨道，验证拒绝原因。
4. 移动、拉伸、删除、Undo/Redo。
5. 保存并重启，检查 Clip 数据一致。

### Scenario F：Preview

1. 播放、暂停、停止。
2. 拖动 playhead。
3. 改变倍速、循环。
4. 检查 2D、时间轴、3D 的机器人位姿/动作时间一致。
5. 检查整个过程没有 serial/HTTP/SSH/LoRa/MQTT 请求或派发。

### Scenario G：Export/Import

1. 导出完整项目包。
2. 新目录导入。
3. 验证地图、轨迹、阵型、Clip、模型资源引用闭环。
4. 检查所有相对路径与 hash。

## 3. UI 视觉验收（UniUni 风格）

Windows 实际运行截图至少包括：

- 1440×900 标准窗口全景。
- 1280×720 较小分辨率全景。
- 左侧地图/阵型/素材 Tab。
- 2D 轨迹绘制和选中状态。
- 右侧 Robot/Trajectory/Clip Inspector。
- 底部 Timeline 的 ACTION/TRAJECTORY 双层结构。
- 3D 地图点云和机器人模型视图。
- 各种空状态（无工程/无地图/无机器人/无素材/无 Clip）。
- 导入、删除、错误、保存成功等对话框。

视觉检查：

- 文本无裁切、错位、重叠、溢出；
- 按钮动态变化后尺寸保持稳定；
- 左/右 Dock 与底部时间轴可拖动调整；
- 缩放窗口时中央视口优先扩展；
- 表格和列表滚动条正常；
- 错误/警告/成功状态颜色有语义，不用大面积色块；
- theme tokens 统一，不允许组件各自定义互相冲突的颜色体系。

截图必须来自实际 Qt 运行窗口，不能使用 Figma/mockup/静态绘制代替。记录系统分辨率、DPI、缩放比例、Python/PySide6 版本。

## 4. 性能和资源

使用真实或接近真实的数据规模测量：

- PCD 导入与解析时间、峰值内存。
- 2D Canvas 同时显示机器人数量/轨迹点数量。
- Timeline Clip 数量从 100、500、1000 增长时绘制/拖动响应。
- 3D 点云点数、模型数量和播放 FPS。
- 打开/关闭工程和窗口时 DB connection、QTimer、worker、GPU 资源是否释放。

报告至少包括 mean/P95/max 和测试机器硬件。超过交互目标时做针对性优化，不要直接引入未经验证的依赖或把数据采样精度任意降低。

## 5. 数据一致性与故障注入

至少模拟：

- DB locked。
- 磁盘空间不足/只读目录。
- JSON 文件损坏。
- PCD 文件缺失/截断。
- 模型 Mesh 丢失。
- 工程包导入失败。
- 时间轴 Clip 资源引用失效。
- 用户取消长时间导入。
- 播放过程中切换项目/关闭窗口。

每种情况检查：没有伪成功、UI 回滚、资源句柄释放、当前工程数据不损坏、日志可定位问题。

## 6. 旧功能回归

1. 对照历史 Git 证据和 `COMPATIBILITY_MATRIX.md`，运行 2026-10-01（含）前已正确功能的回归。
2. 项目原有 Flask 页面、主窗口启动、运维页面、文件导入等不属于本轮的功能，至少做 smoke test，确认没有被本轮改动破坏。
3. 如果舞台编导原来某按钮承担旧工作流，但现在范围明确调整为本地创作，记录变更原因，不把它默默删掉。
4. 验证 `main.py` 仍能按原方式启动，不因引入 3D 依赖导致 Flask/Web 入口启动失败。
5. 检查打包流程是否需要包含新增 3D DLL、URDF、mesh、Qt plugin；没有打包验证就标记 NOT RUN。

## 7. 发布前检查

- Python compile / type / lint（按项目现有工具执行）。
- 所有自动化测试和关键 UI 测试。
- SQLite migration 在真实拷贝数据库上成功，并验证回滚。
- requirements pin / wheel 安装 / Windows 打包依赖。
- 检查日志是否包含用户路径/大段资源敏感内容；不在日志输出完整动作数据或大点云。
- 检查无遗留 debug print、临时数据、假数据和无用依赖。
- 完整审阅 git diff、删除文件、未跟踪文件、依赖和 schema。

## 8. 完成标准

### Must Pass

1. Project → Map → Robot → Trajectory → Formation → Asset → Timeline → Preview 全链路可操作。
2. 重启工程后全部本地数据可恢复。
3. 工程 A/B 严格隔离。
4. PCD、轨迹 JSON、工程包导入/导出可靠。
5. Timeline Clip 与 3D Preview 使用同一数据和同一播放时钟。
6. 新工程无 fake Robot、fake Track、fake Clip。
7. 舞台编导工作区无机器人端/服务端通信/指令下发功能。
8. 项目其他既有 Web/运维功能 smoke test 无回归。
9. Windows Qt GUI 验收截图已生成。
10. 未运行测试和剩余限制全部披露。

任何核心功能未完成时标记 PARTIAL，列出阻塞因素、受影响用户操作和后续最小任务，不允许用文档替代实现。

## 9. 最终交付文档

更新：

- `docs/agent-prompt-pack/state/PROJECT_STATE.md`
- `docs/agent-prompt-pack/state/ARCHITECTURE.md`
- `docs/agent-prompt-pack/state/TASKS.md`
- `docs/agent-prompt-pack/state/COMPATIBILITY_MATRIX.md`
- `docs/agent-prompt-pack/state/TEST_MATRIX.md`
- `docs/agent-prompt-pack/state/PROMPT_EXECUTION_LOG.md`
- `docs/agent-prompt-pack/state/SESSION_HANDOFF.md`
- `docs/agent-prompt-pack/audit/P08_END_TO_END_DATA_FLOW.md`
- `docs/agent-prompt-pack/audit/P08_TEST_REPORT.md`
- `docs/agent-prompt-pack/audit/P08_UI_SCREENSHOTS/`
- `docs/agent-prompt-pack/adr/` 中的关键技术决策。

最终报告必须给出 COMPLETE/PARTIAL、逐项验收表、测试退出码、截图路径、已知限制和用户可复现步骤。


---

<!-- SOURCE: RELEASE_ACCEPTANCE_CHECKLIST.md -->

# 最终交付验收清单

## 本地工程
- [ ] 可新建工程并命名。
- [ ] 可打开已有工程，切换工程不会串用其他工程的 Clip/轨迹/机器人/地图。
- [ ] 保存、另存为、关闭重开后数据完全一致。
- [ ] JSON/工程包导入前有校验与预览，导入失败不污染当前工程。
- [ ] 数据 schema 有版本；升级可回滚或有备份。

## 地图
- [ ] 可导入有效 PCD，显示点数、包围盒、尺寸、编码和路径。
- [ ] 无效 PCD、空文件、损坏文件、重复文件均有清楚提示。
- [ ] 可加载/卸载/重命名/导出/删除地图。
- [ ] 工程引用中的活动地图不能被误删；删除流程明确。
- [ ] 2D 栅格与 3D 点云来自同一地图 ID、同一坐标系与同一原点。

## 机器人与 2D 轨迹
- [ ] 新工程无虚构机器人。
- [ ] 用户可在本地工程中添加、编辑、移除机器人实例。
- [ ] 机器人坐标/朝向单位明确，画布与保存数据往返一致。
- [ ] 可绘制轨迹、追加/删除/拖动控制点、选择/编辑/取消/删除轨迹。
- [ ] JSON 导出/导入/重现后几何轨迹一致。
- [ ] 画布缩放/平移后世界坐标不变。

## 阵型
- [ ] 支持至少网格、横排、纵列、圆形/环形、弧形或仓库已有模板类型。
- [ ] 可编辑成员、间距、行列、中心点、朝向。
- [ ] 保存、加载、删除、应用到舞台可闭环。
- [ ] 阵型成员与当前工程机器人实例匹配，不生成默认 A/B/C/D 机器人。

## 素材库与时间轴
- [ ] 舞蹈/动作/轨迹/阵型资源具有稳定 ID 和类型。
- [ ] 搜索、筛选、详情和预览可用。
- [ ] 动作/舞蹈拖入 ACTION 子层；轨迹拖入 TRAJECTORY 子层；群组轨迹只能放群组轨道。
- [ ] 时间轴 Clip 保存后重启仍在；不能因重载丢失。
- [ ] 移动/拉伸失败时 UI 回滚；成功后数据库和 UI 一致。
- [ ] 删除、撤销、重做后持久化状态一致。
- [ ] 播放头、时长、循环、倍速与 3D 预演共用一个时钟和同一项目数据。

## 3D
- [ ] 不是只把 QPainter 伪 3D 重新命名。
- [ ] 相机轨道旋转、平移、缩放、视图重置可用。
- [ ] 地面、轴向、网格和 PCD 点云可视化。
- [ ] 有可加载的真实模型时显示模型；模型缺失时明确提示，不画假 mesh。
- [ ] URDF 关节姿态与动作帧可驱动模型；无法解析的动作明确报告。
- [ ] 多机器人轨迹和姿态能与时间轴同步播放、暂停、停止、跳转。
- [ ] 预演是可视化，不宣称物理动力学/真实碰撞仿真，除非另有物理引擎证据。

## UI / 质量
- [ ] 符合 UniUni 风格 token 与层级，控件不裁切、不重叠。
- [ ] 1440×900 与 1280×720 下工作区布局可用，splitter 可调。
- [ ] 无项目/地图/机器人/素材/轨道时显示空状态。
- [ ] 所有可见操作都有实际行为或禁用说明。
- [ ] 无舞台编导到机器人通信的动作派发路径。
- [ ] 旧 Flask/运维页面未被破坏。
- [ ] 单元、Repository、Qt UI、回归测试已执行；未运行项明确标注。
- [ ] Windows 实际启动与操作截图保存在 audit 目录。


---

<!-- SOURCE: references/UNIUNI_DESIGN_TOKENS.md -->

# UniUni 1.0.2 视觉参考 Tokens

这些 token 来自此前对 UniUni 1.0.2 安装包中编译 CSS/JS 静态资源的解析。它们是视觉参考，不表示本轮已在 Windows 上验证原软件的动态行为。

| Token | Value |
|---|---|
| base | `#0b0c0f` |
| canvas | `#060708` |
| panel | `#101114` |
| card | `#15161a` |
| control | `#191a20` |
| control-hover | `#20222a` |
| text-primary | `#e4e6ea` |
| text-secondary | `#9ba0aa` |
| text-tertiary | `#6a6f78` |
| accent | `#2e7bf7` |
| accent-hover | `#4a8df9` |
| accent-active | `#2268db` |
| accent-bright | `#6fa3ff` |
| success | `#2bb673` |
| warning | `#f0a228` |
| danger | `#ee4d5a` |

推荐尺寸：标题栏 40px、工具栏 40px、状态栏 24px；按钮 32/28/24px；紧凑/普通行高 28/32px；输入控件圆角 4px、按钮 6px、卡片 8px；间距 4/8/12/16/24/32px。字体建议 11/12/13/15px 分层。

布局意图：左侧资源/对象 Dock + 中间主视口 + 右侧属性 Inspector + 底部时间轴。中间主视口占据主要宽度；左右 Dock 和时间轴都可调整，避免使用无法缩放的固定宽度。
