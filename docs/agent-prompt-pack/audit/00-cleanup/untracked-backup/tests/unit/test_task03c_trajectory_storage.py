"""
@file: tests/unit/test_task03c_trajectory_storage.py
@brief: 任务 03C TrajectoryAsset 持久化接入 SQLite 与引用防护单元测试
@exports: 测试用例函数集合
"""
import json
import sqlite3
import pytest
from src.domain.trajectory.trajectory_asset import TrajectoryAsset, TrajectoryPoint
from src.infrastructure.storage.choreo_sqlite_store import ChoreoSqliteStore


@pytest.fixture
def temp_store(tmp_path):
    """创建完全隔离在 tmp_path 的临时数据库实例，杜绝触碰正式库"""
    db_file = tmp_path / "test_studio_data.db"
    store = ChoreoSqliteStore(db_path=str(db_file))
    return store


def _make_sample_asset(tid: str = "traj_001", name: str = "测试轨迹") -> TrajectoryAsset:
    pts = [
        TrajectoryPoint(x_m=0.0, y_m=0.0, yaw_deg=0.0, s_m=0.0),
        TrajectoryPoint(x_m=1.0, y_m=0.0, yaw_deg=15.0, s_m=1.0),
        TrajectoryPoint(x_m=2.0, y_m=1.0, yaw_deg=45.0, s_m=2.414),
    ]
    return TrajectoryAsset(
        trajectory_id=tid,
        name=name,
        coordinate_frame="stage_world",
        control_points=[(0.0, 0.0), (1.0, 0.0), (2.0, 1.0)],
        sampled_points=pts,
        length_m=2.414,
        recommended_speed_mps=0.8,
        spline_type="catmull_rom",
    )


def test_01_save_trajectory_asset(temp_store):
    """1. 新轨迹保存"""
    asset = _make_sample_asset("traj_save_01", "保存测试轨迹")
    temp_store.save_trajectory_asset(asset)

    with temp_store.get_connection() as conn:
        row = conn.execute("SELECT * FROM trajectories WHERE traj_id = ?", ("traj_save_01",)).fetchone()
        assert row is not None
        assert row["name"] == "保存测试轨迹"
        assert row["asset_json"] is not None


def test_02_load_trajectory_asset(temp_store):
    """2. 新轨迹重新读取"""
    asset = _make_sample_asset("traj_load_02", "加载测试轨迹")
    temp_store.save_trajectory_asset(asset)

    loaded = temp_store.load_trajectory_asset("traj_load_02")
    assert loaded is not None
    assert loaded.trajectory_id == "traj_load_02"
    assert loaded.name == "加载测试轨迹"
    assert loaded.coordinate_frame == "stage_world"
    assert loaded.spline_type == "catmull_rom"


def test_03_control_and_sampled_points_fidelity(temp_store):
    """3. 控制点和采样点在序列化与重载后严格保持一致"""
    asset = _make_sample_asset("traj_fidelity_03")
    temp_store.save_trajectory_asset(asset)

    loaded = temp_store.load_trajectory_asset("traj_fidelity_03")
    assert loaded.control_points == asset.control_points
    assert len(loaded.sampled_points) == len(asset.sampled_points)
    for p_orig, p_load in zip(asset.sampled_points, loaded.sampled_points):
        assert p_orig.x_m == pytest.approx(p_load.x_m)
        assert p_orig.y_m == pytest.approx(p_load.y_m)


def test_04_yaw_deg_unit_preserved(temp_store):
    """4. yaw_deg 角度制单位在存储与还原过程中严格保持"""
    asset = _make_sample_asset("traj_yaw_04")
    temp_store.save_trajectory_asset(asset)

    loaded = temp_store.load_trajectory_asset("traj_yaw_04")
    assert loaded.sampled_points[1].yaw_deg == pytest.approx(15.0)
    assert loaded.sampled_points[2].yaw_deg == pytest.approx(45.0)


