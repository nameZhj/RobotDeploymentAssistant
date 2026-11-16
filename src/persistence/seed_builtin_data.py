# @file: src/persistence/seed_builtin_data.py
# @brief: Seeds LRMP 33 official dances and a clean 0-robot empty stage, plus an explicit on-demand demo loader.
# @exports: ensure_seeded, seed_demo_swarm_preset

from __future__ import annotations

from datetime import datetime
import json

from backend.serial_dance_parser import DEFAULT_DANCE_GROUPS
from src.core.paths import get_paths
from src.domain.track_entities import default_target_alias, pick_track_color
from src.persistence.db_engine import StudioDatabase

_ACTION_DURATION_MAP = {
    "G1_TURN_JUMP": 12.0,
    "G1_TIKTOK": 18.0,
    "G1_TAIJI": 24.0,
    "G1_CXK": 16.0,
    "G2_MOONWALK": 14.0,
    "G3_KUNGFU": 20.0,
    "G3_DANCE1_S2": 15.0,
}

_PREVIEW_NPZ_MAP = {
    "G3_KUNGFU": "preview/G1_KUNG_FU.npz",
    "G2_MOONWALK": "preview/G1_MOONWALK.npz",
    "G1_TIKTOK": "preview/G1_TIKTOK.npz",
    "G1_TURN_JUMP": "preview/G1_TURN_JUMP.npz",
    "G2_WAVE": "preview/G2_WAVE.npz",
    "G3_CYBER": "preview/G3_CYBER.npz",
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_seeded(db: StudioDatabase) -> None:
    """Populate built-in actions and default scene/tracks if empty."""
    with db.session() as conn:
        action_cnt = conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
        if action_cnt == 0:
            _seed_actions(conn)

        scene_cnt = conn.execute("SELECT COUNT(*) FROM scenes").fetchone()[0]
        if scene_cnt == 0:
            _seed_default_scene(conn)


def _seed_actions(conn: object) -> None:
    paths = get_paths()
    default_csv = str(paths.g1_dance_csv) if paths.g1_dance_csv.exists() else ""

    basic_actions = [
        (100001, "站立就绪", "BASIC", "STAND", "G1", 3.0, "", 1),
        (100002, "步态激活", "BASIC", "GAIT", "G1", 2.0, "", 1),
        (100003, "阻尼卸力", "BASIC", "PASSIVE", "G1", 2.0, "", 1),
        (100004, "原地停止", "BASIC", "STOP", "G1", 2.0, "", 1),
    ]
    for no, name, cat, code, model, dur, path, allow_m in basic_actions:
        conn.execute(
            """INSERT INTO actions (no, name, category, lrmp_code, robot_model, duration,
               motion_file_path, is_builtin, sync_status, allow_move, allow_stretch)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'synced', ?, 0)""",
            (no, name, cat, code, model, dur, path, allow_m),
        )

    seq_no = 550001
    for group in DEFAULT_DANCE_GROUPS:
        gid = group["group_id"]
        for item in group["items"]:
            alias = item["alias"]
            name = item["name"]
            dur = _ACTION_DURATION_MAP.get(alias, 14.0)
            motion_path = _PREVIEW_NPZ_MAP.get(alias, default_csv)
            conn.execute(
                """INSERT INTO actions (no, name, category, lrmp_code, robot_model, duration,
                   motion_file_path, is_builtin, sync_status, allow_move, allow_stretch)
                   VALUES (?, ?, ?, ?, 'G1', ?, ?, 1, 'synced', 0, 0)""",
                (seq_no, name, gid, alias, dur, motion_path),
            )
            seq_no += 1


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
