# @file: src/persistence/scene_task_repo.py
# @brief: SQLite CRUD repository for SceneEntity, TaskEntity, TrackEntity, TimelineBlockEntity, and InitPointConfig.
# @exports: SceneTaskRepository

from __future__ import annotations

from datetime import datetime
import json
from typing import List

from src.domain.scene_entities import SceneEntity, TaskEntity
from src.domain.timeline_entities import TimelineBlockEntity
from src.domain.track_entities import InitPointConfig, InitPointItem, TrackEntity
from src.persistence.db_engine import StudioDatabase


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class SceneTaskRepository:
    """Persistence adapter managing scenes, tasks, robot tracks, blocks, and init points."""

    def __init__(self, db: StudioDatabase) -> None:
        self.db = db

    def get_active_scene(self) -> SceneEntity:
        with self.db.session() as conn:
            row = conn.execute("SELECT * FROM scenes ORDER BY id ASC LIMIT 1").fetchone()
            if row is None:
                raise RuntimeError("No scene initialized in database")
            return self._row_to_scene(row)

    def update_scene(self, scene: SceneEntity) -> SceneEntity:
        scene.updated_at = _now()
        with self.db.session() as conn:
            conn.execute(
                """UPDATE scenes SET name=?, stage_width=?, stage_height=?, safety_margin=?,
                   active_map_id=?, bpm=?, time_signature=?, audio_path=?, updated_at=? WHERE id=?""",
                (
                    scene.name, scene.stage_width, scene.stage_height, scene.safety_margin,
                    scene.active_map_id, scene.bpm, scene.time_signature, scene.audio_path,
                    scene.updated_at, scene.id,
                ),
            )
        return scene

    def list_tasks(self, scene_id: int) -> List[TaskEntity]:
        with self.db.session() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE scene_id=? ORDER BY id ASC", (scene_id,)
            ).fetchall()
            return [self._row_to_task(r) for r in rows]

    def get_active_task(self, scene_id: int) -> TaskEntity:
        with self.db.session() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE scene_id=? AND is_active=1 ORDER BY id ASC LIMIT 1",
                (scene_id,),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    "SELECT * FROM tasks WHERE scene_id=? ORDER BY id ASC LIMIT 1", (scene_id,)
                ).fetchone()
            return self._row_to_task(row)

    def create_task(self, task: TaskEntity, set_active: bool = True) -> TaskEntity:
        now = _now()
        with self.db.session() as conn:
            if set_active:
                conn.execute("UPDATE tasks SET is_active=0 WHERE scene_id=?", (task.scene_id,))
            cur = conn.execute(
                """INSERT INTO tasks (scene_id, name, total_duration, is_active, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (task.scene_id, task.name, task.total_duration, int(set_active), now, now),
            )
            task.id = cur.lastrowid
            task.is_active = set_active
        return task

    def switch_active_task(self, scene_id: int, task_id: int) -> TaskEntity:
        with self.db.session() as conn:
            conn.execute("UPDATE tasks SET is_active=0 WHERE scene_id=?", (scene_id,))
            conn.execute("UPDATE tasks SET is_active=1 WHERE id=?", (task_id,))
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            return self._row_to_task(row)

    def delete_task(self, task_id: int) -> None:
        with self.db.session() as conn:
            conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    def list_tracks(self, task_id: int) -> List[TrackEntity]:
        with self.db.session() as conn:
            rows = conn.execute(
                "SELECT * FROM tracks WHERE task_id=? ORDER BY track_no ASC, id ASC", (task_id,)
            ).fetchall()
            return [self._row_to_track(r) for r in rows]

    def upsert_track(self, track: TrackEntity) -> TrackEntity:
        with self.db.session() as conn:
            if track.id is None:
                cur = conn.execute(
                    """INSERT INTO tracks (task_id, track_no, name, target_id, robot_id, robot_ip,
                       robot_model, color_hex, init_x, init_y, init_yaw, muted, locked)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        track.task_id, track.track_no, track.name, track.target_id, track.robot_id,
                        track.robot_ip, track.robot_model, track.color_hex,
                        track.init_x, track.init_y, track.init_yaw,
                        int(track.muted), int(track.locked),
                    ),
                )
                track.id = cur.lastrowid
            else:
                conn.execute(
                    """UPDATE tracks SET track_no=?, name=?, target_id=?, robot_id=?, robot_ip=?,
                       robot_model=?, color_hex=?, init_x=?, init_y=?, init_yaw=?, muted=?, locked=? WHERE id=?""",
                    (
                        track.track_no, track.name, track.target_id, track.robot_id, track.robot_ip,
                        track.robot_model, track.color_hex, track.init_x, track.init_y, track.init_yaw,
                        int(track.muted), int(track.locked), track.id,
                    ),
                )
        return track

    def delete_track(self, track_id: int) -> None:
        with self.db.session() as conn:
            conn.execute("DELETE FROM track_blocks WHERE track_id=?", (track_id,))
            conn.execute("DELETE FROM tracks WHERE id=?", (track_id,))

    def rename_task(self, task_id: int, new_name: str) -> None:
        with self.db.session() as conn:
            conn.execute("UPDATE tasks SET name=?, updated_at=? WHERE id=?", (new_name, _now(), task_id))

    def clear_task_tracks_and_blocks(self, task_id: int) -> None:
        with self.db.session() as conn:
            conn.execute("DELETE FROM track_blocks WHERE task_id=?", (task_id,))
            conn.execute("DELETE FROM tracks WHERE task_id=?", (task_id,))

    def list_blocks(self, task_id: int) -> List[TimelineBlockEntity]:
        with self.db.session() as conn:
            rows = conn.execute(
                "SELECT * FROM track_blocks WHERE task_id=? ORDER BY start_time ASC, id ASC", (task_id,)
            ).fetchall()
            return [self._row_to_block(r) for r in rows]

    def upsert_block(self, blk: TimelineBlockEntity) -> TimelineBlockEntity:
        extra_str = json.dumps(blk.extra, ensure_ascii=False)
        with self.db.session() as conn:
            if blk.id is None:
                cur = conn.execute(
                    """INSERT INTO track_blocks (task_id, track_id, block_type, ref_id, code_no,
                       title, start_time, duration, is_ignored, extra_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        blk.task_id, blk.track_id, blk.block_type, blk.ref_id, blk.code_no,
                        blk.title, blk.start_time, blk.duration, int(blk.is_ignored), extra_str,
                    ),
                )
                blk.id = cur.lastrowid
            else:
                conn.execute(
                    """UPDATE track_blocks SET track_id=?, block_type=?, ref_id=?, code_no=?,
                       title=?, start_time=?, duration=?, is_ignored=?, extra_json=? WHERE id=?""",
                    (
                        blk.track_id, blk.block_type, blk.ref_id, blk.code_no, blk.title,
                        blk.start_time, blk.duration, int(blk.is_ignored), extra_str, blk.id,
                    ),
                )
        return blk

    def delete_block(self, block_id: int) -> None:
        with self.db.session() as conn:
            conn.execute("DELETE FROM track_blocks WHERE id=?", (block_id,))

    def list_init_configs(self, scene_id: int) -> List[InitPointConfig]:
        with self.db.session() as conn:
            rows = conn.execute(
                "SELECT * FROM init_point_configs WHERE scene_id=? ORDER BY id ASC", (scene_id,)
            ).fetchall()
            return [self._row_to_init_cfg(r) for r in rows]

    def save_init_config(self, cfg: InitPointConfig) -> InitPointConfig:
        pts_json = json.dumps(
            [{"trackNo": p.track_no, "targetId": p.target_id, "x": p.x, "y": p.y, "yaw": p.yaw} for p in cfg.points],
            ensure_ascii=False,
        )
        with self.db.session() as conn:
            if cfg.is_default:
                conn.execute("UPDATE init_point_configs SET is_default=0 WHERE scene_id=?", (cfg.scene_id,))
            if cfg.id is None:
                cur = conn.execute(
                    "INSERT INTO init_point_configs (scene_id, name, points_json, is_default) VALUES (?, ?, ?, ?)",
                    (cfg.scene_id, cfg.name, pts_json, int(cfg.is_default)),
                )
                cfg.id = cur.lastrowid
            else:
                conn.execute(
                    "UPDATE init_point_configs SET name=?, points_json=?, is_default=? WHERE id=?",
                    (cfg.name, pts_json, int(cfg.is_default), cfg.id),
                )
        return cfg

    def delete_init_config(self, config_id: int) -> None:
        with self.db.session() as conn:
            conn.execute("DELETE FROM init_point_configs WHERE id=?", (config_id,))

    @staticmethod
    def _row_to_scene(r: object) -> SceneEntity:
        return SceneEntity(
            id=r["id"], name=r["name"], stage_width=r["stage_width"], stage_height=r["stage_height"],
            safety_margin=r["safety_margin"], active_map_id=r["active_map_id"],
            bpm=r["bpm"], time_signature=r["time_signature"], audio_path=r["audio_path"],
            updated_at=r["updated_at"],
        )

    @staticmethod
    def _row_to_task(r: object) -> TaskEntity:
        return TaskEntity(
            id=r["id"], scene_id=r["scene_id"], name=r["name"], total_duration=r["total_duration"],
            is_active=bool(r["is_active"]), created_at=r["created_at"], updated_at=r["updated_at"],
        )

    @staticmethod
    def _row_to_track(r: object) -> TrackEntity:
        return TrackEntity(
            id=r["id"], task_id=r["task_id"], track_no=r["track_no"], name=r["name"],
            target_id=r["target_id"], robot_id=r["robot_id"], robot_ip=r["robot_ip"],
            robot_model=r["robot_model"], color_hex=r["color_hex"], init_x=r["init_x"],
            init_y=r["init_y"], init_yaw=r["init_yaw"], muted=bool(r["muted"]), locked=bool(r["locked"]),
        )

    @staticmethod
    def _row_to_block(r: object) -> TimelineBlockEntity:
        return TimelineBlockEntity(
            id=r["id"], task_id=r["task_id"], track_id=r["track_id"], block_type=r["block_type"],
            ref_id=r["ref_id"], code_no=r["code_no"], title=r["title"], start_time=r["start_time"],
            duration=r["duration"], is_ignored=bool(r["is_ignored"]),
            extra=json.loads(r["extra_json"] or "{}"),
        )

    @staticmethod
    def _row_to_init_cfg(r: object) -> InitPointConfig:
        raw_pts = json.loads(r["points_json"] or "[]")
        items = [
            InitPointItem(
                track_no=int(p.get("trackNo", 1)), target_id=str(p.get("targetId", "A")),
                x=float(p.get("x", 0.0)), y=float(p.get("y", 0.0)), yaw=float(p.get("yaw", 0.0)),
            )
            for p in raw_pts
        ]
        return InitPointConfig(
            id=r["id"], scene_id=r["scene_id"], name=r["name"],
            points=items, is_default=bool(r["is_default"]),
        )
