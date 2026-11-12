# P00 — 接管 Prompt 00–05 执行后的工作区，并修复舞台编导基础链路

**阶段目标**：先让现有舞台编导的对象依赖、数据源、信号槽和空状态真实一致。这个阶段不是重写功能，也不是重新执行旧 Prompt 00–05。它负责接管用户已经修改过的工作区，找出旧 Prompt 没有真正落地的部分，并在保护用户改动的前提下修复根因。

**执行前置**：必须同时读取 `GLOBAL_EXECUTION_CONTRACT.md` 和仓库内 `.agent_workspace/skills/robot-deployment-assistant/SKILL.md`。

## 1. 绝对要求

1. 直接在当前本地仓库工作，不得重置成 GitHub `main`，不得重新 clone 覆盖用户文件。
2. 不要把旧 Prompt 00–05 生成的所有代码一律判定为正确或错误。逐项对照代码、信号槽、数据文件、测试和 UI 操作确认。
3. 本阶段只做舞台编导客户端本地链路。移除/隔离该窗口内的机器人通信、HTTP 上传、串口指令和急停派发；不得删除其他页面的既有运维功能。
4. 本阶段必须修改代码并执行测试，不允许只提交审计报告。
5. 不要新增第二套舞台编导窗口。主入口继续是 `main.py` 中 `StudioWindowManager` 创建的 `MainStudioWindow`。

## 2. 接管和基线检查

先执行并保存完整输出：

```powershell
git rev-parse --show-toplevel
git status --short --branch
git status --porcelain=v2
git rev-parse HEAD
git diff --binary > docs/agent-prompt-pack/audit/P00_before_unstaged.patch
git diff --cached --binary > docs/agent-prompt-pack/audit/P00_before_staged.patch
```

若目录不存在，先创建。保存 untracked 文件清单、用户数据库/地图/轨迹/阵型/模型文件列表及 SHA-256。禁止使用 `git clean`、`git reset --hard`、force checkout 等破坏性命令。

重新读取以下文件的**本地版本**，不可仅依赖 GitHub 静态快照：

- `main.py`
- `src/ui/windows/main_studio_window.py`
- `src/ui/choreo_page/left_dock_tabs.py`
- `src/ui/choreo_page/stage_canvas_2d.py`
- `src/ui/map_manager_panel.py`
- `src/application/stage_director/stage_map_controller.py`
- `src/ui/choreo_page/dual_layer_timeline_canvas.py`
- `src/application/stage_director/timeline_choreo_controller.py`
- `src/infrastructure/storage/choreo_sqlite_store.py`
- `src/infrastructure/storage/timeline_clip_sqlite_adapter.py`
- `src/ui/choreo_page/right_dock_panel.py`
- `src/ui/choreo_page/choreo_toolbar.py`
- `src/ui/choreo_page/stage_overlay_controls.py`
- `src/ui/stage3d/stage_viewport_3d.py`
- `src/application/services/virtual_show_player.py`
- `src/application/stage_director/stage_preview_coordinator.py`
- `src/application/stage_director/stage_preview_engine.py`
- `src/ui/asset_library.py`
- `src/core/asset_registry.py`

对照本包 `PROJECT_AUDIT_BASELINE.md`，生成 `docs/agent-prompt-pack/audit/P00_LOCAL_RECHECK.md`。每项标记 `CONFIRMED / FIXED_ALREADY / NOT_REPRODUCED / UNKNOWN`，并附本地路径、方法名、证据。发现本地代码已修复的项目，不要重复改写。

## 3. 建立唯一的舞台编导依赖注入链

### 3.1 当前已观察到的接线问题

在 GitHub `main` 静态快照中：

- `MainStudioWindow.__init__()` 创建 `self.store = ChoreoSqliteStore()` 和 `self.map_controller = StageMapController(...)`。
- `_build_layout()` 创建 `LeftDockTabs(..., controller=self.controller)`，没有显式传入 `self.map_controller` 和 Store。
- `LeftDockTabs.__init__()` 仅接收 `controller`，再用 `getattr(self.controller, "map_controller", None)` 寻找地图控制器。
- 当 `main.py` 默认创建窗口时，`MainStudioWindow` 的 `controller` 参数没有传入；于是 `MapManagerPanel` 可能自行创建另一个 `StageMapController`。
- `StageCanvas2D` 虽然构造函数支持 `store`，但主窗口没有传 `store=self.store`。
- `DualLayerTimelineCanvas` 内部执行 `TimelineChoreoController()`，没有接收主窗口的项目/数据库上下文。

必须在本地验证以上情况后修复。

### 3.2 具体实施

建立明确的 Composition Root / `StudioRuntimeContext`（名称可调整，但只能有一个主对象），集中创建并持有：

