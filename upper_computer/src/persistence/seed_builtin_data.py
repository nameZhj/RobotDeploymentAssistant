# @file: src/persistence/seed_builtin_data.py
# @brief: Bootstraps a clean 0-robot, 0-fake-action studio stage; real actions arrive exclusively via serial sync.
# @exports: ensure_seeded, seed_demo_swarm_preset

from __future__ import annotations

from datetime import datetime
import json

from src.domain.track_entities import default_target_alias, pick_track_color
from src.persistence.db_engine import StudioDatabase


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_seeded(db: StudioDatabase) -> None:
    """Ensure default empty scene exists and purge any legacy unverified built-in demo actions."""
    with db.session() as conn:
        conn.execute("DELETE FROM actions WHERE is_builtin=1 AND sync_status != 'serial'")
        scene_cnt = conn.execute("SELECT COUNT(*) FROM scenes").fetchone()[0]
        if scene_cnt == 0:
            _seed_default_scene(conn)


def _seed_default_scene(conn: object) -> None:
    """Create a clean 0-robot empty stage and active task; users add real robots themselves."""
    now = _now()
    cur = conn.execute(
        """INSERT INTO scenes (name, stage_width, stage_height, safety_margin,
           active_map_id, bpm, time_signature, audio_path, updated_at)
           VALUES (?, 12.0, 8.0, 0.5, NULL, 120.0, '4/4', '', ?)""",
        ("默认舞台", now),
    )
    scene_id = cur.lastrowid
    conn.execute(
        """INSERT INTO tasks (scene_id, name, total_duration, is_active, created_at, updated_at)
           VALUES (?, ?, 30.0, 1, ?, ?)""",
        (scene_id, "主舞台编排", now, now),
    )
    conn.execute(
        """INSERT INTO trajectory_groups (scene_id, name, robot_count, bound_track_no, sort_order)
           VALUES (?, ?, 1, 1, 0)""",
        (scene_id, "默认轨迹分组"),
    )


def seed_demo_swarm_preset(db: StudioDatabase) -> int:
    """Explicitly add a 4-robot demo swarm on demand (never auto-invoked on blank startup)."""
    with db.session() as conn:
        scene = conn.execute("SELECT id FROM scenes ORDER BY id ASC LIMIT 1").fetchone()
        scene_id = int(scene["id"]) if scene else 1
        task = conn.execute(
            "SELECT id FROM tasks WHERE scene_id=? AND is_active=1 ORDER BY id ASC LIMIT 1",
            (scene_id,),
        ).fetchone()
        if task is None:
            return 0
        task_id = int(task["id"])
        existing = conn.execute("SELECT track_no FROM tracks WHERE task_id=?", (task_id,)).fetchall()
        used_nos = {int(r["track_no"]) for r in existing}
        init_points = []
        added = 0
        for idx in range(1, 5):
            x = -1.5 + (idx - 1) * 1.0
            y = -2.0
            yaw = 1.5708
            alias = default_target_alias(idx)
            init_points.append({"trackNo": idx, "targetId": alias, "x": x, "y": y, "yaw": yaw})
            if idx in used_nos:
                continue
            conn.execute(
                """INSERT INTO tracks (task_id, track_no, name, target_id, robot_id, robot_ip,
                   robot_model, color_hex, init_x, init_y, init_yaw, muted, locked)
                   VALUES (?, ?, ?, ?, ?, ?, 'G1-29DOF', ?, ?, ?, ?, 0, 0)""",
                (
                    task_id, idx, f"G1-{idx:02d}", alias, f"g1_{idx:02d}",
                    f"192.168.123.{100 + idx}", pick_track_color(idx), x, y, yaw,
                ),
            )
            added += 1
        conn.execute(
            """INSERT INTO init_point_configs (scene_id, name, points_json, is_default)
               VALUES (?, ?, ?, 1)""",
            (scene_id, "示例四机方阵站位", json.dumps(init_points, ensure_ascii=False)),
        )
        return added
