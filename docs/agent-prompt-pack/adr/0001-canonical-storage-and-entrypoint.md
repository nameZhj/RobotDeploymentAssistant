# ADR 0001: 规范化单一存储引擎与舞台编导入口链路固化

- **状态**：已批准 (Approved)
- **日期**：2026-11-12
- **决策者**：RobotDeploymentAssistant 核心工程组

## 1. 背景与问题
历史工程中存在以下严重问题：
1. 存在三个相互冲突的 SQLite 数据库：`runtime/shows/studio_data.db`、`studio_core.db`、`choreo_studio.db`，表结构字段互不兼容（如 `actions` 与 `trajectories` 列名冲突），导致查询抛错。
2. 主页唤起舞台编导窗口时，存在 `StudioMainWindow` 与 `MainStudioWindow` 两套窗口壳层，且主页重复点击会导致窗口崩溃或创建多实例。
3. 多个模块在首次启动时硬编码注入假数据，污染数据库。

## 2. 决策内容
1. **单一规范化存储层**：将 `src/core/storage_manager.py`（单例 `storage_manager`）作为系统唯一持久化入口，数据库收敛为 `data/choreo_database.db`，并辅以 `data/` 下的标准 JSON 目录结构。
2. **唯一窗口入口**：将 `MainStudioWindow` 作为唯一编排工作台窗口，由 `main.py::StudioWindowManager` 统一管理单例生命周期，设置 `app.setQuitOnLastWindowClosed(False)`，彻底消除二次打开崩溃。
3. **彻底清除 Mock 注入**：移除启动时注入 POPPING1、固定 IP、固定 2 台在线等代码，所有状态严格以真实数据驱动。

## 3. 后果与影响
- **积极影响**：数据一致性得到保证，356 项测试全绿，主页点击稳定可靠。
- **合规边界**：保留旧数据库冷备份至 `docs/agent-prompt-pack/audit/00-cleanup/db-backup/`，确保用户既有资产不丢失。