- 当前工程会话/当前工程数据库连接配置（P01 会进一步完善 ProjectService；本阶段先提供可扩展的注入接口）。
- 当前工程的 `ChoreoSqliteStore` 或统一 Store。
- 当前工程的 `StageMapController`。
- 当前工程的 `TimelineChoreoController`。
- 当前工程的 Robot/Trajectory/Formation/Asset 查询服务（若已有服务则复用，不要复制）。

将这些对象显式注入，而非让 Widget 内部悄悄 new：

- 扩展 `LeftDockTabs.__init__`，至少显式接收 `map_controller` 和工程上下文；
- `MapManagerPanel` 使用主窗口提供的同一个 `StageMapController`；
- `StageCanvas2D(..., store=...)` 使用同一项目 Store；
- `DualLayerTimelineCanvas` 接收统一创建的 `TimelineChoreoController` 或 Store/DB path + task context；
- `StagePreviewEngine.build_preview_tracks()` 从当前工程上下文取 Store 和项目标识，不得另行打开默认数据库；
- `VirtualShowPlayer`、`StagePreviewCoordinator` 和 3D 视口从同一份 Preview Snapshot 获取数据。

必须提供自动化断言，证明：

```python
main_window.left_tabs.map_panel.controller is main_window.map_controller
main_window.stage_2d.store is main_window.store
main_window.timeline_canvas.choreo_controller 使用当前工程同一 DB path
PreviewEngine 读取的 DB path 与当前工程一致
```

上述表达是验收意图，实际测试可通过正式公开属性验证；不要依赖私有字段做生产逻辑。

### 3.3 依赖生命周期

- 主窗口只负责创建/注入服务，子控件不得持有重复的业务数据库或互相构造对方。
- 工程切换时要么通过可控的 `set_project_context()` 更新依赖，要么由主窗口安全销毁并重新创建工程作用域控件；不得留下旧 DB 连接或旧地图控制器。
- 窗口隐藏/关闭时播放器、worker、文件句柄正确停止/释放；不能因窗口重复打开造成重复 Qt 连接或定时器。
- 不要因为现有 `controller` 参数在历史页面使用而粗暴删除；确认所有调用方后保持兼容。

## 4. 空状态清理：不得显示演示机器人

逐一检查并处理：

- `StageViewport3D.__init__()` 中 `_robot_meta` 和 `_robot_poses` 默认的 `Robot_1` / `Robot_2`。
- `VirtualShowPlayer._init_default_tracks()` 的两台机器人默认轨迹与 `POPPING1`、`POPPING2`、`中华武术` 默认动作。
- `StagePreviewCoordinator.__init__(load_defaults=True)` 和 `_init_default_tracks()` 的同类默认数据。
- 其他窗口构造/刷新逻辑中任何默认机器人、默认 Clip、默认轨迹、默认在线状态。

将产品默认状态改成空数据：

- 新建项目没有机器人、地图、轨迹、动作 Clip。
- 播放器无轨道时停止/禁用播放，显示“当前工程没有可播放的时间轴内容”。
- 3D 视口无机器人时只显示地面、坐标轴、网格/已加载地图和空状态提示。
- 有合法的仓库内置舞蹈/动作素材时可展示素材库，但不能因此自动在舞台上生成机器人或时间轴 Clip。
- 测试若需要演示对象，使用明确的 test fixture，禁止在正式构造函数自动 seed。

增加测试：新建空窗口/空工程时机器人数量为 0、播放器轨道数量为 0、时间轴 Clip 数为 0；切换到 3D 视图不出现任何 Robot_1/Robot_2。

## 5. 从舞台编导窗口隔离通信和运控控件

重点审查 `RightDockPanel`、`ChoreoToolbar`、`StageOverlayControls` 和 `MainStudioWindow._wire_signals()`。

### 5.1 右侧 Dock

`RightDockPanel` 当前在 Inspector 之外包含 HTTP 轨迹上传、IP/Port、通信状态、串口状态和 STAND/GAIT/STOP/PASSIVE 基础指令。把它收敛为纯本地 Inspector：

- 选中对象类型、ID、世界坐标、角度、所属资源/轨道；
- 轨迹属性：名称、时长、点数、长度、绑定机器人；
- 阵型属性：名称、类型、中心点、成员数；
- 时间轴 Clip 属性：素材名称、Clip ID、起始时间、持续时长、轨道层；
- 无对象时显示明确空状态。

删除舞台编导窗口中 HTTP 上传、IP/Port、串口状态、通信状态和机器人指令发射 UI 及其 handler/import/信号。只在本窗口上下文内隔离，不能删除 `robot_trajectory_http_gateway`、serial manager 或其他页面的功能。

### 5.2 急停/动作派发

`MainStudioWindow._on_basic_motion()`、`_on_emergency_brake()` 和任何调用 `serial_manager.send_raw_command()` 的舞台编导连接必须从本地创作路径中断开。舞台预演播放只驱动本地时间轴/视口。

