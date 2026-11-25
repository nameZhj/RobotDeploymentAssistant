# AI 标准研发流程与完成准出规范

> 何时阅读：开始一项多步开发任务、交付总结前或核对准出条件时必读。
> 前置文档：[README.md](README.md)、[07 测试与验证](07_TESTING_AND_VERIFICATION.md)。
> 要点速览：1) 遵循 理解 → 检索 → 规划 → 小步修改 → 自检 → 验证 → 汇报 闭环；2) 新功能须满足 L1–L8 八层深度穿透；3) 变更后必须同步索引、契约与文档。

---

## 1. 标准研发工作流

1. **理解边界**：阅读用户需求并依据 [README 路由表](README.md#2-任务类型--必读文档路由表) 读全必读规范。
2. **精准检索**：按 [02 检索规范](02_RETRIEVAL_AND_READING.md) 查索引与测试依赖，收集涉改文件与符号清单。
3. **先规划后动笔**：复杂/跨层改动先列出涉改文件、符号及验证方案，再小步分批编辑，保持每个模块紧凑（`< 300` 行）。
4. **自检**：对照 [03](03_PYTHON_CODING_RULES.md)/[04](04_DESKTOP_UI_UX_RULES.md)/[05](05_WEB_CONSOLE_RULES.md)/[06](06_PROTOCOL_AND_REALITY_RULES.md) 检查文件头、文案、线程与协议合规。
5. **最小必要验收**：依据 [07](07_TESTING_AND_VERIFICATION.md) 映射表只运行改动域对应的必要验证，节约 Token；仅在跨端大改、重构或发版前运行全量 `run_all_validation.ps1`。

---

## 2. 8 层深度闭环概要 (L1–L8)

任何跨端功能 **MUST** 完整穿透以下 8 层链路（详述见 [00_MASTER §3](../00_MASTER_PROTOCOL_AND_SKILL.md#3-防遗忘-8-层深度闭环标准-8-layer-deep-closure-standard)）：
- **L1 UI 控件层**：可见、文案精简无截断、无死按钮/空回调。
- **L2 Signal 信号层**：控件准确绑定页面/面板槽函数。
- **L3 Service 状态层**：经 `StudioStateService` 并接入 `StudioUndoStack`（如适用）。
- **L4 SQLite 持久化层**：数据入库并支持跨重启还原。
- **L5 上位机通信层**：配网走 LoRa，其余全走 Wi-Fi HTTP。
- **L6 下位机 HTTP 路由层**：参数校验、控制权互斥及标准 HTTP 状态码。
- **L7 ROS/执行与 Webhook 层**：调用真实 `navctl`/ROS/运控并由执行器发送真实回调。
- **L8 回调刷新层**：`HttpCallbackListener` + `StudioEventBus` 驱动 2D/3D 视口实时更新。

---

## 3. 改后同步义务与准出标准 (DoD)

- **改后必须同步**：
  - 变更 `src/` 或 `utils/` 模块公开符号/文件后，**MUST** 运行 `python ai_execution_plan/verify_deep_closure.py` 自动更新 `INDEX.md` 与 `GLOBAL_SYMBOL_INDEX.md`。
  - 协议变动 **MUST** 更新 [00_MASTER §4](../00_MASTER_PROTOCOL_AND_SKILL.md#4-上下位机标准-http-协议接口契约字典-port-8090)；导出变化 **MUST** 更新 `@exports` 与 `__init__.py`；通用规范变动 **MUST** 更新对应 `standards/*.md`。
- **Definition of Done (DoD)**：改动严格收敛于任务范围；满足门禁与 UI/协议规则；改动域对应核心验证在末次编辑后通过；无残留调试/临时文件。

---

## 4. 绝对禁止事项与环境提示

- **高危禁令**：**MUST NOT** 改写 Git 历史（如 `--force`/`reset --hard` 破坏工作区）；**MUST NOT** 删除用户数据或 `.agent_workspace/runtime/*.db`；**MUST NOT** 提交 `.db`/`.pcd`/缓存构建产物；**MUST NOT** 在仓库或工程根目录新建越权目录；**MUST NOT** 绕过/屏蔽门禁测试；引入新依赖时 **MUST** 同步更新 `upper_computer/requirements.txt`。
- **Windows Shell 注意**：Windows PowerShell 5.x 不支持 `&&`，串联依赖步骤 **MUST** 使用 `;` 并检查 `$LASTEXITCODE`（或封装为 `.ps1`）；无 `rg`，改用 `Select-String` 或 Python heredoc。
- **汇报规范**：最终答复保持简洁、中文为主、带可点击路径链接，仅陈述本轮实际观察到的文件、符号与验证结果。

## 自检清单

- [ ] 新功能已穿透 L1–L8 闭环，或局部改动未破坏既有链路
- [ ] 已运行 `verify_deep_closure.py` 完成索引与 300 行门禁同步
- [ ] 无越权根目录文件、未删用户数据库、无新增未登记依赖
- [ ] 已运行与本次改动相匹配的最小必要验证，汇报内容与实测输出完全一致
