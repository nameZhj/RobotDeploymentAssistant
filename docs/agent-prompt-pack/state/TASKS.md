# 工程分阶段任务清单与验收状态

> 最后更新：2026-11-12

| 阶段 | 对应 Prompt | 核心目标 | 依赖阶段 | 优先级 | 当前状态 | 验收证据 |
|---|---|---|---|---|---|---|
| **00** | `prompts/00_BOOTSTRAP_AND_AUDIT.md` | 初始化、备份、审计、舞台编导遗留专项清理 | 无 | P0 | **COMPLETED** | `docs/agent-prompt-pack/audit/00-cleanup/test-results.md` |
| **01** | `prompts/01_GIT_COMPATIBILITY_AND_SAFE_CLEANUP.md` | 旧功能兼容性、回归测试、历史契约保护矩阵 | 00 | P0 | **COMPLETED** | `docs/agent-prompt-pack/audit/01-compatibility/test-results.md` |
| **02** | `prompts/02_ARCHITECTURE_AND_TECH_DECISIONS.md` | 架构边界、唯一 Composition Root / Facade | 01 | P0 | **COMPLETED** | `docs/agent-prompt-pack/audit/02-architecture/test-results.md` |
| **03** | `prompts/03_UX_DESIGN_SYSTEM_AND_APP_SHELL.md` | UniUni 风格 Qt 工作台外壳及响应式布局 | 02 | P1 | **COMPLETED** | `docs/agent-prompt-pack/audit/03-ui/test-results.md` |
| **04** | `prompts/04_DOMAIN_MODELS_SQLITE_PERSISTENCE.md` | 领域模型、规范 SQLite 与 Repository | 02 | P1 | **COMPLETED** | `docs/agent-prompt-pack/audit/04-data/test-results.md` |
| **05** | `prompts/05_MAP_MANAGEMENT_PCD_IMPORT_AND_RENDERING.md` | PCD 地图异步导入、2D/3D 渲染层 | 04 | P1 | **COMPLETED** | `docs/agent-prompt-pack/audit/05-maps/test-results.md` |
| **06** | `prompts/06_2D_TRAJECTORY_EDITOR_AND_PERSISTENCE.md` | 2D 轨迹/Waypoint 编辑器与样条插值 | 04, 05 | P1 | PENDING | 待执行 |
| **07** | `prompts/07_FORMATION_DESIGNER.md` | 多机器人几何阵型设计与动态变换 | 04, 05, 06 | P1 | PENDING | 待执行 |
| **08** | `prompts/08_TIMELINE_ARRANGEMENT_AND_CLIP_EDITOR.md` | 多轨动作/轨迹时间轴编排与 Clip 编辑 | 04, 06, 07 | P1 | PENDING | 待执行 |
| **09** | `prompts/09_3D_PREVIEW_AND_PLAYBACK_SCHEDULER.md` | 确定性 3D 可视化预演与时钟调度 | 04-08 | P1 | PENDING | 待执行 |
| **10** | `prompts/10_ROBOT_ADAPTER_LRMP_DISPATCH.md` | 真机适配器、LRMP 协议编排与下发 | 04, 08 | P1 | PENDING | 待编写 Prompt |
| **11** | `prompts/11_FLEET_MONITOR_AND_OPS.md` | 机群监控、远程建图与运维集成 | 10 | P2 | PENDING | 待编写 Prompt |
| **12** | `prompts/12_E2E_RELEASE_REGRESSION.md` | 端到端集成、打包交付与全功能最终验收 | 00-11 | P0 | PENDING | 待编写 Prompt |
