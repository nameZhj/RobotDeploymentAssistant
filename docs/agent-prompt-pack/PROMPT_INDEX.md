# RobotDeploymentAssistant Prompt Pack — 主索引

**版本：4.0.0 · 当前完整编写范围：00–09**

项目级 Skill：`.agents/skills/robot-deployment-assistant/SKILL.md`

## 一、阶段清单

| 阶段 | 文件 | 目标 | 依赖 |
|---|---|---|---|
| 00 | `prompts/00_BOOTSTRAP_AND_AUDIT.md` | 初始化、备份、审计、舞台编导遗留专项清理 | 无 |
| 01 | `prompts/01_GIT_COMPATIBILITY_AND_SAFE_CLEANUP.md` | 旧功能兼容性、回归测试、保护矩阵 | 00 |
| 02 | `prompts/02_ARCHITECTURE_AND_TECH_DECISIONS.md` | 架构边界、唯一 Composition Root/Facade、ADR | 01 |
| 03 | `prompts/03_UX_DESIGN_SYSTEM_AND_APP_SHELL.md` | UniUni 风格 Qt 工作台外壳 | 02 |
| 04 | `prompts/04_DOMAIN_MODELS_SQLITE_PERSISTENCE.md` | 领域模型、canonical SQLite、迁移、Repository | 02 |
| 05 | `prompts/05_MAP_MANAGEMENT_PCD_IMPORT_AND_RENDERING.md` | PCD 地图管理、异步导入、2D/3D MapLayer | 04 |
| 06 | `prompts/06_2D_TRAJECTORY_EDITOR_AND_PERSISTENCE.md` | 2D 轨迹/waypoint 编辑、撤销重做和 JSON | 04、05 |
| 07 | `prompts/07_FORMATION_DESIGNER.md` | 多机器人阵型设计、变换和保存 | 04、05、06（画布能力） |
| 08 | `prompts/08_TIMELINE_ARRANGEMENT_AND_CLIP_EDITOR.md` | 多轨动作/轨迹时间轴和 Clip 编辑 | 04、06、07 |
| 09 | `prompts/09_3D_PREVIEW_AND_PLAYBACK_SCHEDULER.md` | 确定性 3D 可视化预演与时间调度 | 04–08 |

**10–12 尚未编写，不可执行之前的同编号旧版 Prompt。**

## 二、强制执行顺序

1. 00/01 若已完成且有证据，只核对状态，不重复清理/重建。
2. 02 必须先完成，后续阶段沿用唯一 Application Facade。
3. 03 与 04 可在各自接口稳定后按依赖推进，但不得并行修改共享窗口/数据库构造链；推荐 03 后 04。
4. 05 完成后才能执行 06 的地图坐标编辑验收。
5. 07 使用 04 的 Formation schema 和 05/06 的坐标与画布能力。
6. 08 使用 04 的 Timeline schema 和 06/07 的资源。
7. 09 读取 04–08 数据，不自行建一套 preview DB 或伪造资源。

每次只执行一份阶段 Prompt；完成验收并更新 handoff 后再进入下一份。

## 三、长期规则

- 先读取 `.agents/skills/robot-deployment-assistant/SKILL.md`。
- 保护 2026-10-01（含）以前正确功能。
- 不覆盖用户 dirty changes / untracked files / DB / 地图 / 动作资产。
- RDA 维持 Flask + PySide6 + SQLite；变更须 ADR 批准。
- UI 不直连 SQL/硬件；Domain 不依赖 UI。
- 不显示假机器人、地图、轨迹、动作、clip、电量、IP 和在线数。
- 轨迹和阵型使用世界坐标、显式 frame 和单位。
- Timeline 使用整数毫秒，Clip 引用真实 source。
- 预演默认 LOCAL ONLY，不向真机下发。
- 不支持/未验证能力明确标 `UNAVAILABLE`/`UNKNOWN`，不能虚假成功。

## 四、每次 Agent 会话开始

1. 确认当前工作区是 RDA 原工程。
2. 读 Skill、本索引、本阶段 Prompt。
3. 读取 `docs/agent-prompt-pack/state/` 状态与 handoff；尚未初始化则走 00。
4. 保存 Git status/diff 与用户数据备份。
5. 确认依赖阶段验收通过。
6. 按 Prompt 修改并运行测试。
7. 检查完整 diff、文件删除和新依赖。
8. 更新状态文件和 handoff。

## 五、参考资料

- `references/UNIUNI_1.0.2_界面与交互逆向分析.md`
- `references/UNIUNI_DESIGN_TOKENS.json`
- `references/RDA_舞台编导现状代码审计.md`

UniUni 资料主要来自编译 JS/CSS 静态分析；没有 Windows 实际运行证据时，不得声称动态界面已亲自验证。
