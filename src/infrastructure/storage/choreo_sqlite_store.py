"""
@file: src/infrastructure/storage/choreo_sqlite_store.py
@brief: Choreo SQLite 数据存储引擎，管理 scenes、trajectories、actions 与 timeline_clips 核心表
@exports: ChoreoSqliteStore, DEFAULT_DB_PATH, DEFAULT_ACTIONS
"""
import contextlib
import json
import os
import sqlite3
import time
from typing import Any, Dict, Generator, List, Optional
from src.domain.trajectory.trajectory_asset import TrajectoryAsset
from src.infrastructure.storage.trajectory_sqlite_adapter import TrajectorySqliteAdapter


DEFAULT_DB_PATH = os.path.join("runtime", "shows", "studio_data.db")

DEFAULT_ACTIONS = [
    ("550502", "POPPING1", "A2-W", 38.62, "assets/motions/550502_popping1.npz"),
    ("550503", "POPPING2", "A2-W", 25.82, "assets/motions/550503_popping2.npz"),
    ("550504", "POPPING3", "A2-W", 30.02, "assets/motions/550504_popping3.npz"),
    ("550506", "芭蕾", "A2-W", 32.02, "assets/motions/550506_ballet.npz"),
    ("act_g1_kungfu", "G1_太极抱拳", "Unitree_G1", 6.00, "preview/G1_KUNG_FU.npz"),
    ("act_g1_moonwalk", "G1_太空漫步", "Unitree_G1", 6.00, "preview/G1_MOONWALK.npz"),
    ("act_g1_tiktok", "G1_流行手势舞", "Unitree_G1", 6.00, "preview/G1_TIKTOK.npz"),
    ("act_g1_turnjump", "G1_旋转跳跃", "Unitree_G1", 5.00, "preview/G1_TURN_JUMP.npz"),
    ("act_g2_wave", "G2_机械电流波浪", "Unitree_G1", 5.00, "preview/G2_WAVE.npz"),
    ("act_g3_cyber", "G3_赛博重节拍", "Unitree_G1", 5.50, "preview/G3_CYBER.npz"),
]


class ChoreoSqliteStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_tables()
        self._seed_default_actions()

    @contextlib.contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_tables(self) -> None:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scenes (
                    scene_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    pcd_path TEXT,
                    init_points_json TEXT,
                    bgm_path TEXT,
                    updated_at REAL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trajectories (
                    traj_id TEXT PRIMARY KEY,
                    robot_group TEXT NOT NULL,
                    name TEXT NOT NULL,
                    waypoints_json TEXT NOT NULL,
                    duration REAL NOT NULL,
                    created_at REAL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS actions (
                    action_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    model_type TEXT DEFAULT 'A2-W',
                    duration REAL NOT NULL,
                    anim_path TEXT
                )
            """)
            cur.execute("""
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
            TrajectorySqliteAdapter.ensure_columns(conn)
            conn.commit()

    def _seed_default_actions(self) -> None:
        with self.get_connection() as conn:
            cur = conn.cursor()
            for row in DEFAULT_ACTIONS:
                cur.execute(
                    "INSERT OR IGNORE INTO actions (action_id, name, model_type, duration, anim_path) VALUES (?, ?, ?, ?, ?)",
                    row
                )
            conn.commit()

    # --- Scene Operations ---
    def save_scene(self, scene_id: str, name: str, pcd_path: str = "",
                   init_points_json: str = "[]", bgm_path: str = "") -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO scenes (scene_id, name, pcd_path, init_points_json, bgm_path, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (scene_id, name, pcd_path, init_points_json, bgm_path, time.time())
            )
            conn.commit()

    def get_scene(self, scene_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM scenes WHERE scene_id = ?", (scene_id,)).fetchone()
            return dict(row) if row else None

    def list_scenes(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM scenes ORDER BY updated_at DESC")]

    # --- Trajectory Operations ---
    def save_trajectory(
        self,
        traj_id: str,
        robot_group: str,
        name: str,
        waypoints_json: str,
        duration: float,
        allow_overwrite_referenced: bool = False
    ) -> None:
        """保存旧版轨迹记录，严格执行与 TrajectoryAsset 一致的引用保护与原子写入"""
        TrajectorySqliteAdapter.save_legacy(
            self,
            traj_id=traj_id,
            robot_group=robot_group,
            name=name,
            waypoints_json=waypoints_json,
            duration=duration,
            allow_overwrite_referenced=allow_overwrite_referenced
        )

    def get_trajectory(self, traj_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM trajectories WHERE traj_id = ?", (traj_id,)).fetchone()
            return dict(row) if row else None

    def list_trajectories(self, robot_group: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            if robot_group:
                rows = conn.execute("SELECT * FROM trajectories WHERE robot_group = ? ORDER BY created_at ASC", (robot_group,))
            else:
                rows = conn.execute("SELECT * FROM trajectories ORDER BY created_at ASC")
            return [dict(r) for r in rows]

    def delete_trajectory(self, traj_id: str) -> bool:
        with self.get_connection() as conn:
            cur = conn.execute("DELETE FROM trajectories WHERE traj_id = ?", (traj_id,))
            conn.commit()
            return cur.rowcount > 0

    # --- TrajectoryAsset Operations ---
    def save_trajectory_asset(self, asset: TrajectoryAsset, robot_group: str = "Robot_1",
                              allow_overwrite_referenced: bool = False) -> None:
        TrajectorySqliteAdapter.save_asset(self, asset, robot_group, allow_overwrite_referenced=allow_overwrite_referenced)

    def load_trajectory_asset(self, trajectory_id: str) -> Optional[TrajectoryAsset]:
        return TrajectorySqliteAdapter.load_asset(self, trajectory_id)

    def list_trajectory_assets(self, robot_group: Optional[str] = None) -> List[TrajectoryAsset]:
        return TrajectorySqliteAdapter.list_assets(self, robot_group)

    def delete_trajectory_asset(self, trajectory_id: str) -> bool:
        return TrajectorySqliteAdapter.delete_asset(self, trajectory_id)

    # --- Action Operations ---
    def save_action(self, action_id: str, name: str, duration: float,
                    model_type: str = "A2-W", anim_path: str = "") -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO actions (action_id, name, model_type, duration, anim_path)
                VALUES (?, ?, ?, ?, ?)
                """,
                (action_id, name, model_type, duration, anim_path)
            )
            conn.commit()

    def get_action(self, action_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM actions WHERE action_id = ?", (action_id,)).fetchone()
            return dict(row) if row else None

    def list_actions(self, search: str = "", model_type: str = "") -> List[Dict[str, Any]]:
        query = "SELECT * FROM actions WHERE 1=1"
        params: List[Any] = []
        if search:
            query += " AND (name LIKE ? OR action_id LIKE ?)"
            pat = f"%{search}%"
            params.extend([pat, pat])
        if model_type and model_type != "全部型号":
            query += " AND model_type = ?"
            params.append(model_type)
        query += " ORDER BY action_id ASC"
        with self.get_connection() as conn:
            return [dict(r) for r in conn.execute(query, params)]

    # --- Timeline Clips Operations ---
    def save_clip(self, clip_id: str, robot_id: str, track_layer: str, ref_id: str,
                  start_ms: int, duration_ms: int, task_name: str = "默认任务1") -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO timeline_clips
                (clip_id, task_name, robot_id, track_layer, ref_id, start_ms, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (clip_id, task_name, str(robot_id), track_layer, ref_id, start_ms, duration_ms)
            )
            conn.commit()

    def list_clips(self, task_name: str = "默认任务1", robot_id: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM timeline_clips WHERE task_name = ?"
        params: List[Any] = [task_name]
        if robot_id:
            query += " AND robot_id = ?"
            params.append(str(robot_id))
        query += " ORDER BY start_ms ASC"
        with self.get_connection() as conn:
            return [dict(r) for r in conn.execute(query, params)]

    def delete_clip(self, clip_id: str) -> bool:
        with self.get_connection() as conn:
            cur = conn.execute("DELETE FROM timeline_clips WHERE clip_id = ?", (clip_id,))
            conn.commit()
            return cur.rowcount > 0

    def clear_clips(self, task_name: str = "默认任务1") -> int:
        with self.get_connection() as conn:
            cur = conn.execute("DELETE FROM timeline_clips WHERE task_name = ?", (task_name,))
            conn.commit()
            return cur.rowcount

