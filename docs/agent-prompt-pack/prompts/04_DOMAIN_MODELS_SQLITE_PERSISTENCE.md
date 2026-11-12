# PROMPT 04 — 舞台编导领域数据模型、SQLite 统一持久化与迁移

> **类型：数据层落地。** 本阶段要建立可迁移、可验证、可导入导出的领域数据契约，并将舞台编导的数据读写收敛到 02 阶段确定的 canonical repository。不要以新建一套数据库的方式绕过旧库；不要在 UI 层做 JSON/SQL 拼接；不要创建任何生产默认假数据。

## 0. 前置条件

必须确认以下阶段状态：
- Prompt 00：已完成并有备份记录。
- Prompt 01：`COMPATIBILITY_MATRIX.md` 已建立，当前测试基线已保存。
- Prompt 02：已确定 canonical DB 路径、Composition Root、Repository 入口与应用 Facade。
- Prompt 03：UI 以 Facade 获取场景、机器人、动作和轨迹数据。

如果 02 尚未通过，不得擅自再建数据库路径或第二套 Repository。遇到 02 决策未完成的部分，先把阻塞点写入 handoff，不得自行猜测。

## 1. 本阶段目标和不包含的工作

### 必须完成
1. 明确 Scene、Robot、RobotGroup、MapAsset、Trajectory、Formation、ActionAsset、Timeline、TimelineTrack、TimelineClip 的字段与关系。
2. 建立唯一 schema 版本管理。
3. 将旧表/旧 JSON/旧数据库映射到 canonical model。
4. 实现可重复、事务安全、可回滚的 SQLite migration。
5. 建立 Domain Validation、Repository、Import/Export 契约和单元测试。
6. 用真实仓储数据驱动 UI；没有数据时显示空状态。

### 不在本阶段实现
- 2D 轨迹鼠标编辑（Prompt 06）。
- PCD 地图导入 UI（Prompt 05）。
- 机器人实时控制或任务下发。
- 3D 预演调度器和物理采样。
- 复杂阵型求解算法。
- 从云端同步用户数据。

## 2. 数据库现状盘点与唯一化

先根据 Prompt 02 的 dependency map 检查当前所有数据库文件、连接点和 schema。至少检查此前识别的三个库：
- `runtime/shows/studio_data.db`
- `runtime/shows/studio_core.db`
- `runtime/shows/choreo_studio.db`

这些名字是审计快照中发现的候选项，必须以当前工作区实际路径为准。执行：
- 列出所有 `*.db`、`*.sqlite`、`*.sqlite3`；
- 对每个库读取 `PRAGMA user_version`、`sqlite_master`、表字段、索引、外键；
- 对每个业务表统计行数，不导出用户敏感字段；
- 查明每个 repository 当前连接哪个 DB；
- 建立 `docs/agent-prompt-pack/audit/04-data/database-inventory.md`。

### 统一原则
- 最终只有一个舞台编导 canonical database。
- 不允许不同 Repository 对同一 DB 使用冲突 schema。
- 不允许为了“统一”而直接删除旧 DB。
- 旧 DB 在迁移完成并通过验证前始终保留，只读打开。
- 迁移完成后在兼容期内记录 legacy DB 的来源路径、hash、迁移批次和处理状态。
- 生产数据库文件不能由测试 fixture 覆盖。

如果历史业务中存在确实独立的数据域（例如既有设备运维 DB），可保留为独立 DB；但必须说明它不属于舞台编导场景/轨迹/动作的 canonical store，不能把不同业务数据库强行合并。

## 3. 规范化领域模型

优先使用项目当前 dataclass/schema 方式；若 02 已接受 Pydantic，则沿用已经批准的版本。不要再引入第二套验证框架。

所有 ID 在 Domain 层都使用明确类型（推荐 UUID 字符串；若历史 ID 必须保留，使用带 namespace 的兼容 ID，不得把历史整数 ID 转成不稳定的数组下标）。

