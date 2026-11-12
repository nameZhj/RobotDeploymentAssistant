"""
@file: tests/unit/test_task05b_timeline_drag_drop_choreo.py
@brief: 任务 05B 动作与轨迹素材拖放到时间轴编排自动化测试用例集
@exports: 测试用例集
"""
import json
import os
import sqlite3
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QEvent, QMimeData, QPoint, Qt
from PySide6.QtGui import QDropEvent, QKeyEvent
from PySide6.QtWidgets import QApplication

from src.application.stage_director.timeline_choreo_controller import (
    TimelineChoreoController,
)
from src.domain.timeline.timeline_clip_asset import (
    TimelineClipAsset,
    TrackLayerType,
    compute_trajectory_duration_ms,
)
from src.infrastructure.storage.choreo_sqlite_store import ChoreoSqliteStore
from src.infrastructure.storage.timeline_clip_sqlite_adapter import (
    TimelineClipSqliteAdapter,
)
from src.infrastructure.storage.trajectory_sqlite_adapter import (
    TrajectorySqliteAdapter,
)
from src.ui.choreo_page.dual_layer_timeline_canvas import (
    DualLayerTimelineCanvas,
    TimelineBlock,
)
from src.ui.choreo_page.lib_panels_controller import LibPanelsController

# 保证 QApplication 全局单例
app = QApplication.instance() or QApplication([])


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_timeline_choreo.db")
    store = ChoreoSqliteStore(db_file)
    with store.get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO trajectories (traj_id, robot_group, name, waypoints_json, duration, created_at)
            VALUES ('traj_circle_01', 'Robot_1', '单机圆形轨迹', '[]', 4.5, 1000.0)
        """)
        conn.commit()
    return db_file


def test_01_timeline_clip_asset_validation():
    clip = TimelineClipAsset(
        clip_id="c1",
        robot_id="1",
        track_layer=TrackLayerType.ACTION,
        ref_id="550502",
        name="POPPING",
        start_ms=1000,
        duration_ms=2500,
    )
    clip.validate()
    assert clip.end_ms == 3500
    assert clip.start_s == 1.0
    assert clip.duration_s == 2.5

    d = clip.to_dict()
    assert d["clip_id"] == "c1"
    restored = TimelineClipAsset.from_dict(d)
    assert restored.clip_id == "c1"
    assert restored.track_layer == TrackLayerType.ACTION

    with pytest.raises(ValueError, match="Clip ID"):
        TimelineClipAsset(clip_id="", robot_id="1").validate()

    with pytest.raises(ValueError, match="robot_id"):
        TimelineClipAsset(clip_id="c2", robot_id="").validate()

    with pytest.raises(ValueError, match="非法的轨道子层级"):
        TimelineClipAsset(clip_id="c2", robot_id="1", track_layer="INVALID").validate()

    with pytest.raises(ValueError, match="起始时间必须 >= 0"):
        TimelineClipAsset(clip_id="c2", robot_id="1", start_ms=-10).validate()

    with pytest.raises(ValueError, match="过短"):
        TimelineClipAsset(clip_id="c2", robot_id="1", duration_ms=150).validate()

    with pytest.raises(ValueError, match="群组素材必须绑定至群组轨道"):
        TimelineClipAsset(clip_id="c3", robot_id="1", is_group=True).validate()


def test_02_time_semantics_trajectory_duration():
    # 弧长 5m, 速度 1m/s -> 5000ms
    assert compute_trajectory_duration_ms(5.0, 1.0) == 5000
    # 弧长 3m, 速度 0.5m/s -> 6000ms
    assert compute_trajectory_duration_ms(3.0, 0.5) == 6000
    # 距离过小时保证最小时长 500ms
    assert compute_trajectory_duration_ms(0.01, 1.0) == 500
    # 速度异常小保护
    assert compute_trajectory_duration_ms(1.0, 0.0) == int(1.0 / 0.05 * 1000)


def test_03_sqlite_adapter_crud_safety(temp_db):
    adapter = TimelineClipSqliteAdapter(temp_db)
    clip = TimelineClipAsset("clip_001", robot_id="1", track_layer=TrackLayerType.ACTION, ref_id="550502", name="Dance", start_ms=0, duration_ms=3000)
    adapter.save_clip(clip)

    retrieved = adapter.get_clip("clip_001")
    assert retrieved is not None
    assert retrieved.name == "Dance"
    assert retrieved.duration_ms == 3000

    # 再次保存相同 ID，执行 UPDATE 而不是 INSERT OR REPLACE
    clip.start_ms = 500
    adapter.save_clip(clip)
    assert adapter.get_clip("clip_001").start_ms == 500

    assert adapter.update_clip_position("clip_001", 1200) is True
    assert adapter.get_clip("clip_001").start_ms == 1200

    assert adapter.update_clip_duration("clip_001", 4000) is True
    assert adapter.get_clip("clip_001").duration_ms == 4000

    assert adapter.delete_clip("clip_001") is True
    assert adapter.get_clip("clip_001") is None


def test_04_controller_drop_action_on_single_robot(temp_db):
    ctrl = TimelineChoreoController(temp_db)
    asset_data = {"asset_type": "ACTION", "asset_id": "550502", "name": "POPPING", "duration": 3.86}
    ok, msg, clip = ctrl.create_clip_from_dropped_asset(asset_data, target_track_id="1", target_sub_layer=TrackLayerType.ACTION, start_ms=500)
    assert ok is True
    assert clip is not None
    assert clip.robot_id == "1"
    assert clip.track_layer == TrackLayerType.ACTION
    assert clip.start_ms == 500
    assert clip.duration_ms == 3860


def test_05_controller_drop_trajectory_on_single_robot(temp_db):
    ctrl = TimelineChoreoController(temp_db)
    asset_data = {"asset_type": "TRAJECTORY", "asset_id": "traj_circle_01", "name": "Circle", "length_m": 4.0, "recommended_speed_mps": 0.8}
    ok, msg, clip = ctrl.create_clip_from_dropped_asset(asset_data, target_track_id="2", target_sub_layer=TrackLayerType.TRAJECTORY, start_ms=1000)
    assert ok is True
    assert clip is not None
    assert clip.robot_id == "2"
    assert clip.track_layer == TrackLayerType.TRAJECTORY
    assert clip.start_ms == 1000
    assert clip.duration_ms == 5000  # 4.0 / 0.8 = 5.0s -> 5000ms


def test_06_controller_drop_group_trajectory_on_group_track(temp_db):
    ctrl = TimelineChoreoController(temp_db)
    asset_data = {"asset_type": "GROUP_TRAJECTORY", "asset_id": "grp_matrix_01", "name": "矩阵编队", "duration_ms": 6000}
    ok, msg, clip = ctrl.create_clip_from_dropped_asset(asset_data, target_track_id="GROUP", target_sub_layer=TrackLayerType.TRAJECTORY, start_ms=0)
    assert ok is True
    assert clip is not None
    assert clip.robot_id == "GROUP"
    assert clip.is_group is True
    assert clip.track_layer == TrackLayerType.TRAJECTORY
    assert clip.duration_ms == 6000


def test_07_controller_reject_cross_track_binding(temp_db):
    ctrl = TimelineChoreoController(temp_db)
    # 群组素材不可拖到单机轨道
    grp_data = {"asset_type": "GROUP_TRAJECTORY", "asset_id": "grp_01", "name": "GroupA"}
    ok, msg, clip = ctrl.create_clip_from_dropped_asset(grp_data, target_track_id="1", target_sub_layer=TrackLayerType.TRAJECTORY, start_ms=0)
    assert ok is False
    assert clip is None
    assert "群组轨迹素材必须放置于群组轨道" in msg

    # 单机素材不可拖到群组轨道
    single_data = {"asset_type": "TRAJECTORY", "asset_id": "traj_01", "name": "SingleTraj"}
    ok2, msg2, clip2 = ctrl.create_clip_from_dropped_asset(single_data, target_track_id="GROUP", target_sub_layer=TrackLayerType.TRAJECTORY, start_ms=0)
    assert ok2 is False
    assert clip2 is None
    assert "单机器人素材禁止直接绑定至群组编队轨道" in msg2


def test_08_controller_move_resize_delete_undo(temp_db):
    ctrl = TimelineChoreoController(temp_db)
    asset = {"asset_type": "ACTION", "asset_id": "550502", "name": "POPPING", "duration_ms": 2000, "allow_stretch": True}
    ok, _, clip = ctrl.create_clip_from_dropped_asset(asset, "1", TrackLayerType.ACTION, 0)
    cid = clip.clip_id

    # 移动
    assert ctrl.move_clip(cid, 1500) is True
    assert ctrl.get_clip(cid).start_ms == 1500

    # 拉伸
    assert ctrl.resize_clip(cid, 3500) is True
    assert ctrl.get_clip(cid).duration_ms == 3500

    # 撤销与恢复
    assert ctrl.undo() is True
    assert ctrl.get_clip(cid).duration_ms == 2000  # 回退到拉伸前
    assert ctrl.redo() is True
    assert ctrl.get_clip(cid).duration_ms == 3500  # 重做到拉伸后

    # 删除
    assert ctrl.delete_clip(cid) is True
    assert ctrl.get_clip(cid) is None


def test_09_database_persistence_and_reload(temp_db):
    ctrl1 = TimelineChoreoController(temp_db, task_name="演出任务A")
    asset = {"asset_type": "ACTION", "asset_id": "550502", "name": "演出开场", "duration_ms": 3000}
    ctrl1.create_clip_from_dropped_asset(asset, "1", TrackLayerType.ACTION, 200)

    # 重启模拟：使用新 controller 实例重新连接
    ctrl2 = TimelineChoreoController(temp_db, task_name="演出任务A")
    clips = ctrl2.list_clips()
    assert len(clips) == 1
    assert clips[0].name == "演出开场"
    assert clips[0].start_ms == 200
    assert clips[0].duration_ms == 3000


def test_10_reference_protection_prevents_trajectory_deletion(temp_db):
    store = ChoreoSqliteStore(temp_db)
    adapter = TimelineClipSqliteAdapter(temp_db)
    # 1. 建立时间轴 Clip 引用 traj_circle_01
    clip = TimelineClipAsset("clip_ref_test", robot_id="1", track_layer=TrackLayerType.TRAJECTORY, ref_id="traj_circle_01", name="圆形", start_ms=0, duration_ms=2000)
    adapter.save_clip(clip)

    # 2. 尝试删除该轨迹素材 -> 必须被引用保护拦截
    with pytest.raises(ValueError, match="正被时间轴引用"):
        TrajectorySqliteAdapter.delete_asset(store, "traj_circle_01")

    # 3. 删除时间轴 Clip
    adapter.delete_clip("clip_ref_test")

    # 4. 再次删除轨迹素材 -> 成功删除
    assert TrajectorySqliteAdapter.delete_asset(store, "traj_circle_01") is True


def test_11_dual_layer_timeline_canvas_drag_drop(temp_db):
    canvas = DualLayerTimelineCanvas(None)
    canvas.choreo_controller = TimelineChoreoController(temp_db)
    canvas.load_from_store()

    # 模拟放置动作素材
    asset = {"asset_type": "ACTION", "asset_id": "550502", "name": "测试动作", "duration_ms": 2500}
    ok, msg, clip = canvas.choreo_controller.create_clip_from_dropped_asset(asset, "1", TrackLayerType.ACTION, 300)
    assert ok is True
    canvas.load_from_store()

    # 检验 blocks
    matching = [b for b in canvas._blocks if b.block_id == clip.clip_id]
    assert len(matching) == 1
    assert matching[0].start_ms == 300
    assert matching[0].duration_ms == 2500

    # 模拟选中并删除
    canvas._selected_block = matching[0]
    canvas.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier))
    assert canvas.choreo_controller.get_clip(clip.clip_id) is None


def test_12_lib_panels_controller_metadata(temp_db):
    store = ChoreoSqliteStore(temp_db)
    with store.get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO actions (action_id, name, model_type, duration, anim_path) VALUES (?, ?, ?, ?, ?)",
            ("550502", "POPPING1", "A2-W", 38.62, "assets/motions/550502_popping1.npz"),
        )
        conn.commit()
    panel = LibPanelsController(None)
    panel.store = store
    panel.refresh_trajectories()
    panel.refresh_actions()

    assert panel.table_act.rowCount() >= 1
    item = panel.table_act.item(0, 0)
    data = item.data(Qt.UserRole)
    assert data["asset_type"] == "ACTION"
    assert data["asset_id"] == "550502"
    assert data["duration_ms"] > 0
