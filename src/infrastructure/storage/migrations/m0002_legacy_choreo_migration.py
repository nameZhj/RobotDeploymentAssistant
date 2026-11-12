"""
@file: src/infrastructure/storage/migrations/0002_legacy_choreo_migration.py
@brief: 历史编排数据库映射与增量平滑迁移脚本
@exports: MIGRATION_ID, TARGET_VERSION, up
"""
from datetime import datetime, timezone
import json
import logging
import sqlite3
from typing import Any, Dict

logger = logging.getLogger("Migration0002")

MIGRATION_ID = "0002_legacy_choreo_migration"
TARGET_VERSION = 2


def up(conn: sqlite3.Connection) -> Dict[str, Any]:
    """执行 0002 历史数据映射迁移，平滑迁移旧版 scenes/trajectories/tracks 至规范表"""
    cur = conn.cursor()
    stats = {"scenes_migrated": 0, "trajectories_migrated": 0, "tracks_migrated": 0}
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. 检查是否存在旧版 scenes
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "scenes" in tables:
        cols = [c[1] for c in cur.execute("PRAGMA table_info(scenes)").fetchall()]
        if "description" not in cols:
            cur.execute("ALTER TABLE scenes ADD COLUMN description TEXT;")
        if "coordinate_frame_id" not in cols:
            cur.execute("ALTER TABLE scenes ADD COLUMN coordinate_frame_id TEXT DEFAULT 'map';")
        if "distance_unit" not in cols:
            cur.execute("ALTER TABLE scenes ADD COLUMN distance_unit TEXT DEFAULT 'm';")
        if "angle_unit" not in cols:
            cur.execute("ALTER TABLE scenes ADD COLUMN angle_unit TEXT DEFAULT 'rad';")
        if "schema_version" not in cols:
            cur.execute("ALTER TABLE scenes ADD COLUMN schema_version INTEGER DEFAULT 1;")

    # 2. 检查旧版 trajectories 字段适配
    if "trajectories" in tables:
        tcols = [c[1] for c in cur.execute("PRAGMA table_info(trajectories)").fetchall()]
        if "revision" not in tcols:
            cur.execute("ALTER TABLE trajectories ADD COLUMN revision INTEGER DEFAULT 1;")
        if "geometry_type" not in tcols:
            cur.execute("ALTER TABLE trajectories ADD COLUMN geometry_type TEXT DEFAULT 'POLYLINE_2D';")
        if "coordinate_frame_id" not in tcols:
            cur.execute("ALTER TABLE trajectories ADD COLUMN coordinate_frame_id TEXT DEFAULT 'map';")
        if "distance_unit" not in tcols:
            cur.execute("ALTER TABLE trajectories ADD COLUMN distance_unit TEXT DEFAULT 'm';")
        if "angle_unit" not in tcols:
            cur.execute("ALTER TABLE trajectories ADD COLUMN angle_unit TEXT DEFAULT 'rad';")

    return stats
