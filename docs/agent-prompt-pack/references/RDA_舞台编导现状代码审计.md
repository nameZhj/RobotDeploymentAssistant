# RDA 舞台编导当前代码审计（基于已上传 RAR）

> 审计对象：`RobotDeploymentAssistant.rar` 解压后的 `RobotDeploymentAssistant/`。  
> 本文是 ChatGPT 对归档源码和归档内 `.git` 的直接读取结果。没有修改源码。  
> RAR 内工作树存在大量 dirty changes，因此结论描述的是“上传时工作树快照”，不是纯净 HEAD。

## 1. 真实入口链路

主页按钮位于 `web/components/navbar.html`：

- DOM ID：`btn-open-studio-window`
- 文案：`🎬 舞台编导`
- class：`btn-nav-action`
- inline 样式：蓝紫渐变背景、蓝色边框、`#93c5fd` 文字、700 字重、inline-flex、6px gap、蓝色外发光。
- 基础 `.btn-nav-action` 样式：`padding: 4px 12px`、`border-radius: 16px`、`font-size: 0.78rem`。
- 事件位于 `web/js/app.js`：点击后 `POST /api/system/open-studio`，解析 JSON 并显示 toast。
- API 位于 `app.py`：`/api/system/open-studio` 调用 `main.launch_studio_window()`。
- Qt 窗口生命周期位于 `main.py`：`StudioWindowManager`。
- 创建的窗口是 `src/ui/windows/studio_main_window.py::StudioMainWindow`。
- 舞蹈编排页是 `src/ui/windows/main_studio_window.py::MainStudioWindow`。

因此，**“舞台编导”不是一个网页路由页面，而是主页按钮通过 Flask API 唤起的独立 PySide6 桌面窗口。** 后续所有舞台编导界面改造应以 `StudioMainWindow -> MainStudioWindow` 作为真实入口链路，不要创建一个假设存在的 `src/ui/director_page/stage_director_page.py` 来替代它。

## 2. 项目技术栈（已验证）

- Python 项目。
- Flask 主页/API。
- PySide6/Qt 桌面舞台编导窗口。
- SQLite 本地存储。
- PySerial/LoRa/LRMP 机器人通信。
- Paramiko SSH/SFTP。
- NumPy、PCD 点云处理、栅格投影。
- Qt 绘制和 OpenGL/3D 视口、URDF/STL 机器人模型。

不要把 RDA 改成 Electron/Vue。UniUni 的 Electron/Vue 是参考软件技术栈，不是 RDA 的代码底座。

## 3. 当前舞台编导窗口结构

### 3.1 全局 `StudioMainWindow`

文件：`src/ui/windows/studio_main_window.py`

- 默认窗口 `1440×900`，最小 `1200×720`。
- 顶部 `StudioHeaderBar` 高 `50 px`。
- 中间 `QStackedWidget`，页面顺序：
  1. `MainStudioWindow`：舞蹈编排。
  2. `MonitorPageView`：表演监测。
  3. `NavigationMapPage`：导航地图。
- 底部 `StudioFooterBar` 高 `30 px`。
- `StudioHeaderBar` 有 3 个主导航按钮：舞蹈编排、表演监测、导航地图。

### 3.2 编排页 `MainStudioWindow`

文件：`src/ui/windows/main_studio_window.py`

- 内部顶部 `TopShowHeader` 高 `56 px`。
- 垂直 splitter：上部工作区 + 底部时间轴。
- 上部水平 splitter 初始宽度 `[280, 860, 360]`。
- 左侧 dock 最小宽 `260 px`，但当前 `_build_layout()` 没有向 `left_dock_layout` 添加任何控件，是空白占位。
- 中间是 2D/3D `QStackedWidget`，使用 `StageCanvas2D` 和 `StageViewport3D`。
- 右侧最小宽 `320 px`，放 `LibPanelsController`。
- 底部时间轴最小高 `220 px`，放 `TimelineLeftToolbar` + `DualLayerTimelineCanvas`。

## 4. 已确认的假数据和无效交互

### 4.1 自动注入的演示数据