统一字段约定：
- 时间戳使用 UTC ISO-8601 字符串或项目已批准的统一时间格式；不可混用本地时间字符串和 Unix 秒。
- 距离、速度、角度单位必须显式记录；角度单位固定用 `rad` 或沿用历史约定并通过 adapter 转换，禁止一部分用 degree、一部分用 rad 却没有声明。
- XY 平面轴向、世界坐标原点、正向旋转必须读取现有 PCD/轨迹/模型约定；不能推断为 ROS 或游戏引擎默认。
- 可选字段缺失用 `None`，不能把未知值替换成 0。
- JSON 存储必须有 `schema_version`。
- Domain model 不直接持有 QWidget、sqlite connection 或设备 socket。

### 3.1 Scene

字段至少包括：
- `scene_id`：稳定主键。
- `name`：必填，去除首尾空格，长度限制由 validator 明确。
- `description`：可空。
- `active_map_id`：可空外键。
- `coordinate_frame_id`：可空；若场景没有地图或坐标框架，明确标记未标定。
- `distance_unit`：`m`/历史兼容单位。
- `angle_unit`：`rad`/历史兼容单位。
- `created_at`、`updated_at`。
- `schema_version`。

约束：
- rename 不改变 scene_id。
- 删除场景必须检查是否有轨迹、时间轴和执行记录引用。
- 不能默默级联删除用户的轨迹/动作。

### 3.2 Robot

字段分为**持久配置**和**运行时遥测**，绝不能把在线状态当作静态配置：

持久配置：
- `robot_id`、`display_name`、`model_type`、`hardware_id`（若存在）、`transport_kind`、`namespace`、`enabled`、`created_at`、`updated_at`。

运行时数据单独由 provider 提供，不要求全部持久化：
- `connection_state`：ONLINE/OFFLINE/DEGRADED/UNKNOWN；
- `battery_percent`：0–100 或 None；
- `pose`：含 frame_id 和 timestamp；
- `last_seen_at`；
- `stale`。

禁止：
- 用 A/B/C/D 假机器人填充列表；
- 未收到电量时显示 0%；
- 把 `UNKNOWN` 自动改成 `OFFLINE` 后宣称已检测到离线；
- 把模拟器状态标成真实机器人状态。

### 3.3 RobotGroup

字段：
- `group_id`、`scene_id`、`name`、`description`。
- `member_robot_ids` 使用显式排序关系，不能依赖 SQL 未声明的默认顺序。
- 可选 `formation_id`。
- `created_at`、`updated_at`。

约束：成员 robot 必须存在；成员重复应报 validation error；成员是否必须同型号由真实硬件能力决定，不可先验禁止异型号混编。

### 3.4 MapAsset

字段：
- `map_id`、`scene_id`、`display_name`。
- `file_uri`：项目管理的相对资源 URI，禁止只存临时下载目录路径。
- `source_filename`。
- `format`：按实际 parser 已支持的格式枚举，不得写“支持所有点云”。
- `encoding`：从文件头/解析器实际确认。
- `point_count`、`width`、`height`、`fields`、`resolution`、`bounds`：解析成功才能填写；未知为空。
- `origin_pose`、`coordinate_frame_id`、`distance_unit`：按源文件和项目现有坐标契约读取。
- `sha256`、`file_size_bytes`。
- `import_state`：`IMPORTING`、`READY`、`FAILED`、`MISSING`。
- `import_error_code`、`import_error_message`。
- `created_at`、`updated_at`。

约束：
- READY 必须有存在、可读、hash 匹配的文件。
- MISSING 不得在画布中假装加载成功。
- 相同 SHA-256 默认提示重复资源；可由用户选择复用已有地图或另存副本，不能无声覆盖。
- 删除地图前检查 Scene.active_map_id、Trajectory.map_id 和其它引用。

### 3.5 Trajectory

Trajectory 是**几何路径数据**，不是时间轴片段。

字段：
- `trajectory_id`、`scene_id`、`name`。
- `map_id`（可空；无地图时必须显式说明坐标框架）。
- `robot_id` 或 `group_id`，两者不能同时为空或同时赋值，除非已有业务明确支持共享轨迹。
- `coordinate_frame_id`、`distance_unit`、`angle_unit`。
- `geometry_type`，本阶段至少支持 `POLYLINE_2D`；只有真实实现支持时才加 3D 类型。
- `waypoints_json`，带 schema_version。
- `point_count`、`total_length`、`estimated_duration_ms`（未知可空）。
- `created_at`、`updated_at`、`revision`。

Waypoint JSON 最少结构：

