"""
@file: tests/unit/test_task04c_d4_group_trajectory_persistence.py
@brief: 任务 04C-D4 群组轨迹配置 SQLite 持久化、引用保护与事务回滚测试
@exports: 测试用例集
"""
import os
import sqlite3
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from src.application.stage_director.group_trajectory_controller import (
    GroupTrajectoryController,
)
from src.domain.trajectory.group_trajectory import GroupTrajectory, GroupTrajectoryMember
from src.domain.trajectory.trajectory_asset import TrajectoryAsset, TrajectoryPoint
from src.infrastructure.storage.choreo_sqlite_store import ChoreoSqliteStore
from src.infrastructure.storage.group_trajectory_sqlite_adapter import (
    GroupTrajectorySqliteAdapter,
)
from src.infrastructure.storage.trajectory_sqlite_adapter import (
    TrajectorySqliteAdapter,
)


@pytest.fixture
def temp_store(tmp_path):
    db_file = str(tmp_path / "test_persist_studio.db")
    store = ChoreoSqliteStore(db_file)
    with store.get_connection() as conn:
        conn.execute("""
            INSERT INTO trajectories (traj_id, robot_group, name, waypoints_json, duration, created_at)
            VALUES ('ref_existing_01', 'Robot_1', '已有单机轨迹', '[]', 10.0, 1000.0)
        """)
        conn.commit()
    return store


def _make_group(gid: str = "grp_test_01", ref_id: str = "ref_existing_01") -> GroupTrajectory:
    m1 = GroupTrajectoryMember("A", offset_x_m=0.5, offset_y_m=1.0, delta_yaw_deg=0.0)
    m2 = GroupTrajectoryMember("B", offset_x_m=-0.5, offset_y_m=-1.0, delta_yaw_deg=10.0)
    return GroupTrajectory(
        group_trajectory_id=gid,
        name="测试编队配置",
        reference_trajectory_id=ref_id,
        coordinate_frame="stage_world",
        members=(m1, m2),
    )


def test_01_save_and_get_group_config(temp_store):
    """1. 成功保存群组配置并在重启后精准恢复各成员相对偏移。"""
    group = _make_group()
    GroupTrajectorySqliteAdapter.save_group(temp_store, group)

    recovered = GroupTrajectorySqliteAdapter.get_group(temp_store, "grp_test_01")
    assert recovered is not None
    assert recovered.group_trajectory_id == "grp_test_01"
    assert recovered.name == "测试编队配置"
    assert recovered.reference_trajectory_id == "ref_existing_01"
    assert len(recovered.members) == 2
    assert recovered.members[0].robot_id == "A"
    assert recovered.members[0].offset_x_m == 0.5
    assert recovered.members[1].robot_id == "B"
    assert recovered.members[1].delta_yaw_deg == 10.0


def test_02_list_saved_groups(temp_store):
    """2. 能够按更新时间倒序列出保存的群组摘要清单。"""
    g1 = _make_group("grp_01")
    g2 = _make_group("grp_02")
    GroupTrajectorySqliteAdapter.save_group(temp_store, g1)
    GroupTrajectorySqliteAdapter.save_group(temp_store, g2)

    summaries = GroupTrajectorySqliteAdapter.list_groups(temp_store)
    assert len(summaries) == 2
    ids = [s["group_trajectory_id"] for s in summaries]
    assert "grp_01" in ids and "grp_02" in ids


def test_03_update_existing_group_without_insert_replace(temp_store):
    """3. 更新群组配置时使用确定性 UPDATE 语句，保留原有元数据。"""
    g = _make_group("grp_upd")
    GroupTrajectorySqliteAdapter.save_group(temp_store, g)

    # 修改配置后更新
    m_new = GroupTrajectoryMember("A", offset_x_m=2.0, offset_y_m=3.0)
    g_updated = GroupTrajectory(
        group_trajectory_id="grp_upd",
        name="已更新名称",
        reference_trajectory_id="ref_existing_01",
        members=(m_new,),
    )
    GroupTrajectorySqliteAdapter.save_group(temp_store, g_updated, allow_overwrite=True)

    loaded = GroupTrajectorySqliteAdapter.get_group(temp_store, "grp_upd")
    assert loaded.name == "已更新名称"
    assert len(loaded.members) == 1
    assert loaded.members[0].offset_x_m == 2.0


def test_04_prevent_overwrite_when_disallowed(temp_store):
    """4. 在不允许覆盖时，对已存在群组重复保存抛出异常。"""
    g = _make_group("grp_no_ow")
    GroupTrajectorySqliteAdapter.save_group(temp_store, g)
    with pytest.raises(ValueError, match="未授权覆盖"):
        GroupTrajectorySqliteAdapter.save_group(temp_store, g, allow_overwrite=False)


def test_05_delete_group_success(temp_store):
    """5. 能够正确删除指定的群组配置。"""
    g = _make_group("grp_del")
    GroupTrajectorySqliteAdapter.save_group(temp_store, g)
    assert GroupTrajectorySqliteAdapter.get_group(temp_store, "grp_del") is not None

    deleted = GroupTrajectorySqliteAdapter.delete_group(temp_store, "grp_del")
    assert deleted is True
    assert GroupTrajectorySqliteAdapter.get_group(temp_store, "grp_del") is None


def test_06_reject_nonexistent_reference_trajectory(temp_store):
    """6. 引用不存在的单机器人参考轨迹时原子回滚并拒绝创建群组。"""
    g_bad = _make_group(ref_id="nonexistent_ref_999")
    with pytest.raises(ValueError, match="不存在"):
        GroupTrajectorySqliteAdapter.save_group(temp_store, g_bad)


def test_07_reference_protection_on_referenced_single_trajectory(temp_store):
    """7. 被群组引用的单机器人参考轨迹，受 TrajectorySqliteAdapter 引用保护阻止删除。"""
    g = _make_group("grp_ref_test", ref_id="ref_existing_01")
    GroupTrajectorySqliteAdapter.save_group(temp_store, g)

    with temp_store.get_connection() as conn:
        refs = TrajectorySqliteAdapter.check_reference_count(conn, "ref_existing_01")
        assert refs >= 1

    # 尝试覆盖或删除该参考轨迹时默认被拒绝
    dummy_asset = TrajectoryAsset(trajectory_id="ref_existing_01", name="篡改", control_points=[(0, 0), (1, 1)])
    with pytest.raises(ValueError, match="正被.*引用"):
        TrajectorySqliteAdapter.save_asset(temp_store, dummy_asset, allow_overwrite_referenced=False)
