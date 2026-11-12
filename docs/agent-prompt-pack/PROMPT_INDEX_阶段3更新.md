# RDA Prompt Pack — 阶段 3：04–06 业务功能实现指令

**本包版本：3.0.0-phase3**

本阶段重写并补齐 Prompt 04–06。完整执行链条目前为 00–06。后续 07–12 尚未重写，不能执行旧版本 07–12。

## 当前包内容

- `prompts/00_BOOTSTRAP_AND_AUDIT.md`：阶段 1 初始化与清理任务。
- `prompts/01_GIT_COMPATIBILITY_AND_SAFE_CLEANUP.md`：旧功能基线与回归测试。
- `prompts/02_ARCHITECTURE_AND_TECH_DECISIONS.md`：RDA 架构收敛和技术决策。
- `prompts/03_UX_DESIGN_SYSTEM_AND_APP_SHELL.md`：UniUni 风格 Qt 主工作台。
- `prompts/04_DOMAIN_MODELS_SQLITE_PERSISTENCE.md`：领域数据模型与 SQLite。
- `prompts/05_MAP_MANAGEMENT_PCD_IMPORT_AND_RENDERING.md`：地图资源和 PCD。
- `prompts/06_2D_TRAJECTORY_EDITOR_AND_PERSISTENCE.md`：2D 轨迹编辑器。

参考资料：
- `references/UNIUNI_1.0.2_界面与交互逆向分析.md`
- `references/UNIUNI_DESIGN_TOKENS.json`
- `references/RDA_舞台编导现状代码审计.md`

## 执行顺序

严格顺序，不允许并发修改共享代码：

1. 00：备份、项目盘点、舞台编导代码清理。若已完成且验收通过，不重复执行破坏性步骤。
2. 01：建立旧功能回归基线。若已完成，不重复初始化，只补缺失测试。
3. 02：统一依赖方向和 Application Facade。
4. 03：建立可用的 Qt 工作台外壳。
5. 04：领域模型、数据库迁移和持久化。
6. 05：地图导入和渲染。
7. 06：2D 轨迹编辑。

04 依赖 02，05 依赖 04，06 依赖 04 和 05。

## Agent 会话启动要求

每次启动新会话：
1. 读取 `.agents/skills/robot-deployment-assistant/SKILL.md`（若仓库内已有该 Skill）。
2. 读取 `PROJECT_STATE.md`、`ARCHITECTURE.md`、`DECISIONS.md`、`TASKS.md`、`TEST_MATRIX.md`、`COMPATIBILITY_MATRIX.md`、`PROMPT_EXECUTION_LOG.md`、`SESSION_HANDOFF.md`（依项目实际路径）。
3. 检查 Git status 和当前分支。
4. 检查上一个 Prompt 的验收结果与未解决事项。
5. 不得只凭本 index 文件覆盖已有项目状态。

## 版本边界

- 2026-10-01 之前正确功能为保护对象。
- 不允许 reset/clean/stash 作为默认清理方式。
- 不允许删除未提交的用户文件。
- 不允许 UI 显示虚构机器人、地图、动作、轨迹、clip、遥测或网络信息。
- RDA 技术栈维持 Flask + PySide6 + SQLite；除非明确 ADR 批准，否则不迁移 Electron/Vue。
- 所有地图/轨迹必须有可验证的持久化数据契约。
- 页面中任何可见控件必须具有有效 handler、enabled condition、错误反馈和测试覆盖；未实现功能不显示。

## 阶段 3 的验收门槛

- 数据库只有一套舞台编导 canonical schema/repository。
- legacy 数据迁移有数量核验、hash 和回滚记录。
- MapAsset READY 对应完整、存在且 hash 验证的文件。
- 2D/3D 视口使用同一个 map_id 与原始地图 hash。
- 轨迹坐标是 world coordinate，不是 screen pixel。
- trajectory JSON 有 schema_version 和 coordinate frame。
- Undo/Redo 可重放、可撤销，保存 dirty index 正确。
- 关键功能有真实 fixture、自动化测试和验收报告。

本包不是 00–12 全部完工声明。07–12 将在下一阶段单独设计。
