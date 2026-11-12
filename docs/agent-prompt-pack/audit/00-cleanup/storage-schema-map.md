# SQLite 存储体系与 Schema 映射审计报告

> 审计日期：2026-11-12  
> 审计范围：RobotDeploymentAssistant 全项目 SQLite 存储、历史冲突解决与规范化持久化设计

---

## 1. 现有 SQLite 数据库清单与哈希

| 数据库文件 | 所在路径 | 大小 (bytes) | SHA-256 校验和 | 角色/状态 |
|---|---|---|---|---|
| `choreo_database.db` | `data/choreo_database.db` | 94,208 | `18927364CA75A0C7D23AF80809297F1E0F61BE546902DC64EDF732E71236F088` | **规范核心库 (Canonical)** |
| `choreo_studio.db` | `runtime/shows/choreo_studio.db` | 81,920 | `28AE26AABC64A424C50E6C0F50A70BAD93C60595882EF6694FF03B968C3F31FA` | 历史归档库 (已备份) |
| `studio_core.db` | `runtime/shows/studio_core.db` | 65,536 | `06792F3D6EA011B6356846F141DB053C3F272DBD2BCDB14D94F2D89645046B83` | 历史归档库 (已备份) |
| `studio_data.db` | `runtime/shows/studio_data.db` | 61,440 | `2FBA5CE86D884E7B4FF3DF3D9F3565E5967822BB29FF3BCE2667DB3C1D38CF18` | 历史演示注入库 (已隔离/停用注入) |

所有四个数据库已完整冷备份至 `docs/agent-prompt-pack/audit/00-cleanup/db-backup/`。

---

## 2. 历史冲突分析

在 Prompt 00 审计中发现以下主要冲突：
1. **字段定义冲突**：
   - 旧 `StudioController` 创建 `actions(id, name, model, duration)` 与 `trajectories(id, robot_id, name, pts, duration)`。
   - 旧 `ChoreoSqliteStore` 期望 `actions(action_id, name, model_type, duration, anim_path)` 与 `trajectories(traj_id, robot_group, name, waypoints_json, duration, created_at)`。
   - 两者均使用 `CREATE TABLE IF NOT EXISTS`，当先打开一个结构后，另一个组件查询必然引发 `no such column` 崩溃。
2. **多库割裂**：
   - `StudioRepository` 连接 `studio_core.db` 管理场景初始点与任务。
   - `ChoreoRepository` 连接 `choreo_studio.db` 管理动作与时间轴片段。
   - UI 控件 `DualLayerTimelineCanvas` 直接 `sqlite3.connect()` 绕过 Repository 执行原子度不保的 SQL 操作。
3. **演示数据污染**：
   - 各层在首次初始化时注入固定 `POPPING1`、`A/B/C/D 假机器人`、`100001 假轨迹` 等，导致无法区分真伪。

---

## 3. 规范化单一持久化架构 (Canonical Architecture)

由 `src/core/storage_manager.py`（单例 `storage_manager`）作为系统唯一持久化调度器：

### 3.1 核心表 Schema

```sql
-- 1. 场景主表
CREATE TABLE IF NOT EXISTS scenes (
    scene_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    active_map_id TEXT DEFAULT 'map_default',
    active_init_cfg_id INTEGER DEFAULT 1,
    active_task_name TEXT DEFAULT '默认任务1',
    music_path TEXT DEFAULT '',
    music_title TEXT DEFAULT '未配置音乐',
    music_duration_s REAL DEFAULT 120.0,
    updated_at REAL
);

-- 2. 机器人轨道与硬件映射
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id TEXT NOT NULL,
    robot_id INTEGER NOT NULL,
    lora_id TEXT NOT NULL,
    sn TEXT DEFAULT '',
    alias TEXT DEFAULT '',
    UNIQUE(scene_id, robot_id)
);

-- 3. 初始位姿点
CREATE TABLE IF NOT EXISTS init_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id TEXT NOT NULL,
    cfg_id INTEGER DEFAULT 1,
    robot_id INTEGER NOT NULL,
    x REAL DEFAULT 0.0,
    y REAL DEFAULT 0.0,
    yaw REAL DEFAULT 0.0,
    robot_alias TEXT DEFAULT '',
    model_type TEXT DEFAULT 'Unitree_G1',
    UNIQUE(scene_id, cfg_id, robot_id)
);

-- 4. 2D/群组轨迹
CREATE TABLE IF NOT EXISTS trajectories (
    trajectory_id TEXT PRIMARY KEY,
    scene_id TEXT DEFAULT 'scene_001',
    group_id TEXT DEFAULT '',
    name TEXT NOT NULL,
    target_type TEXT DEFAULT 'single',
    target_id TEXT DEFAULT 'A',
    formation_id TEXT DEFAULT '',
    duration REAL DEFAULT 3.0,
    max_velocity REAL DEFAULT 1.2,
    interpolation TEXT DEFAULT 'catmull_rom',
    control_points_json TEXT NOT NULL,
    sampled_points_json TEXT DEFAULT '[]',
    created_at REAL
);

-- 5. 轨道状态记录
CREATE TABLE IF NOT EXISTS track_state (
    id TEXT PRIMARY KEY,
    scene_id TEXT DEFAULT 'scene_001',
    robot_id INTEGER NOT NULL,
    group_id INTEGER DEFAULT 0,
    no INTEGER NOT NULL,
    type TEXT NOT NULL,
    name TEXT DEFAULT '',
    time REAL DEFAULT 0.0,
    start_time REAL DEFAULT 0.0,
    end_time REAL DEFAULT 0.0,
    content_json TEXT DEFAULT '{}'
);

-- 6. 时间轴动作/轨迹片段
CREATE TABLE IF NOT EXISTS fragments (
    fragment_id TEXT PRIMARY KEY,
    scene_id TEXT DEFAULT 'scene_001',
    name TEXT NOT NULL,
    start_time REAL DEFAULT 0.0,
    duration REAL DEFAULT 10.0,
    content_json TEXT DEFAULT '{}'
);
```

### 3.2 文件镜像体系与原子性
- 地图索引：`data/maps/maps_index.json`
- 轨迹实体：`data/trajectories/<trajectory_id>.json`
- 阵型定义：`data/formations/<formation_id>.json`
- 工程快照：`data/projects/<project_id>_choreo.json`
- 所有文件写入均通过内存序列化后原子更新，并同 SQLite 数据库保持双写一致性。
