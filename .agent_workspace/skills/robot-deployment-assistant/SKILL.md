---
name: robot-deployment-assistant
description: 在 RobotDeploymentAssistant 原工程中执行代码审计、维护和舞台编导客户端本地创作功能开发。适用于 PySide6 工作台、本地工程、PCD 地图、2D 轨迹、阵型、素材库、动作时间轴、3D 可视化预演、SQLite 持久化及旧功能回归。必须保护 2026-10-01（含）之前已正确工作的既有功能，并仅将 UniUni 1.0.2 用作 UX 参考。
---

# RobotDeploymentAssistant 项目工程 Skill

## 1. 适用范围与优先级

本 Skill 用于 RobotDeploymentAssistant 原工程的代码审查、Bug 修复、重构、界面重做、数据迁移、地图处理、轨迹/阵型/动作编排和回归维护。对于 `docs/RDA_ClientStudio_PromptPack_V2/` 中定义的舞台编导任务，默认只实现客户端纯本地创作功能，不扩展机器人端或服务端通信。

**保护边界：**
- Git 记录中 2026-10-01（含）之前已经正确实现的功能必须保持行为兼容。允许修改旧文件，但必须维护既有接口、数据格式、持久化内容和用户工作流；不属于本次舞台编导范围的既有通信/运维功能应保持原样，不得顺带删除或重写。
- 通过真实 Git 历史、Characterization Tests、兼容性矩阵和回归测试证明保护情况；不能仅凭 commit 日期推断某功能正确。
- `UniUni-1.0.2-setup.exe` 是 UX 参考，不是代码底座。不得将其代码、商标、图像、字体或受保护资源复制进 RDA。
- 不得整仓重写、覆盖用户未提交修改、执行破坏性 Git 清理，或用静态 Demo/mock 假装真实业务完成。

本 Skill 的长期约束优先于单个 Prompt 的局部指令。若 Prompt 与 Skill 冲突，先记录冲突并采用更安全、可回滚的方案，不得默默忽略 Skill。

## 2. 固定项目路径约定

以下路径均相对于真实 `RobotDeploymentAssistant` 仓库根目录。**路径大小写及目录名必须严格一致**：

```text
.agent_workspace/
└── skills/
    └── robot-deployment-assistant/
        └── SKILL.md                         # 本 Skill，工程规则的权威版本

docs/
└── RDA_ClientStudio_PromptPack_V2/           # 当前舞台编导客户端 Prompt Pack 根目录
    ├── README.md
    ├── PROMPT_INDEX.md
    ├── GLOBAL_EXECUTION_CONTRACT.md
    ├── PROJECT_AUDIT_BASELINE.md
    ├── RELEASE_ACCEPTANCE_CHECKLIST.md
    ├── PROMPT_EXECUTION_ORDER.txt
    ├── P00_START_HERE.md
    ├── ALL_PROMPTS_COMBINED.md
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
    ├── references/
    │   └── UNIUNI_DESIGN_TOKENS.md
    ├── state/                                # Agent 运行状态与会话交接
    ├── audit/                                # 审计、测试、差异和截图证据
    └── adr/                                  # 技术决策记录
```

路径规则：

- Skill 的唯一仓库路径是 `.agent_workspace/skills/robot-deployment-assistant/SKILL.md`，注意是单数目录 `.agent_workspace`，不是 `.agents`。
- 当前 Prompt 包的唯一根目录是 `docs/RDA_ClientStudio_PromptPack_V2/`。
- 阶段 Prompt 的唯一目录是 `docs/RDA_ClientStudio_PromptPack_V2/prompts/`。
- 工程状态、审计证据和 ADR 分别放在本 Prompt 包根目录下的 `state/`、`audit/`、`adr/`，不得另行创建旧目录 `docs/RDA_ClientStudio_PromptPack_V2/`。
- Prompt 包内文件相互引用时，执行 Agent 必须以仓库根目录为基准解析上述路径；不得依赖 IDE 当前工作目录或终端当前目录碰巧位于 Prompt 包内部。
- 不要在仓库根目录、`docs/` 根目录或另一个 Prompt Pack 目录中复制出互相冲突的状态文件。
- `state/`、`audit/`、`adr/` 是本 Skill/Prompt Pack 运行时产生的工程记录；目录或文件尚不存在时按阶段 Prompt 创建，不得声称它们原本已经存在。

## 3. 每次会话的固定启动流程

