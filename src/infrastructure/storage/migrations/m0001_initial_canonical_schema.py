"""
@file: src/infrastructure/storage/migrations/0001_initial_canonical_schema.py
@brief: 初始规范 SQLite 数据库 Schema 迁移脚本 (12 核心表与高性能业务索引)
@exports: MIGRATION_ID, TARGET_VERSION, up
"""
import sqlite3

MIGRATION_ID = "0001_initial_canonical_schema"
TARGET_VERSION = 1


def up(conn: sqlite3.Connection) -> None:
    """执行 0001 初始 Schema 建立，创建 12 张核心规范表与外键索引"""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            success INTEGER NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scenes (
            scene_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            active_map_id TEXT DEFAULT 'map_default',
            active_init_cfg_id INTEGER DEFAULT 1,
            active_task_name TEXT DEFAULT '',
            music_title TEXT DEFAULT '未配置音乐',
            music_duration_s REAL DEFAULT 120.0,
            coordinate_frame_id TEXT DEFAULT 'map',
            distance_unit TEXT DEFAULT 'm',
            angle_unit TEXT DEFAULT 'rad',
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            schema_version INTEGER DEFAULT 1
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS robots (
            robot_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            model_type TEXT DEFAULT 'Unitree_G1',
            hardware_id TEXT,
            transport_kind TEXT DEFAULT 'SIM',
            namespace TEXT DEFAULT '',
            enabled INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS robot_groups (
            group_id TEXT PRIMARY KEY,
            scene_id TEXT NOT NULL REFERENCES scenes(scene_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            formation_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS robot_group_members (
            group_id TEXT NOT NULL REFERENCES robot_groups(group_id) ON DELETE CASCADE,
            robot_id TEXT NOT NULL REFERENCES robots(robot_id) ON DELETE RESTRICT,
            display_order INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (group_id, robot_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS maps (
            map_id TEXT PRIMARY KEY,
            scene_id TEXT REFERENCES scenes(scene_id) ON DELETE SET NULL,
            display_name TEXT NOT NULL,
            file_uri TEXT NOT NULL,
            source_filename TEXT NOT NULL,
            format TEXT DEFAULT 'PCD',
            encoding TEXT DEFAULT 'ASCII',
            point_count INTEGER,
            width INTEGER,
            height INTEGER,
            fields_json TEXT,
            resolution REAL,
            bounds_json TEXT,
            origin_pose_json TEXT,
            coordinate_frame_id TEXT DEFAULT 'map',
            distance_unit TEXT DEFAULT 'm',
            sha256 TEXT NOT NULL,
            file_size_bytes INTEGER DEFAULT 0,
            import_state TEXT DEFAULT 'READY',
            import_error_code TEXT,
            import_error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trajectories (
            trajectory_id TEXT PRIMARY KEY,
            scene_id TEXT NOT NULL REFERENCES scenes(scene_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            target_type TEXT DEFAULT 'single',
            target_id TEXT DEFAULT 'A',
            formation_id TEXT,
            duration REAL DEFAULT 3.0,
            max_velocity REAL DEFAULT 1.2,
            interpolation TEXT DEFAULT 'catmull_rom',
            map_id TEXT REFERENCES maps(map_id) ON DELETE RESTRICT,
            robot_id TEXT REFERENCES robots(robot_id) ON DELETE SET NULL,
            group_id TEXT REFERENCES robot_groups(group_id) ON DELETE SET NULL,
            coordinate_frame_id TEXT DEFAULT 'map',
            distance_unit TEXT DEFAULT 'm',
            angle_unit TEXT DEFAULT 'rad',
            geometry_type TEXT DEFAULT 'POLYLINE_2D',
            waypoints_json TEXT NOT NULL DEFAULT '[]',
            control_points_json TEXT DEFAULT '[]',
            sampled_points_json TEXT DEFAULT '[]',
            point_count INTEGER NOT NULL DEFAULT 0,
            total_length REAL,
            estimated_duration_ms INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT '',
            revision INTEGER DEFAULT 1
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS formations (
            formation_id TEXT PRIMARY KEY,
            scene_id TEXT NOT NULL REFERENCES scenes(scene_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            layout_type TEXT DEFAULT 'GRID',
            description TEXT,
            parameters_json TEXT NOT NULL DEFAULT '{}',
            member_offsets_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            revision INTEGER DEFAULT 1
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS actions (
            action_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            model_type TEXT DEFAULT 'Unitree_G1',
            asset_uri TEXT NOT NULL,
            source_filename TEXT NOT NULL,
            file_sha256 TEXT,
            duration_ms INTEGER,
            sample_rate_hz REAL,
            joint_names_json TEXT DEFAULT '[]',
            compatibility_json TEXT DEFAULT '{}',
            metadata_json TEXT DEFAULT '{}',
            import_state TEXT DEFAULT 'READY',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS timelines (
            timeline_id TEXT PRIMARY KEY,
            scene_id TEXT NOT NULL REFERENCES scenes(scene_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            duration_ms INTEGER DEFAULT 120000,
            frame_rate REAL DEFAULT 30.0,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            revision INTEGER DEFAULT 1
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS timeline_tracks (
            track_id TEXT PRIMARY KEY,
            timeline_id TEXT NOT NULL REFERENCES timelines(timeline_id) ON DELETE CASCADE,
            track_type TEXT NOT NULL DEFAULT 'ROBOT',
            robot_id TEXT REFERENCES robots(robot_id) ON DELETE SET NULL,
            group_id TEXT REFERENCES robot_groups(group_id) ON DELETE SET NULL,
            display_order INTEGER DEFAULT 0,
            muted INTEGER DEFAULT 0,
            locked INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS timeline_clips (
            clip_id TEXT PRIMARY KEY,
            track_id TEXT NOT NULL REFERENCES timeline_tracks(track_id) ON DELETE CASCADE,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            start_ms INTEGER NOT NULL,
            duration_ms INTEGER NOT NULL,
            offset_ms INTEGER DEFAULT 0,
            playback_rate REAL DEFAULT 1.0,
            enabled INTEGER DEFAULT 1,
            revision INTEGER DEFAULT 1
        )
    """)

    # 兼容历史库中已存在但缺少规范列的旧表结构
    for tbl, col, col_def in [
        ("scenes", "description", "TEXT"),
        ("scenes", "coordinate_frame_id", "TEXT DEFAULT 'map'"),
        ("scenes", "distance_unit", "TEXT DEFAULT 'm'"),
        ("scenes", "angle_unit", "TEXT DEFAULT 'rad'"),
        ("scenes", "schema_version", "INTEGER DEFAULT 1"),
        ("scenes", "music_title", "TEXT DEFAULT '未配置音乐'"),
        ("scenes", "music_duration_s", "REAL DEFAULT 120.0"),
        ("scenes", "active_init_cfg_id", "INTEGER DEFAULT 1"),
        ("scenes", "active_task_name", "TEXT DEFAULT ''"),
        ("scenes", "created_at", "TEXT DEFAULT ''"),
        ("scenes", "updated_at", "TEXT DEFAULT ''"),
        ("trajectories", "updated_at", "TEXT DEFAULT ''"),
        ("trajectories", "waypoints_json", "TEXT DEFAULT '[]'"),
        ("trajectories", "point_count", "INTEGER DEFAULT 0"),
        ("trajectories", "total_length", "REAL DEFAULT 0.0"),
        ("trajectories", "estimated_duration_ms", "INTEGER DEFAULT 0"),
        ("trajectories", "revision", "INTEGER DEFAULT 1"),
        ("trajectories", "geometry_type", "TEXT DEFAULT 'POLYLINE_2D'"),
        ("trajectories", "coordinate_frame_id", "TEXT DEFAULT 'map'"),
        ("trajectories", "distance_unit", "TEXT DEFAULT 'm'"),
        ("trajectories", "angle_unit", "TEXT DEFAULT 'rad'"),
        ("timeline_clips", "track_id", "TEXT DEFAULT ''"),
        ("timeline_clips", "source_type", "TEXT DEFAULT 'ACTION'"),
        ("timeline_clips", "source_id", "TEXT DEFAULT ''"),
        ("timeline_clips", "offset_ms", "INTEGER DEFAULT 0"),
        ("timeline_clips", "playback_rate", "REAL DEFAULT 1.0"),
        ("timeline_clips", "enabled", "INTEGER DEFAULT 1"),
        ("timeline_clips", "revision", "INTEGER DEFAULT 1"),
    ]:
        existing_cols = [c[1] for c in cur.execute(f"PRAGMA table_info({tbl})").fetchall()]
        if col not in existing_cols:
            cur.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_def};")

    # 业务索引
    cur.execute("CREATE INDEX IF NOT EXISTS idx_maps_scene_state ON maps(scene_id, import_state);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trajectories_scene ON trajectories(scene_id, updated_at);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_actions_model_name ON actions(model_type, name);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_timelines_scene ON timelines(scene_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_timeline_tracks_display ON timeline_tracks(timeline_id, display_order);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_timeline_clips_track_start ON timeline_clips(track_id, start_ms);")
