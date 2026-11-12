# PROMPT 00 — 舞台编导现有实现清理与可运行性恢复

**本阶段不是新功能开发阶段。** 本阶段唯一目标：从主页“🎬 舞台编导”按钮进入现有 Qt 窗口，清理错误/重复/无响应的遗留控件、移除生产环境自动注入的虚假演示数据、修复编排页存储冲突和信号接线，使现有舞台编导界面成为一个真实、可操作、没有假数据的稳定基线。完成本阶段前，不得开始 2D 新功能、阵型、舞蹈时间轴或 3D 新功能的重新开发。

## A. 本阶段的真实上下文（不要重新猜测）

开始编码前先读取：

1. `.agents/skills/robot-deployment-assistant/SKILL.md`
2. `docs/agent-prompt-pack/references/UNIUNI_1.0.2_界面与交互逆向分析.md`
3. `docs/agent-prompt-pack/references/RDA_舞台编导现状代码审计.md`
4. `AGENT_GUIDE.md`
5. `README.md`

UniUni 的逆向分析已经由 ChatGPT 完成并放入 references。**禁止把“解析 UniUni”再次分配给本地 Agent，也不要重新安装/运行 UniUni。** 你只需要按报告把可借鉴的信息架构和交互规则落实到 RDA。

项目底座是 Python + Flask + PySide6 + SQLite 的 RobotDeploymentAssistant。主页按钮入口链路已经存在：

`web/components/navbar.html#btn-open-studio-window`
→ `web/js/app.js`
→ `POST /api/system/open-studio`
→ `app.py::open_studio_route`
→ `main.py::launch_studio_window`
→ `StudioWindowManager`
→ `src/ui/windows/studio_main_window.py::StudioMainWindow`
→ `src/ui/windows/main_studio_window.py::MainStudioWindow`

不要另建 Electron/Vue 项目，不要另建一个假设存在的 `director_page` 入口替换这条链路。

## B. 执行前保护与审计输出

### B1. 确认真实仓库和工作区

在项目根目录执行并记录：

```powershell
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git log --all --date=iso --pretty=format:"%h %ad %s"
git status --short --branch
git diff --stat
git diff --cached --stat
git ls-files --others --exclude-standard
```

创建输出目录：

```text
docs/agent-prompt-pack/audit/00-cleanup/
```

至少保存：

- `git-status-before.txt`
- `git-log-before.txt`
- `git-diff-before.patch`（包含 `git diff --binary`）
- `git-diff-cached-before.patch`
- `untracked-files-before.txt`
- `file-inventory-before.txt`
- `database-inventory-before.txt`
- `cleanup-ledger.csv`

对未跟踪文件建立可恢复副本或归档；对 `runtime/shows/` 下所有 SQLite 数据库先复制到 `audit/00-cleanup/db-backup/`，同时记录文件大小、修改时间和 SHA-256。不要执行 `git reset`、`git clean`、强制 checkout、强制 rebase 或覆盖式恢复。

### B2. 建立可执行基线

从 `requirements.txt`、构建脚本和 import 语句确认依赖。当前代码入口明确依赖 PySide6，但上传快照的 `requirements.txt` 未列出 PySide6；先核对项目真实运行环境和打包依赖，再修复依赖清单，不要凭猜测升级所有依赖。

执行项目现有测试和守卫脚本。记录：
- 实际命令；
- 通过/失败数量；
- 失败是代码错误还是依赖缺失；
- 首次启动窗口是否成功；
- 主页按钮是否能唤起窗口；
- Qt 异常日志和 SQLite 错误。

不要把“当前分析容器缺依赖”写成项目代码失败；也不要把未运行的 UI 写成通过。

## C. 先固定入口，不要改坏主页

主页“舞台编导”按钮的现有视觉样式应保留，不要重复增加第二个入口。

`web/components/navbar.html` 中当前按钮：

- ID：`btn-open-studio-window`
- 文案：`🎬 舞台编导`
- 基础 class：`btn-nav-action`
- 基础 padding：`4px 12px`
- 基础圆角：`16px`
- 基础字号：`0.78rem`
- 当前强调样式：蓝紫渐变、蓝色边框、`#93c5fd` 文字、700 字重、6px 图标/文字间距、蓝色外发光。

点击行为必须保持：