def test_05_s_m_arc_length_preserved(temp_store):
    """5. s_m 空间物理累计弧长保持准确"""
    asset = _make_sample_asset("traj_sm_05")
    temp_store.save_trajectory_asset(asset)

    loaded = temp_store.load_trajectory_asset("traj_sm_05")
    assert loaded.sampled_points[0].s_m == pytest.approx(0.0)
    assert loaded.sampled_points[1].s_m == pytest.approx(1.0)
    assert loaded.sampled_points[2].s_m == pytest.approx(2.414)
    assert loaded.length_m == pytest.approx(2.414)


def test_06_independent_saving_multiple_assets(temp_store):
    """6. 不同 trajectory_id 独立保存与列表查询"""
    a1 = _make_sample_asset("traj_indep_01", "第一段轨迹")
    a2 = _make_sample_asset("traj_indep_02", "第二段轨迹")
    temp_store.save_trajectory_asset(a1)
    temp_store.save_trajectory_asset(a2)

    all_assets = temp_store.list_trajectory_assets()
    ids = [a.trajectory_id for a in all_assets]
    assert "traj_indep_01" in ids
    assert "traj_indep_02" in ids


def test_07_duplicate_id_overwrite(temp_store):
    """7. 重复 ID 的处理（无冲突覆盖更新，字段保持最新）"""
    a1 = _make_sample_asset("traj_dup_07", "初始版本")
    temp_store.save_trajectory_asset(a1)

    a2 = _make_sample_asset("traj_dup_07", "修改后版本")
    a2.length_m = 3.5
    a2.sampled_points[-1].s_m = 3.5
    temp_store.save_trajectory_asset(a2)

    loaded = temp_store.load_trajectory_asset("traj_dup_07")
    assert loaded.name == "修改后版本"
    assert loaded.length_m == pytest.approx(3.5)


def test_08_non_existent_id_returns_none(temp_store):
    """8. 不存在 ID 的读取返回 None"""
    assert temp_store.load_trajectory_asset("non_existent_9999") is None


def test_09_corrupted_json_error_handling(temp_store):
    """9. 损坏 JSON 的错误处理（抛出包含原因的明确 ValueError）"""
    with temp_store.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO trajectories (traj_id, robot_group, name, waypoints_json, duration, created_at, asset_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("traj_corrupt", "Robot_1", "损坏测试", "[]", 1.0, 1000.0, "{broken_json_not_valid...")
        )
        conn.commit()

    with pytest.raises(ValueError, match="asset_json 数据已损坏"):
        temp_store.load_trajectory_asset("traj_corrupt")


def test_10_legacy_trajectory_compatibility(temp_store):
    """10. 旧格式轨迹读取兼容（无 asset_json 时通过历史字段平滑还原）"""
    with temp_store.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO trajectories (traj_id, robot_group, name, waypoints_json, duration, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("traj_legacy_01", "Robot_1", "历史旧轨迹", '[{"x": 0.0, "y": 0.0, "t": 0.0}, {"x": 3.0, "y": 4.0, "t": 8.0}]', 8.0, 1000.0)
        )
        conn.commit()

    asset = temp_store.load_trajectory_asset("traj_legacy_01")
    assert asset is not None
    assert asset.trajectory_id == "traj_legacy_01"
    assert asset.name == "历史旧轨迹"
    assert len(asset.control_points) >= 2
    assert asset.control_points[0] == (0.0, 0.0)
    assert asset.control_points[-1] == (3.0, 4.0)
    assert asset.length_m > 0.0


def test_11_delete_and_reference_protection(temp_store):
    """11. 删除及引用保护（被时间轴引用时禁止删除，未被引用时成功删除）"""
    asset = _make_sample_asset("traj_ref_11", "受保护轨迹")
    temp_store.save_trajectory_asset(asset)

    # 1. 在 timeline_clips 中建立引用
    temp_store.save_clip(
        clip_id="clip_test_01",
        robot_id="1",
        track_layer="TRAJECTORY",
        ref_id="traj_ref_11",
        start_ms=0,
        duration_ms=2500,
    )

    # 尝试删除应被严格阻断
    with pytest.raises(ValueError, match="正被时间轴引用"):
        temp_store.delete_trajectory_asset("traj_ref_11")

    # 2. 解除引用后允许正常删除
    temp_store.delete_clip("clip_test_01")
    deleted = temp_store.delete_trajectory_asset("traj_ref_11")
    assert deleted is True
    assert temp_store.load_trajectory_asset("traj_ref_11") is None