| 文件 | 位置/对象 | 当前问题 |
|---|---|---|
| `src/application/studio_controller.py` | `_init_sqlite()` | 自动插入 POPPING1/2/3、芭蕾、两条轨迹、多个时间轴 clip |
| `src/infrastructure/storage/choreo_sqlite_store.py` | `DEFAULT_ACTIONS`、`_seed_default_actions()` | 首次打开数据库自动插入四条 A2-W 动作及 `assets/motions/*.npz` 路径 |
| `src/infrastructure/storage/db_bootstrap.py` | `bootstrap_seed_data()` | 自动创建四台 A/B/C/D 机器人、两个轨迹组、9 个片段 |
| `src/ui/choreo_page/stage_canvas_2d.py` | `_robot_spawns`、`_draw_robot_spawns()` | 画布默认绘制 Robot_1(A)、Robot_2(B)，坐标固定为 (-2,0)/(2,0) |
| `src/ui/choreo_page/interactive_stage_2d.py` | `robot_spawns`、`generate_default_point_cloud(12000)` | 默认画两台机器人并生成合成点云 |
| `src/ui/choreo_page/dual_layer_timeline_canvas.py` | `_seed_default_blocks()` | 首次显示 5 个假动作/假轨迹块，另有固定 `BARRIER_9001` |
| `src/ui/choreo_page/action_library_panel.py` | `_seed_default_actions()` | POPPING1、芭蕾、中华武术、Moonwalk、Bow 五条假动作 |
| `src/ui/choreo_page/trajectory_library_panel.py` | `_seed_default_trajectories()` | Robot_1/2/3 轨道和三条假轨迹 |
| `src/ui/choreo_page/timeline_left_toolbar.py` | `_init_ui()` | 固定任务选项“默认任务1/迎宾编舞-A/矩阵变换-B”，固定 A2-W Robot_1/2 轨道头 |
| `src/ui/shell/header_and_footer.py` | `StudioHeaderBar` | 场景选项固定为 123、现场舞台、实验室展厅 |
| `src/ui/shell/header_and_footer.py` | `StudioFooterBar` | 固定 PRO、系统 1.0.2、联网、IP 172.18.0.1、机器人在线 2 |
| `src/ui/windows/main_studio_window.py` | `_on_save_button_clicked()` | 生成时间戳伪 plan_id，并显示“保存成功”，没有证明数据已持久化/编译 |

**处理原则：** 删除“启动时自动注入假数据”的代码，不等于删除用户数据库里的真实记录。任何已有 SQLite 文件必须先备份；只有能够通过精确指纹证明是旧版自动 seed 的记录，才允许执行可回滚迁移。不能按名称模糊匹配后批量删除用户数据。

### 4.2 已确认无响应/错误接线控件

| 文件 | 控件 | 当前接线 | 结论 |
|---|---|---|---|
| `src/ui/choreo_page/lib_panels_controller.py` | `btn_bind` | `clicked.connect(lambda: None)` | 明确无效 |
| `src/ui/windows/main_studio_window.py` | `timeline_toolbar.btn_play` | 额外连接 `lambda: None` | 无意义重复连接 |
| `src/ui/windows/main_studio_window.py` | `btn_save` | `clicked` 直接连 `_on_save_button_clicked`，同时 `saveClicked` 信号也连同一方法 | 一次点击可能执行两次 |
| `src/ui/choreo_page/timeline_left_toolbar.py` | 撤销/重做/分割/删除/缩放/吸附/循环/任务切换 | 信号已定义并发出，但主窗口未连接对应业务处理 | 表面可点，实际未完成 |
| `src/ui/header/top_show_header.py` | 新建/导入/保存、模式切换 | 定义信号，但编排页未连接到项目操作 | 无响应入口 |
| `src/ui/choreo_page/stage_overlay_controls.py` | 轨迹绘制/草图笔 | 同时用 `clicked` 和 `toggled` 发同一类信号 | 重复事件 |
| `src/ui/choreo_page/stage_overlay_controls.py` | 3D 展示动画 | `clicked` 和 `toggled` 都发 `animationToggled` | 重复事件 |
| `src/ui/choreo_page/stage_overlay_controls.py` | 清空草图/清空全部 | 两个按钮都连接同一个 `clearAllClicked` | 按钮文案与实际动作不一致 |
| `src/ui/choreo_page/stage_overlay_controls.py` | 刷新 | 连接 `resetOriginClicked`，实际重置相机 | 文案与行为不一致 |
| `src/ui/choreo_page/stage_overlay_controls.py` | 原点重置/正视视角 | 两个按钮都连接相同 reset 信号 | 功能重复 |
| `src/ui/choreo_page/lib_panels_controller.py` | 轨迹删除/导出 | 按钮操作隐藏的 `tree_traj`，可见的是 `table_traj` | 用户无法通过可见表格选中目标 |
| `src/ui/windows/main_studio_window.py` | 左侧 dock | 容器存在但没有任何子控件 | 空白占位，浪费约 280px |

### 4.3 重复实现/疑似废弃组件（必须先查引用，不能仅凭名字删）

