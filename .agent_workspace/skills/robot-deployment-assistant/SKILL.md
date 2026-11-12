---
name: robot-deployment-assistant
description: 在 RobotDeploymentAssistant 原工程中执行安全审计、代码维护、架构演进和机器人部署编排功能开发。适用于 2D/3D 轨迹、阵型、动作时间轴、PCD 地图、机器人适配、SQLite 持久化和旧功能回归。必须保护 2026-10-01（含）之前已正确工作的 Git 功能，并仅将 UniUni 1.0.2 用作 UX 参考。
---

# RobotDeploymentAssistant 项目工程 Skill

## 1. 适用范围与优先级

本 Skill 用于 RobotDeploymentAssistant 原工程的所有代码审查、Bug 修复、重构、界面重做、数据迁移、地图处理、轨迹/阵型/动作编排和机器人联调任务。

**保护边界：**
- Git 记录中 2026-10-01（含）之前已经正确实现的功能必须保持行为兼容。允许修改旧文件，但必须维护既有接口、数据格式、持久化内容、通信协议和用户工作流。
- 通过真实 Git 历史、Characterization Tests、兼容性矩阵和回归测试证明保护情况；不能仅凭 commit 日期推断某功能正确。
- `UniUni-1.0.2-setup.exe` 是 UX 参考，不是代码底座。不得将其代码、商标、图像、字体或受保护资源复制进 RDA。
- 不得整仓重写、覆盖用户未提交修改、执行破坏性 Git 清理，或用静态 Demo/mock 假装真实业务完成。

本 Skill 的长期约束优先于单个 Prompt 的局部指令。若 Prompt 与 Skill 冲突，先记录冲突并采用更安全、可回滚的方案，不得默默忽略 Skill。

## 2. 固定项目路径约定

以下路径均相对于真实 `RobotDeploymentAssistant` 仓库根目录：

```text
.agents/skills/robot-deployment-assistant/SKILL.md
docs/agent-prompt-pack/
├── PROMPT_INDEX.md
├── PROMPT_INDEX_阶段1更新.md
├── PROMPT_INDEX_阶段2更新.md
├── PROMPT_INDEX_阶段3更新.md
├── PROMPT_INDEX_阶段4更新.md
├── prompts/
├── references/
├── templates/
├── state/
├── audit/
└── adr/
```

- `state/` 是工程运行状态文档的唯一权威位置。
- `audit/` 保存命令输出、测试报告、截图、差异分析和验收证据。
- `adr/` 保存有编号的技术决策记录。
- 不要在仓库根目录和 `docs/` 中维护多份互相冲突的状态文件。
- 这些目录和状态文件是本 Skill/Prompt Pack 建立的工程运行记录，不得声称它们原本就在用户 RAR 中。

## 3. 每次会话的固定启动流程

### 3.1 定位真实仓库

1. 确认当前 IDE workspace 是 RobotDeploymentAssistant 原工程，不是在临时解压目录、另一个项目或 Prompt Pack 下载目录。
2. 执行 `git rev-parse --show-toplevel`、`git status --short --branch`、`git rev-parse HEAD`；无 `.git` 时记录 `GIT_HISTORY_UNAVAILABLE`，禁止 `git init` 伪造历史。
3. 读取本 Skill 和 `docs/agent-prompt-pack/PROMPT_INDEX.md`。
4. 定位本次执行的 Prompt 文件。若用户明确指定阶段，不能自行切换阶段。
5. 检查 `docs/agent-prompt-pack/state/` 状态文件是否存在。

### 3.2 首次初始化

若 `state/PROJECT_STATE.md` 不存在或标记 `NOT_INITIALIZED`：
1. 不得因状态文件缺失停止工作；这是新工程记录的正常状态。
2. 先备份 dirty diff、staged diff、未跟踪文件、数据库和用户资源，记录 SHA-256。
3. **先执行 Prompt 00**，完成真实仓库定位、审计、舞台编导专项清理矩阵和证据采集。
4. 再执行 Prompt 01，完成全工程旧功能兼容性矩阵与基线测试。
5. 创建并根据证据填充第 4 节的状态文件。
6. 只有状态初始化完成且 handoff 明确时，才进入 02 及后续功能开发。

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

固定位置：`docs/agent-prompt-pack/state/`

- `PROJECT_STATE.md`：初始化状态、仓库根目录证据、当前分支/HEAD、dirty 状态、当前阶段、完成项、阻塞项和下一步。
- `ARCHITECTURE.md`：真实技术栈、模块入口、依赖方向、数据流和证据路径。
- `DECISIONS.md`：ADR 索引；详细 ADR 放 `docs/agent-prompt-pack/adr/`。
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

UniUni 分析以 `references/UNIUNI_1.0.2_界面与交互逆向分析.md` 和 `references/UNIUNI_DESIGN_TOKENS.json` 为依据。该资料主要来自安装包静态 JS/CSS 解析；如无 Windows 实际运行录屏，不得宣称已验证动态效果。

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
- 优先复用已经验证可用的 Qt、PCD、3D 和通信实现；不得因为参考软件采用 Electron/Vue 就复制其技术栈。

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

## 11. 阶段依赖约定

标准开发顺序：
- 00：初始化、备份、审计、舞台编导遗留清理。
- 01：全项目旧功能保护与回归基线。
- 02：架构边界与技术决策。
- 03：UniUni 风格 Qt 主工作台。
- 04：领域数据模型、SQLite canonical schema、迁移。
- 05：地图管理、PCD 导入和 2D/3D 地图层。
- 06：2D 轨迹编辑和持久化。
- 07：机器人阵型设计与队形数据。
- 08：动作/轨迹时间轴编排。
- 09：3D 可视化预演与确定性播放调度。
- 10：机器人适配器、通信与安全下发。
- 11：监测、远程建图/上传及运维集成（仅在协议和服务端契约明确后）。
- 12：端到端集成、打包、性能和最终回归。

不得跳过前置数据契约或并行修改共享核心模块。用户明确要求跳步时，先验证依赖是否已完成，再按实际状态执行。

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
