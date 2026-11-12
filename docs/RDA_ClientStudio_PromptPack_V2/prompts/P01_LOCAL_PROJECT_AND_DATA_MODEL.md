# P01 — 本地工程管理、项目隔离和统一数据持久化

**阶段目标**：把“舞台编导工程”变成真正的本地数据容器。用户可以创建、打开、保存、另存为、导入、导出工程；项目中的地图引用、机器人、轨迹、阵型、素材引用和时间轴 Clip 必须跟随工程，重启程序后可以恢复。

**前置**：P00 COMPLETE。执行前读取全局执行契约和正确 Skill。

## 1. 本阶段不能做什么

不开发任何网络上传、机器人通信、设备发现、远程项目、远程下发和运维能力。不要实现机器人命令编译/部署。也不要把 `lrmp_compiler` 当成本地工程管理器，除非代码审计能证明它本身是项目存档服务；不得因名字或历史用途猜测。

## 2. 先审计现有持久化，不得直接建第二套数据库

必须阅读并追踪：

- `src/infrastructure/storage/choreo_sqlite_store.py`
- `src/infrastructure/storage/timeline_clip_sqlite_adapter.py`
- `src/infrastructure/storage/trajectory_sqlite_adapter.py`
- `src/infrastructure/storage/stage_map_sqlite_adapter.py`
- `src/infrastructure/storage/group_trajectory_sqlite_adapter.py`
- `src/infrastructure/storage/*formation*`（存在时）
- `src/core/storage_manager.py`
- `src/core/lrmp_compiler.py`
- `src/ui/header/top_show_header.py`
- `src/ui/windows/main_studio_window.py`
- 所有现有 scene/project JSON、SQLite 表和 migration。

建立 `P01_PERSISTENCE_AUDIT.md`：数据库路径、表结构、主键、外键、Repository/Adapter、默认项目/任务行为、旧数据目录、各模块当前使用的 DB path。扫描用户当前数据文件并记录 SHA-256。不要把开发目录中的空数据库和用户真实数据库混为一谈。

当前 GitHub `main` 快照中 `ChoreoSqliteStore.DEFAULT_DB_PATH` 是 `data/choreo_database.db`；`StageMapController` 支持传 `db_path`；`TimelineChoreoController` 也支持 `db_path`。这给统一工程数据库留下了复用入口，但必须在本地检查所有 Adapter 是否都使用同一路径。

## 3. 定义工程文件格式和目录结构

提交 ADR 并选定一个权威方案：

- 推荐可移植的工程目录/压缩包格式；
- 一个工程有稳定 `project_id`；
- 工程有 `manifest.json`；
- 工程数据库与地图、轨迹、阵型等本地资源有明确归属；
- 工程导出可以包含所有引用资源，导入后不依赖原机器绝对路径。

推荐逻辑结构（可以根据当前 `storage_manager` 路径调整，但要写 ADR）：

```text
<projects_root>/
  <project-folder>/
    project.json
    project.sqlite3
    assets/
      maps/*.pcd
      trajectories/*.json
      formations/*.json
      actions/...
      audio/...
    cache/                 # 可重建缓存，不作为真源
```

工程清单至少包含：

```json
{
  "schema_version": 1,
  "project_id": "UUID",
  "name": "Project Name",
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601",
  "active_map_id": null,
  "settings": {
    "coordinate_frame": "stage_world",
    "position_unit": "m",
    "angle_unit": "deg",
    "time_unit": "ms"
  }
}
```

以上为契约示意，真实字段要与领域模型一致。禁止把屏幕像素、窗口尺寸、临时选中控件状态写进项目核心数据。可恢复的 UI 偏好可以另存 `ui_state.json`。

如果评估后选择“一个全局 DB 加 project_id”，必须保证所有表都进行项目隔离并有 migration；不允许部分表全局、部分表按项目，从而产生串项目数据。若选择“每工程一个 SQLite”，所有 Adapter 的 `db_path` 必须一致。选定后不得混搭。

## 4. 必须实现的 Application 层接口

创建或完善一个单一工程服务（例如 `ProjectService`），对 UI 提供以下操作；命名可调整，但行为必须完整：

- `create_project(name, destination?)`
- `open_project(project_id_or_path)`
- `save_project()`
- `save_project_as(destination)`
- `close_project()`
- `import_project(archive_path, destination?)`
- `export_project(project_id, archive_path, include_assets=True)`
- `rename_project(project_id, new_name)`
- `list_recent_projects()`
- `get_current_project()`
- `validate_project(path)`

返回明确的 Result/错误类型，不要靠 QMessageBox 结果作为业务成功状态。ProjectService 负责：

1. ID 和名称校验。
2. 创建目录和 canonical SQLite schema。
3. 确保项目数据与项目资源路径互相隔离。
4. 保存 manifest/数据库事务。
5. 导入工程时验证 zip 内路径，拒绝 `../`、绝对路径和越界写入。
6. 验证资源存在、hash 一致、schema_version 可识别。
7. 保存失败时保留原文件并报告原因。
8. 为关闭工程/切换工程提供 dirty-check / 未保存变更策略。

## 5. 统一数据模型

至少梳理并形成 `DATA_CONTRACTS.md`：