### 3.1 定位真实仓库

1. 确认当前 IDE workspace 是 RobotDeploymentAssistant 原工程，不是在临时解压目录、另一个项目或 Prompt Pack 下载目录。
2. 执行 `git rev-parse --show-toplevel`、`git status --short --branch`、`git rev-parse HEAD`；无 `.git` 时记录 `GIT_HISTORY_UNAVAILABLE`，禁止 `git init` 伪造历史。
3. 读取本 Skill 和 `docs/RDA_ClientStudio_PromptPack_V2/PROMPT_INDEX.md`。
4. 读取 `docs/RDA_ClientStudio_PromptPack_V2/GLOBAL_EXECUTION_CONTRACT.md`，并定位用户指定的阶段 Prompt（位于 `docs/RDA_ClientStudio_PromptPack_V2/prompts/`）。若用户明确指定阶段，不能自行切换阶段。
5. 检查 `docs/RDA_ClientStudio_PromptPack_V2/state/` 状态文件是否存在；审计和截图证据写入同一 Prompt Pack 根目录下的 `audit/`。

### 3.2 首次初始化

若 `state/PROJECT_STATE.md` 不存在或标记 `NOT_INITIALIZED`：
1. 不得因状态文件缺失停止工作；这是新工程记录的正常状态。
2. 先备份 dirty diff、staged diff、未跟踪文件、数据库和用户资源，记录 SHA-256。
3. **先执行本 Prompt Pack 的 P00**（`docs/RDA_ClientStudio_PromptPack_V2/prompts/P00_WORKSPACE_RECOVERY_AND_WIRING.md`），完成工作区接管、旧功能影响评估、舞台编导专项复核、依赖注入修复和证据采集。
4. 按 `PROMPT_INDEX.md` 和 `PROMPT_EXECUTION_ORDER.txt` 顺序执行 P01–P08；不得把旧版 Prompt 编号套用到 V2。
5. 创建并根据证据填充第 4 节的状态文件。
6. 只有 P00 完成且 handoff 明确时，才进入 P01 及后续功能开发。

不得把模板中的 `TBD`/`UNKNOWN` 当作审计事实。

### 3.3 后续会话

只有当 `state/PROJECT_STATE.md` 标记 `INITIALIZATION_STATUS: COMPLETE` 时，才读取已有状态：
- `PROJECT_STATE.md`
- `SESSION_HANDOFF.md`
- `ARCHITECTURE.md`
- `DECISIONS.md` 和本阶段相关 ADR
- `TASKS.md`
- `COMPATIBILITY_MATRIX.md`
- `TEST_MATRIX.md`
- `PROMPT_EXECUTION_LOG.md`
- `UX_REFERENCE_LOG.md`
- `DATA_CONTRACTS.md`

如果初始化后某份状态文件意外缺失，先从 Git、审计目录和 handoff 恢复；不能自动当成首次初始化，更不能凭记忆填充。恢复不完整时标记 `RECOVERED_WITH_GAPS`。

## 4. 状态文档的最低要求

固定位置：`docs/RDA_ClientStudio_PromptPack_V2/state/`

- `PROJECT_STATE.md`：初始化状态、仓库根目录证据、当前分支/HEAD、dirty 状态、当前阶段、完成项、阻塞项和下一步。
- `ARCHITECTURE.md`：真实技术栈、模块入口、依赖方向、数据流和证据路径。
- `DECISIONS.md`：ADR 索引；详细 ADR 放 `docs/RDA_ClientStudio_PromptPack_V2/adr/`。
- `TASKS.md`：按 Prompt 分阶段任务、依赖、优先级和验收状态。
- `COMPATIBILITY_MATRIX.md`：2026-10-01（含）前正确功能、历史证据、行为契约、测试方法和风险。
- `TEST_MATRIX.md`：测试命令、环境、范围、退出码、结果及未运行原因。
- `PROMPT_EXECUTION_LOG.md`：执行日期、Prompt、起止 HEAD、修改文件、测试、结论和回滚点。
- `SESSION_HANDOFF.md`：工作区状态、改动、测试、阻塞、不可触碰事项、恢复命令和下一阶段入口。
- `UX_REFERENCE_LOG.md`：UniUni 观察证据、静态资源分析来源、操作步骤、观察日期和 UNKNOWN。
- `DATA_CONTRACTS.md`：坐标系、单位、机器人、地图、轨迹、阵型、动作、时间轴和 JSON schema 约定。

