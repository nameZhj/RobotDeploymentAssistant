# @file: src/persistence/db_engine.py
# @brief: Thread-safe SQLite database connection manager, schema bootstrapper, and transaction context.
# @exports: StudioDatabase, get_database

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import threading
from typing import Iterator, Optional

from src.core.paths import get_paths
from src.persistence.schema_ddl import ALL_TABLES_DDL, SCHEMA_VERSION


class StudioDatabase:
    """Thread-safe SQLite gateway scoped to .agent_workspace/runtime/uniuni_studio.db."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path) if db_path else get_paths().db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialized = False
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def initialize(self) -> None:
        """Execute canonical 10-table DDL and seed built-in dance/scene data if fresh."""
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            conn = self._connect()
            try:
                conn.executescript(ALL_TABLES_DDL)
                self._migrate_columns(conn)
                conn.execute(
                    "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
                    ("schema_version", str(SCHEMA_VERSION)),
                )
                conn.commit()
            finally:
                conn.close()
            self._initialized = True

    @staticmethod
    def _migrate_columns(conn: sqlite3.Connection) -> None:
        cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(trajectories)").fetchall()}
        if "visible_on_map" not in cols:
            conn.execute("ALTER TABLE trajectories ADD COLUMN visible_on_map INTEGER NOT NULL DEFAULT 1")
        if "bound_track_nos_json" not in cols:
            conn.execute("ALTER TABLE trajectories ADD COLUMN bound_track_nos_json TEXT NOT NULL DEFAULT '[]'")

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        """Yield a transactional SQLite connection guarded by an RLock."""
        with self._lock:
            conn = self._connect()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()


_DEFAULT_DB: Optional[StudioDatabase] = None


def get_database(db_path: Optional[Path] = None, reset: bool = False) -> StudioDatabase:
    """Return the singleton StudioDatabase instance (with seed data ensured)."""
    global _DEFAULT_DB
    expected = db_path or get_paths().db_path
    if _DEFAULT_DB is None or reset or db_path is not None or _DEFAULT_DB.db_path != expected:
        db = StudioDatabase(db_path=db_path)
        from src.persistence.seed_builtin_data import ensure_seeded
        ensure_seeded(db)
        if db_path is None:
            _DEFAULT_DB = db
        return db
    return _DEFAULT_DB
