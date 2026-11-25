# RobotDeploymentAssistant AI 通用工程规范总览

> 何时阅读：任意 AI 会话首次介入本仓库时第一步阅读。
> 前置文档：无（本文件为规范总入口与路由表）。
> 要点速览：1) 本规范体系与具体 AI 工具/模型无关；2) 严格遵循 README → 01 → 02 → 专题文档 的渐进阅读顺序；3) 规范冲突时以本 `standards/` 目录为最高工程基准。

---

## 1. 定位与强制阅读顺序

本目录面向所有编程 AI 与开发者，提供**跨模型、低上下文负担**的分片工程规范，覆盖检索、阅读、编码、UI、协议、测试与验收。

**强制阅读顺序**：
1. 本入口文档 [README.md](README.md)（确定任务所属类别与必读清单）。
2. [01 仓库结构、分区契约与运行入口](01_REPO_MAP_AND_ENTRYPOINTS.md)（掌握目录边界与双 `src` 隔离）。
3. [02 检索、定位与代码阅读规范](02_RETRIEVAL_AND_READING.md)（掌握省 Token 检索与分窗阅读方法）。
4. 按下表跳转到对应专题规范执行开发或排查。

---

## 2. 任务类型 → 必读文档路由表

| 任务类型 | 适用范围举例 | 必读文档 |
|---|---|---|
| **改桌面 UI** | `upper_computer/src/ui/`、`src/viewport3d/` | [01](01_REPO_MAP_AND_ENTRYPOINTS.md)、[02](02_RETRIEVAL_AND_READING.md)、[03](03_PYTHON_CODING_RULES.md)、[04](04_DESKTOP_UI_UX_RULES.md)、[07](07_TESTING_AND_VERIFICATION.md) |
| **改 Web 控制台** | `upper_computer/web/`、`upper_computer/app.py` | [01](01_REPO_MAP_AND_ENTRYPOINTS.md)、[02](02_RETRIEVAL_AND_READING.md)、[05](05_WEB_CONSOLE_RULES.md)、[07](07_TESTING_AND_VERIFICATION.md) |
| **改协议或下位机接口** | `lower_computer/`、`upper_computer/src/protocol/` | [01](01_REPO_MAP_AND_ENTRYPOINTS.md)、[02](02_RETRIEVAL_AND_READING.md)、[03](03_PYTHON_CODING_RULES.md)、[06](06_PROTOCOL_AND_REALITY_RULES.md)、[07](07_TESTING_AND_VERIFICATION.md)、[主协议 §4](../00_MASTER_PROTOCOL_AND_SKILL.md) |
| **改算法或数学** | `upper_computer/src/algorithms/`、`src/math/` | [01](01_REPO_MAP_AND_ENTRYPOINTS.md)、[02](02_RETRIEVAL_AND_READING.md)、[03](03_PYTHON_CODING_RULES.md)、[07](07_TESTING_AND_VERIFICATION.md) |
| **只修 bug** | 局部故障定位与最小修复 | [01](01_REPO_MAP_AND_ENTRYPOINTS.md)、[02](02_RETRIEVAL_AND_READING.md) + 对应端规范（[03](03_PYTHON_CODING_RULES.md)/[04](04_DESKTOP_UI_UX_RULES.md)/[05](05_WEB_CONSOLE_RULES.md)/[06](06_PROTOCOL_AND_REALITY_RULES.md)）+ [07](07_TESTING_AND_VERIFICATION.md) |
| **新增功能** | 端到端新特性与闭环接入 | 全套 [01](01_REPO_MAP_AND_ENTRYPOINTS.md)–[08](08_WORKFLOW_AND_DONE_CRITERIA.md)（按 [08](08_WORKFLOW_AND_DONE_CRITERIA.md) 验收 L1–L8 闭环） |
| **只回答问题** | 架构解析、代码追踪、方案评估 | [01](01_REPO_MAP_AND_ENTRYPOINTS.md)、[02](02_RETRIEVAL_AND_READING.md) + 所问模块对应专题规范 |

