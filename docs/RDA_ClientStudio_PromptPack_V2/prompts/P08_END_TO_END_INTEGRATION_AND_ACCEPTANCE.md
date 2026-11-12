# P08 — 舞台编导端到端集成、视觉验收、性能和回归

**阶段目标**：验证前序所有功能真正组成同一个客户端工作流。修复模块集成问题、视觉问题、持久化问题和回归问题；交付可供用户验收的 Windows 运行版本证据。

**前置**：P00–P07 COMPLETE 或有逐项列明的 PARTIAL。不得通过隐藏未完成项将阶段改为 COMPLETE。

## 1. 集成审计

读取并贯通：

- `main.py` → `StudioWindowManager` → `MainStudioWindow`
- ProjectService / RuntimeContext
- `LeftDockTabs` / `MapManagerPanel` / `FormationPanel` / `AssetLibraryPanel`
- `StageCanvas2D` / `StageViewport3D`
- `DualLayerTimelineCanvas` / `TimelineChoreoController`
- PreviewPlaybackService / StagePreviewEngine / Sampler
- `RightDockPanel`（纯本地 Inspector）
- 所有 Repository / SQLite Adapter / JSON import-export。

输出 `P08_END_TO_END_DATA_FLOW.md`，用 Mermaid 画出：

1. 工程打开的数据流。
2. 地图导入与加载数据流。
3. 机器人创建与 2D 轨迹保存流。
4. 阵型 Apply 数据流。
5. 素材拖放到时间轴数据流。
6. 时间轴播放到 3D Pose 的数据流。
7. 工程导出/导入数据流。

对每条链路标明具体类/方法/信号、领域对象、Repository/DB 表和错误回滚策略。若任何 UI 控件只触发 log 或改变标签，没有持久化或状态更新，视为未完成。

## 2. 端到端验收场景

使用可重置的测试工程 `RDA_E2E_Test_Project`，不使用用户真实工程数据库。测试夹具应包含：

- 一张小型合法 PCD（fixture）。
- 两个 RobotInstance（其中至少一个绑定真实模型资源；若仓库无模型则记录阻塞）。
- 一条 Robot A 轨迹、一条 Robot B 轨迹。
- 一个 Grid 阵型和一个 Circle/Arc 阵型。
- 至少一个有真实关节关键帧的 Dance/Action Asset；若资源不存在，不得伪造，记录缺失并只执行可测试子集。

端到端执行步骤：

### Scenario A：Project lifecycle

1. 创建工程。
2. 保存。
3. 关闭工程。
4. 重新打开。
5. 检查项目 ID、数据库路径、资源相对路径和当前选中状态。

### Scenario B：Map pipeline

1. 导入 PCD。
2. 验证文件 hash 和元数据。
3. 加载到 2D 和 3D。
4. 检查两视图的原点/边界/方向。
5. 卸载再加载。

### Scenario C：Robot + Trajectory

1. 创建两台 RobotInstance。
2. 分别绘制轨迹。
3. 编辑控制点并保存。
4. JSON 导出，再导入另一个测试工程。
5. 对比世界坐标数据。

### Scenario D：Formation

1. 创建阵型。
2. 修改间距、中心和朝向。
3. 触发冲突提示。
4. Apply 到 RobotInstance。
5. 检查 2D/3D 对象同步。

### Scenario E：Asset + Timeline

1. 在本地素材库搜索一个舞蹈和一条轨迹。
2. 拖放到正确轨道/子层。
3. 尝试错误轨道，验证拒绝原因。
4. 移动、拉伸、删除、Undo/Redo。
5. 保存并重启，检查 Clip 数据一致。

### Scenario F：Preview

1. 播放、暂停、停止。
2. 拖动 playhead。
3. 改变倍速、循环。
4. 检查 2D、时间轴、3D 的机器人位姿/动作时间一致。
5. 检查整个过程没有 serial/HTTP/SSH/LoRa/MQTT 请求或派发。

### Scenario G：Export/Import

1. 导出完整项目包。
2. 新目录导入。
3. 验证地图、轨迹、阵型、Clip、模型资源引用闭环。
4. 检查所有相对路径与 hash。

## 3. UI 视觉验收（UniUni 风格）

Windows 实际运行截图至少包括：

- 1440×900 标准窗口全景。
- 1280×720 较小分辨率全景。
- 左侧地图/阵型/素材 Tab。
- 2D 轨迹绘制和选中状态。
- 右侧 Robot/Trajectory/Clip Inspector。
- 底部 Timeline 的 ACTION/TRAJECTORY 双层结构。
- 3D 地图点云和机器人模型视图。
- 各种空状态（无工程/无地图/无机器人/无素材/无 Clip）。
- 导入、删除、错误、保存成功等对话框。

视觉检查：

