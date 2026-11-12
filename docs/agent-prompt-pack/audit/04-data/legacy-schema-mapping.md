# 历史 Schema 到规范 Schema 映射契约 (Legacy Schema Mapping)

> 审计基准: Prompt 04 | 依据 Canonical DB: `data/choreo_database.db`

## 1. 映射策略与生命周期

在统一持久化演进过程中，系统存在多张历史形态表（`trajectories` 旧结构、`runtime/shows/studio_data.db` 等）。为保障既有资产平滑升级且不破坏历史数据完整性，采用如下映射规则：

1. **零数据丢失原则**：历史记录必须无损转换为 Canonical Entity；
2. **确定性转换**：缺失坐标默认转换为明确空值或标准化默认值，严禁使用 NaN 或随机值；
3. **隔离解耦**：历史库仅以只读方式挂载抽取，抽取后原库封存冷备份。

---

## 2. 表级映射规则矩阵

### 2.1 轨迹表 (`trajectories`)

| 历史字段 / 表现 | Canonical 规范字段 (`trajectories`) | 转换/适配逻辑 | 边界与校验 |
| :--- | :--- | :--- | :--- |
| `traj_id` / `trajectory_id` | `trajectory_id` | 直接对齐，保留原始字符串 ID | 必须非空且符合标识符字符集 |
| `scene_id` | `scene_id` | 保留所属场景，缺失时归入 `scene_001` | 外键级联检查 |
| `name` | `name` | 去除首尾空白字符 | 长度限制 1-64 |
| `waypoints_json` | `waypoints_json` | 标准 JSON 列表，提取 `(x, y, z, yaw, t)` | 校验有限浮点数 (NaN/Inf 拒绝) |
| `control_points_json` | `control_points_json` | 保留兼容样条控制点 | 格式合法性解析 |
| `sampled_points_json` | `sampled_points_json` | 保留兼容稠密采样点 | 格式合法性解析 |
| `target_type` | `target_type` | 单机或群组标识 (默认 `'single'`) | 枚举校验 |
| `target_id` | `target_id` | 机器人或阵型编号 (默认 `'A'`) | 非空字符串 |
| `created_at` (float/str) | `created_at` | 规范化为 ISO-8601 或 Unix 时间戳 | 必填 |
| `updated_at` (float/str) | `updated_at` | 记录更新时间戳 | 必填 |

### 2.2 动作表 (`actions`)

| 历史字段 (`studio_data.actions`) | Canonical 规范字段 (`actions`) | 转换/适配逻辑 | 边界与校验 |
| :--- | :--- | :--- | :--- |
| `action_id` | `action_id` | 唯一动作标识符 | 必须非空 |
| `name` | `name` | 动作名称 (如 `POPPING_DANCE`) | 必填 |
| `model_type` | `model_type` | 机器人机型 (默认 `'Unitree_G1'`) | 白名单支持机型 |
| `anim_path` / `asset_uri` | `asset_uri` | 相对/绝对路径归一化 | 检验文件哈希与存在性 |
| `duration` (秒) | `duration_ms` | 乘以 1000 转为整型毫秒 | 大于 0 |
| `import_state` | `import_state` | `READY` / `MISSING` | 文件不存在时置为 `MISSING` |

### 2.3 时间轴片段 (`clips` / `timeline_clips`)

| 历史字段 (`studio_data.clips`) | Canonical 规范字段 (`timeline_clips`) | 转换/适配逻辑 | 边界与校验 |
| :--- | :--- | :--- | :--- |
| `id` / `clip_id` | `clip_id` | 规范 UUID/字符串 ID | 主键唯一 |
| `robot_id` | `track_id` (via `timeline_tracks`) | 关联到对应机器人的 Track 记录 | 外键完整性 |
| `layer` | `track_type` | 区分 `ROBOT` / `FORMATION` / `BARRIER` | 必须为受支持轨道类型 |
| `start_time` (秒) | `start_ms` | 乘以 1000 转换为整型毫秒 | 非负整数 |
| `duration` (秒) | `duration_ms` | 乘以 1000 转换为整型毫秒 | 大于 0 |
| `ref_id` | `source_id` | 动作 ID 或轨迹 ID | 必须在动作或轨迹表中存在 |

---

## 3. 校验契约与安全机制

- **外键约束激活**：`PRAGMA foreign_keys = ON`，阻止孤儿片段与破坏性级联；
- **原子事务**：迁移与保存操作使用显式事务包裹（`BEGIN IMMEDIATE` / `COMMIT`）；
- **幂等性保障**：支持多次重复运行迁移逻辑，通过 `schema_migrations` 记录与表结构内省避免重复变更。
