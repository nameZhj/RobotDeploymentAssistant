"""
@file: src/infrastructure/storage/stage_map_sqlite_adapter.py
@brief: 本地 PCD 地图 SQLite 持久化、引用保护与原子复制适配器
@exports: StageMapSqliteAdapter, atomic_copy_pcd
"""
import contextlib
import os
import sqlite3
import time
from typing import Generator, List, Optional
from src.domain.map.stage_map_asset import StageMapAsset

DEFAULT_DB_PATH = os.path.join("runtime", "shows", "studio_data.db")


def atomic_copy_pcd(src_path: str, dest_dir: str = "runtime/stage_maps") -> str:
    """以原子方式安全复制 PCD 文件至统一存储目录，规避异常残留与重名覆盖"""
    if not os.path.isfile(src_path):
        raise FileNotFoundError(f"源 PCD 文件不存在或不可读: '{src_path}'")
    os.makedirs(dest_dir, exist_ok=True)
    base_name = os.path.basename(src_path)
    stem, ext = os.path.splitext(base_name)
    target_path = os.path.normpath(os.path.join(dest_dir, f"{stem}{ext}"))

    if os.path.abspath(src_path) == os.path.abspath(target_path):
        return target_path

    idx = 1
    while os.path.exists(target_path):
        target_path = os.path.normpath(os.path.join(dest_dir, f"{stem}_{idx}{ext}"))
        idx += 1

    temp_path = target_path + ".tmp"
    try:
        with open(src_path, "rb") as fsrc, open(temp_path, "wb") as fdst:
            while True:
                chunk = fsrc.read(65536)
                if not chunk:
                    break
                fdst.write(chunk)
            fdst.flush()
            os.fsync(fdst.fileno())
        os.replace(temp_path, target_path)
        return target_path
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise


class StageMapSqliteAdapter:
    """提供舞台地图素材在 studio_data.db 中的持久化维护与关联引用保护"""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_table()

    @contextlib.contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_table(self) -> None:
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stage_maps (
                    map_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_size_bytes INTEGER NOT NULL,
                    point_count INTEGER NOT NULL,
                    min_x REAL NOT NULL,
                    max_x REAL NOT NULL,
                    min_y REAL NOT NULL,
                    max_y REAL NOT NULL,
                    min_z REAL NOT NULL,
                    max_z REAL NOT NULL,
                    origin_x REAL DEFAULT 0.0,
                    origin_y REAL DEFAULT 0.0,
                    resolution REAL DEFAULT 0.05,
                    width INTEGER DEFAULT 0,
                    height INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.commit()

    def save_map(self, asset: StageMapAsset) -> None:
        with self.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO stage_maps (
                    map_id, name, file_path, file_size_bytes, point_count,
                    min_x, max_x, min_y, max_y, min_z, max_z,
                    origin_x, origin_y, resolution, width, height,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                asset.map_id, asset.name, asset.file_path, asset.file_size_bytes, asset.point_count,
                asset.min_x, asset.max_x, asset.min_y, asset.max_y, asset.min_z, asset.max_z,
                asset.origin_x, asset.origin_y, asset.resolution, asset.width, asset.height,
                asset.created_at, asset.updated_at
            ))
            conn.commit()

    def get_map(self, map_id: str) -> Optional[StageMapAsset]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM stage_maps WHERE map_id = ?", (map_id,)).fetchone()
            return StageMapAsset.from_dict(dict(row)) if row else None

    def list_maps(self) -> List[StageMapAsset]:
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM stage_maps ORDER BY created_at DESC").fetchall()
            return [StageMapAsset.from_dict(dict(r)) for r in rows]

    def delete_map(self, map_id: str) -> bool:
        with self.get_connection() as conn:
            cur = conn.execute("DELETE FROM stage_maps WHERE map_id = ?", (map_id,))
            conn.commit()
            return cur.rowcount > 0

    def check_map_in_use(self, map_id: str, active_map_id: Optional[str] = None) -> bool:
        if active_map_id and map_id == active_map_id:
            return True
        map_asset = self.get_map(map_id)
        if not map_asset:
            return False
        with self.get_connection() as conn:
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM scenes WHERE pcd_path = ?",
                    (map_asset.file_path,)
                ).fetchone()
                if row and row[0] > 0:
                    return True
            except sqlite3.OperationalError:
                pass
            try:
                row_proj = conn.execute(
                    "SELECT COUNT(*) FROM show_projects WHERE current_map_id = ?",
                    (map_id,)
                ).fetchone()
                if row_proj and row_proj[0] > 0:
                    return True
            except sqlite3.OperationalError:
                pass
            try:
                row_traj = conn.execute(
                    "SELECT COUNT(*) FROM trajectories WHERE map_id = ?",
                    (map_id,)
                ).fetchone()
                if row_traj and row_traj[0] > 0:
                    return True
            except sqlite3.OperationalError:
                pass
        return False
