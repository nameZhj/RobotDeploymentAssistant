"""
@file: src/infrastructure/storage/db_bootstrap.py
@brief: SQLite 8张关联表关系型存储架构初始化与种子数据引导引擎
@exports: DEFAULT_DB_PATH, init_database, create_tables, bootstrap_seed_data
"""
import os
import sqlite3
from typing import Optional

DEFAULT_DB_PATH = os.path.join("runtime", "shows", "studio_core.db")

DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS scenes (
        scene_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        active_map_id TEXT DEFAULT 'map_default',
        active_init_cfg_id INTEGER DEFAULT 1,
        active_task_name TEXT DEFAULT '默认任务1',
        music_path TEXT DEFAULT '',
        music_title TEXT DEFAULT '未配置音乐',
        music_duration_s REAL DEFAULT 120.0
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS tracks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scene_id TEXT DEFAULT '123',
        robot_id INTEGER NOT NULL,
        lora_id TEXT NOT NULL,
        sn TEXT DEFAULT '',
        alias TEXT DEFAULT '',
        UNIQUE(scene_id, robot_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS init_points (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scene_id TEXT DEFAULT '123',
        cfg_id INTEGER DEFAULT 1,
        robot_id INTEGER NOT NULL,
        x REAL DEFAULT 0.0,
        y REAL DEFAULT 0.0,
        yaw REAL DEFAULT 0.0,
        robot_alias TEXT DEFAULT '',
        model_type TEXT DEFAULT 'A2-W',
        UNIQUE(scene_id, cfg_id, robot_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scene_id TEXT DEFAULT '123',
        no INTEGER NOT NULL UNIQUE,
        name TEXT NOT NULL,
        lora_alias TEXT DEFAULT '',
        key_combo TEXT DEFAULT '',
        type TEXT DEFAULT 'dance',
        time REAL DEFAULT 6.0,
        transition REAL DEFAULT 0.0,
        allow_stretch INTEGER DEFAULT 0,
        allow_move INTEGER DEFAULT 0,
        keyframes_json TEXT DEFAULT '[]'
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS trajectory_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scene_id TEXT DEFAULT '123',
        name TEXT NOT NULL,
        track_id INTEGER DEFAULT 1
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS trajectories (
        no INTEGER PRIMARY KEY,
        scene_id TEXT DEFAULT '123',
        group_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        time REAL DEFAULT 3.0,
        trajectory_point_data TEXT NOT NULL,
        interpolation_mode TEXT DEFAULT 'uniform',
        max_acc REAL DEFAULT 1.5,
        hold_direction INTEGER DEFAULT 0,
        hold_direction_yaw REAL DEFAULT 0.0,
        end_turn INTEGER DEFAULT 0,
        end_turn_yaw REAL DEFAULT 0.0
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS track_state (
        id TEXT PRIMARY KEY,
        scene_id TEXT DEFAULT '123',
        robot_id INTEGER NOT NULL,
        group_id INTEGER DEFAULT 0,
        no INTEGER NOT NULL,
        type TEXT NOT NULL,
        name TEXT DEFAULT '',
        time REAL DEFAULT 0.0,
        start_time REAL DEFAULT 0.0,
        end_time REAL DEFAULT 0.0,
        allow_stretch INTEGER DEFAULT 0,
        max_acc REAL DEFAULT 1.5,
        hold_direction INTEGER DEFAULT 0,
        hold_direction_yaw REAL DEFAULT 0.0,
        end_turn INTEGER DEFAULT 0,
        end_turn_yaw REAL DEFAULT 0.0,
        interpolation_mode TEXT DEFAULT 'uniform',
        trajectory_point_data TEXT DEFAULT ''
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS fragments (
        fragment_id TEXT PRIMARY KEY,
        scene_id TEXT DEFAULT '123',
        name TEXT NOT NULL,
        start_time REAL DEFAULT 0.0,
        duration REAL DEFAULT 10.0,
        content_json TEXT DEFAULT '{}'
    );
    """
]


def create_tables(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    for ddl in DDL_STATEMENTS:
        cursor.execute(ddl)
    conn.commit()


def bootstrap_seed_data(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM scenes")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO scenes (scene_id, name, music_title) VALUES ('123', '经典编排舞台', '未配置音乐')"
        )
    cursor.execute("SELECT COUNT(*) FROM tracks")
    if cursor.fetchone()[0] == 0:
        tracks = [
            ('123', 1, 'A', 'Robot_1', '机器人 1'),
            ('123', 2, 'B', 'Robot_2', '机器人 2'),
            ('123', 3, 'C', 'Robot_3', '机器人 3'),
            ('123', 4, 'D', 'Robot_4', '机器人 4'),
        ]
        cursor.executemany(
            "INSERT INTO tracks (scene_id, robot_id, lora_id, sn, alias) VALUES (?, ?, ?, ?, ?)",
            tracks
        )
    cursor.execute("SELECT COUNT(*) FROM trajectory_groups")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO trajectory_groups (scene_id, name, track_id) VALUES ('123', '轨道1编导轨迹组', 1)")
        cursor.execute("INSERT INTO trajectory_groups (scene_id, name, track_id) VALUES ('123', '轨道2编导轨迹组', 2)")
    cursor.execute("SELECT COUNT(*) FROM fragments")
    if cursor.fetchone()[0] == 0:
        frags = [(f"{i:02d}", '123', f"片段 {i:02d}", float(i - 1) * 10.0, 10.0) for i in range(1, 10)]
        cursor.executemany("INSERT INTO fragments (fragment_id, scene_id, name, start_time, duration) VALUES (?, ?, ?, ?, ?)", frags)
    conn.commit()


def init_database(db_path: Optional[str] = None) -> sqlite3.Connection:
    target_path = db_path or DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    conn = sqlite3.connect(target_path)
    create_tables(conn)
    bootstrap_seed_data(conn)
    return conn