- 文本无裁切、错位、重叠、溢出；
- 按钮动态变化后尺寸保持稳定；
- 左/右 Dock 与底部时间轴可拖动调整；
- 缩放窗口时中央视口优先扩展；
- 表格和列表滚动条正常；
- 错误/警告/成功状态颜色有语义，不用大面积色块；
- theme tokens 统一，不允许组件各自定义互相冲突的颜色体系。

截图必须来自实际 Qt 运行窗口，不能使用 Figma/mockup/静态绘制代替。记录系统分辨率、DPI、缩放比例、Python/PySide6 版本。

## 4. 性能和资源

使用真实或接近真实的数据规模测量：

- PCD 导入与解析时间、峰值内存。
- 2D Canvas 同时显示机器人数量/轨迹点数量。
- Timeline Clip 数量从 100、500、1000 增长时绘制/拖动响应。
- 3D 点云点数、模型数量和播放 FPS。
- 打开/关闭工程和窗口时 DB connection、QTimer、worker、GPU 资源是否释放。

报告至少包括 mean/P95/max 和测试机器硬件。超过交互目标时做针对性优化，不要直接引入未经验证的依赖或把数据采样精度任意降低。

## 5. 数据一致性与故障注入

至少模拟：

- DB locked。
- 磁盘空间不足/只读目录。
- JSON 文件损坏。
- PCD 文件缺失/截断。
- 模型 Mesh 丢失。
- 工程包导入失败。
- 时间轴 Clip 资源引用失效。
- 用户取消长时间导入。
- 播放过程中切换项目/关闭窗口。

每种情况检查：没有伪成功、UI 回滚、资源句柄释放、当前工程数据不损坏、日志可定位问题。

## 6. 旧功能回归

1. 对照历史 Git 证据和 `COMPATIBILITY_MATRIX.md`，运行 2026-10-01（含）前已正确功能的回归。
2. 项目原有 Flask 页面、主窗口启动、运维页面、文件导入等不属于本轮的功能，至少做 smoke test，确认没有被本轮改动破坏。
3. 如果舞台编导原来某按钮承担旧工作流，但现在范围明确调整为本地创作，记录变更原因，不把它默默删掉。
4. 验证 `main.py` 仍能按原方式启动，不因引入 3D 依赖导致 Flask/Web 入口启动失败。
5. 检查打包流程是否需要包含新增 3D DLL、URDF、mesh、Qt plugin；没有打包验证就标记 NOT RUN。

## 7. 发布前检查

- Python compile / type / lint（按项目现有工具执行）。
- 所有自动化测试和关键 UI 测试。
- SQLite migration 在真实拷贝数据库上成功，并验证回滚。
- requirements pin / wheel 安装 / Windows 打包依赖。
- 检查日志是否包含用户路径/大段资源敏感内容；不在日志输出完整动作数据或大点云。
- 检查无遗留 debug print、临时数据、假数据和无用依赖。
- 完整审阅 git diff、删除文件、未跟踪文件、依赖和 schema。

## 8. 完成标准

### Must Pass

1. Project → Map → Robot → Trajectory → Formation → Asset → Timeline → Preview 全链路可操作。
2. 重启工程后全部本地数据可恢复。
3. 工程 A/B 严格隔离。
4. PCD、轨迹 JSON、工程包导入/导出可靠。
5. Timeline Clip 与 3D Preview 使用同一数据和同一播放时钟。
6. 新工程无 fake Robot、fake Track、fake Clip。
7. 舞台编导工作区无机器人端/服务端通信/指令下发功能。
8. 项目其他既有 Web/运维功能 smoke test 无回归。
9. Windows Qt GUI 验收截图已生成。
10. 未运行测试和剩余限制全部披露。

任何核心功能未完成时标记 PARTIAL，列出阻塞因素、受影响用户操作和后续最小任务，不允许用文档替代实现。

## 9. 最终交付文档

更新：

- `docs/agent-prompt-pack/state/PROJECT_STATE.md`
- `docs/agent-prompt-pack/state/ARCHITECTURE.md`
- `docs/agent-prompt-pack/state/TASKS.md`
- `docs/agent-prompt-pack/state/COMPATIBILITY_MATRIX.md`
- `docs/agent-prompt-pack/state/TEST_MATRIX.md`
- `docs/agent-prompt-pack/state/PROMPT_EXECUTION_LOG.md`
- `docs/agent-prompt-pack/state/SESSION_HANDOFF.md`
- `docs/agent-prompt-pack/audit/P08_END_TO_END_DATA_FLOW.md`
- `docs/agent-prompt-pack/audit/P08_TEST_REPORT.md`
- `docs/agent-prompt-pack/audit/P08_UI_SCREENSHOTS/`
- `docs/agent-prompt-pack/adr/` 中的关键技术决策。

最终报告必须给出 COMPLETE/PARTIAL、逐项验收表、测试退出码、截图路径、已知限制和用户可复现步骤。