def test_12_write_failure_rollback(temp_store, monkeypatch):
    """12. 数据库写入失败时事务严格回滚，无残留数据"""
    asset = _make_sample_asset("traj_rollback_12", "回滚测试")

    # 模拟在执行写入 SQL 时发生严重磁盘故障抛出 OperationalError
    orig_get_conn = temp_store.get_connection

    class BadConnectionWrapper:
        def __init__(self, real_conn):
            self._real = real_conn

        def __getattr__(self, name):
            return getattr(self._real, name)

        def execute(self, sql, *args, **kwargs):
            if "INSERT INTO trajectories" in sql or "UPDATE trajectories" in sql:
                raise sqlite3.OperationalError("模拟磁盘写满或异常中断")
            return self._real.execute(sql, *args, **kwargs)

    import contextlib

    @contextlib.contextmanager
    def bad_get_connection():
        with orig_get_conn() as real_conn:
            yield BadConnectionWrapper(real_conn)

    monkeypatch.setattr(temp_store, "get_connection", bad_get_connection)

    with pytest.raises(sqlite3.OperationalError, match="模拟磁盘写满"):
        temp_store.save_trajectory_asset(asset)

    # 还原并检查数据库中是否存在未提交的残留记录
    monkeypatch.undo()
    loaded = temp_store.load_trajectory_asset("traj_rollback_12")
    assert loaded is None


def test_13_migration_idempotent_and_legacy_data_preserved(tmp_path):
    """13. 迁移幂等性与历史数据保留：多次执行 ensure_columns 不报错且原表数据分毫不差"""
    db_file = tmp_path / "legacy_pure.db"
    conn = sqlite3.connect(str(db_file))
    # 模拟纯旧版本数据库结构 (无 asset_json 字段)
    conn.execute(
        """
        CREATE TABLE trajectories (
            traj_id TEXT PRIMARY KEY,
            robot_group TEXT NOT NULL,
            name TEXT NOT NULL,
            waypoints_json TEXT NOT NULL,
            duration REAL NOT NULL,
            created_at REAL
        )
        """
    )
    conn.execute(
        "INSERT INTO trajectories VALUES ('old_1', 'Robot_1', '历史轨迹1', '[[-1.0, 0.0], [1.0, 0.0]]', 2.0, 1000.0)"
    )
    conn.commit()

    from src.infrastructure.storage.trajectory_sqlite_adapter import TrajectorySqliteAdapter
    # 连续调用 3 次 ensure_columns 验证幂等
    TrajectorySqliteAdapter.ensure_columns(conn)
    TrajectorySqliteAdapter.ensure_columns(conn)
    TrajectorySqliteAdapter.ensure_columns(conn)

    cols = [c[1] for c in conn.execute("PRAGMA table_info(trajectories)").fetchall()]
    assert "asset_json" in cols
    assert cols.count("asset_json") == 1

    # 验证原数据行完好无损
    row = conn.execute("SELECT * FROM trajectories WHERE traj_id = 'old_1'").fetchone()
    assert row[0] == "old_1"
    assert row[2] == "历史轨迹1"
    assert row[4] == 2.0
    conn.close()


