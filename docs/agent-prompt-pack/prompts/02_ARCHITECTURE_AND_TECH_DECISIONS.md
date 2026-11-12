# PROMPT 02 — RDA 舞台编导架构收敛与技术实现边界

> **本阶段目标：** 把 RDA 已有的舞台编导实现收敛成唯一、可测试、可维护的架构通路。不是重写技术栈，也不是只写一份架构报告。本阶段要提交可运行的架构增量，并为 04–10 的功能开发准备稳定的服务边界。

## 1. 已知项目边界

- 主项目：RobotDeploymentAssistant。
- UI：Python + PySide6/Qt。
- Web 首页/API：Flask。
- 本地持久化：SQLite。
- 已有舞台编导组件：`StudioMainWindow`、`MainStudioWindow`、`StageCanvas2D`、`StageViewport3D`、`DualLayerTimelineCanvas`、`LibPanelsController`。
- 已有业务/存储相关类：`StudioController`、`ChoreoSqliteStore`、`StudioRepository`、`ChoreoRepository`、`ChoreoSceneStore`。
- UniUni 的 Electron/Vue/Konva/Three.js 是参考软件实现，不是 RDA 技术迁移目标。

实际代码路径以当前工作区为准；如果某路径已在 Prompt 00 被替换、移动或合并，沿当前引用继续，不要重新造一份同名实现。

## 2. 本阶段必须落地的架构结果

完成后，舞台编导页面必须遵守下面的依赖方向：

```text
PySide6 UI Widgets
    │  signals / slots；不写 SQL、不直连硬件
    ▼
Application Use Cases / Controllers
    │  调用 Domain Services 和 Ports
    ▼
Domain Models / Validation / Commands
    │
    ├── Persistence Ports ──> SQLite Repositories
    ├── Robot Ports ────────> Serial / LoRa / LRMP Adapters
    ├── Map Ports ──────────> PCD / Map Importers
    └── Preview Ports ──────> Existing Qt 2D / 3D Viewports
```

规则：
- UI 不允许 `sqlite3.connect()`。
- UI 不允许直接打开串口、SSH、SFTP 或 socket。
- Domain 不允许 import PySide6、Flask 或硬件 SDK。
- Infrastructure 不允许反向 import UI。
- Service 层不能直接访问 QWidget 属性来修改视觉状态；通过返回结果/Qt signal 通知 UI。
- 当前项目中已存在的等价层必须复用，不能为满足目录示例再创建重复包。

## 3. 先形成实际依赖图，然后只实施三个架构改造

### 3.1 依赖图

扫描所有 `src/ui/choreo_page/`、`src/ui/windows/`、`src/application/`、`src/domain/`、`src/infrastructure/storage/`、机器人通信和地图模块，生成：

`docs/agent-prompt-pack/audit/02-architecture/dependency-map.md`

必须列出：
- 当前主窗口构造函数创建了哪些 Widget；
- 每个 Widget 依赖哪些 Controller/Repository；
- UI 中存在的 SQLite 直接访问；
- 重复 repository 和 schema；
- 循环 import；
- 当前未使用但仍有引用的实现；
- 3D/PCD 数据从文件到视口的完整调用路径。

### 3.2 建立唯一舞台编导 Composition Root

复用现有 `StudioWindowManager` / `MainStudioWindow` 创建链路。不要新建第二个 QApplication、第二套 Flask 服务或第二个主窗口管理器。

创建或扩展一个依赖组装入口，建议命名：

- `src/application/studio/studio_dependencies.py`
- `src/application/studio/studio_facade.py`

只有当前项目无等价模块时才新建。其职责：

1. 创建唯一数据库连接/连接工厂。
2. 创建唯一 canonical repository。
3. 创建 `StudioController` 或现有 facade。
4. 创建机器人状态 provider。
5. 创建地图/轨迹/动作查询 service。
6. 把 facade 注入 `MainStudioWindow` 和其子组件。
7. 负责窗口关闭时释放数据库连接、后台线程和 signal subscription。

要求：
- 同一个窗口生命周期只能有一个 canonical database/repository 实例，不能多个组件各自打开 `studio_data.db`。
- `MainStudioWindow` 构造函数不应包含业务 SQL。
- widget 只接收构造参数，不自己猜数据库路径。
- 增加测试确保两个面板使用同一 repository 实例或同一事务边界。

### 3.3 统一 UI 调用的 Use Case 接口

在当前 `StudioController` 的基础上增加清晰的应用方法。方法名可按项目现有风格调整，但功能必须对应：

```python
load_scene(scene_id: str) -> SceneViewData
list_robots(scene_id: str) -> list[RobotViewData]
list_actions(robot_model: str | None = None) -> list[ActionViewData]
list_trajectories(scene_id: str) -> list[TrajectoryViewData]
list_timeline_clips(scene_id: str) -> list[TimelineClipViewData]
create_empty_scene(name: str) -> SceneViewData
save_scene(scene_id: str) -> SaveResult
import_trajectory(path: Path) -> ImportResult
export_trajectory(trajectory_id: str, path: Path) -> ExportResult
```

不要提前把未来尚未实现的机器人下发、实时建图方法做成返回 success 的假接口。对未来能力可定义 Protocol，但状态必须是 `UNAVAILABLE`，并且 UI 不可显示可执行按钮。

应用层方法要求：
- 输入参数校验；
- 捕获仓储异常并转换为稳定的 application error code；
- 返回不可变/只读 view data；
- 记录结构化日志，不记录密码、token、license secret；
- 单个用例只提交一次数据库事务；
- Qt signal 在 UI thread 更新控件；耗时 IO/解析不得阻塞 UI thread。