- `src/ui/choreo/stage_canvas_2d.py` 与 `src/ui/choreo_page/stage_canvas_2d.py`：同名 `StageCanvas2D`，不同实现。
- `src/ui/choreo_page/interactive_stage_2d.py`：第三套 2D 画布实现。
- `src/ui/choreo/dual_timeline_panel.py` 与 `src/ui/choreo_page/dual_layer_timeline_canvas.py` / `dual_track_timeline.py`：时间轴实现重叠。
- `src/ui/choreo/right_library_panels.py`、`src/ui/choreo_page/lib_panels_controller.py`、`action_library_panel.py`、`trajectory_library_panel.py`：右侧资源库实现重叠。
- 主窗口当前明确导入 `src.ui.choreo_page.stage_canvas_2d.StageCanvas2D`、`DualLayerTimelineCanvas`、`LibPanelsController`；其他实现是否删除必须再做全仓引用、测试和动态 import 检查。

## 5. 存储层冲突（P0）

当前存在多个数据库文件和同名表的不同 schema：

| 模块 | 默认 DB | 关键 schema |
|---|---|---|
| `StudioController` | `runtime/shows/studio_data.db` | `trajectories(id,robot_id,name,pts,duration)`、`actions(id,name,model,duration)`、`clips(...)` |
| `ChoreoSqliteStore` | `runtime/shows/studio_data.db` | 期望 `trajectories(traj_id,robot_group,waypoints_json,...)`、`actions(action_id,model_type,...)`、`timeline_clips(...)` |
| `StudioRepository` | `runtime/shows/studio_core.db` | scenes/tracks/init_points/actions/trajectory_groups/trajectories/track_state/fragments |
| `ChoreoRepository` / `ChoreoSceneStore` | `runtime/shows/choreo_studio.db` | 另一套 scene/trajectory/timeline schema |

`StudioController` 和 `ChoreoSqliteStore` **共用 `studio_data.db`，但对 `actions` 和 `trajectories` 的列定义不一致**。二者都使用 `CREATE TABLE IF NOT EXISTS`，不会自动合并 schema。一个模块创建表后，另一个模块再按自己的列名查询，可能出现 `no such column`。这是编排页启动、刷新或数据保存的高风险故障点。

清理阶段必须先：
1. 备份所有现存 DB 文件。
2. 在临时副本上复现各 Store 的建表顺序和查询行为。
3. 选择唯一的舞台编导数据访问入口；不要让 UI 组件直接拼 SQL。
4. 编写迁移/兼容层和 round-trip 测试。
5. 不得删除或覆盖原始 DB 文件。

## 6. Git 历史与工作区状态

RAR 内含 `.git`。归档时 Git 信息：

- 分支：`master`，跟踪 `origin/master`。
- HEAD：`a5973d498ea43ffe6d5dae56f715935a7ffefcfb`。
- HEAD 日期：2026-09-11。
- 可见提交数：19。
- 可见历史最新提交日期：2026-09-11，早于用户指定的 2026-10-01 保护边界。
- 上传快照存在大量未提交修改和未跟踪文件；`git diff --stat` 显示 51 个已跟踪文件变更，约 13,358 insertions / 14,488 deletions，另有大量未跟踪目录/文件。

因此不能把整个当前目录当成干净的 HEAD，也不能简单 `git checkout .` 或重置到 HEAD。上传快照里的未提交修改是用户当前工作的一部分，必须先备份、逐文件审查和保护。

## 7. 本次环境验证结果

当前分析容器未安装 `PySide6`、`Flask`、`Paramiko`、`pyserial`。因此：

- `scripts/verify_guardrails.py`：文件长度检查 0 违规、AST/空壳检查 0 违规、资产配置 0 缺失；模块导入检查有 13 项因缺少运行依赖而失败。
- `python -m pytest -q tests/unit`：测试收集阶段因 `paramiko` 未安装而中断。
- 以上是本分析容器依赖不完整导致的结果，不等于用户 Windows 开发环境的测试结果，也不能用来宣称项目测试通过。

## 8. 本次审计的直接结论

舞台编导并非从零开始。RDA 已有 2D/3D 画布、轨迹库、动作库、时间轴、SQLite、PCD、机器人通信、执行协调等大量代码，但目前存在：

1. 多套并行 UI 组件，主窗口只接入其中部分。
2. 启动时自动填充的假机器人、假动作、假轨迹、假任务和假状态。
3. 多个控件没有业务处理，或信号重复连接。
4. 时间轴和资源库控件连接到不同数据存储。
5. 两个存储模块共享同一个 SQLite 文件却使用冲突 schema。
6. 主窗口左侧 dock 空白，整体布局尚未收敛。

**正确顺序：先备份并清理假数据/错误事件/冲突存储，再做新的功能编码。不要在这些基础问题未修复前继续增加按钮、面板或新的数据库类。**