def test_14_legacy_save_invalidates_stale_asset_json(temp_store):
    """14. 新旧写入一致性：旧接口更新轨迹时清空 asset_json，防止新接口读出过期脏数据"""
    # 1. 先用新接口存入 asset (点在 0,0 -> 1,0 -> 2,1)
    asset = _make_sample_asset("traj_sync_14", "新版轨迹")
    temp_store.save_trajectory_asset(asset)

    # 确认新接口读取无误
    loaded1 = temp_store.load_trajectory_asset("traj_sync_14")
    assert loaded1.control_points[-1] == (2.0, 1.0)

    # 2. 调用旧接口 save_trajectory 修改点位 (改为 10,10 -> 20,20)
    new_wps = json.dumps([{"x": 10.0, "y": 10.0}, {"x": 20.0, "y": 20.0}])
    temp_store.save_trajectory("traj_sync_14", "Robot_1", "旧接口覆写轨迹", new_wps, 5.0)

    # 3. 再次用新接口读取，必须解析出最新点位，严禁返回旧 asset_json
    loaded2 = temp_store.load_trajectory_asset("traj_sync_14")
    assert loaded2 is not None
    assert loaded2.name == "旧接口覆写轨迹"
    assert loaded2.control_points[0] == (10.0, 10.0)
    assert loaded2.control_points[-1] == (20.0, 20.0)


def test_15_referenced_asset_update_protection(temp_store):
    """15. 被引用素材更新保护：已被时间轴引用的素材默认禁止静默覆盖，显式指定时方可覆盖"""
    asset = _make_sample_asset("traj_ref_upd_15", "初版受保护")
    temp_store.save_trajectory_asset(asset)

    # 在 timeline_clips 中建立引用
    temp_store.save_clip("clip_upd_1", "1", "TRAJ", "traj_ref_upd_15", 0, 1000)

    # 尝试修改但未带 allow_overwrite_referenced=True，必须被阻断
    modified_asset = _make_sample_asset("traj_ref_upd_15", "试图静默覆盖")
    with pytest.raises(ValueError, match="默认禁止覆盖更新"):
        temp_store.save_trajectory_asset(modified_asset, allow_overwrite_referenced=False)

    # 显式指定 allow_overwrite_referenced=True 时允许更新
    temp_store.save_trajectory_asset(modified_asset, allow_overwrite_referenced=True)
    reloaded = temp_store.load_trajectory_asset("traj_ref_upd_15")
    assert reloaded.name == "试图静默覆盖"


def test_16_delete_atomic_transaction_and_rollback(temp_store, monkeypatch):
    """16. 删除操作原子事务与并发安全：删除执行中途异常时事务完整回滚"""
    asset = _make_sample_asset("traj_del_atomic", "原子删除测试")
    temp_store.save_trajectory_asset(asset)

    orig_get_conn = temp_store.get_connection

    class FailingDeleteConnection:
        def __init__(self, real_conn):
            self._real = real_conn

        def __getattr__(self, name):
            return getattr(self._real, name)

        def execute(self, sql, *args, **kwargs):
            if "DELETE FROM trajectories" in sql:
                raise sqlite3.OperationalError("模拟删除中途 I/O 硬件锁死")
            return self._real.execute(sql, *args, **kwargs)

    import contextlib

    @contextlib.contextmanager
    def failing_get_conn():
        with orig_get_conn() as real_conn:
            yield FailingDeleteConnection(real_conn)

    monkeypatch.setattr(temp_store, "get_connection", failing_get_conn)

    with pytest.raises(sqlite3.OperationalError, match="模拟删除中途 I/O 硬件锁死"):
        temp_store.delete_trajectory_asset("traj_del_atomic")

    monkeypatch.undo()
    # 验证未发生半删除，数据仍然完好存在
    assert temp_store.load_trajectory_asset("traj_del_atomic") is not None


def test_17_duration_semantics_distinct_from_clip(temp_store):
    """17. duration 语义区分：表中 duration 仅为估算值，与 TrajectoryClip 播放时间解耦"""
    from src.domain.trajectory.trajectory_compiler import TrajectoryCompiler

    asset = _make_sample_asset("traj_dur_semantic")
    # length_m = 2.414, recommended_speed_mps = 0.8 -> 估算时长约 3.02s
    temp_store.save_trajectory_asset(asset)

    with temp_store.get_connection() as conn:
        row = conn.execute("SELECT duration FROM trajectories WHERE traj_id = 'traj_dur_semantic'").fetchone()
        estimated_dur = row["duration"]
        assert estimated_dur == pytest.approx(3.02, abs=0.05)

    # 该轨迹在时间轴 Clip 中可以按任意实际业务时长播放 (如拉伸为 12000ms 或压缩为 1500ms)
    compiled_long, dur_long = TrajectoryCompiler.compile_asset(asset, duration_ms=12000)
    assert dur_long == 12.0
    assert compiled_long[-1][0] == 12.0

    compiled_short, dur_short = TrajectoryCompiler.compile_asset(asset, duration_ms=1500)
    assert dur_short == 1.5
    assert compiled_short[-1][0] == 1.5


