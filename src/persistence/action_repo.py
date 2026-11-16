# @file: src/persistence/action_repo.py
# @brief: SQLite repository managing built-in LRMP 33 official dances and custom imported actions.
# @exports: ActionRepository

from __future__ import annotations

from typing import List, Optional

from src.domain.action_entities import ActionEntity
from src.persistence.db_engine import StudioDatabase


class ActionRepository:
    """Provides searchable and filterable CRUD operations on choreography ActionEntity records."""

    def __init__(self, db: StudioDatabase) -> None:
        self.db = db

    def list_actions(self, keyword: str = "", robot_model: str = "ALL") -> List[ActionEntity]:
        sql = "SELECT * FROM actions WHERE 1=1"
        params: List[object] = []
        if keyword.strip():
            kw = f"%{keyword.strip()}%"
            sql += " AND (name LIKE ? OR lrmp_code LIKE ? OR CAST(no AS TEXT) LIKE ?)"
            params.extend([kw, kw, kw])
        if robot_model and robot_model != "ALL":
            sql += " AND robot_model = ?"
            params.append(robot_model)
        sql += " ORDER BY no ASC, id ASC"
        with self.db.session() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [self._row_to_action(r) for r in rows]

    def get_action(self, action_id: int) -> Optional[ActionEntity]:
        with self.db.session() as conn:
            row = conn.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()
            return self._row_to_action(row) if row else None

    def find_by_code_or_no(self, code_or_no: str) -> Optional[ActionEntity]:
        with self.db.session() as conn:
            row = conn.execute(
                "SELECT * FROM actions WHERE lrmp_code=? OR CAST(no AS TEXT)=? LIMIT 1",
                (code_or_no, code_or_no),
            ).fetchone()
            return self._row_to_action(row) if row else None

    def upsert_action(self, action: ActionEntity) -> ActionEntity:
        with self.db.session() as conn:
            if action.id is None:
                cur = conn.execute(
                    """INSERT INTO actions (no, name, category, lrmp_code, robot_model, duration,
                       motion_file_path, is_builtin, sync_status, allow_move, allow_stretch)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        action.no, action.name, action.category, action.lrmp_code,
                        action.robot_model, action.duration, action.motion_file_path,
                        int(action.is_builtin), action.sync_status,
                        int(action.allow_move), int(action.allow_stretch),
                    ),
                )
                action.id = cur.lastrowid
            else:
                conn.execute(
                    """UPDATE actions SET no=?, name=?, category=?, lrmp_code=?, robot_model=?,
                       duration=?, motion_file_path=?, is_builtin=?, sync_status=?,
                       allow_move=?, allow_stretch=? WHERE id=?""",
                    (
                        action.no, action.name, action.category, action.lrmp_code,
                        action.robot_model, action.duration, action.motion_file_path,
                        int(action.is_builtin), action.sync_status,
                        int(action.allow_move), int(action.allow_stretch), action.id,
                    ),
                )
        return action

    def delete_action(self, action_id: int) -> None:
        with self.db.session() as conn:
            conn.execute("DELETE FROM actions WHERE id=?", (action_id,))

    @staticmethod
    def _row_to_action(r: object) -> ActionEntity:
        return ActionEntity(
            id=r["id"], no=r["no"], name=r["name"], category=r["category"],
            lrmp_code=r["lrmp_code"], robot_model=r["robot_model"], duration=r["duration"],
            motion_file_path=r["motion_file_path"], is_builtin=bool(r["is_builtin"]),
            sync_status=r["sync_status"], allow_move=bool(r["allow_move"]),
            allow_stretch=bool(r["allow_stretch"]),
        )