```json
{
  "schema_version": 1,
  "coordinate_frame_id": "map",
  "distance_unit": "m",
  "angle_unit": "rad",
  "geometry_type": "POLYLINE_2D",
  "waypoints": [
    {
      "waypoint_id": "stable-id",
      "x": 0.0,
      "y": 0.0,
      "yaw": null,
      "speed": null,
      "time_from_start_ms": null,
      "metadata": {}
    }
  ]
}
```

注意：
- 这是新格式的目标契约；旧文件必须通过 versioned adapter 转换。
- 不要直接覆盖用户已有 JSON。
- `yaw`、`speed`、`time_from_start_ms` 可空，不得伪造默认速度。
- 所有数值必须 finite；NaN/Infinity 不得写入 JSON。
- waypoint_id 在同一轨迹内唯一。
- point_count 必须与 waypoints 实际数量一致。

### 3.6 Formation

字段：
- `formation_id`、`scene_id`、`name`、`description`。
- `layout_type`：例如 GRID/LINE/CIRCLE/CUSTOM，只有实现的类型才允许入库。
- `parameters_json`：带版本和单位。
- `member_offsets_json`：robot_id -> relative pose；不能用数组位置隐式绑定机器人。
- `created_at`、`updated_at`、`revision`。

本阶段只定义并校验数据契约，不实现自动队形求解器。

### 3.7 ActionAsset

字段：
- `action_id`、`name`、`model_type`。
- `asset_uri`、`source_filename`、`file_sha256`。
- `duration_ms`、`sample_rate_hz`、`joint_names`（解析器能提供时）。
- `compatibility_json`、`metadata_json`。
- `import_state`、`created_at`、`updated_at`。

要求：
- 未解析的 duration 必须为 None，不得全部写成 0。
- 动作文件缺失时 UI 标记资源不可用。
- 不允许把无效的 `assets/motions/...` 路径当成有效动作。

### 3.8 Timeline / TimelineTrack / TimelineClip

Timeline：
- `timeline_id`、`scene_id`、`name`、`frame_rate`（只在项目实际采用帧率时设置）、`duration_ms`、`revision`。

TimelineTrack：
- `track_id`、`timeline_id`、`track_type`（ROBOT/ACTION/TRAJECTORY/EVENT 等仅限实现类型）、`robot_id`/`group_id`、`display_order`、`muted`、`locked`。

TimelineClip：
- `clip_id`、`track_id`、`source_type`、`source_id`、`start_ms`、`duration_ms`、`offset_ms`、`playback_rate`、`enabled`、`revision`。
- source_type 与 source_id 必须能对应真实资源。
- start_ms、offset_ms 非负；duration_ms 大于 0；playback_rate 有明确有效区间。
- 不能因资源库的动作被删除就静默留下失效 clip。
- 片段引用资源使用外键或应用层引用校验；删除资源前先检测引用。

## 4. SQLite 表结构与索引

根据 02 的 ADR 实施最终 schema。逻辑表建议：

- `schema_migrations`
- `scenes`
- `robots`
- `robot_groups`
- `robot_group_members`
- `maps`
- `trajectories`
- `formations`
- `actions`
- `timelines`
- `timeline_tracks`
- `timeline_clips`

可增减，但每张表必须说明用途。建议字段：
- 主键 TEXT；
- 外键显式声明；
- `created_at`/`updated_at`；
- JSON 字段使用 TEXT 保存，读写前后都验证；
- `revision` 用于乐观并发控制。

索引至少评估：
- `maps(scene_id, import_state)`；
- `trajectories(scene_id, updated_at)`；
- `actions(model_type, name)`；
- `timelines(scene_id)`；
- `timeline_tracks(timeline_id, display_order)`；
- `timeline_clips(track_id, start_ms)`；
- 外键引用列索引。

配置：
- `PRAGMA foreign_keys=ON` 必须在每条 connection 上设置。
- busy_timeout 使用配置值且写进 ADR。
- 连接线程归属遵守 Prompt 02 的决策。
- 不允许用 `check_same_thread=False` 代替线程模型设计。
- 不允许 `INSERT OR REPLACE` 造成外键对象隐式删除/重建。

## 5. 迁移实现

建立 versioned migration，例如 `src/infrastructure/storage/migrations/0001_initial.py`、`0002_legacy_choreo_import.py`，命名按项目实际结构调整。