## 5. 事实、证据和不确定性

关键结论使用下列标签：
- `[OBSERVED]`：被当前代码、命令输出、测试或实际运行行为直接证明。注明文件路径/命令/测试。
- `[INFERRED]`：依据多项证据推导。列明依据和不确定性。
- `[UNKNOWN]`：当前不能证明。写明需要的文件、设备、环境或实验。

禁止：
- 把建议目录或示例接口写成已存在事实；
- 把源码静态分析说成实际启动应用；
- 把测试未运行说成通过；
- 把 mock 机器人、静态 JSON 或模拟遥测说成真机状态；
- 把 3D 可视化预演说成物理仿真，除非已有验证过的动力学/碰撞模型和实验报告。

UniUni 分析以 `docs/RDA_ClientStudio_PromptPack_V2/references/UNIUNI_DESIGN_TOKENS.md`、本 Prompt Pack 内的 `PROJECT_AUDIT_BASELINE.md` 及可验证的既有逆向分析材料为依据。引用不存在的参考文件时必须标记 UNKNOWN，不得凭文件名臆造内容。该资料主要来自安装包静态 JS/CSS 解析；如无 Windows 实际运行录屏，不得宣称已验证动态效果。

## 6. Git、用户数据和回滚安全

任何改动前：
1. 记录 branch、HEAD、`git status --porcelain=v2`。
2. 保存 `git diff --binary`、`git diff --cached --binary`。
3. 复制未跟踪文件和用户数据库/地图/动作资产。
4. 生成 SHA-256 manifest 并验证恢复。
5. 标记 Agent 自己创建的改动范围，避免覆盖用户原有修改。

严禁：
- `git reset --hard`
- `git clean -fd` / `git clean -fdx`
- force push
- 未经审计的 rebase
- 批量删除未知用途目录
- 静默覆盖 SQLite 数据库、地图或用户动作资源
- 用 stash 作为唯一备份
- 对无 `.git` 的快照伪造 Git 历史

清理前必须证明没有动态加载、反射、插件注册、外部脚本、序列化或测试依赖；证据不足则隔离/弃用，不直接删除。

## 7. 架构与技术边界

- 以 RDA 实际仓库代码和 ADR 为准，不预设新框架。
- 已确认舞台编导运行栈为 Python + PySide6/Qt，主 Web/API 为 Flask，本地持久化为 SQLite。除非 ADR 明确批准，不得迁移 Electron/Vue。
- UI Widgets 不写 SQL、不直接操作串口/SSH/socket；通过 Application Use Cases/Facade。
- Domain 层不依赖 PySide6、Flask 或设备 SDK。
- Infrastructure 不反向依赖 UI。
- 数据库由 Composition Root/Repository 层创建和管理，禁止同一业务域存在 schema 冲突的多套 Repository。
- 耗时 PCD 解析、文件 IO、网络/硬件 IO 不能阻塞 Qt 主线程；worker 必须能取消，窗口关闭时正确收尾。
- 新依赖必须有 ADR：版本、Python/Windows 兼容、许可证、安全状态、性能、安装体积、维护状态和退出成本。
- 对舞台编导本地创作功能，优先复用已经验证可用的 Qt、PCD、3D 和本地存储实现；不得因为参考软件采用 Electron/Vue 就复制其技术栈。通信能力属于现有运维系统边界，不是本 Prompt Pack 的开发目标。

## 8. 领域数据不变量

对所有地图、轨迹、阵型、动作和时间轴数据：
- 数据结构必须有 `schema_version`。
- ID 稳定且唯一；不能使用列表下标作为资源 ID。
- 明确 coordinate frame、单位、坐标手性、原点、heading 方向、时间单位和采样率。
- World coordinate 与 screen pixel 严格分离；持久化不得保存 screen coordinate。
- 未知数据使用 `None`/显式 UNKNOWN，不伪造为 0。
- 数值拒绝 NaN/Infinity。
- Map READY 必须关联存在、完整、hash 验证的文件。
- 轨迹几何数据不等于时间轴片段；TimelineClip 引用资源而不复制资源内容。
- 资源删除前检查 scene/group/timeline 引用。
- 时间轴片段必须定义 start/duration/offset/rate 和引用版本策略。
- JSON 导入遵循 parse -> validate -> normalize -> preview -> confirm -> persist。
- 导出采用 UTF-8 和临时文件原子替换。

