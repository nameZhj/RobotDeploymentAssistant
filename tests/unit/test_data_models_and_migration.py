"""
@file: tests/unit/test_data_models_and_migration.py
@brief: Prompt 04 领域模型校验、版本化 SQLite 迁移与原子导入导出专项测试
@exports: test_schema_creation_on_empty_db, test_versioned_migrations_pipeline, test_migration_idempotency, test_domain_entity_validation_finite_coords, test_domain_entity_units_and_time_checks, test_foreign_key_reference_protection, test_trajectory_import_export_roundtrip_atomic
"""
import json
import math
import os
from pathlib import Path
import sqlite3
import pytest

from src.application.studio.studio_facade import StudioFacade
from src.core.models import ControlPoint, TrajectoryModel
from src.core.storage_manager import StorageManager
from src.domain.choreo_entities import (
    ActionAssetEntity,
    DomainValidator,
    FormationEntity,
    MapAssetEntity,
    RobotEntity,
    RobotGroupEntity,
    SceneEntity,
    TimelineClipEntity,
    TimelineEntity,
    TimelineTrackEntity,
    TrajectoryEntity,
)
from src.infrastructure.storage.migration_engine import MigrationEngine


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_canonical.db"
    return str(db_file)


def test_schema_creation_on_empty_db(temp_db):
    """验证空数据库上初次执行迁移能够成功建表并初始化 user_version"""
    conn = sqlite3.connect(temp_db)
    applied = MigrationEngine.apply_all(conn)
    assert len(applied) >= 2
    assert "0001_initial_canonical_schema" in applied

    cur = conn.cursor()
    cur.execute("PRAGMA user_version;")
    assert cur.fetchone()[0] == 2

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = [r[0] for r in cur.fetchall()]
    for expected in ["scenes", "robots", "robot_groups", "maps", "trajectories", "actions", "timelines", "timeline_clips"]:
        assert expected in tables
    conn.close()


def test_migration_idempotency(temp_db):
    """验证迁移引擎具备幂等性，重复运行不产生重复记录或报错"""
    conn = sqlite3.connect(temp_db)
    MigrationEngine.apply_all(conn)
    second_run = MigrationEngine.apply_all(conn)
    assert len(second_run) == 0
    manifest = MigrationEngine.get_manifest(conn)
    assert manifest["current_user_version"] == 2
    assert manifest["total_applied"] == 2
    conn.close()


def test_migration_rollback_on_error(tmp_path):
    """验证迁移过程中异常将触发原子回滚，旧库保持完好"""
    db_path = str(tmp_path / "rollback_test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA user_version = 0;")
    conn.execute("CREATE TABLE dummy (id INT);")
    conn.commit()

    class FaultyMigration:
        MIGRATION_ID = "9999_faulty"
        TARGET_VERSION = 99
        @staticmethod
        def up(c):
            c.execute("CREATE TABLE will_rollback (id INT);")
            raise RuntimeError("模拟突发故障")

    from src.infrastructure.storage import migration_engine
    orig = migration_engine.REGISTERED_MIGRATIONS
    migration_engine.REGISTERED_MIGRATIONS = [FaultyMigration]
    try:
        with pytest.raises(RuntimeError, match="模拟突发故障"):
            MigrationEngine.apply_all(conn)
    finally:
        migration_engine.REGISTERED_MIGRATIONS = orig

    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cur.fetchall()]
    assert "will_rollback" not in tables
    assert "dummy" in tables
    conn.close()


def test_domain_entity_validation_finite_coords():
    """验证领域模型严格拦截 NaN、Infinity 与非有限坐标点"""
    with pytest.raises(ValueError, match="不能为 NaN"):
        DomainValidator.validate_finite(float("nan"), "test_x")

    with pytest.raises(ValueError, match="不能为 NaN"):
        DomainValidator.validate_finite(float("inf"), "test_y")

    wps_with_nan = [{"waypoint_id": "p1", "x": float("nan"), "y": 0.0}]
    with pytest.raises(ValueError, match="不能为 NaN"):
        DomainValidator.validate_waypoints(wps_with_nan)

    wps_with_dup = [
        {"waypoint_id": "p1", "x": 0.0, "y": 0.0},
        {"waypoint_id": "p1", "x": 1.0, "y": 1.0},
    ]
    with pytest.raises(ValueError, match="waypoint_id 重复"):
        DomainValidator.validate_waypoints(wps_with_dup)