若 `ChoreoToolbar` 或 `StageOverlayControls` 仍包含急停按钮：从舞台编导创作工具栏移除；或明确禁用并显示“本地预演不控制真实设备”。不能点击后向串口发送任何数据。

对舞台编导的播放、暂停、停止、拖动播放头做测试，断言不会触发串口/HTTP/SSH。

## 6. 修复保存和时间轴编辑的假成功风险

### 6.1 保存

当前快照中 `MainStudioWindow._on_save_button_clicked()`：

- 直接访问 `timeline_canvas._blocks` 和 `_tracks`；
- 固定保存 `scene_001` / `主舞台默认场景`；
- 无条件弹出 SQLite 和 `data/projects/` 保存成功。

本阶段先拆除这种“无论实际结果如何都成功”的实现：

- 不再从 QWidget 私有绘制状态构造持久化记录；
- 由 application service/use case 从领域数据/Repository 读取并保存；
- 数据库或文件写入失败时必须显示真实错误，不显示成功；
- 在 P01 工程服务落地前，若尚不存在有效当前工程，可以禁用保存并提示“请先创建/打开本地工程”，但不得伪成功。
- `TopShowHeader` 的 New/Open/Save/Import/Export 信号逐一追踪并连接到真实动作；不能用清空画布冒充新建工程。

### 6.2 时间轴编辑

`DualLayerTimelineCanvas.mouseMoveEvent()` 当前直接修改画布内 `TimelineBlock`，释放时才持久化。检查 `TimelineChoreoController.move_clip()` / `resize_clip()` 的 bool 返回值：

- 鼠标按下时记录旧值；拖动阶段只维护 preview state；
- 鼠标释放时提交业务命令；
- 返回 False 或抛异常时回滚旧值、刷新视图、显示错误；
- 提交成功才更新选中项/脏状态；
- 禁止 UI 显示新值但 DB 仍保存旧值。

若本地已实现更完整的 Command/Undo 机制，优先复用。

## 7. 必须检查的其它信号连接

完整检查并输出一张信号槽清单：

- Header：New / Open / Save / Import / Export。
- ChoreoToolbar：新建、保存、导入轨迹、导入地图、模式切换、撤销、清除、完成轨迹、重置视图。
- StageOverlayControls：2D/3D 切换、网格、重置相机、播放、清除、模式。
- LeftDockTabs：地图加载/卸载、阵型应用、机器人选择、素材选择。
- TimelineLeftToolbar：播放、停止、撤销/重做、删除、缩放、吸附、循环。
- DualLayerTimelineCanvas：拖放、选择、移动、拉伸、删除、撤销、重做、播放头。

对每个控件记录 objectName、信号、slot、业务效果、失败反馈、测试方式。检查重连、重复 connect、lambda 捕获变量和销毁生命周期。

## 8. 本阶段验收

### Must Pass

1. `MainStudioWindow` 只存在一套当前工程的 Store、MapController、TimelineController 依赖，并且所有子组件用的是同一份上下文。
2. 空工程启动没有假机器人、假轨迹、假 Clip 和假播放内容。
3. 舞台编导不再有机器人指令派发、串口急停或 HTTP 上传入口；项目其他运维页保持完整。
4. Header 的新建/保存等按钮不再通过清空画布或伪成功弹窗冒充工程操作。
5. 时间轴持久化失败会回滚 UI 状态。
6. 关键 Qt 信号槽有自动化测试或逐项验证记录。
7. 对受影响的现有功能进行回归；未运行的 Windows Qt 项明确标记 NOT RUN。

### 用户手工验证流程

1. 启动现有主程序，从原入口打开舞台编导窗口。
2. 新建或进入空工程；确认左侧没有凭空产生机器人、地图或轨迹。
3. 切换 2D/3D；确认 3D 为空场景。
4. 点击本地播放；无 Clip 时应禁用或提示，不得发设备命令。
5. 检查右侧 Inspector 仅显示本地对象属性，不出现通信/上传/串口状态。
6. 用自动化测试模拟 SQLite 更新失败，确认时间轴恢复旧位置。

## 9. 交付文件和报告

- `docs/agent-prompt-pack/audit/P00_LOCAL_RECHECK.md`
- `docs/agent-prompt-pack/audit/P00_SIGNAL_SLOT_MATRIX.md`
- `docs/agent-prompt-pack/audit/P00_TEST_REPORT.md`
- `docs/agent-prompt-pack/state/PROJECT_STATE.md`
- `docs/agent-prompt-pack/state/ARCHITECTURE.md`
- `docs/agent-prompt-pack/state/SESSION_HANDOFF.md`
- 相关测试文件及实际代码修复。

仅当 Must Pass 全部具备证据时标记 `COMPLETE`。完成后只进入 `P01_LOCAL_PROJECT_AND_DATA_MODEL.md`。
