# 数据库现状盘点报告 (Database Inventory)

> 审计时间: 2026-11-12 | 依据: Prompt 04 | 范围: 工作区所有 SQLite 数据库

## 1. 数据库文件清单

| 数据库路径 | 大小 (Bytes) | user_version | 外键支持 | 表数量 | 状态/归属 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `./data/choreo_database.db` | 94208 | 0 | OFF | 6 | **规范数据库 (Canonical DB)** |
| `./docs/agent-prompt-pack/audit/00-cleanup/db-backup/choreo_database.db` | 94208 | 0 | OFF | 6 | 冷备份 (只读隔离) |
| `./docs/agent-prompt-pack/audit/00-cleanup/db-backup/choreo_studio.db` | 81920 | 0 | OFF | 12 | 冷备份 (只读隔离) |
| `./docs/agent-prompt-pack/audit/00-cleanup/db-backup/studio_core.db` | 65536 | 0 | OFF | 8 | 冷备份 (只读隔离) |
| `./docs/agent-prompt-pack/audit/00-cleanup/db-backup/studio_data.db` | 61440 | 0 | OFF | 7 | 冷备份 (只读隔离) |
| `./docs/agent-prompt-pack/audit/01-compatibility/backup/database-copy/choreo_database.db` | 94208 | 0 | OFF | 6 | 冷备份 (只读隔离) |
| `./docs/agent-prompt-pack/audit/01-compatibility/backup/database-copy/choreo_studio.db` | 81920 | 0 | OFF | 12 | 冷备份 (只读隔离) |
| `./docs/agent-prompt-pack/audit/01-compatibility/backup/database-copy/studio_core.db` | 65536 | 0 | OFF | 8 | 冷备份 (只读隔离) |
| `./docs/agent-prompt-pack/audit/01-compatibility/backup/database-copy/studio_data.db` | 61440 | 0 | OFF | 7 | 冷备份 (只读隔离) |
| `./runtime/shows/choreo_studio.db` | 81920 | 0 | OFF | 12 | 历史活动库 (待归档/迁移) |
| `./runtime/shows/studio_core.db` | 65536 | 0 | OFF | 8 | 历史活动库 (待归档/迁移) |
| `./runtime/shows/studio_data.db` | 61440 | 0 | OFF | 7 | 历史活动库 (待归档/迁移) |

## 2. 核心候选库 Schema 与数据对比

### 2.1 `./data/choreo_database.db`
- **User Version**: 0
- **文件大小**: 94208 字节

| 表名 | 记录数 | 主键列 | 关键字段 |
| :--- | :--- | :--- | :--- |
| `fragments` | 0 | `fragment_id` | fragment_id, scene_id, name, start_time, duration... |
| `init_points` | 0 | `id` | id, scene_id, cfg_id, robot_id, x... |
| `scenes` | 4 | `scene_id` | scene_id, name, active_map_id, active_init_cfg_id, active_task_name... |
| `track_state` | 3 | `id` | id, scene_id, robot_id, group_id, no... |
| `tracks` | 5 | `id` | id, scene_id, robot_id, lora_id, sn... |
| `trajectories` | 3 | `trajectory_id` | trajectory_id, scene_id, group_id, name, target_type... |

### 2.2 `./runtime/shows/studio_data.db`
- **User Version**: 0
- **文件大小**: 61440 字节

| 表名 | 记录数 | 主键列 | 关键字段 |
| :--- | :--- | :--- | :--- |
| `actions` | 10 | `action_id` | action_id, name, model_type, duration, anim_path |
| `clips` | 5 | `id` | id, robot_id, layer, ref_id, title... |
| `group_trajectories` | 0 | `group_trajectory_id` | group_trajectory_id, name, reference_trajectory_id, coordinate_frame, members_json... |
| `scenes` | 0 | `scene_id` | scene_id, name, pcd_path, init_points_json, bgm_path... |
| `stage_maps` | 0 | `map_id` | map_id, name, file_path, file_size_bytes, point_count... |
| `timeline_clips` | 2 | `clip_id` | clip_id, task_name, robot_id, track_layer, ref_id... |
| `trajectories` | 23 | `traj_id` | traj_id, robot_group, name, waypoints_json, duration... |

### 2.3 `./runtime/shows/studio_core.db`
- **User Version**: 0
- **文件大小**: 65536 字节

| 表名 | 记录数 | 主键列 | 关键字段 |
| :--- | :--- | :--- | :--- |
| `actions` | 0 | `id` | id, scene_id, no, name, lora_alias... |
| `fragments` | 9 | `fragment_id` | fragment_id, scene_id, name, start_time, duration... |
| `init_points` | 0 | `id` | id, scene_id, cfg_id, robot_id, x... |
| `scenes` | 1 | `scene_id` | scene_id, name, active_map_id, active_init_cfg_id, active_task_name... |
| `track_state` | 0 | `id` | id, scene_id, robot_id, group_id, no... |
| `tracks` | 4 | `id` | id, scene_id, robot_id, lora_id, sn... |
| `trajectories` | 0 | `no` | no, scene_id, group_id, name, time... |
| `trajectory_groups` | 2 | `id` | id, scene_id, name, track_id |

### 2.4 `./runtime/shows/choreo_studio.db`
- **User Version**: 0
- **文件大小**: 81920 字节

| 表名 | 记录数 | 主键列 | 关键字段 |
| :--- | :--- | :--- | :--- |
| `actions` | 5 | `action_id` | action_id, name, model_type, duration_s, keyframes_json... |
| `fragments` | 0 | `frag_no` | frag_no, name, blocks_json, updated_at |
| `init_point_configs` | 2 | `cfg_id, scene_id, track_id` | cfg_id, scene_id, cfg_name, track_id, robot_alias... |
| `init_points` | 0 | `id` | id, scene_id, group_id, group_name, robot_id... |
| `nav_maps` | 1 | `map_id` | map_id, name, pcd_path, grid_res, origin_x... |
| `scenes` | 1 | `scene_id` | scene_id, name, active_map_id, active_init_cfg_id, active_task_name... |
| `timeline_clips` | 5 | `clip_id` | clip_id, scene_id, task_name, track_id, sub_layer... |
| `track_state` | 0 | `block_id` | block_id, scene_id, robot_id, type, no... |
| `tracks` | 0 | `track_id` | track_id, scene_id, robot_id, sn, alias... |
| `traj_groups` | 2 | `group_id` | group_id, scene_id, robot_label, model_type, bound_track_id |
| `trajectories` | 2 | `traj_id` | traj_id, group_id, name, control_pts_json, sampled_pts_json... |
| `trajectory_groups` | 0 | `id` | id, scene_id, name, track_id |

## 3. 统一与迁移策略 (ADR-002 执行)

1. **唯一 Canonical 数据库**: `data/choreo_database.db`。
2. **外键强校验**: 每次数据库连接强制执行 `PRAGMA foreign_keys = ON`。
3. **迁移流水线**: 采用版本化迁移表 `schema_migrations`，保证事务性与可重入性。
4. **历史库隔离**: `runtime/shows/studio_data.db`、`studio_core.db`、`choreo_studio.db` 完成数据入库验证后标记为 MIGRATED，仅作冷归档。