### 3.4 清除 UI 到 SQLite 的直连

重点审查：
- `src/ui/choreo_page/dual_layer_timeline_canvas.py`
- `src/ui/choreo_page/lib_panels_controller.py`
- `src/application/studio_controller.py`
- `src/infrastructure/storage/choreo_sqlite_store.py`
- `src/infrastructure/storage/db_bootstrap.py`

所有 UI 直连 DB 代码迁移到 repository/use case。`DualLayerTimelineCanvas` 中拖动 clip 后应 emit `clipMoveRequested(clip_id, new_start)`，由 Controller 完成验证和持久化；Widget 只在成功后确认新位置，失败则恢复旧位置并显示错误。

## 4. 第三方库选型必须以 RDA 为主体

本阶段不进行 Electron/Vue 迁移。针对需要的能力作小范围技术选择：

### 4.1 UI 和桌面架构

- 首选当前 PySide6。
- 不引入 React/Vue/Electron。
- 不引入第二套窗口系统。
- Qt `QSplitter`、`QStackedWidget`、`QAbstractItemModel`、`QUndoStack` 等优先评估原生能力。
- 如果现有 Widget 可满足交互，保留现有实现，不因“想要更现代”换成另一个 UI 框架。

### 4.2 2D 画布

比较：
1. 项目当前 `StageCanvas2D` 实现；
2. Qt `QGraphicsView/QGraphicsScene`；
3. 现有自绘 `QWidget + QPainter`。

本阶段不重写画布，只对 pan/zoom/selection/绘制/坐标转换能力做 benchmark 和 ADR。后续 06 才实施轨迹绘制功能。

### 4.3 3D 视口

- 优先复用当前 `StageViewport3D` 和已有 Qt/OpenGL/URDF/STL 代码。
- 不新增 Three.js/Babylon.js；这些与当前 PySide6 桌面应用不是同一运行栈。
- 如果当前 3D 视口确实存在无法维护的技术缺陷，提交 ADR 比较现有 Qt 方案、PyVista/VTK 等选择，必须测量安装包体积、显存和交互性能后再决定。

### 4.4 PCD

先分析现有 PCD parser 和 NumPy 转换链路。
- 当前自有解析可覆盖用户样本时，先保持。
- Open3D 可作为可选导入/降采样工具，但不能把它强制加进 UI 主进程而没有内存/包体评估。
- 若引入 Open3D，必须单独测试 ASCII、binary、binary_compressed 的支持情况和大文件峰值内存。
- 不允许仅凭库名宣称支持某格式。

### 4.5 SQLite

- 默认保留 Python `sqlite3`，不因为“ORM 更现代”就改 SQLAlchemy。
- 迁移统一使用 `PRAGMA user_version` 或项目已有版本管理器。
- 对 schema 版本、事务、索引、foreign key、busy timeout、连接线程归属和备份策略做 ADR。
- 如果选择 ORM，必须证明能无损兼容现有用户 DB，并提供迁移/回滚脚本。

### 4.6 数据结构校验

比较：
- 标准库 `dataclasses` + 明确 validator；
- 项目已有 schema 工具；
- Pydantic（仅当现有 Python 版本兼容且收益足以抵消依赖成本）。

不要为一个简单 JSON schema 引入多个互相重复的验证框架。

## 5. 必须创建的 ADR

创建目录 `docs/agent-prompt-pack/adr/`，至少写：

- `ADR-001-stage-director-dependency-boundaries.md`
- `ADR-002-canonical-sqlite-repository.md`
- `ADR-003-2d-3d-rendering-strategy.md`
- `ADR-004-pcd-processing-strategy.md`
- `ADR-005-validation-and-migrations.md`

每份必须包含：问题、现状证据、候选方案、成本/收益、许可证和平台影响、性能结果、决定、拒绝方案原因、迁移计划、回滚方法。

## 6. 代码质量门槛

- 新增应用层方法必须有单元测试。
- UI 组件不允许 import `sqlite3`。
- 同一场景的轨迹/动作/clip 不能写入两个不同 DB。
- 数据库连接在一个明确层创建和关闭。
- 不允许 UI thread 同步解析大 PCD 或执行 SSH/串口等待。
- 每个 worker 支持 cancellation；窗口关闭时不遗留线程。
- 不能创建新的 `MainStudioWindow` 替换旧入口。
- 不得用 `except Exception: pass` 隐藏失败。
- 不允许通过 monkey patch 修改 Qt Widget 的行为。

## 7. 端到端验收

1. 启动 Flask 主页并点击“舞台编导”，只有一个窗口被创建。
2. `MainStudioWindow` 创建依赖时，Repository 数量符合设计，不会两个组件各自打开同一 DB。
3. 左侧机器人列表、右侧动作库、轨迹库都从 Facade 获取数据，UI 文件没有 sqlite import。
4. 点击轨迹删除时，UI 发出 use case 请求；Controller 检查 clip 引用，成功后 repository 删除，UI 刷新；失败时保持原项并显示错误。
5. 拖动时间轴片段只更新内存预览，松开时提交一次 update use case；保存失败回滚到原位置。
6. Qt 主线程在耗时仓储/文件操作时仍能响应窗口拖动和最小化。
7. 关闭窗口后线程、连接和 signal subscription 释放，没有重复打开时的 stale callbacks。

## 8. 交付

提交实际代码、五份 ADR、依赖图、测试报告和一个清晰的类/调用图。列出真实新增依赖及其许可证、锁定版本、安装包体积影响。不得只提交 Mermaid 图或架构建议。

完成后更新项目状态和 handoff；02 不开始绘制 2D 新功能。
