# 检索、定位与代码阅读规范

> 何时阅读：在搜索符号、读取源码或定位跨端调用链前阅读。
> 前置文档：[README.md](README.md)、[01 仓库结构](01_REPO_MAP_AND_ENTRYPOINTS.md)。
> 要点速览：1) 遵循 索引 → 文件头 → 精准范围读取 链路，严禁盲目全库扫描；2) 历史大文件严格分页窗口读取（<=150 行）；3) 修改可见文本或 DOM ID 前必须先反查测试。

---

## 1. 标准定位与检索顺序

定位模块或符号时，**MUST** 按以下顺序逐步收敛：

1. **工程索引定位**：
   - 上位机先查 [upper_computer/.agent_workspace/INDEX.md](../../upper_computer/.agent_workspace/INDEX.md)；
   - 下位机先查 [lower_computer/.agent_workspace/INDEX.md](../../lower_computer/.agent_workspace/INDEX.md)；
   - 跨端与全局符号查 [GLOBAL_SYMBOL_INDEX.md](../GLOBAL_SYMBOL_INDEX.md)。
2. **协议契约定位**：涉及上下位机接口或参数字段，先查 [00_MASTER_PROTOCOL_AND_SKILL.md §4](../00_MASTER_PROTOCOL_AND_SKILL.md#4-上下位机标准-http-协议接口契约字典-port-8090)。
3. **模块契约头核验**：读取目标 `.py` 文件前 10 行的 `# @file:` / `# @brief:` / `# @exports:` 验证职责匹配。
4. **精准行段读取**：先用关键词定位行号，再只读取目标函数/类所在行区间。
5. **兜底全局检索**：仅当以上步骤均未命中时，再扩至目录级检索。

---

## 2. 阅读预算与上下文纪律

- **`<= 300` 行新架构文件**：在已通过 `INDEX.md` 确认归属后，**SHOULD** 优先只读目标函数区间；确需掌握完整上下文时可一次读取整文件。
- **历史大文件（`app.py` 1337 行、`backend/deployment_core.py` 1104 行、`web/js/wizard.js` 1818 行、`web/js/tab_panels.js` 1634 行、`web/css/style.css` 3604 行）**：
  - **MUST NOT** 一次性通读全文；
  - **MUST** 先检索路由名、函数名或 DOM ID 所在行号，再以 `<= 150` 行为窗口分段读取。
- **不重复读原则**：维护本轮已读文件与行范围记录；未发生编辑的文件 **MUST NOT** 重复读取。
- **并发检索**：互不依赖的多处文件读取或搜索 **SHOULD** 在同一轮并发发起。

---

## 3. 改前测试反查红线

在修改或删除任何**用户可见文案、控件标题、状态文字、CSS 类名或 HTML 元素 ID** 前，**MUST** 先在 `upper_computer/tests/` 与 `lower_computer/tests/` 中检索该字符串或 ID，确认是否被既有回归断言锁定（常见锁定清单见 [05](05_WEB_CONSOLE_RULES.md) 与 [07](07_TESTING_AND_VERIFICATION.md)）。

---

## 4. Windows / PowerShell 检索实用配方

本工作区在 Windows PowerShell 环境下，**未安装 `rg`**，**MUST** 使用内置命令或 Python 脚本：

- **列目录与找文件**：
  ```powershell
  Get-ChildItem upper_computer/src -Recurse -File -Filter "*.py"
  ```
- **文本/符号检索**：
  ```powershell
  Select-String -Path upper_computer/tests/*.py -Pattern "target_id|hint_footer"
  ```
- **中文 UTF-8 输出防乱码**：PowerShell 读取含中文的源码或日志前，**SHOULD** 先设置输出编码或通过 Python 指定 `encoding="utf-8"`：
  ```powershell
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  ```
- **多行脚本防引号踩坑**：PowerShell 中单行 `python -c '...'` 极易因嵌套引号失效，**SHOULD** 使用多行 here-string 管道：
  ```powershell
  @'
  import pathlib
  print(len(pathlib.Path("upper_computer/app.py").read_text(encoding="utf-8").splitlines()))
  '@ | python -
  ```

---

## 5. 跨端功能 8 层追踪法

阅读完整功能链路时，按 [08](08_WORKFLOW_AND_DONE_CRITERIA.md) 与 [主协议 §3](../00_MASTER_PROTOCOL_AND_SKILL.md#3-防遗忘-8-层深度闭环标准-8-layer-deep-closure-standard) 自上而下逐层定位：UI 控件（L1）→ 槽函数/事件（L2）→ `StudioStateService`（L3）→ SQLite Repo（L4）→ `RobotHttpClient`（L5，耗时调用必经 `src/ui/common/async_task.py` 后台执行）→ 下位机 `routes.py`/`ControlArbiter`（L6）→ `ros_bridge`/`TaskChainExecutor` + Webhook（L7）→ `HttpCallbackListener` + `StudioEventBus`（L8）。

## 自检清单

- [ ] 检索时已先查 `INDEX.md` / `GLOBAL_SYMBOL_INDEX.md`，未盲搜大文件
- [ ] 读取大文件时已用符号定位并控制在 `<= 150` 行窗口内
- [ ] 待修改的文案或 ID 已在 `tests/` 中完成反向检索确认
