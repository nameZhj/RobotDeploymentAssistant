# @file: src/persistence/trajectory_repo.py
# @brief: SQLite CRUD repository for TrajectoryGroupEntity and TrajectoryEntity with track numbering rules.
# @exports: TrajectoryRepository

from __future__ import annotations

from datetime import datetime
import json
from typing import List, Optional

from src.domain.trajectory_entities import (
    ControlPoint2D,
    TrajectoryEntity,
    TrajectoryGroupEntity,
)
from src.persistence.db_engine import StudioDatabase


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class TrajectoryRepository:
    """Manages trajectory library groups, track bindings, and per-trajectory assets."""

    def __init__(self, db: StudioDatabase) -> None:
        self.db = db

    def list_groups(self, scene_id: int) -> List[TrajectoryGroupEntity]:
        with self.db.session() as conn:
            rows = conn.execute(
                "SELECT * FROM trajectory_groups WHERE scene_id=? ORDER BY sort_order ASC, id ASC",
                (scene_id,),
            ).fetchall()
            return [self._row_to_group(r) for r in rows]

    def upsert_group(self, grp: TrajectoryGroupEntity) -> TrajectoryGroupEntity:
        with self.db.session() as conn:
            if grp.id is None:
                cur = conn.execute(
                    """INSERT INTO trajectory_groups (scene_id, name, robot_count, bound_track_no, sort_order)
                       VALUES (?, ?, ?, ?, ?)""",
                    (grp.scene_id, grp.name, grp.robot_count, grp.bound_track_no, grp.sort_order),
                )
                grp.id = cur.lastrowid
            else:
                conn.execute(
                    """UPDATE trajectory_groups SET name=?, robot_count=?, bound_track_no=?, sort_order=?
                       WHERE id=?""",
                    (grp.name, grp.robot_count, grp.bound_track_no, grp.sort_order, grp.id),
                )
        return grp

    def rename_group(self, group_id: int, new_name: str) -> None:
        with self.db.session() as conn:
            conn.execute("UPDATE trajectory_groups SET name=? WHERE id=?", (new_name, group_id))

    def count_block_references(self, traj_ids: List[int]) -> int:
        if not traj_ids:
            return 0
        placeholders = ",".join("?" for _ in traj_ids)
        with self.db.session() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) FROM track_blocks WHERE block_type='trajectory' AND ref_id IN ({placeholders})",
                tuple(traj_ids),
            ).fetchone()
            return int(row[0]) if row else 0

    def delete_group(self, group_id: int) -> None:
        with self.db.session() as conn:
            rows = conn.execute("SELECT id FROM trajectories WHERE group_id=?", (group_id,)).fetchall()
            for r in rows:
                conn.execute("DELETE FROM track_blocks WHERE block_type='trajectory' AND ref_id=?", (int(r["id"]),))
            conn.execute("DELETE FROM trajectory_groups WHERE id=?", (group_id,))

    def list_trajectories(self, group_id: Optional[int] = None) -> List[TrajectoryEntity]:
        with self.db.session() as conn:
            if group_id is not None:
                rows = conn.execute(
                    "SELECT * FROM trajectories WHERE group_id=? ORDER BY no ASC, id ASC", (group_id,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM trajectories ORDER BY no ASC, id ASC").fetchall()
            return [self._row_to_traj(r) for r in rows]

    def get_trajectory(self, traj_id: int) -> Optional[TrajectoryEntity]:
        with self.db.session() as conn:
            row = conn.execute("SELECT * FROM trajectories WHERE id=?", (traj_id,)).fetchone()
            return self._row_to_traj(row) if row else None

    def next_trajectory_no(self, track_no: int = 1) -> int:
        """Compute stage track-prefixed number (e.g., 100001 for track 1, 200001 for track 2)."""
        base = max(1, track_no) * 100000
        upper = base + 99999
        with self.db.session() as conn:
            row = conn.execute(
                "SELECT MAX(no) FROM trajectories WHERE no >= ? AND no <= ?", (base, upper)
            ).fetchone()
            max_no = row[0] if row and row[0] is not None else base
            return max_no + 1

    def upsert_trajectory(self, traj: TrajectoryEntity) -> TrajectoryEntity:
        traj.updated_at = _now()
        pts_json = json.dumps(
            [{"x": p.x, "y": p.y, "yaw": p.yaw} for p in traj.control_points],
            ensure_ascii=False,
        )
        bound_json = json.dumps([int(x) for x in traj.bound_track_nos])
        with self.db.session() as conn:
            if traj.id is None:
                cur = conn.execute(
                    """INSERT INTO trajectories (group_id, no, name, duration, control_points_json,
                       interpolation_mode, hold_direction, hold_yaw, end_turn, end_yaw,
                       max_acc, run_mode, point_data_csv, visible_on_map, bound_track_nos_json, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        traj.group_id, traj.no, traj.name, traj.duration, pts_json,
                        traj.interpolation_mode, int(traj.hold_direction), traj.hold_yaw,
                        int(traj.end_turn), traj.end_yaw, traj.max_acc, traj.run_mode,
                        traj.point_data_csv, int(traj.visible_on_map), bound_json, traj.updated_at,
                    ),
                )
                traj.id = cur.lastrowid
            else:
                conn.execute(
                    """UPDATE trajectories SET group_id=?, no=?, name=?, duration=?, control_points_json=?,
                       interpolation_mode=?, hold_direction=?, hold_yaw=?, end_turn=?, end_yaw=?,
                       max_acc=?, run_mode=?, point_data_csv=?, visible_on_map=?, bound_track_nos_json=?, updated_at=? WHERE id=?""",
                    (
                        traj.group_id, traj.no, traj.name, traj.duration, pts_json,
                        traj.interpolation_mode, int(traj.hold_direction), traj.hold_yaw,
                        int(traj.end_turn), traj.end_yaw, traj.max_acc, traj.run_mode,
                        traj.point_data_csv, int(traj.visible_on_map), bound_json, traj.updated_at, traj.id,
                    ),
                )
        return traj

    def delete_trajectory(self, traj_id: int) -> None:
        with self.db.session() as conn:
            conn.execute("DELETE FROM track_blocks WHERE block_type='trajectory' AND ref_id=?", (traj_id,))
            conn.execute("DELETE FROM trajectories WHERE id=?", (traj_id,))

    def sort_trajectories_by_track(self, scene_id: int) -> List[TrajectoryGroupEntity]:
        """Sort groups so bound track numbers appear in ascending order."""
        groups = self.list_groups(scene_id)
        groups.sort(key=lambda g: (g.bound_track_no is None, g.bound_track_no or 9999, g.id or 0))
        with self.db.session() as conn:
            for idx, g in enumerate(groups):
                g.sort_order = idx
                conn.execute("UPDATE trajectory_groups SET sort_order=? WHERE id=?", (idx, g.id))
        return groups

    @staticmethod
    def _row_to_group(r: object) -> TrajectoryGroupEntity:
        return TrajectoryGroupEntity(
            id=r["id"], scene_id=r["scene_id"], name=r["name"], robot_count=r["robot_count"],
            bound_track_no=r["bound_track_no"], sort_order=r["sort_order"],
        )

    @staticmethod
    def _row_to_traj(r: object) -> TrajectoryEntity:
        raw_pts = json.loads(r["control_points_json"] or "[]")
        cps = [
            ControlPoint2D(x=float(p.get("x", 0.0)), y=float(p.get("y", 0.0)), yaw=float(p.get("yaw", 0.0)))
            for p in raw_pts
        ]
        keys = r.keys() if hasattr(r, "keys") else ()
        vis = bool(r["visible_on_map"]) if "visible_on_map" in keys else True
        bound_raw = json.loads(r["bound_track_nos_json"] or "[]") if "bound_track_nos_json" in keys else []
        return TrajectoryEntity(
            id=r["id"], group_id=r["group_id"], no=r["no"], name=r["name"], duration=r["duration"],
            control_points=cps, interpolation_mode=r["interpolation_mode"],
            hold_direction=bool(r["hold_direction"]), hold_yaw=r["hold_yaw"],
            end_turn=bool(r["end_turn"]), end_yaw=r["end_yaw"],
            max_acc=r["max_acc"], run_mode=r["run_mode"],
            point_data_csv=r["point_data_csv"],
            visible_on_map=vis,
            bound_track_nos=[int(x) for x in bound_raw],
            updated_at=r["updated_at"],
        )