1. 只触发一次 `POST /api/system/open-studio`。
2. 请求期间禁用按钮或显示轻量 loading，防止连续创建多个窗口。
3. 返回 `success=true` 时显示服务端 `msg`。
4. 返回失败或 HTTP 错误时显示明确错误，不得显示“已启动”。
5. 重复点击应复用现有 `StudioWindowManager` 窗口，不得创建多个 Studio 窗口。
6. 不要改动主页其他运维、部署、串口和 3D 预览入口。

验收：点击一次只创建/唤起一个 `StudioMainWindow`；窗口已打开时再次点击只 bring-to-front；Qt 启动失败时主页显示错误 toast。

## D. 清理舞台编导窗口中的假状态和假资源

### D1. 清理 `StudioHeaderBar` 的假场景选项

文件：`src/ui/shell/header_and_footer.py`

当前 `StudioHeaderBar._build_ui()` 把场景 ComboBox 固定填为：

- `123`
- `现场舞台`
- `实验室展厅`

这些不是从仓库读取的场景记录。改成从真实场景仓储加载：

- ComboBox 宽度建议 `180 px`，高度 `30 px`。
- 左侧标签“场景”字号 `11 px`、颜色 `#94A3B8`。
- 只展示数据库真实存在的场景，显示名称，`userData` 保存真实 scene_id。
- 当前场景无记录时显示单项“未创建场景”，并禁用依赖场景的编辑/保存操作。
- 点击切换场景时先检查当前工程是否有未保存修改；有修改则弹出“保存 / 放弃 / 取消”。
- 不得保留“现场舞台”“实验室展厅”这种没有数据库记录的演示选项。

### D2. 清理底栏虚假设备信息

同文件 `StudioFooterBar` 当前固定显示 PRO、系统 1.0.2、联网、IP `172.18.0.1`、机器人在线 2。全部改成真实状态绑定：

- 用户身份没有真实来源时显示“本地会话”，不得写死 admin。
- 系统版本读取项目配置/打包版本；没有值显示 `--`。
- 网络状态必须来自真实网络检测；未检测显示“未知”，离线显示“离线”。
- IP 必须来自实际选定网卡；没有有效 IP 显示 `--`。
- 在线机器人数量必须来自真实设备状态/心跳；没有设备时显示 `机器人 0`。
- PRO/订阅徽章没有真实授权源时不显示。
- 底栏高度保持 `30 px`，字体 `11 px`，间距 `10 px`；在线点绿色 `#10B981`，离线灰色 `#64748B`，错误红色 `#EF4444`。

### D3. 清除自动注入的假机器人/动作/轨迹/任务

按以下文件逐项处理：

1. `src/application/studio_controller.py`
   - `_init_sqlite()` 不得在首次启动时插入 POPPING1/2/3、芭蕾、`100001/100002` 假轨迹和假 clip。
   - `current_plan_id=8001`、`current_run_id=9001` 不得伪装成真实已编译计划或执行记录。
   - `_emit_pose_at()` 不得无条件循环固定机器人 ID `(1, 2)` 并把 `(-2,0)/(2,0)` 当作真实设备状态。
   - 无真实机器人时返回空 pose 集合；若确实需要内部仿真，必须由显式“仿真模式”开关启用，并在 UI 每处标记“仿真”，不能进入真机列表或下发流程。
   - 120 秒自动归零只能作为显式循环播放配置，不能作为隐藏固定行为。

2. `src/infrastructure/storage/choreo_sqlite_store.py`
   - 禁止 `_seed_default_actions()` 自动插入 `DEFAULT_ACTIONS`。
   - `DEFAULT_ACTIONS` 中 `assets/motions/*.npz` 路径没有实际文件/来源证明时不得作为动作库条目。
   - 动作库为空时显示空状态：“尚无可用动作。连接机器人同步动作，或导入真实动作文件。”
   - 动作必须来自真实数据库记录、机器人动态动作列表或用户导入文件；显示来源和适配机型。

