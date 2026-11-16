# @file: src/persistence/map_fragment_repo.py
# @brief: SQLite CRUD repository for PcdMapEntity local point-cloud maps and 1..99 timeline fragments.
# @exports: MapFragmentRepository

from __future__ import annotations

from datetime import datetime
import json
from typing import List, Optional

from src.domain.map_entities import PcdMapEntity
from src.domain.timeline_entities import TimelineFragmentEntity
from src.persistence.db_engine import StudioDatabase


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class MapFragmentRepository:
    """Manages local PCD map assets and numbered quick choreography fragments."""

    def __init__(self, db: StudioDatabase) -> None:
        self.db = db

    def list_maps(self) -> List[PcdMapEntity]:
        with self.db.session() as conn:
            rows = conn.execute("SELECT * FROM pcd_maps ORDER BY id DESC").fetchall()
            return [self._row_to_map(r) for r in rows]

    def get_map(self, map_id: int) -> Optional[PcdMapEntity]:
        with self.db.session() as conn:
            row = conn.execute("SELECT * FROM pcd_maps WHERE id=?", (map_id,)).fetchone()
            return self._row_to_map(row) if row else None

    def upsert_map(self, pcd: PcdMapEntity) -> PcdMapEntity:
        bbox_str = json.dumps(pcd.bbox, ensure_ascii=False)
        calib_str = json.dumps(pcd.calib_matrix, ensure_ascii=False)
        with self.db.session() as conn:
            if pcd.id is None:
                cur = conn.execute(
                    """INSERT INTO pcd_maps (name, file_path, file_size, point_count, bbox_json,
                       grid_png_path, resolution, origin_x, origin_y, calib_matrix_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        pcd.name, pcd.file_path, pcd.file_size, pcd.point_count, bbox_str,
                        pcd.grid_png_path, pcd.resolution, pcd.origin_x, pcd.origin_y,
                        calib_str, pcd.created_at or _now(),
                    ),
                )
                pcd.id = cur.lastrowid
            else:
                conn.execute(
                    """UPDATE pcd_maps SET name=?, file_path=?, file_size=?, point_count=?, bbox_json=?,
                       grid_png_path=?, resolution=?, origin_x=?, origin_y=?, calib_matrix_json=? WHERE id=?""",
                    (
                        pcd.name, pcd.file_path, pcd.file_size, pcd.point_count, bbox_str,
                        pcd.grid_png_path, pcd.resolution, pcd.origin_x, pcd.origin_y,
                        calib_str, pcd.id,
                    ),
                )
        return pcd

    def delete_map(self, map_id: int, record_ignored_path: bool = True) -> Optional[str]:
        """Delete PCD map record and return its file_path; records path to prevent auto-rescan."""
        deleted_path: Optional[str] = None
        with self.db.session() as conn:
            row = conn.execute("SELECT file_path FROM pcd_maps WHERE id=?", (map_id,)).fetchone()
            if row:
                deleted_path = str(row["file_path"])
                if record_ignored_path and deleted_path:
                    meta_row = conn.execute("SELECT value FROM schema_meta WHERE key='deleted_map_paths'").fetchone()
                    items = set(json.loads(meta_row["value"]) if meta_row else [])
                    items.add(deleted_path)
                    conn.execute(
                        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('deleted_map_paths', ?)",
                        (json.dumps(sorted(items), ensure_ascii=False),),
                    )
            conn.execute("UPDATE scenes SET active_map_id=NULL WHERE active_map_id=?", (map_id,))
            conn.execute("DELETE FROM pcd_maps WHERE id=?", (map_id,))
        return deleted_path

    def list_deleted_map_paths(self) -> set[str]:
        with self.db.session() as conn:
            row = conn.execute("SELECT value FROM schema_meta WHERE key='deleted_map_paths'").fetchone()
            return set(json.loads(row["value"]) if row else [])

    def unmark_deleted_map_path(self, file_path: str) -> None:
        with self.db.session() as conn:
            row = conn.execute("SELECT value FROM schema_meta WHERE key='deleted_map_paths'").fetchone()
            if not row:
                return
            items = set(json.loads(row["value"]))
            items.discard(file_path)
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('deleted_map_paths', ?)",
                (json.dumps(sorted(items), ensure_ascii=False),),
            )

    def list_fragments(self, scene_id: int) -> List[TimelineFragmentEntity]:
        with self.db.session() as conn:
            rows = conn.execute(
                "SELECT * FROM fragments WHERE scene_id=? ORDER BY slot_no ASC", (scene_id,)
            ).fetchall()
            return [self._row_to_fragment(r) for r in rows]

    def save_fragment(self, frag: TimelineFragmentEntity) -> TimelineFragmentEntity:
        payload_str = json.dumps(frag.payload, ensure_ascii=False)
        with self.db.session() as conn:
            conn.execute(
                "DELETE FROM fragments WHERE scene_id=? AND slot_no=?", (frag.scene_id, frag.slot_no)
            )
            cur = conn.execute(
                """INSERT INTO fragments (scene_id, slot_no, name, duration, payload_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (frag.scene_id, frag.slot_no, frag.name, frag.duration, payload_str, _now()),
            )
            frag.id = cur.lastrowid
        return frag

    def delete_fragment(self, fragment_id: int) -> None:
        with self.db.session() as conn:
            conn.execute("DELETE FROM fragments WHERE id=?", (fragment_id,))

    @staticmethod
    def _row_to_map(r: object) -> PcdMapEntity:
        return PcdMapEntity(
            id=r["id"], name=r["name"], file_path=r["file_path"], file_size=r["file_size"],
            point_count=r["point_count"], bbox=json.loads(r["bbox_json"] or "{}"),
            grid_png_path=r["grid_png_path"], resolution=r["resolution"],
            origin_x=r["origin_x"], origin_y=r["origin_y"],
            calib_matrix=json.loads(r["calib_matrix_json"] or "{}"), created_at=r["created_at"],
        )

    @staticmethod
    def _row_to_fragment(r: object) -> TimelineFragmentEntity:
        return TimelineFragmentEntity(
            id=r["id"], scene_id=r["scene_id"], slot_no=r["slot_no"], name=r["name"],
            duration=r["duration"], payload=json.loads(r["payload_json"] or "{}"),
            created_at=r["created_at"],
        )