- `Project`
- `MapAsset`（复用 `StageMapAsset`，避免重复定义）
- `RobotInstance`（P03 实现，但 P01 先确定工程归属字段）
- `TrajectoryAsset` / `TrajectoryPoint`
- `Formation` / `FormationMember`
- `ActionAsset` / DanceAsset
- `TimelineClipAsset`
- `TimelineTrack`（轨道可以是动态视图模型，但应具有稳定 ID）

每个实体明确：ID 类型、项目 ID、名称、类型、时间/坐标单位、schema_version、文件引用、更新时间和删除/引用策略。

必须区分：

- 素材 Asset：可复用定义；
- Timeline Clip：素材在某条轨道某个时间点的实例；
- Robot Instance：当前项目中的机器人对象，不等同于物理设备在线状态；
- Robot Model：可复用模型/URDF 资源；
- 预览 Pose：由轨迹、动作、时间计算出来的瞬时派生状态，不持久化为主数据。

## 6. SQLite 统一与迁移

1. 所有当前工程的 Store/Adapter 必须接收同一 DB path 或同一 Repository。
2. `ChoreoSqliteStore`、`TimelineClipSqliteAdapter`、`StageMapSqliteAdapter`、`TrajectorySqliteAdapter` 等不能在各自代码中悄悄选择不同默认数据库。
3. 数据库 schema 版本与项目 manifest 版本分开管理；添加可重复执行的 migration。
4. 迁移先备份旧 DB，再事务迁移；失败能够恢复备份。
5. 对旧 `data/choreo_database.db`、`runtime/stage_maps`、`runtime/maps`、`storage_manager` 中的轨迹/阵型文件做只读盘点，设计用户可确认的“导入旧数据”流程。不能自动搬走、删除或重命名旧数据。
6. 若旧数据无法完整识别，保留源文件并将不可迁移项列出；不允许吞异常后显示成功。
7. 对资源文件记录 SHA-256；导出工程包时检查引用闭环。

## 7. UI：在现有 TopShowHeader 中完成真实工程操作

主要入口：`src/ui/header/top_show_header.py`、`src/ui/windows/main_studio_window.py`。

将 Header 的 New / Open / Save / Save As / Import / Export / Recent Projects 连接至 ProjectService。若当前 UI 没有 Save As 或 Recent，补齐但沿用现有视觉主题，不另做新窗口。

交互要求：

- New：询问工程名称和保存位置；创建空工程；切换到空场景。
- Open：工程列表/文件选择；显示名称、更新时间和资源摘要；确认后加载。
- Save：只有持久化成功才显示成功状态；保存过程中防止重复点击。
- Save As：复制工程数据和引用资源，生成新 project_id；不得与原项目共享可变 SQLite 文件。
- Import：导入 `.rda`/ZIP 工程包，先预览工程名、资源数、版本和校验结果。
- Export：打包 manifest、数据库和所引用资源；提供导出成功路径。
- Close/Switch：有未保存变更时提示保存/放弃/取消。
- 最近工程：记录在用户配置中，不把绝对路径写入工程内部作为唯一引用。

按钮必须有 objectName 和 UI 自动化测试定位 ID。

## 8. 接入 P00 的统一 Runtime Context

工程打开/切换后，主窗口把同一工程上下文注入：

- `ChoreoSqliteStore(db_path=current_project.db_path)`
- `StageMapController(db_path=current_project.db_path, map_dir=current_project.maps_dir)`
- `TimelineChoreoController(db_path=current_project.db_path, task_name=...)`
- 轨迹/阵型/Asset Repositories
- StagePreviewEngine

不得出现地图已经切换到新项目、时间轴仍读取旧项目 DB 的情况。

## 9. 测试和验收

### Must Pass

1. 创建 A、B 两个工程，分别建数据，切换后数据绝不串用。
2. 保存关闭重启再打开，工程元信息、地图引用、机器人/轨迹/阵型/Clip 数据一致。
3. Save As 后新旧项目各自独立修改，不互相污染。
4. 导出/导入工程包，校验资源文件 hash 一致，引用闭环。
5. 非法 ZIP 路径、损坏 SQLite、未知 schema version、缺失资源均拒绝导入，原工程不受影响。
6. 模拟保存失败，不得出现成功提示，不得丢失当前内存中的未保存修改。
7. 旧数据库迁移前后数据条数、关键字段和资源哈希一致；源备份存在。
8. `MainStudioWindow` 在新建/打开/切换工程后，地图、2D 画布、时间轴、3D 预览使用同一 project_id / DB path。

### UI 手工验收

- 新建“测试工程 A”，新增一条轨迹/阵型/Clip，保存并关闭。
- 新建“测试工程 B”，不应看到 A 的任何机器人、轨迹、阵型或 Clip。
- 重新打开 A，所有数据恢复。
- A 导出 ZIP，再导入为 C，C 与 A 内容一致但 project_id 不同。
- 在导入损坏包时确认出现明确错误，并且 C/A 原数据不改变。

## 10. 交付

- ProjectService / Repository / Schema / Migration 的真实实现。
- `DATA_CONTRACTS.md`、ADR、数据迁移报告。
- Header 工程管理 UI 与 Qt 测试。
- `P01_TEST_REPORT.md` 和更新后的 `SESSION_HANDOFF.md`。

完成后进入 P02。若 P01 尚未建立项目级 DB/资源隔离，不得进入地图/轨迹/时间轴的正式功能开发。