3. `src/infrastructure/storage/db_bootstrap.py`
   - `bootstrap_seed_data()` 不得创建虚构 A/B/C/D 四台机器人、虚构轨迹组和 9 个片段。
   - 可保留一个必要的空默认场景记录（如果现有代码仍依赖 scene_id=123），但名称应为“默认场景”，不得伪造地图、音乐、机器人和轨迹。
   - 空场景的 tracks、actions、trajectory_groups、trajectories、track_state、fragments 应为空。
   - 不要删除已经存在的用户记录；仅停止新建假记录。旧数据库的样本清理必须通过 D5 的精确指纹和备份规则处理。

4. `src/ui/choreo_page/stage_canvas_2d.py`
   - 删除 `_robot_spawns` 和 `_draw_robot_spawns()` 中固定 A/B 两台机器人。
   - 改为读取真实机器人/初始点列表；无机器人时画布显示空状态文字“未发现机器人。连接设备或导入机器人配置后可开始编排。”
   - 不得默认在世界坐标 (-2,0)/(2,0) 画机器人。

5. `src/ui/choreo_page/interactive_stage_2d.py`
   - 不得在正式编排页面构造时调用 `generate_default_point_cloud(num_points=12000)` 并将合成点云当作现场地图。
   - 如果该类不在主入口调用链中，按 G 节引用审查处理；不得继续作为正式入口。
   - 无地图时显示“尚未加载地图”，保留网格和坐标轴，但不得显示虚构障碍物。

6. `src/ui/choreo_page/dual_layer_timeline_canvas.py`
   - 删除 `_seed_default_blocks()` 和固定 `BARRIER_9001`。
   - 初始时间轴必须是空轨道；显示空状态“从右侧动作库或轨迹库拖入片段以开始编排。”
   - 只有数据库中真实存在的 clips 才能绘制蓝色动作块/绿色轨迹块。

7. `src/ui/choreo_page/action_library_panel.py`
   - 删除 `_seed_default_actions()` 及五条虚构动作。
   - 无真实引用时按 G 节删除；若保留则必须从真实仓储查询，不得保留假型号 G1/H2 和假动作数据。

8. `src/ui/choreo_page/trajectory_library_panel.py`
   - 删除 `_seed_default_trajectories()` 中 Robot_1/2/3 和 traj_circle/forward/s_curve。
   - 无真实引用时按 G 节删除；若保留则从真实仓储查询。

9. `src/ui/choreo_page/timeline_left_toolbar.py`
   - 删除固定任务项“默认任务1/迎宾编舞-A/矩阵变换-B”。
   - 删除固定轨道头 A2-W Robot_1/Robot_2。
   - 任务下拉从真实任务列表加载；没有任务时显示“未选择编排方案”占位且禁用依赖任务的操作。
   - 轨道头按真实参与机器人动态创建；没有机器人时不显示虚构轨道。

10. `src/ui/choreo_page/lib_panels_controller.py`
    - 不得用硬编码 Robot_1/Robot_2 分组。
    - 轨迹列表按数据库真实 group/track 关系展示。
    - 动作列表按真实来源展示。
    - 没有数据时分别显示轨迹库/动作库空状态。

### D4. 假数据的数据库安全规则

禁止对生产 DB 执行 `DELETE FROM ...` 全表清空。

先在 `audit/00-cleanup/db-backup/` 保存所有 DB。对于旧自动 seed 样本：
- 先记录表结构、行数、主键、完整字段值；
- 用精确 ID + 精确名称 + 已知 seed 代码位置进行指纹匹配；
- 只有能够证明某条记录由上述 seed 代码创建、且不是用户编辑/导入的数据，才可在事务中删除；
- 无法确认来源的记录标记为 `unverified_legacy` 并从默认列表隐藏/提示来源未验证，不得擅自删除；
- 为每个迁移编写 `upgrade -> verify -> rollback` 测试；
- 迁移前后都输出 DB SHA-256、行数和 schema version。

## E. 修复明确的无响应按钮和重复信号

### E1. `TopShowHeader` 顶栏

文件：`src/ui/header/top_show_header.py`

当前按钮：
- `新建`
- `导入`
- `保存`
- 模式 ComboBox
- CLOCK 状态
- T0 倒计时
- 急停控件

当前 `newProjectRequested`、`importProjectRequested`、`saveProjectRequested`、`modeChanged` 信号没有在 `MainStudioWindow` 接线。

