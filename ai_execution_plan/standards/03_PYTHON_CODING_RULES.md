# Python 编码规范与架构约束

> 何时阅读：在 `upper_computer/` 或 `lower_computer/` 中编写、拆分或重构任意 `.py` 模块前必读。
> 前置文档：[01 仓库结构](01_REPO_MAP_AND_ENTRYPOINTS.md)、[02 检索阅读](02_RETRIEVAL_AND_READING.md)。
> 要点速览：1) `src/` 与 `utils/` 严格满足 `<= 300` 行及顶部三段契约头；2) 新代码严守单向分层与 `src.core.*` 统一基础设施；3) 严禁阻断 UI 线程、静默吞异常及 `lambda: None` 占位桩。

---

## 1. 300 行与文件头自动化门禁

`upper_computer/src/`、`upper_computer/utils/`、`lower_computer/src/`、`lower_computer/utils/` 下所有 `.py` 文件由 `ai_execution_plan/verify_deep_closure.py` 强制校验：

1. **行数硬限**：单文件 **MUST `<= 300` 行**；建议达到 `~250` 行即按单一职责拆分子模块。
2. **契约头格式**：文件**前 10 行** **MUST** 出现以下三个标签，`@file` **MUST** 精确等于相对于所属工程根（`upper_computer/` 或 `lower_computer/`）的 POSIX 路径：
   ```python
   # @file: src/protocol/example_client.py
   # @brief: Single-sentence responsibility summary.
   # @exports: ExampleClient, helper_func
   ```
3. **导出同步**：增删公开类或函数后，**MUST** 同步更新文件头 `# @exports:` 与同级 `__init__.py` 的导出及 `__all__`。

---

## 2. 语法、类型标注与命名约定

- 模块顶部 **SHOULD** 放置 `from __future__ import annotations`。
- 所有公开函数、方法签名及返回值 **SHOULD** 带有明确类型注解（`typing` 兼容 Python 3.12）。
- 命名遵循 PEP 8：模块/函数/变量 `snake_case`，类 `PascalCase`，配置常量 `UPPER_CASE`，内部私有方法以下划线 `_` 开头。

---

## 3. 模块依赖方向（新架构区）

在 `upper_computer/src/` 中编写新代码时，**MUST** 严格遵守自底向上的单向依赖，**MUST NOT** 反向导入或制造环依赖：

`core` → `domain` → `math` / `algorithms` → `persistence` → `protocol` → `services` → `ui` / `viewport3d`

- 下位机方向：`config` → `commands` / `ros_bridge` → `task_chain` → `api`。
- 对既有历史模块中的跨层历史导入保持克制，**MUST NOT** 为调整结构而无故大规模重构无关代码。

---

## 4. 基础设施唯一入口

- **路径解析**：**MUST** 调用 `src.core.paths.get_paths()` 获取工作区、数据库、日志或资源路径，**MUST NOT** 自行拼接根目录相对路径或创建根级 `runtime/`、`cache/`、`installer/`。
- **日志记录**：**MUST** 通过 `src.core.logger.get_studio_logger()` / 标准模块 logger 输出，日志落盘于 `.agent_workspace/runtime/logs/`。
- **配置读写**：持久化设置 **MUST** 通过 `src.core.settings.get_settings()` 与 `save_settings()` 读写，避免散落硬编码默认值。

---

## 5. 异常处理、异步任务与线程安全

- **禁止静默吞异常**：**MUST NOT** 使用裸 `except: pass` 隐藏错误；需记录异常信息并向上层或界面返回真实故障原因。
- **禁止阻塞 UI 主线程**：任何网络请求（HTTP/SSH）、串口 I/O 或大文件（`.pcd`/`.tar`）加载 **MUST** 放入 `src/ui/common/async_task.py`（`BackgroundTaskRunner` / `run_in_background`）或后台线程执行。
- **跨线程刷 UI**：后台线程回调修改界面或共享状态时，**MUST** 通过 `StudioEventBus`（`src/core/event_bus.py`）或 Qt `Signal` 切回主线程，严禁在工作线程直接操作 `QWidget`。

---

## 6. 历史大文件与反空桩规则

- **历史巨型文件隔离**：对已超过 300 行的历史文件（如 `app.py`、`backend/deployment_core.py` 等），新增业务 **SHOULD** 独立拆入新模块并仅在旧文件中做最小入口接入，**MUST NOT** 继续向旧文件追加大段逻辑。
- **严禁黑洞/占位实现**：**MUST NOT** 编写 `lambda: None` 空信号绑定、无后台响应的假按钮，或以 TODO 占位代码冒充已完成功能。

## 自检清单

- [ ] 新增/改动的所有 `src/` 与 `utils/` Python 文件均 `<= 300` 行且前 10 行含合规 `@file`/`@brief`/`@exports`
- [ ] 公开 API 均有类型标注，且 `__init__.py` 与 `@exports` 同步更新
- [ ] 无 `except: pass`、无主线程阻塞 I/O、无 `lambda: None` 空绑定