每次 migration：
1. 记录 migration id、checksum、开始时间、结果。
2. 在事务中执行可事务化 DDL/DML。
3. 完成后更新 schema version。
4. 异常时 rollback，旧版本 DB 仍可打开。
5. migration 不可重复插入重复记录。
6. 检查源数据映射数量：源记录数、成功迁移数、跳过数、失败数。
7. 对无法确定的字段写 migration warning，不得臆造值。
8. 完成后做外键检查、JSON 检查、文件存在性和 hash 核验。

对于现有三个候选 DB：
- 先只读备份和分析；
- 识别 schema 冲突；
- 设计字段映射表；
- 迁移到 canonical DB；
- 对比迁移前后数量和关键业务字段；
- 生成 `migration_manifest.json`；
- 只有验收通过才标记 legacy DB 为 migrated。
不得删除 legacy DB，不得在失败时继续启动“半迁移”界面。

## 6. Repository 接口

Repository 不暴露 SQL row、sqlite cursor 或 connection 给 Application/UI。

必须实现或扩展以下用例接口（命名可依现有风格）：

```python
list_scenes() -> list[SceneViewData]
get_scene(scene_id) -> SceneViewData
create_scene(command) -> SceneViewData
update_scene(command) -> SceneViewData

list_maps(scene_id) -> list[MapViewData]
get_map(map_id) -> MapViewData
set_scene_active_map(scene_id, map_id) -> Result
delete_map(map_id) -> Result

list_robots(scene_id) -> list[RobotViewData]
list_robot_groups(scene_id) -> list[RobotGroupViewData]

list_trajectories(scene_id) -> list[TrajectoryViewData]
get_trajectory(trajectory_id) -> TrajectoryDetail
save_trajectory(command) -> SaveResult
delete_trajectory(trajectory_id) -> Result

list_actions(model_type=None) -> list[ActionViewData]

load_timeline(scene_id) -> TimelineViewData
save_timeline(command) -> SaveResult
```

对上面不存在的业务域，可返回显式 `UNSUPPORTED`，但不能返回虚假成功。UI 只依赖 application facade，不直接依赖 repository。

## 7. Import / Export 与兼容性

为 trajectory、timeline 和场景工程文件定义 versioned JSON 格式。

- `schema_version` 必须必填。
- 导入先 parse -> validate -> normalize -> preview -> confirm -> persist。
- 校验失败不得覆盖已有同名资源。
- 导出使用 UTF-8、稳定字段顺序、明确单位和坐标系。
- 对旧 JSON 格式编写 adapter；保留原始 source 文件 hash 和导入来源。
- 未知 schema_version 返回 `UNSUPPORTED_SCHEMA_VERSION`。
- 不允许“尽量猜字段名”然后悄悄导入。
- 导出采用临时文件 + fsync/原子替换；失败时不留下损坏的目标文件。

## 8. 必须覆盖的测试

- schema 从空 DB 创建成功。
- 每个 migration 从上个版本升级成功。
- 同一 migration 重跑不产生重复数据。
- migration 中断后可重试。
- legacy DB 合并计数可核对。
- JSON 字段 malformed 时返回稳定错误码。
- waypoint NaN/Infinity/重复 ID/缺坐标被拒绝。
- FK 引用存在时阻止危险删除。
- revision 不一致时返回 `CONFLICT`，不覆盖其他更新。
- 用户目录缺少地图文件时 MapAsset 标记 MISSING。
- trajectory 导入导出 round-trip。
- timeline clip 引用不存在的 action/trajectory 时拒绝。
- 测试使用独立临时 DB，结束清理临时目录；不得触碰生产 `runtime/`。

## 9. 交付

提交：
- canonical schema 和 migration 代码；
- Domain models 和 validators；
- Repository/Facade 方法；
- legacy schema -> canonical mapping 文件；
- `database-inventory.md`；
- `migration_manifest.json` 示例和真实迁移结果；
- JSON schema 或等价字段契约；
- 测试报告；
- 数据库恢复/回滚演练记录。

不要做 UI 重画。Prompt 04 完成后更新 PROJECT_STATE、TEST_MATRIX、DECISIONS 和 SESSION_HANDOFF。