处理要求：
- 如果本阶段能接入真实仓储/归档器并完成可测试的“新建空工程、导入工程、保存工程”，则保留按钮。
- 如果某项没有真实实现，不得保留一个可点击但无响应的按钮；暂时从 UI 移除，不能用 QMessageBox“功能开发中”冒充完成。
- `新建`：创建真实空场景/工程；若当前工程 dirty，先弹保存确认。
- `导入`：调用已有安全 project archive importer；选择文件后校验 manifest/schema/路径穿越，成功后加载新工程；失败显示错误，不覆盖当前工程。
- `保存`：调用真实仓储事务/项目归档写入；保存成功必须能关闭窗口再重新打开并恢复数据。
- 模式下拉只保留执行引擎实际支持的模式；切换必须更新真实 controller state，不能只改变 ComboBox 文本。

### E2. `TimelineLeftToolbar` 顶部与工具条

文件：`src/ui/choreo_page/timeline_left_toolbar.py`

保留并明确控件规格：
- 时间轴顶部工具栏高 `34 px`。
- “播放/暂停”按钮：高度 `28 px`，宽度至少 `64 px`；点击只调用一次播放状态切换；播放时文字改“暂停”，暂停时文字改“播放”。
- “保存”按钮：高度 `28 px`；只有当前编排有可保存变更且存储正常时启用；点击一次只保存一次。
- 任务选择框：高度 `28 px`，宽度 `180 px`；只显示真实任务。
- 左侧图标工具栏宽 `36 px`；图标按钮 `26×24 px`，tooltip 必须包含动作名和快捷键。
- 轨道标签区宽 `160 px`；每个真实机器人轨道头高 `56 px`。

逐个检查 `undoClicked`、`redoClicked`、`splitClicked`、`deleteClicked`、`zoomChanged`、`snapToggled`、`loopToggled`、`taskChanged`：
- 有真实实现且完成测试：连接到 controller/engine。
- 没有真实实现：从可见 UI 移除该按钮/开关，不能只留一个空槽。
- `main_studio_window.py` 中删除 `btn_play.clicked.connect(lambda: None)`。
- `btn_save.clicked` 和 `saveClicked` 只能保留一条调用链；一次点击必须只触发一次保存。

### E3. `StageOverlayControls`

文件：`src/ui/choreo_page/stage_overlay_controls.py`

统一工具条按钮规格：
- 高度 `28 px`，圆角 `4 px`，左右 padding `10 px`。
- 普通按钮背景 `#1C2230`，边框 `#2B3448`，文字 `#E2E8F0`。
- hover 背景 `#263147`，边框 `#1E6FFF`。
- active 背景 `#1E6FFF`，文字白色。
- 按钮文字必须明确，不允许只有不明意义的 emoji。

2D 模式只保留这些有真实行为的控件：
1. `轨迹绘制`（checkable）：切换到 TRAJ；再次关闭切换到 IDLE；状态只发出一次。
2. `草图笔`（checkable）：切换到 SKETCH；再次关闭切换到 IDLE；状态只发出一次。
3. `撤销`：只撤销最近一次绘图命令/航点；无可撤销内容时禁用。
4. `清空草图`：只清除草图，不得删除轨迹。
5. `清空轨迹`：清除当前选中轨迹；若是全部轨迹，必须二次确认。

3D 模式只保留：
1. `播放/暂停`：只触发一次播放状态改变。
2. `重置相机`：只重置相机位置。
3. `网格`：切换真实网格显示。

删除或隐藏当前无真实行为的“刷新”按钮。`正视视角` 若未实现独立 front camera preset，则删除；不得和“原点重置”共用同一个 signal 假装是两个功能。

修复重复事件：checkable 按钮只使用 `toggled` 或 `clicked` 中一种接线策略；同一个用户点击不得发出两次 `modeChanged`、`animationToggled` 或 `viewDimensionChanged`。

底部操作提示必须与真实鼠标事件一致：
- 左键：添加航点（仅轨迹绘制模式）。
- 右键：结束当前轨迹（至少 2 个航点）。
- Alt + 左键拖动：平移画布。
- 滚轮：缩放。
- Ctrl+Z：撤销最后一个航点/命令。
不支持的快捷键不得写在提示卡上。

### E4. `LibPanelsController`

文件：`src/ui/choreo_page/lib_panels_controller.py`

