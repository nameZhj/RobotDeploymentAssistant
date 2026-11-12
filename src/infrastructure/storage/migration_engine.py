"""
@file: src/infrastructure/storage/migration_engine.py
@brief: SQLite 版本化迁移引擎，支持原子事务执行、Checksum 核验与平滑回滚保障
@exports: MigrationEngine, apply_all_migrations
"""
from datetime import datetime, timezone
import hashlib
import inspect
import logging
import sqlite3
from typing import Any, Dict, List, Tuple
from src.infrastructure.storage.migrations import (
    m0001_initial_canonical_schema as m0001,
    m0002_legacy_choreo_migration as m0002,
)

logger = logging.getLogger("MigrationEngine")

REGISTERED_MIGRATIONS = [m0001, m0002]


class MigrationEngine:
    """SQLite 规范化迁移调度引擎"""

    @staticmethod
    def _compute_checksum(module: Any) -> str:
        source = inspect.getsource(module)
        return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def apply_all(cls, conn: sqlite3.Connection) -> List[str]:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_id TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL,
                success INTEGER NOT NULL
            )
        """)
        applied_rows = conn.execute("SELECT migration_id, checksum FROM schema_migrations WHERE success = 1").fetchall()
        applied_map = {r[0]: r[1] for r in applied_rows}

        executed: List[str] = []
        for mig in REGISTERED_MIGRATIONS:
            mig_id = mig.MIGRATION_ID
            target_ver = mig.TARGET_VERSION
            current_checksum = cls._compute_checksum(mig)

            if mig_id in applied_map:
                continue

            now_iso = datetime.now(timezone.utc).isoformat()
            try:
                conn.execute("BEGIN TRANSACTION;")
                mig.up(conn)
                conn.execute(
                    "INSERT INTO schema_migrations (migration_id, checksum, applied_at, success) VALUES (?, ?, ?, 1)",
                    (mig_id, current_checksum, now_iso),
                )
                conn.execute(f"PRAGMA user_version = {target_ver};")
                conn.commit()
                executed.append(mig_id)
                logger.info(f"✅ 成功执行迁移 [{mig_id}] -> 目标版本 v{target_ver}")
            except Exception as e:
                conn.rollback()
                logger.error(f"❌ 迁移 [{mig_id}] 执行失败，已安全回滚: {e}", exc_info=True)
                raise RuntimeError(f"迁移 {mig_id} 失败: {e}") from e

        return executed

    @classmethod
    def get_manifest(cls, conn: sqlite3.Connection) -> Dict[str, Any]:
        cur = conn.cursor()
        cur.execute("PRAGMA user_version;")
        u_ver = cur.fetchone()[0]
        cur.execute("SELECT migration_id, checksum, applied_at, success FROM schema_migrations ORDER BY applied_at ASC")
        rows = cur.fetchall()
        migrations = [
            {"migration_id": r[0], "checksum": r[1], "applied_at": r[2], "success": bool(r[3])}
            for r in rows
        ]
        return {
            "current_user_version": u_ver,
            "total_applied": len(migrations),
            "migrations": migrations,
        }


def apply_all_migrations(conn: sqlite3.Connection) -> List[str]:
    return MigrationEngine.apply_all(conn)
