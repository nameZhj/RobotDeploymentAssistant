# 会话交接文档 (Session Handoff)

> 目的：确保后续 Agent 会话能够无需猜测、严格无缝接续当前工程进展。

---

## 1. 当前工作区状态

- **仓库路径**：`E:/code/python/RobotDeploymentAssistant`
- **Git HEAD**：`1ce6d79f91aa6ab3a53562d519cb213794bfc60e` (main 分支)
- **初始化状态**：`INITIALIZATION_STATUS: COMPLETE`
- **已完成阶段**：Prompt 00（审计清理）、Prompt 01（兼容性契约保护）、Prompt 02（架构边界收敛与 Use Case 门面）、Prompt 03（UniUni 风格主工作台外壳与设计系统）、Prompt 04（领域数据模型、SQLite 持久化与迁移）、Prompt 05（地图资源管理、PCD 导入解析与 2D/3D 加载）均已闭环完成。
- **下一阶段入口**：`docs/agent-prompt-pack/prompts/06_2D_TRAJECTORY_EDITOR_AND_PERSISTENCE.md`

---

## 2. 关键改动与验证成果

1. **UniUni 规范化设计系统实装**：在 `src/ui/theme/uniuni_inspired_theme.py` 建立色彩与尺寸 Token 引擎，应用到 `main.py` 与 `MainStudioWindow`。
2. **响应式三栏与底部 Splitter**：主窗口支持 1440×900 默认与 1200×720 最小边界，上部水平工作区分割为左侧 260px、中央画布 stretch=1、右侧 310px，底部时间轴高度 260px（最小 220px）。
3. **真实运行截图存盘**：完成 1440×900 与 1200×720 双分辨率离线渲染截图，存储于 `docs/agent-prompt-pack/audit/03-ui/screenshots/`。
4. **全控件事件映射表交付**：输出 `control-event-map.csv`，覆盖所有可见按钮、快捷键 (Ctrl+N, Ctrl+O, Ctrl+S) 与事件处理器，无空槽与 `lambda: None`。
5. **Prompt 04 规范持久化与迁移闭环**：
   - 确立 `data/choreo_database.db` 单一 Canonical 数据库，全量收敛适配器。
   - 实现 `MigrationEngine`，完成 `0001` 与 `0002` 迁移并经过幂等、原子回滚、外键保护演练。
   - 彻底清除所有残余假数据与双重工具栏，实现无 Mock 数据状态。
6. **Prompt 05 PCD 地图管道与安全防护闭环**：
   - 彻底清除 `sample_stage.pcd` 假点云注入，实现空地图引导状态。
   - 实现 `MapStorageService`，严格校验 `../` 路径遍历非法访问，支持 Staging 暂存与 SHA-256 查重。
   - 统一 ASCII 与 Binary 双编码 PCD 点云解析，对缺失 XYZ、0 字节与 binary_compressed 明确拒绝。
   - 在用引用安全保护：活跃加载地图或被工程引用地图禁止物理删除。
7. **自动化测试证据**：
   - `pytest tests/unit/test_map_management_and_pcd_pipeline.py -v`：6/6 通过 (100%)；
   - `pytest tests/unit/test_data_models_and_migration.py -v`：7/7 通过 (100%)；
   - `pytest tests/unit/test_ui_shell_controls.py -v`：4/4 通过 (100%)；
   - `pytest tests/compatibility -v`：20/20 通过 (100%)；
   - `pytest tests -q --ignore=docs`：397/397 通过 (100%)；
   - `python tests/verify_choreo_e2e.py`：10/10 检验项通过 (100%)。

---

## 3. 严禁与不可触碰事项 (Red Lines)

1. **严禁在 UI 控件中执行 `sqlite3.connect()` 或直接操作数据库**。
2. **严禁在 UI 控件中直连硬件通信端口（串口/SSH/SFTP）**。
3. **严禁技术栈漂移（固定为 Python + PySide6 + Flask + SQLite，禁止引入 Electron/Vue）**。
4. **严禁在控件中硬编码样式字符串，必须引用单一 Theme Token**。
5. **保护 2026-10-01 前历史功能行为契约**。

---

## 4. 快速验证命令

```powershell
# 1. 运行 UI 外壳与控件事件测试
pytest tests/unit/test_ui_shell_controls.py -v

# 2. 运行历史契约套件
pytest tests/compatibility -v

# 3. 运行全项目 384 个测试
pytest tests -q --ignore=docs

# 4. 运行端到端流程验收
python tests/verify_choreo_e2e.py
```