当前轨迹区域同时创建 `table_traj` 和 `tree_traj`，但 `tree_traj.hide()`；删除和导出却读取隐藏 tree 的 currentItem，导致用户无法从可见表格选择目标。`btn_bind` 绑定 `lambda: None`。

修改：
- 轨迹库只保留一个可见列表控件；优先保留支持分组的 `QTreeWidget`，或者把分组列整合到现有 table。不得同时维护两个不同 selection state。
- 列：`编号`、`名称`、`时长`、`所属机器人/轨道`。
- 顶部按钮只保留 `新增轨迹`、`导入 JSON`、`导出 JSON`、`删除` 中真实完成的操作。
- `绑定` 暂时删除；等 06/07 阶段完成真实机器人轨道绑定后再添加。
- 选中轨迹后，导出/删除才启用；删除前弹出确认，并检查时间轴引用。
- 动作库搜索框高度 `30 px`，placeholder“搜索动作名称或编号”；机型筛选仅展示仓储中真实存在的型号。
- 动作行双击必须只插入一次时间轴 clip；没有可用机器人轨道时给出明确提示并不插入。
- 轨迹和动作列表无数据时显示空状态，不显示 Robot_1/Robot_2 假分组。

### E5. 假保存必须修复

文件：`src/ui/windows/main_studio_window.py::_on_save_button_clicked()`

当前逻辑用时间戳拼一个 plan_id，刷新视图后直接弹“不可变演播计划导出编译成功”。这不是保存证明。

改成：
1. 检查当前项目、地图、轨道、clip 是否满足保存 schema。
2. 调用唯一仓储保存当前编排数据。
3. 等待事务成功提交。
4. 保存失败显示错误并保留 dirty 状态。
5. 保存成功显示真实文件/项目名和保存时间。
6. 不得凭空生成 plan_id；只有真正调用 `ImmutablePlanCompiler` 并得到有效结果后，才能展示 plan_id。
7. 若本阶段无法接通可靠保存，移除“保存成功”弹窗和假 plan_id；按钮置为 disabled 并显示原因，不得假成功。

## F. P0：修复 SQLite schema 冲突

本阶段必须解决，否则后续所有 UI 行为都不可信。

已知冲突：
- `StudioController` 和 `ChoreoSqliteStore` 都使用 `runtime/shows/studio_data.db`。
- `StudioController` 创建 `actions(id,name,model,duration)`、`trajectories(id,robot_id,name,pts,duration)`。
- `ChoreoSqliteStore` 期望 `actions(action_id,name,model_type,duration,anim_path)`、`trajectories(traj_id,robot_group,name,waypoints_json,duration,created_at)`。
- 两者 `CREATE TABLE IF NOT EXISTS` 不会替换旧表结构。
- `StudioRepository` 使用 `studio_core.db`。
- `ChoreoRepository` 和 `ChoreoSceneStore` 使用 `choreo_studio.db`。

必须实施：
1. 搜索全项目所有 SQLite 打开位置、schema 创建位置、表名和列名。
2. 对三个 DB 文件分别制作 schema 图和数据来源图。
3. 选择舞台编导的唯一 canonical repository；选择依据是实际调用图、已有用户数据、迁移风险和测试，不是个人偏好。
4. UI 控件不允许自行 `sqlite3.connect()` 执行 SQL。`DualLayerTimelineCanvas` 当前直接连接 `DB_PATH` 更新/删除 clip，必须改为调用 repository/controller 的命令方法。
5. `StudioController` 不再自行建一套与 `ChoreoSqliteStore` 冲突的表；将其改为业务 facade，所有 CRUD 调用 canonical repository。
6. 若必须保留 `studio_core.db` 的场景/初始化点数据，明确其边界并提供 adapter；不得把同一份轨迹/动作/clip 分散写到多个 DB。
7. 数据迁移只在临时副本上先执行；迁移脚本必须有版本号、事务、备份、校验、回滚。
8. 至少建立以下测试：
   - 新 DB 首次初始化不注入任何假机器人/动作/轨迹/clip。
   - 旧 schema DB 可以迁移且原始记录数量和内容可验证。
   - Store A 创建后 Store B 查询不会 `no such column`。
   - 新建轨迹 -> 保存 -> 重启仓储 -> 读取内容完全一致。
   - 新建 clip -> 拖动修改 -> 保存 -> 重启后 start/duration 一致。
   - 删除被引用轨迹被拒绝，解除引用后才能删除。

