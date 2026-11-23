# @file: src/persistence/schema_ddl.py
# @brief: SQLite 10-table canonical DDL schema for scenes, tasks, tracks, trajectories, actions, blocks, init points, maps, and fragments.
# @exports: SCHEMA_VERSION, ALL_TABLES_DDL

from __future__ import annotations

SCHEMA_VERSION = 1

ALL_TABLES_DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    stage_width REAL NOT NULL DEFAULT 12.0,
    stage_height REAL NOT NULL DEFAULT 8.0,
    safety_margin REAL NOT NULL DEFAULT 0.5,
    active_map_id INTEGER,
    bpm REAL NOT NULL DEFAULT 120.0,
    time_signature TEXT NOT NULL DEFAULT '4/4',
    audio_path TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id INTEGER NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    total_duration REAL NOT NULL DEFAULT 30.0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    track_no INTEGER NOT NULL,
    name TEXT NOT NULL,
    target_id TEXT NOT NULL,
    robot_id TEXT NOT NULL,
    robot_ip TEXT NOT NULL DEFAULT '192.168.123.101',
    robot_model TEXT NOT NULL DEFAULT 'G1-29DOF',
    color_hex TEXT NOT NULL,
    init_x REAL NOT NULL DEFAULT 0.0,
    init_y REAL NOT NULL DEFAULT 0.0,
    init_yaw REAL NOT NULL DEFAULT 0.0,
    muted INTEGER NOT NULL DEFAULT 0,
    locked INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS trajectory_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id INTEGER NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    robot_count INTEGER NOT NULL DEFAULT 1,
    bound_track_no INTEGER,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS trajectories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES trajectory_groups(id) ON DELETE CASCADE,
    no INTEGER NOT NULL,
    name TEXT NOT NULL,
    duration REAL NOT NULL DEFAULT 5.0,
    control_points_json TEXT NOT NULL DEFAULT '[]',
    interpolation_mode TEXT NOT NULL DEFAULT 'uniform',
    hold_direction INTEGER NOT NULL DEFAULT 0,
    hold_yaw REAL NOT NULL DEFAULT 0.0,
    end_turn INTEGER NOT NULL DEFAULT 0,
    end_yaw REAL NOT NULL DEFAULT 0.0,
    max_acc REAL NOT NULL DEFAULT 1.5,
    run_mode INTEGER NOT NULL DEFAULT 504,
    point_data_csv TEXT NOT NULL DEFAULT '',
    visible_on_map INTEGER NOT NULL DEFAULT 1,
    bound_track_nos_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    no INTEGER NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'G1',
    lrmp_code TEXT NOT NULL,
    robot_model TEXT NOT NULL DEFAULT 'G1',
    duration REAL NOT NULL DEFAULT 10.0,
    motion_file_path TEXT NOT NULL DEFAULT '',
    is_builtin INTEGER NOT NULL DEFAULT 1,
    sync_status TEXT NOT NULL DEFAULT 'synced',
    allow_move INTEGER NOT NULL DEFAULT 0,
    allow_stretch INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS track_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    block_type TEXT NOT NULL,
    ref_id INTEGER NOT NULL DEFAULT 0,
    code_no TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    start_time REAL NOT NULL DEFAULT 0.0,
    duration REAL NOT NULL DEFAULT 5.0,
    is_ignored INTEGER NOT NULL DEFAULT 0,
    extra_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS init_point_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id INTEGER NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    points_json TEXT NOT NULL DEFAULT '[]',
    is_default INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS pcd_maps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER NOT NULL DEFAULT 0,
    point_count INTEGER NOT NULL DEFAULT 0,
    bbox_json TEXT NOT NULL DEFAULT '{}',
    grid_png_path TEXT NOT NULL DEFAULT '',
    resolution REAL NOT NULL DEFAULT 0.05,
    origin_x REAL NOT NULL DEFAULT 0.0,
    origin_y REAL NOT NULL DEFAULT 0.0,
    calib_matrix_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fragments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id INTEGER NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    slot_no INTEGER NOT NULL,
    name TEXT NOT NULL,
    duration REAL NOT NULL DEFAULT 5.0,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_scene ON tasks(scene_id);
CREATE INDEX IF NOT EXISTS idx_tracks_task ON tracks(task_id, track_no);
CREATE INDEX IF NOT EXISTS idx_traj_group ON trajectories(group_id, no);
CREATE INDEX IF NOT EXISTS idx_blocks_task_track ON track_blocks(task_id, track_id, start_time);
CREATE INDEX IF NOT EXISTS idx_fragments_scene_slot ON fragments(scene_id, slot_no);
"""
