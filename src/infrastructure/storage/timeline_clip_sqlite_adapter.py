"""
@file: src/infrastructure/storage/timeline_clip_sqlite_adapter.py
@brief: 时间轴 Clip 与 timeline_clips 表持久化适配器，严格执行外键安全更新与防误删
@exports: TimelineClipSqliteAdapter
"""
import contextlib
import os
import sqlite3
from typing import Any, Dict, Generator, List, Optional
from src.domain.timeline.timeline_clip_asset import TimelineClipAsset

DEFAULT_DB_PATH = os.path.join("data", "choreo_database.db")


class TimelineClipSqliteAdapter:
    """提供时间轴 Clip 在 SQLite 中的原子持久化，彻底杜绝 INSERT OR REPLACE 破坏外键引用"""

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
                CREATE TABLE IF NOT EXISTS timeline_clips (
                    clip_id TEXT PRIMARY KEY,
                    task_name TEXT DEFAULT '默认任务1',
                    robot_id TEXT NOT NULL,
                    track_layer TEXT NOT NULL,
                    ref_id TEXT NOT NULL,
                    start_ms INTEGER NOT NULL,
                    duration_ms INTEGER NOT NULL
                )
            """)
            cols = [c[1] for c in conn.execute("PRAGMA table_info(timeline_clips)").fetchall()]
            if "name" not in cols:
                conn.execute("ALTER TABLE timeline_clips ADD COLUMN name TEXT DEFAULT ''")
            conn.commit()

    def save_clip(self, clip: TimelineClipAsset) -> None:
        """安全保存或更新 Clip：通过显式 SELECT 分支更新，保护所有引用完整性"""
        clip.validate()
        cid = str(clip.clip_id)
        with self.get_connection() as conn:
            row = conn.execute("SELECT clip_id FROM timeline_clips WHERE clip_id = ?", (cid,)).fetchone()
            if row:
                conn.execute("""
                    UPDATE timeline_clips
                    SET task_name = ?, robot_id = ?, track_layer = ?, ref_id = ?,
                        start_ms = ?, duration_ms = ?, name = ?
                    WHERE clip_id = ?
                """, (
                    clip.task_name, str(clip.robot_id), clip.track_layer, str(clip.ref_id),
                    int(clip.start_ms), int(clip.duration_ms), clip.name, cid
                ))
            else:
                conn.execute("""
                    INSERT INTO timeline_clips
                    (clip_id, task_name, robot_id, track_layer, ref_id, start_ms, duration_ms, name)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    cid, clip.task_name, str(clip.robot_id), clip.track_layer, str(clip.ref_id),
                    int(clip.start_ms), int(clip.duration_ms), clip.name
                ))
            conn.commit()

    def update_clip_position(self, clip_id: str, start_ms: int) -> bool:
        with self.get_connection() as conn:
            cur = conn.execute(
                "UPDATE timeline_clips SET start_ms = ? WHERE clip_id = ?",
                (max(0, int(start_ms)), str(clip_id))
            )
            conn.commit()
            return cur.rowcount > 0

    def update_clip_duration(self, clip_id: str, duration_ms: int) -> bool:
        with self.get_connection() as conn:
            cur = conn.execute(
                "UPDATE timeline_clips SET duration_ms = ? WHERE clip_id = ?",
                (max(200, int(duration_ms)), str(clip_id))
            )
            conn.commit()
            return cur.rowcount > 0

    def delete_clip(self, clip_id: str) -> bool:
        with self.get_connection() as conn:
            cur = conn.execute("DELETE FROM timeline_clips WHERE clip_id = ?", (str(clip_id),))
            conn.commit()
            return cur.rowcount > 0

    def get_clip(self, clip_id: str) -> Optional[TimelineClipAsset]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM timeline_clips WHERE clip_id = ?", (str(clip_id),)).fetchone()
            return TimelineClipAsset.from_dict(dict(row)) if row else None

    def list_clips(self, task_name: str = "默认任务1", robot_id: Optional[str] = None) -> List[TimelineClipAsset]:
        """批量获取指定任务与轨道的 Clip，自动由 ref_id 补全未命名的历史素材"""
        q = "SELECT * FROM timeline_clips WHERE task_name = ?"
        params: List[Any] = [task_name]
        if robot_id is not None:
            q += " AND robot_id = ?"
            params.append(str(robot_id))
        q += " ORDER BY start_ms ASC"

        with self.get_connection() as conn:
            rows = conn.execute(q, params).fetchall()
            results: List[TimelineClipAsset] = []
            for r in rows:
                d = dict(r)
                if not d.get("name"):
                    ref = str(d.get("ref_id", ""))
                    d["name"] = self._resolve_name(conn, d.get("track_layer", ""), ref)
                results.append(TimelineClipAsset.from_dict(d))
            return results

    def _resolve_name(self, conn: sqlite3.Connection, layer: str, ref_id: str) -> str:
        try:
            if "ACTION" in layer:
                r = conn.execute("SELECT name FROM actions WHERE action_id = ?", (ref_id,)).fetchone()
                if r and r[0]: return str(r[0])
            elif "TRAJ" in layer:
                r = conn.execute("SELECT name FROM trajectories WHERE traj_id = ?", (ref_id,)).fetchone()
                if r and r[0]: return str(r[0])
                r_gt = conn.execute("SELECT name FROM group_trajectories WHERE group_trajectory_id = ?", (ref_id,)).fetchone()
                if r_gt and r_gt[0]: return str(r_gt[0])
        except Exception:
            pass
        return f"Clip-{ref_id}"