def test_domain_entity_units_and_time_checks():
    """验证时间轴片段、场景单位与播放速率的合法性约束"""
    scene = SceneEntity(scene_id="sc_01", name="场景1", distance_unit="m", angle_unit="rad")
    assert scene.distance_unit == "m"

    with pytest.raises(ValueError, match="不支持的距离单位"):
        SceneEntity(scene_id="sc_02", name="场景2", distance_unit="inches")

    with pytest.raises(ValueError, match="片段持续时长"):
        TimelineClipEntity(
            clip_id="c1", track_id="t1", source_type="ACTION", source_id="a1",
            start_ms=0, duration_ms=0, playback_rate=1.0
        )

    with pytest.raises(ValueError, match="播放速率超出合法区间"):
        TimelineClipEntity(
            clip_id="c2", track_id="t1", source_type="ACTION", source_id="a1",
            start_ms=0, duration_ms=1000, playback_rate=50.0
        )


def test_foreign_key_reference_protection(temp_db):
    """验证外键约束开启时，禁止直接删除被引用的父级资源"""
    conn = sqlite3.connect(temp_db)
    MigrationEngine.apply_all(conn)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")

    cur.execute("INSERT INTO scenes (scene_id, name, created_at, updated_at) VALUES ('sc_fk', '测试场景', '2026', '2026')")
    cur.execute("INSERT INTO robots (robot_id, display_name, created_at, updated_at) VALUES ('R01', '机甲1', '2026', '2026')")
    cur.execute("INSERT INTO maps (map_id, display_name, file_uri, source_filename, sha256, created_at, updated_at) VALUES ('m01', '地图1', 'uri', 'f.pcd', 'sha', '2026', '2026')")
    cur.execute("""
        INSERT INTO trajectories (trajectory_id, scene_id, name, map_id, robot_id, waypoints_json, created_at, updated_at)
        VALUES ('tr_fk', 'sc_fk', '轨迹1', 'm01', 'R01', '[]', '2026', '2026')
    """)
    conn.commit()

    # 删除被轨迹引用的 map_id 应当触发外键 RESTRICT 异常
    with pytest.raises(sqlite3.IntegrityError):
        cur.execute("DELETE FROM maps WHERE map_id = 'm01'")
        conn.commit()

    conn.close()


def test_trajectory_import_export_roundtrip_atomic(tmp_path, temp_db):
    """验证轨迹原子导出（临时文件+fsync替换）与带 schema_version 的无损导入"""
    mgr = StorageManager(base_dir=str(tmp_path), db_path=temp_db)
    facade = StudioFacade(storage=mgr)

    traj = TrajectoryModel(
        trajectory_id="tr_roundtrip",
        name="测试回环轨迹",
        schema_version="1.0",
        control_points=[ControlPoint(seq=0, x=1.0, y=2.0), ControlPoint(seq=1, x=3.5, y=4.5)],
    )
    mgr.save_trajectory(traj)

    export_path = tmp_path / "exported_traj.json"
    exp_res = facade.export_trajectory("tr_roundtrip", export_path)
    assert exp_res.success is True
    assert export_path.exists()

    # 验证导出的 JSON 包含 schema_version 且无残留 tmp 文件
    with open(export_path, "r", encoding="utf-8") as f:
        content = json.load(f)
    assert content["schema_version"] == "1.0"
    assert content["trajectory_id"] == "tr_roundtrip"

    tmp_files = list(tmp_path.glob("*.tmp_*"))
    assert len(tmp_files) == 0

    # 验证导入功能
    imp_res = facade.import_trajectory(export_path)
    assert imp_res.success is True
    assert imp_res.trajectory_id == "tr_roundtrip"

    # 验证未知版本导入被拒绝
    bad_version_path = tmp_path / "bad_ver.json"
    content["schema_version"] = "99.0"
    with open(bad_version_path, "w", encoding="utf-8") as f:
        json.dump(content, f)

    bad_res = facade.import_trajectory(bad_version_path)
    assert bad_res.success is False
    assert "UNSUPPORTED_SCHEMA_VERSION" in bad_res.msg