---

## 3. 规则优先级与冲突裁决

当不同文档表述存在差异时，**MUST** 按如下优先级裁决（高优先级覆盖低优先级）：

1. **当前会话用户的显式指令**
2. **`ai_execution_plan/standards/*.md`**（本通用规范体系）
3. [00_MASTER_PROTOCOL_AND_SKILL.md](../00_MASTER_PROTOCOL_AND_SKILL.md)（仓库三分区、L1–L8 闭环定义、HTTP 接口契约字典）
4. [robot-deployment-assistant SKILL.md](../../upper_computer/.agent_workspace/skills/robot-deployment-assistant/SKILL.md)（早期领域设计参考；如 `StageHintFooter` 已删除等过期 UI 描述以实码及本 `standards/` 为准）
5. 各目录自带 `README.md`（注意：`upper_computer/README.md` 架构说明已过时，仅作历史背景）

---

## 4. 规范文档维护规则

- **篇幅硬约束**：本目录下每份 `.md` 文件 **MUST `<= 150` 行**，采用短列表与结论句，禁止长段落说教。
- **单一事实源**：任何规则变更 **MUST** 只更新唯一归属专题文档，其它文档仅通过相对链接引用，**MUST NOT** 复制大段规则文本。
- **自动索引禁改**：`upper_computer/.agent_workspace/INDEX.md`、`lower_computer/.agent_workspace/INDEX.md` 及 `ai_execution_plan/GLOBAL_SYMBOL_INDEX.md` 由 `ai_execution_plan/verify_deep_closure.py` 自动覆写生成，**MUST NOT** 手工编辑。

---

## 5. 相关参考文档与脚本清单

- [00_MASTER_PROTOCOL_AND_SKILL.md](../00_MASTER_PROTOCOL_AND_SKILL.md)：仓库三分区契约、8 层深度闭环与 Port 8090 HTTP 接口字典。
- [01_STEP1](../01_STEP1_WORKSPACE_SPLIT.md) ～ [06_STEP6](../06_STEP6_E2E_CLOSURE_VERIFICATION.md)：历史重构阶段分步计划（仅作背景参考，不作现行约束）。
- [GLOBAL_SYMBOL_INDEX.md](../GLOBAL_SYMBOL_INDEX.md)：双端 Python 模块与导出符号全局总索引（自动生成）。
- [upper_computer INDEX.md](../../upper_computer/.agent_workspace/INDEX.md) / [lower_computer INDEX.md](../../lower_computer/.agent_workspace/INDEX.md)：各自工程的模块速查索引（自动生成）。
- `ai_execution_plan/STATE_CHECKLIST.json`：核心规则键值与历史步骤完成状态机。
- `ai_execution_plan/verify_deep_closure.py` / `run_all_validation.ps1` / `test_dual_computer_e2e.py`：代码门禁审计、全量测试入口与双端 E2E 闭环测试。
- [SKILL.md](../../upper_computer/.agent_workspace/skills/robot-deployment-assistant/SKILL.md)：算法公式、UniUni v3 视觉令牌与历史基线说明。
- `upper_computer/docs/LRMP V1.0-R3 精简指令规范(1).md` & `upper_computer/群控商业化补充说明.md`：LRMP 帧协议与群控商业化权威参考。
- `lower_computer/下位机ros信息`：下位机实机 ROS 1.17.4 话题、服务与 `/opt/vsis_nav/navctl` 命令参考。

## 自检清单

- [ ] 已明确本次任务类型，并按路由表打开全部必读规范文档
- [ ] 已确认遵循 `standards/` 高于旧版 `SKILL.md` 与工程 `README.md` 的裁决顺序
- [ ] 修改规则时仅改动唯一归属文档并保持文件 `<= 150` 行