def test_18_legacy_save_unreferenced_updates_normally(temp_store):
    """18. 旧接口常规更新：未被时间轴引用的轨迹允许正常更新点位与属性"""
    wps1 = json.dumps([{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}])
    temp_store.save_trajectory("traj_leg_18", "Robot_1", "原轨迹", wps1, 2.0)

    wps2 = json.dumps([{"x": 0.0, "y": 0.0}, {"x": 5.0, "y": 5.0}])
    temp_store.save_trajectory("traj_leg_18", "Robot_1", "更新后轨迹", wps2, 4.0)

    with temp_store.get_connection() as conn:
        row = conn.execute("SELECT * FROM trajectories WHERE traj_id = 'traj_leg_18'").fetchone()
        assert row["name"] == "更新后轨迹"
        assert row["duration"] == 4.0
        assert row["waypoints_json"] == wps2


def test_19_legacy_save_referenced_in_timeline_clips_rejected_by_default(temp_store):
    """19. 旧接口引用防护：被 timeline_clips 引用的轨迹默认拒绝覆盖，报错包含 ID 与计数"""
    wps1 = json.dumps([{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}])
    temp_store.save_trajectory("traj_leg_19", "Robot_1", "受保护轨迹", wps1, 2.0)
    temp_store.save_clip("clip_test_19", "Robot_1", "TRAJ", "traj_leg_19", 0, 2000)

    wps2 = json.dumps([{"x": 10.0, "y": 10.0}, {"x": 20.0, "y": 20.0}])
    with pytest.raises(ValueError, match="正被 1 处时间轴片段引用，默认禁止覆盖更新") as exc_info:
        temp_store.save_trajectory("traj_leg_19", "Robot_1", "恶意篡改", wps2, 5.0)
    assert "traj_leg_19" in str(exc_info.value)


def test_20_legacy_save_referenced_in_clips_table_rejected_by_default(temp_store):
    """20. 旧接口兼容防护：被历史 clips 表引用的轨迹同样受到拦截保护"""
    with temp_store.get_connection() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS clips (clip_id TEXT PRIMARY KEY, ref_id TEXT, robot_id TEXT)")
        conn.commit()

    wps1 = json.dumps([{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}])
    temp_store.save_trajectory("traj_leg_20", "Robot_1", "历史表保护轨迹", wps1, 2.0)

    with temp_store.get_connection() as conn:
        conn.execute("INSERT INTO clips (clip_id, ref_id, robot_id) VALUES ('c1', 'traj_leg_20', 'Robot_1')")
        conn.commit()

    with pytest.raises(ValueError, match="正被 1 处时间轴片段引用，默认禁止覆盖更新"):
        temp_store.save_trajectory("traj_leg_20", "Robot_1", "企图覆写", wps1, 3.0)


def test_21_legacy_save_referenced_allowed_when_flag_true(temp_store):
    """21. 旧接口强制覆盖：显式指定 allow_overwrite_referenced=True 时允许更新被引用素材"""
    wps1 = json.dumps([{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}])
    temp_store.save_trajectory("traj_leg_21", "Robot_1", "强制更新轨迹", wps1, 2.0)
    temp_store.save_clip("clip_test_21", "Robot_1", "TRAJ", "traj_leg_21", 0, 2000)

    wps2 = json.dumps([{"x": 2.0, "y": 3.0}, {"x": 4.0, "y": 5.0}])
    temp_store.save_trajectory("traj_leg_21", "Robot_1", "已强制更新", wps2, 6.0, allow_overwrite_referenced=True)

    with temp_store.get_connection() as conn:
        row = conn.execute("SELECT * FROM trajectories WHERE traj_id = 'traj_leg_21'").fetchone()
        assert row["name"] == "已强制更新"
        assert row["duration"] == 6.0