## G. 重复组件的处置

以下组件存在重叠，但不得仅凭文件名直接删除：

- `src/ui/choreo/stage_canvas_2d.py`
- `src/ui/choreo_page/stage_canvas_2d.py`
- `src/ui/choreo_page/interactive_stage_2d.py`
- `src/ui/choreo/dual_timeline_panel.py`
- `src/ui/choreo_page/dual_layer_timeline_canvas.py`
- `src/ui/choreo_page/dual_track_timeline.py`
- `src/ui/choreo/right_library_panels.py`
- `src/ui/choreo_page/lib_panels_controller.py`
- `src/ui/choreo_page/action_library_panel.py`
- `src/ui/choreo_page/trajectory_library_panel.py`

执行：
1. `rg` 搜索每个类、模块路径、动态 import、测试 import。
2. 建立 `cleanup-ledger.csv`：文件、类、引用位置、活跃入口、功能重叠、处置。
3. 对未被主入口/测试/动态注册引用的重复组件，先移入 `src/_quarantine/stage_director_legacy/` 或删除并保留 Git patch；不要把仍被使用的模块迁走。
4. 删除后更新 `.agent_workspace/INDEX.md` 和 `scripts/verify_guardrails.py` 的索引规则。
5. 保留真正活跃的 `MainStudioWindow`、`StudioMainWindow`、`StageCanvas2D`、`StageViewport3D`、`DualLayerTimelineCanvas`、`LibPanelsController` 的单一实现路径。
6. 不得为了满足“单文件 300 行”而机械拆分；拆分应服务于真实模块边界。

## H. 本阶段必须达到的可运行界面状态

启动“舞台编导”后，窗口应当显示一个干净、真实数据驱动的编排工作台：

### H1. 全局窗口

- 窗口 `1440×900`，最小 `1200×720`。
- 全局顶栏高 `50 px`，底栏高 `30 px`。
- 顶栏主导航仍是“舞蹈编排 / 表演监测 / 导航地图”。
- 场景选择只显示数据库中的场景。
- 底栏只显示真实网络、IP、机器人数量、当前场景、音乐状态。
- 没有真实值显示 `--` 或“未连接”，不得显示虚构在线数。

### H2. 舞蹈编排页

- 内部顶部工具栏高 `56 px`。
- 当前 280px 左 dock 为空；本阶段若没有真实机器人列表组件，就从 splitter 移除空 dock，把宽度交给中央画布。不得保留一个空白 280px 面板。
- 中央区域显示真实地图；没有地图时显示网格和“尚未加载地图”提示，不得生成默认点云。
- 2D/3D 切换只切换实际存在的视口。
- 右侧资源面板宽度目标 `320–360 px`，分为轨迹库和动作库两个清晰区域。
- 底部时间轴最小高 `220 px`；无真实机器人时不画机器人轨道；无 clips 时显示空状态。
- 任何按钮都必须在 cleanup-ledger 中有唯一事件处理器；没有处理器的按钮必须移除或禁用并给出明确原因。

### H3. 空状态

必须分别实现并截图验证：
- 无地图：中央画布显示“尚未加载地图”，提供唯一明确的“加载地图”入口（若本阶段地图入口可用）。
- 无机器人：机器人区域显示“未连接机器人”，不画虚构机器人。
- 无轨迹：轨迹库显示“暂无轨迹”，提供真实“绘制/导入”入口；若入口尚未实现则不显示按钮。
- 无动作：动作库显示“暂无可用动作”，说明需要从真实设备同步或导入。
- 无时间轴 clip：时间轴显示“从动作库或轨迹库添加片段”。
- 保存失败：错误提示和 dirty 状态保留；保存成功必须能重启恢复。

## I. 逐项验收（必须执行）

### I1. 入口验收
1. 从 RDA 主页点击“🎬 舞台编导”。
2. 确认 Qt 窗口出现一次。
3. 连续点击按钮 3 次，确认仍只有一个窗口实例。
4. 关闭窗口后再点击，确认可重新打开。
5. Qt 初始化异常时主页显示错误，而不是成功 toast。

