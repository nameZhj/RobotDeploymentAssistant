"""
@file: src/infrastructure/storage/choreo_repository.py
@brief: 编排工作室 SQLite 七表仓储实现（场景、轨道、初始化点、轨迹库、时间轴与片段网格）
@exports: ChoreoRepository, choreo_repository
"""
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class ChoreoRepository:
    """提供场景、机群轨道、初始化点、轨迹库、双子层时间轴与 01~99 片段的持久化存取"""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or os.path.join("runtime", "shows", "choreo_studio.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self) -> None:
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS scenes (
                    scene_id TEXT PRIMARY KEY, name TEXT NOT NULL, music_path TEXT DEFAULT '',
                    music_title TEXT DEFAULT '', bpm REAL DEFAULT 120.0, beat_numerator INTEGER DEFAULT 4,
                    beat_denominator INTEGER DEFAULT 4, stage_width REAL DEFAULT 10.0,
                    stage_height REAL DEFAULT 10.0, calibration_matrix TEXT DEFAULT '{}', is_enabled INTEGER DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS tracks (
                    track_id INTEGER PRIMARY KEY, scene_id TEXT NOT NULL, robot_id INTEGER NOT NULL,
                    sn TEXT DEFAULT '', alias TEXT DEFAULT '', lora_id TEXT DEFAULT 'A', model_type TEXT DEFAULT 'g1_29dof'
                );
                CREATE TABLE IF NOT EXISTS init_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, scene_id TEXT NOT NULL, group_id INTEGER NOT NULL,
                    group_name TEXT DEFAULT '', robot_id INTEGER NOT NULL, x REAL DEFAULT 0.0, y REAL DEFAULT 0.0, yaw REAL DEFAULT 0.0
                );
                CREATE TABLE IF NOT EXISTS trajectory_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, scene_id TEXT NOT NULL, name TEXT NOT NULL, track_id INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS trajectories (
                    no INTEGER PRIMARY KEY, name TEXT NOT NULL, group_id INTEGER NOT NULL, time REAL DEFAULT 2.0,
                    max_acc REAL DEFAULT 1.0, allow_stretch INTEGER DEFAULT 0, hold_direction INTEGER DEFAULT 0,
                    hold_direction_yaw REAL DEFAULT 0.0, end_turn INTEGER DEFAULT 0, end_turn_yaw REAL DEFAULT 0.0,
                    interpolation_mode TEXT DEFAULT 'catmull_rom', trajectory_point_data TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS track_state (
                    block_id TEXT PRIMARY KEY, scene_id TEXT NOT NULL, robot_id INTEGER NOT NULL, type TEXT NOT NULL,
                    no INTEGER NOT NULL, start_time REAL NOT NULL, end_time REAL NOT NULL, time REAL NOT NULL,
                    ignored INTEGER DEFAULT 0, dirty INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS fragments (
                    frag_no INTEGER PRIMARY KEY, name TEXT NOT NULL, blocks_json TEXT NOT NULL, updated_at REAL NOT NULL
                );
            """)

    def upsert_scene(self, scene: Dict[str, Any]) -> None:
        sid = str(scene.get("scene_id", "scene_1"))
        mat = scene.get("calibration_matrix", {})
        mat_s = json.dumps(mat) if isinstance(mat, dict) else str(mat)
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO scenes (scene_id, name, music_path, music_title, bpm, beat_numerator,
                    beat_denominator, stage_width, stage_height, calibration_matrix, is_enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scene_id) DO UPDATE SET
                    name=excluded.name, music_path=excluded.music_path, music_title=excluded.music_title,
                    bpm=excluded.bpm, beat_numerator=excluded.beat_numerator, beat_denominator=excluded.beat_denominator,
                    stage_width=excluded.stage_width, stage_height=excluded.stage_height,
                    calibration_matrix=excluded.calibration_matrix, is_enabled=excluded.is_enabled;
            """, (sid, scene.get("name", "默认舞台"), scene.get("music_path", ""), scene.get("music_title", ""),
                  float(scene.get("bpm", 120.0)), int(scene.get("beat_numerator", 4)), int(scene.get("beat_denominator", 4)),
                  float(scene.get("stage_width", 10.0)), float(scene.get("stage_height", 10.0)), mat_s, int(scene.get("is_enabled", 1))))

    def get_scene(self, scene_id: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM scenes WHERE scene_id = ?", (scene_id,)).fetchone()
            if not row:
                return None
            res = dict(row)
            try:
                res["calibration_matrix"] = json.loads(res.get("calibration_matrix") or "{}")
            except Exception:
                res["calibration_matrix"] = {}
            return res

    def save_tracks(self, scene_id: str, tracks: List[Dict[str, Any]]) -> None:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM tracks WHERE scene_id = ?", (scene_id,))
            for t in tracks:
                conn.execute("""
                    INSERT INTO tracks (track_id, scene_id, robot_id, sn, alias, lora_id, model_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (int(t.get("track_id", 1)), scene_id, int(t.get("robot_id", 1)), t.get("sn", ""),
                      t.get("alias", f"Robot_{t.get('robot_id', 1)}"), t.get("lora_id", "A"), t.get("model_type", "g1_29dof")))

    def get_tracks(self, scene_id: str) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM tracks WHERE scene_id = ? ORDER BY track_id", (scene_id,)).fetchall()
            return [dict(r) for r in rows]

    def add_trajectory_group(self, scene_id: str, name: str, track_id: int = 0) -> int:
        with self._get_conn() as conn:
            cur = conn.execute("INSERT INTO trajectory_groups (scene_id, name, track_id) VALUES (?, ?, ?)",
                               (scene_id, name, int(track_id)))
            return int(cur.lastrowid)

    def add_trajectory(self, traj: Dict[str, Any]) -> int:
        gid = int(traj.get("group_id", 1))
        with self._get_conn() as conn:
            grp = conn.execute("SELECT track_id FROM trajectory_groups WHERE id = ?", (gid,)).fetchone()
            raw_tid = int(grp["track_id"]) if grp else 0
            tid = max(1, raw_tid)
            traj_no = traj.get("no")
            if traj_no is None:
                base = tid * 100000
                row = conn.execute("SELECT MAX(no) as max_no FROM trajectories WHERE no >= ? AND no < ?",
                                   (base, base + 100000)).fetchone()
                traj_no = (row["max_no"] + 1) if (row and row["max_no"] is not None) else (base + 1)
            conn.execute("""
                INSERT INTO trajectories (no, name, group_id, time, max_acc, allow_stretch,
                    hold_direction, hold_direction_yaw, end_turn, end_turn_yaw, interpolation_mode, trajectory_point_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (int(traj_no), traj.get("name", f"轨迹_{traj_no}"), gid, float(traj.get("time", 2.0)),
                  float(traj.get("max_acc", 1.0)), int(traj.get("allow_stretch", 0)),
                  int(traj.get("hold_direction", 0)), float(traj.get("hold_direction_yaw", 0.0)),
                  int(traj.get("end_turn", 0)), float(traj.get("end_turn_yaw", 0.0)),
                  traj.get("interpolation_mode", "catmull_rom"), traj.get("trajectory_point_data", "")))
            return int(traj_no)

    def delete_trajectory(self, traj_id: int, force: bool = False) -> Tuple[bool, int, str]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM track_state WHERE type = 'trajectory' AND no = ?",
                               (int(traj_id),)).fetchone()
            ref_cnt = int(row["cnt"]) if row else 0
            if ref_cnt > 0 and not force:
                return False, ref_cnt, f"轨迹 {traj_id} 被 {ref_cnt} 个时间轴块引用，受保护禁止删除"
            if ref_cnt > 0 and force:
                conn.execute("DELETE FROM track_state WHERE type = 'trajectory' AND no = ?", (int(traj_id),))
            conn.execute("DELETE FROM trajectories WHERE no = ?", (int(traj_id),))
            msg = f"已强制删除轨迹 {traj_id} 并清理 {ref_cnt} 个引用" if force else f"轨迹 {traj_id} 删除成功"
            return True, ref_cnt, msg

    def save_track_state(self, scene_id: str, blocks: List[Dict[str, Any]]) -> None:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM track_state WHERE scene_id = ?", (scene_id,))
            for b in blocks:
                bid = str(b.get("block_id") or f"{b.get('type')}_{b.get('robot_id')}_{b.get('no')}_{b.get('start_time')}")
                conn.execute("""
                    INSERT INTO track_state (block_id, scene_id, robot_id, type, no, start_time, end_time, time, ignored, dirty)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (bid, scene_id, int(b.get("robot_id", 1)), str(b.get("type", "active")),
                      int(b.get("no", 0)), float(b.get("start_time", 0.0)), float(b.get("end_time", 0.0)),
                      float(b.get("time", 0.0)), int(b.get("ignored", 0)), int(b.get("dirty", 0))))

    def get_track_state(self, scene_id: str, robot_id: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            if robot_id is not None:
                rows = conn.execute("SELECT * FROM track_state WHERE scene_id = ? AND robot_id = ? ORDER BY start_time",
                                    (scene_id, int(robot_id))).fetchall()
            else:
                rows = conn.execute("SELECT * FROM track_state WHERE scene_id = ? ORDER BY robot_id, start_time",
                                    (scene_id,)).fetchall()
            return [dict(r) for r in rows]

    def save_fragment(self, frag_no: int, name: str, blocks: List[Dict[str, Any]]) -> bool:
        if not (1 <= int(frag_no) <= 99):
            raise ValueError(f"片段编号必须在 01~99 范围内: {frag_no}")
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO fragments (frag_no, name, blocks_json, updated_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(frag_no) DO UPDATE SET name=excluded.name, blocks_json=excluded.blocks_json, updated_at=excluded.updated_at
            """, (int(frag_no), name, json.dumps(blocks, ensure_ascii=False), time.time()))
            return True

    def get_fragment(self, frag_no: int) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM fragments WHERE frag_no = ?", (int(frag_no),)).fetchone()
            if not row:
                return None
            res = dict(row)
            res["blocks"] = json.loads(res.get("blocks_json") or "[]")
            return res


choreo_repository = ChoreoRepository()