def test_22_legacy_save_preserves_foreign_key_and_no_deletion_cascade(temp_store):
    """22. REPLACE 语义修复审查：确保更新操作不触发外键级联删除或行重建"""
    with temp_store.get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS test_fk_subscribers (
                sub_id TEXT PRIMARY KEY,
                traj_id TEXT REFERENCES trajectories(traj_id) ON DELETE CASCADE
            )
        """)
        conn.commit()

    wps1 = json.dumps([{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}])
    temp_store.save_trajectory("traj_fk_22", "Robot_1", "外键父行", wps1, 2.0)

    with temp_store.get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("INSERT INTO test_fk_subscribers (sub_id, traj_id) VALUES ('sub_1', 'traj_fk_22')")
        conn.commit()

    # 更新父轨迹 (UPDATE 而非 INSERT OR REPLACE)
    wps2 = json.dumps([{"x": 0.0, "y": 0.0}, {"x": 3.0, "y": 3.0}])
    temp_store.save_trajectory("traj_fk_22", "Robot_1", "外键父行更新", wps2, 3.5, allow_overwrite_referenced=True)

    # 验证子表外键记录依然存在（若为 INSERT OR REPLACE 则先 DELETE 会导致子行被级联删除）
    with temp_store.get_connection() as conn:
        sub = conn.execute("SELECT * FROM test_fk_subscribers WHERE sub_id = 'sub_1'").fetchone()
        assert sub is not None
        assert sub["traj_id"] == "traj_fk_22"


def test_23_legacy_save_invalidates_asset_json_and_reconstructs(temp_store):
    """23. 写入后清空缓存：旧接口写入后 asset_json 为 NULL，重新读取能根据新点位确定性重建"""
    asset = _make_sample_asset("traj_inv_23", "原始Asset")
    temp_store.save_trajectory_asset(asset)

    # 旧接口覆写点位
    new_wps = json.dumps([{"x": 8.0, "y": 8.0}, {"x": 16.0, "y": 16.0}])
    temp_store.save_trajectory("traj_inv_23", "Robot_1", "旧接口刷新", new_wps, 4.0)

    with temp_store.get_connection() as conn:
        row = conn.execute("SELECT asset_json FROM trajectories WHERE traj_id = 'traj_inv_23'").fetchone()
        assert row["asset_json"] is None

    reconstructed = temp_store.load_trajectory_asset("traj_inv_23")
    assert reconstructed is not None
    assert reconstructed.control_points[0] == (8.0, 8.0)
    assert reconstructed.control_points[-1] == (16.0, 16.0)


def test_24_legacy_save_write_failure_rollback(temp_store, monkeypatch):
    """24. 旧接口事务安全：写入中途异常时事务完整回滚"""
    wps = json.dumps([{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 1.0}])
    orig_get_conn = temp_store.get_connection

    class BadConn:
        def __init__(self, real):
            self._real = real

        def __getattr__(self, name):
            return getattr(self._real, name)

        def execute(self, sql, *args, **kwargs):
            if "INSERT INTO trajectories" in sql or "UPDATE trajectories" in sql:
                raise sqlite3.OperationalError("模拟底层故障")
            return self._real.execute(sql, *args, **kwargs)

    import contextlib

    @contextlib.contextmanager
    def bad_conn():
        with orig_get_conn() as real:
            yield BadConn(real)

    monkeypatch.setattr(temp_store, "get_connection", bad_conn)
    with pytest.raises(sqlite3.OperationalError, match="模拟底层故障"):
        temp_store.save_trajectory("traj_fail_24", "Robot_1", "失败测试", wps, 2.0)

    monkeypatch.undo()
    with temp_store.get_connection() as conn:
        row = conn.execute("SELECT * FROM trajectories WHERE traj_id = 'traj_fail_24'").fetchone()
        assert row is None