### I2. 假数据验收
1. 删除/备份旧测试 DB 后启动新 DB。
2. 动作库数量应为 0。
3. 轨迹库数量应为 0。
4. 时间轴 clip 数量应为 0。
5. 机器人列表应为 0，除非真实设备发现返回机器人。
6. 不应显示 Robot_1/Robot_2、POPPING1、中华武术、默认任务1、迎宾编舞-A、矩阵变换-B、BARRIER_9001、固定 IP、在线 2 等假内容。
7. 用户手动导入/创建的真实记录必须正常显示。

### I3. 控件行为验收
1. 顶栏每个可见按钮点击一次只执行一个动作。
2. 播放按钮点击一次进入播放，再点击一次暂停；不能一点击自启又立刻停止。
3. 保存按钮一次点击只触发一次数据库事务。
4. 轨迹导出/删除只能针对可见列表中选中的记录。
5. 无选中项时删除/导出禁用。
6. 草图清空不能删除轨迹；清空轨迹不能清空地图。
7. 2D/3D 切换只发出一次事件。
8. 所有无实现按钮已移除或禁用，不存在 `lambda: None` 的可见按钮处理器。

### I4. 数据持久化验收
1. 新建一个空工程/场景。
2. 保存并关闭窗口。
3. 重新打开舞台编导。
4. 当前场景仍存在，且没有出现自动生成的机器人/动作/轨迹。
5. 导入一条真实测试轨迹 fixture，显示在轨迹库。
6. 将其添加到时间轴，保存、重启后仍存在。
7. 导出 JSON 并重新导入，字段和点位一致。

### I5. 回归验收
- 运行 `scripts/verify_guardrails.py`。
- 运行所有可执行单元测试。
- 运行主页 Flask API 测试。
- 运行舞台编导 Qt offscreen smoke test（如果环境支持）。
- 对 `backend/`、主页机器人控制、部署向导、License、SSH/SFTP、串口、3D 舞蹈预览相关测试全部回归。
- 任何依赖缺失必须明确记录，不能跳过后宣称全绿。

## J. 交付物与完成条件

本阶段必须实际修改源码并提交可运行增量，不接受只写审计报告。

必须交付：
1. 清理后的代码。
2. `docs/agent-prompt-pack/audit/00-cleanup/cleanup-ledger.csv`。
3. `docs/agent-prompt-pack/audit/00-cleanup/storage-schema-map.md`。
4. `docs/agent-prompt-pack/audit/00-cleanup/before-after-ui/` 截图。
5. `docs/agent-prompt-pack/audit/00-cleanup/test-results.md`。
6. 数据库备份和迁移/回滚说明。
7. Git diff 摘要和受影响文件列表。
8. 明确列出删除、隔离、修复、保留的文件和控件。

只有以下条件全部满足才算完成：
- 主页入口不变且稳定。
- 舞台编导窗口能正常打开。
- 没有虚构机器人、动作、轨迹、任务、地图、网络状态。
- 没有可见无响应按钮。
- 没有重复点击/重复信号导致的双重操作。
- SQLite schema 冲突被修复并有迁移测试。
- 用户数据未丢失。
- 旧的部署、串口、License、SSH、主页机器人控制和原有 3D 舞蹈预览回归通过。
- 所有结果都有真实运行证据。

## K. 本阶段禁止事项

- 不开发新的阵型算法、完整 2D 轨迹编辑器、动作编排系统或 3D 新功能；这些属于后续 Prompt。
- 不安装 UniUni、不再做 UniUni 逆向。
- 不把 mock/demo 数据继续留在生产启动路径。
- 不用“功能开发中”弹窗冒充按钮可用。
- 不保留 `lambda: None`、空 signal slot 或重复 signal connection。
- 不直接删除 SQLite 数据库。
- 不用 `git reset --hard`、`git clean -fd`、force push。
- 不把未验证的运行结果写成通过。

**完成本阶段后，更新 `docs/agent-prompt-pack/state/PROJECT_STATE.md`、`TASKS.md`、`COMPATIBILITY_MATRIX.md`、`TEST_MATRIX.md`、`PROMPT_EXECUTION_LOG.md` 和 `SESSION_HANDOFF.md`。若这些状态文件不存在，先按 `templates/state/` 中的模板创建；不要假设它们预先存在。**
