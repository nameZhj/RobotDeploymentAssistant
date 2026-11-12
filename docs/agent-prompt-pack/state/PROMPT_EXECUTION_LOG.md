# Prompt 执行记录与回滚点审计日志

> 维护规则：每个阶段执行前后必须记录起止 HEAD、修改文件、测试命令与结论。

---

## 执行记录：PROMPT 00

- **执行日期**：2026-11-12
- **执行阶段**：`prompts/00_BOOTSTRAP_AND_AUDIT.md`
- **起始 HEAD**：`1ce6d79f91aa6ab3a53562d519cb213794bfc60e`
- **当前 HEAD**：`1ce6d79f91aa6ab3a53562d519cb213794bfc60e`
- **修改/清理文件**：
  - 移除遗留及 Mock 组件：`src/ui/shell/*`, `src/ui/monitor/*`, `src/ui/monitor_page/*`, `src/ui/left_dock/*`, `src/ui/right_dock/*`, `src/ui/windows/studio_main_window.py`
  - 核心持久化重构：`src/core/storage_manager.py`, `src/core/models.py`, `data/choreo_database.db`
  - 编导主界面接线与生命周期加固：`main.py`, `src/ui/windows/main_studio_window.py`, `src/ui/choreo_page/*`
- **测试执行与退出码**：
  - `pytest tests/unit -q` (Exit Code: 0, 356 Passed)
  - `python tests/verify_choreo_e2e.py` (Exit Code: 0, 10/10 Passed)
- **执行结论**：
  - [OBSERVED] 彻底清理假数据与多库冲突，确立规范基线。

---

## 执行记录：PROMPT 01

- **执行日期**：2026-11-12
- **执行阶段**：`prompts/01_GIT_COMPATIBILITY_AND_SAFE_CLEANUP.md`
- **起始 HEAD**：`1ce6d79f91aa6ab3a53562d519cb213794bfc60e`
- **当前 HEAD**：`1ce6d79f91aa6ab3a53562d519cb213794bfc60e`
- **新增/修改测试与配置**：
  - `tests/compatibility/conftest.py`
  - `tests/compatibility/test_homepage_entry_contract.py`
  - `tests/compatibility/test_flask_api_contracts.py`
  - `tests/compatibility/test_robot_transport_contracts.py`
  - `tests/compatibility/test_ssh_sftp_contracts.py`
  - `tests/compatibility/test_license_contracts.py`
  - `tests/compatibility/test_map_data_contracts.py`
  - `tests/compatibility/test_3d_preview_contracts.py`
  - `tests/compatibility/test_studio_launch_contracts.py`
  - `tests/fixtures/compatibility/README.md`
- **测试执行与退出码**：
  - `pytest tests/compatibility -v` (Exit Code: 0, 20 Passed in 1.08s)
  - `pytest tests -q --ignore=docs` (Exit Code: 0, 376 Passed in 9.31s)
  - `python tests/verify_choreo_e2e.py` (Exit Code: 0, 10/10 Passed in 1.80s)
- **执行结论**：
  - [OBSERVED] 2026-10-01 前 13 核心功能族契约已完整工程化并 100% 回归通过。

---

## 执行记录：PROMPT 02

- **执行日期**：2026-11-12
- **执行阶段**：`prompts/02_ARCHITECTURE_AND_TECH_DECISIONS.md`
- **起始 HEAD**：`1ce6d79f91aa6ab3a53562d519cb213794bfc60e`
- **当前 HEAD**：`1ce6d79f91aa6ab3a53562d519cb213794bfc60e`
- **新增/修改代码与 ADR**：
  - `src/application/studio/studio_facade.py` (统一 9 大 Use Case 接口与 View Data 契约)
  - `src/application/studio/studio_dependencies.py` (唯一 Composition Root 与 dispose 释放)
  - `src/application/studio_controller.py` (移除遗留 mock 演示数据插入)
  - 5 份核心技术决策 ADR (ADR-001 ~ ADR-005)
  - `tests/unit/test_studio_facade_use_cases.py`
- **测试执行与退出码**：
  - `pytest tests/unit/test_studio_facade_use_cases.py -v` (Exit Code: 0, 4 Passed in 0.94s)
  - `pytest tests -q --ignore=docs` (Exit Code: 0, 380 Passed in 9.70s)
  - `python tests/verify_choreo_e2e.py` (Exit Code: 0, 10/10 Passed in 1.82s)
- **执行结论**：
  - [OBSERVED] 架构边界清晰收敛，UI 零直接 SQL 访问，5 份核心技术决策 ADR 批准生效。

---

## 执行记录：PROMPT 03

- **执行日期**：2026-11-12
- **执行阶段**：`prompts/03_UX_DESIGN_SYSTEM_AND_APP_SHELL.md`
- **起始 HEAD**：`1ce6d79f91aa6ab3a53562d519cb213794bfc60e`
- **当前 HEAD**：`1ce6d79f91aa6ab3a53562d519cb213794bfc60e`
- **新增/修改代码与审计产物**：
  - `src/ui/theme/uniuni_inspired_theme.py` (统一 UniUni 设计 Token 与 QSS 引擎)
  - `src/ui/windows/main_studio_window.py` (注入 UniUni 样式与三栏 Splitter 尺寸)
  - `src/ui/header/top_show_header.py` (增加 Ctrl+N/O/S 快捷键与视觉反馈)
  - `main.py` (统一应用全局 UniUni 主题)
  - `docs/agent-prompt-pack/audit/03-ui/control-event-map.csv` (全控件事件映射表)
  - `docs/agent-prompt-pack/audit/03-ui/screenshots/` (1440x900 与 1200x720 离线截图)
  - `tests/unit/test_ui_shell_controls.py` (UI 控件与 Token 测试)
- **测试执行与退出码**：
  - `pytest tests/unit/test_ui_shell_controls.py -v` (Exit Code: 0, 4 Passed in 1.50s)
  - `pytest tests -q --ignore=docs` (Exit Code: 0, 384 Passed in 11.05s)
  - `python tests/verify_choreo_e2e.py` (Exit Code: 0, 10/10 Passed in 1.82s)
- **执行结论**：
  - [OBSERVED] UniUni 风格主工作台外壳与设计系统已完成实装，双分辨率截图存盘，384 项测试全部通过。