## 9. UI 与真实功能标准

- 所有可见控件必须有稳定 widget id、明确 handler、enabled condition、状态变化、错误反馈和测试 ID。
- 没有实现的功能不要显示可点击控件，不允许 `lambda: None`、假 Toast、伪成功。
- 状态展示必须来自真实来源；未知电量不显示 0%，未知在线状态不显示在线。
- Demo/mock 必须通过适配接口隔离，并显式标记 `SIMULATION` / `MOCK`。
- 空数据必须显示合理空状态，禁止自动 seed 假机器人、地图、动作、轨迹、clip 和在线数字。
- Qt splitter/stack/model-view 等优先复用；不要为了 UI 视觉重构破坏业务调用路径。
- UniUni 仅借鉴其可验证的布局/色彩/交互逻辑，不复制品牌资产。

## 10. 测试和完成定义

每个 Prompt 阶段结束时必须：
1. 执行本阶段 Domain/Repository/UI 测试。
2. 执行受影响的旧功能回归测试。
3. 列明每个命令的退出码、环境、执行范围和未运行理由。
4. 审查完整 diff，包括删除文件、未跟踪文件和依赖变更。
5. 确认备份可用、用户 DB/地图/动作资源无损。
6. 更新 PROJECT_STATE、TASKS、COMPATIBILITY_MATRIX、TEST_MATRIX、PROMPT_EXECUTION_LOG、SESSION_HANDOFF 和相关 ADR。
7. 给出完成/部分完成/阻塞，不得把未验证项目标记 PASS。

若 Qt/Flask/硬件依赖在当前机器不可用：
- 可以执行静态、纯 Domain 和 fake adapter 测试；
- 相关 Qt/hardware integration 必须标记 `NOT RUN`，写明缺失依赖和建议验证环境；
- 不得把 skipped tests 当作通过。

## 11. 舞台编导客户端 Prompt Pack V2 阶段依赖

当前舞台编导专项的唯一执行路线为：

- P00：工作区接管、审计复核、主窗口依赖注入和本地创作基础链路修复。
- P01：本地工程、工程上下文和统一数据持久化。
- P02：本地地图管理、PCD 导入解析以及 2D/3D 共享地图数据。
- P03：机器人实例注册和 2D 单机/多机轨迹编辑、保存、JSON 重现。
- P04：参数化阵型设计、成员配置、预览、保存与应用。
- P05：统一本地素材库、资源元数据、搜索、详情、预览和拖放数据契约。
- P06：双层时间轴、轨道、拖放、移动/拉伸、撤销/重做、保存和本地播放时钟。
- P07：真正的 3D 可视化场景、地图点云/模型、机器人姿态与时间轴同步预演。
- P08：端到端集成、Windows Qt 实机验收、回归、性能和交付证据。

执行约束：

1. 一次只执行一个阶段；每阶段必须读取 Prompt Pack 根目录中的全局执行约束和对应 Prompt。
2. P04/P05 只能在 P03 的机器人与轨迹数据契约稳定后开始；P06 必须等待 P05 的素材契约；P07 必须等待工程、地图、轨迹和时间轴数据源稳定；P08 最后执行。
3. 不得跳过前置数据契约、并行改写共享 Store/Repository，或创建平行舞台窗口。
4. 本路线只覆盖客户端本地功能。机器人通信、命令派发、远程建图/上传、设备遥测、认证和安全下发均不属于 P00–P08 的验收范围；不得为了这些内容延后或阻断本地功能交付。
5. 项目原有 Flask/Web 运维页面和其他既有功能属于保护对象。断开舞台编导对通信组件的依赖，不代表可以删除整个项目的通信/运维模块。
6. 如用户另行明确提出通信/运维开发需求，必须作为独立任务重新确认范围、接口契约和测试条件；不能自动并入本 Prompt Pack。

## 12. 提交前自检

在结束当前任务前，回答自己并在 handoff 记录：
- 这次修改是否会破坏 2026-10-01 前的行为？
- 有没有把 UI/Domain/Infrastructure 依赖方向反过来？
- 有没有新增第二套 DB/schema 或隐藏的 mock？
- 每个新控件是否真正触发业务行为？
- 是否保存了用户 dirty changes 和数据？
- 关键行为是否有测试证据？
- 未执行的测试是否明确标出？
- 下一位 Agent 是否能仅凭 Skill + 状态文档 + handoff 恢复工作？
