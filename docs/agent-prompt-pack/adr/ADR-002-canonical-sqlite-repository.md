# ADR-002: 唯一规范化 SQLite 仓储与文件镜像双写策略

- **状态**：APPROVED
- **日期**：2026-11-12
- **决策者**：RobotDeploymentAssistant 核心工程组

## 1. 背景与问题
历史代码中散落 `choreo_database.db`、`studio_data.db`、`studio_core.db`、`choreo_studio.db` 四个数据库文件，且存在 `actions` 与 `trajectories` 表列名冲突，引发 `no such column` 报错。

## 2. 候选方案评估
- **方案 A（引入 SQLAlchemy ORM）**：劣势：增加大型第三方依赖、包体膨胀约 15MB，且对已有字典与元组交互有侵入性改动。
- **方案 B（收敛标准库 sqlite3 + StorageManager 事务门面，推荐）**：优势：零新增依赖、利用 SQLite 事务与 `ON CONFLICT` 保障原子性，且与 `data/` 下 JSON 文件建立双写镜像。

## 3. 决策内容
1. 确立 `data/choreo_database.db` 为系统唯一规范化数据库。
2. 由 `src/core/storage_manager.py` 统管 6 核心表（scenes, tracks, init_points, trajectories, track_state, fragments）。
3. 关键资源（轨迹、阵型、工程）在写入数据库的同时原子写入 `data/` 对应 JSON，提供双重恢复保障。

## 4. 后果与回滚计划
- **积极影响**：数据源唯一，消除表结构冲突与脏数据注入。
- **回滚方案**：所有历史数据库均已冷备份至 `docs/agent-prompt-pack/audit/00-cleanup/db-backup/`。
