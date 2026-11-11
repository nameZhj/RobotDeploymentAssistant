"""
@file: src/infrastructure/storage/studio_repository.py
@brief: 编排工作室 SQLite 8张关联表事务型仓储服务
@exports: StudioRepository
"""
import contextlib
import os
import sqlite3
from typing import Any, Dict, Generator, List, Optional, Tuple
from src.infrastructure.storage.db_bootstrap import DEFAULT_DB_PATH, init_database


class StudioRepository:
    """8张关联表原子读写仓储，支持轨迹编号铁律与删除防误删引用保护"""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        conn = init_database(self.db_path)
        conn.close()

    @contextlib.contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # --- 1. Scene ---
    def get_scene(self, scene_id: str = "123") -> Optional[Dict[str, Any]]:
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM scenes WHERE scene_id = ?", (scene_id,)).fetchone()
            return dict(row) if row else None

    def update_music(self, scene_id: str, path: str, title: str, dur_s: float) -> None:
        with self.transaction() as conn:
            conn.execute("UPDATE scenes SET music_path=?, music_title=?, music_duration_s=? WHERE scene_id=?", (path, title, dur_s, scene_id))

    # --- 2. Tracks ---
    def get_tracks(self, scene_id: str = "123") -> List[Dict[str, Any]]:
        with self.transaction() as conn:
            rows = conn.execute("SELECT * FROM tracks WHERE scene_id = ? ORDER BY robot_id ASC", (scene_id,)).fetchall()
            return [dict(r) for r in rows]

    def save_track(self, robot_id: int, lora_id: str, sn: str = "", alias: str = "", scene_id: str = "123") -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO tracks (scene_id, robot_id, lora_id, sn, alias) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(scene_id, robot_id) DO UPDATE SET lora_id=excluded.lora_id, sn=excluded.sn, alias=excluded.alias",
                (scene_id, robot_id, lora_id.strip().upper(), sn, alias)
            )

    # --- 3. Init Points ---
    def get_init_point_configs(self, scene_id: str = "123", cfg_id: Optional[int] = None) -> List[Dict[str, Any]]:
        with self.transaction() as conn:
            q = "SELECT * FROM init_points WHERE scene_id = ?"
            params: List[Any] = [scene_id]
            if cfg_id is not None:
                q += " AND cfg_id = ?"
                params.append(cfg_id)
            q += " ORDER BY robot_id ASC"
            return [dict(r) for r in conn.execute(q, params).fetchall()]

    def save_init_points(self, scene_id: str, cfg_id: int, points: List[Dict[str, Any]]) -> None:
        with self.transaction() as conn:
            for p in points:
                conn.execute(
                    "INSERT INTO init_points (scene_id, cfg_id, robot_id, x, y, yaw, robot_alias, model_type) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(scene_id, cfg_id, robot_id) DO UPDATE SET "
                    "x=excluded.x, y=excluded.y, yaw=excluded.yaw, robot_alias=excluded.robot_alias, model_type=excluded.model_type",
                    (scene_id, cfg_id, int(p["robot_id"]), float(p.get("x", 0.0)), float(p.get("y", 0.0)),
                     float(p.get("yaw", 0.0)), p.get("robot_alias", ""), p.get("model_type", "A2-W"))
                )

    # --- 4. Actions ---
    def search_actions(self, keyword: str = "") -> List[Dict[str, Any]]:
        with self.transaction() as conn:
            q = "SELECT * FROM actions WHERE 1=1"
            params: List[Any] = []
            if keyword:
                q += " AND (CAST(no AS TEXT) LIKE ? OR name LIKE ? OR lora_alias LIKE ?)"
                kw = f"%{keyword}%"
                params.extend([kw, kw, kw])
            q += " ORDER BY no ASC"
            return [dict(r) for r in conn.execute(q, params).fetchall()]

    def save_action(self, act: Dict[str, Any], scene_id: str = "123") -> int:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO actions (scene_id, no, name, lora_alias, key_combo, type, time, transition, allow_stretch, allow_move) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(no) DO UPDATE SET name=excluded.name, "
                "lora_alias=excluded.lora_alias, key_combo=excluded.key_combo, time=excluded.time, transition=excluded.transition",
                (scene_id, act["no"], act["name"], act.get("lora_alias", ""), act.get("key_combo", ""),
                 act.get("type", "dance"), float(act.get("time", 6.0)), float(act.get("transition", 0.0)),
                 int(act.get("allow_stretch", 0)), int(act.get("allow_move", 0)))
            )
            return act["no"]

    # --- 5 & 6. Trajectory Groups & Trajectories ---
    def get_trajectory_groups(self, scene_id: str = "123") -> List[Dict[str, Any]]:
        with self.transaction() as conn:
            rows = conn.execute("SELECT * FROM trajectory_groups WHERE scene_id = ? ORDER BY id ASC", (scene_id,)).fetchall()
            return [dict(r) for r in rows]

    def create_trajectory_group(self, name: str, track_id: int = 1, scene_id: str = "123") -> int:
        with self.transaction() as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO trajectory_groups (scene_id, name, track_id) VALUES (?, ?, ?)", (scene_id, name, track_id))
            return cur.lastrowid

    def create_trajectory(
        self,
        group_id: int,
        name: str,
        point_data: str,
        time_dur: float = 3.0,
        interp_mode: str = "uniform",
        max_acc: float = 1.5,
        hold_dir: int = 0,
        hold_yaw: float = 0.0,
        end_turn: int = 0,
        end_yaw: float = 0.0,
        scene_id: str = "123"
    ) -> Dict[str, Any]:
        with self.transaction() as conn:
            grp = conn.execute("SELECT track_id FROM trajectory_groups WHERE id = ?", (group_id,)).fetchone()
            track_id = int(grp["track_id"]) if grp and grp["track_id"] is not None else 1
            base_no = track_id * 100000
            cur = conn.cursor()
            cur.execute("SELECT MAX(no) FROM trajectories WHERE no >= ? AND no < ?", (base_no, base_no + 100000))
            row = cur.fetchone()
            curr_max = row[0] if (row and row[0] is not None) else base_no
            new_no = curr_max + 1

            conn.execute(
                "INSERT INTO trajectories (no, scene_id, group_id, name, time, trajectory_point_data, "
                "interpolation_mode, max_acc, hold_direction, hold_direction_yaw, end_turn, end_turn_yaw) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (new_no, scene_id, group_id, name, float(time_dur), point_data.strip(), interp_mode,
                 float(max_acc), int(hold_dir), float(hold_yaw), int(end_turn), float(end_yaw))
            )
            return {
                "no": new_no, "scene_id": scene_id, "group_id": group_id, "name": name,
                "time": time_dur, "trajectory_point_data": point_data.strip(),
                "interpolation_mode": interp_mode, "max_acc": max_acc,
                "hold_direction": hold_dir, "hold_direction_yaw": hold_yaw,
                "end_turn": end_turn, "end_turn_yaw": end_yaw
            }

    def delete_trajectory(self, traj_no: int, force: bool = False) -> Tuple[bool, int, str]:
        with self.transaction() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM track_state WHERE no = ? AND type = 'trajectory'", (traj_no,))
            ref_count = cur.fetchone()[0]
            if ref_count > 0 and not force:
                return False, ref_count, f"拒绝删除：该轨迹已被 {ref_count} 个时间轴块引用"
            if force and ref_count > 0:
                conn.execute("DELETE FROM track_state WHERE no = ? AND type = 'trajectory'", (traj_no,))
            conn.execute("DELETE FROM trajectories WHERE no = ?", (traj_no,))
            return True, ref_count, "删除成功"

    # --- 7. Track State ---
    def get_track_state(self, scene_id: str = "123", robot_id: Optional[int] = None) -> List[Dict[str, Any]]:
        with self.transaction() as conn:
            q = "SELECT * FROM track_state WHERE scene_id = ?"
            params: List[Any] = [scene_id]
            if robot_id is not None:
                q += " AND robot_id = ?"
                params.append(robot_id)
            q += " ORDER BY robot_id ASC, start_time ASC"
            return [dict(r) for r in conn.execute(q, params).fetchall()]

    def save_track_state_block(self, b: Dict[str, Any], scene_id: str = "123") -> str:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO track_state (id, scene_id, robot_id, group_id, no, type, name, time, start_time, end_time, "
                "allow_stretch, max_acc, hold_direction, hold_direction_yaw, end_turn, end_turn_yaw, interpolation_mode, trajectory_point_data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "start_time=excluded.start_time, end_time=excluded.end_time, time=excluded.time, name=excluded.name",
                (str(b["id"]), scene_id, int(b["robot_id"]), int(b.get("group_id", 0)), int(b["no"]), str(b["type"]),
                 str(b.get("name", "")), float(b.get("time", 0.0)), float(b.get("start_time", 0.0)), float(b.get("end_time", 0.0)),
                 int(b.get("allow_stretch", 0)), float(b.get("max_acc", 1.5)), int(b.get("hold_direction", 0)),
                 float(b.get("hold_direction_yaw", 0.0)), int(b.get("end_turn", 0)), float(b.get("end_turn_yaw", 0.0)),
                 str(b.get("interpolation_mode", "uniform")), str(b.get("trajectory_point_data", "")))
            )
            return str(b["id"])

    # --- 8. Fragments ---
    def get_fragments(self, scene_id: str = "123") -> List[Dict[str, Any]]:
        with self.transaction() as conn:
            rows = conn.execute("SELECT * FROM fragments WHERE scene_id = ? ORDER BY fragment_id ASC", (scene_id,)).fetchall()
            return [dict(r) for r in rows]
