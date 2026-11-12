"""
@file: tests/unit/test_p2_map_and_2d_trajectory.py
@brief: P2 本地 PCD 地图管理、单机与群体 2D 轨迹闭环自动化测试集
@exports: 测试用例集合
"""
import os
import sqlite3
import numpy as np
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from src.application.stage_director.group_trajectory_controller import GroupTrajectoryController
from src.application.stage_director.stage_map_controller import StageMapController
from src.domain.map.stage_map_asset import (
    InvalidPcdFileError, StageMapAsset, UnsupportedPcdFormatError, validate_pcd_file
)
from src.domain.project.show_project import ShowProject
from src.domain.trajectory.group_trajectory import GroupTrajectory, GroupTrajectoryMember
from src.domain.trajectory.trajectory_asset import TrajectoryAsset, TrajectoryPoint
from src.domain.transform.stage_coordinate_transform import (
    CanvasTransformConfig, StageCoordinateTransform
)
from src.infrastructure.map.pcd_io_engine import PcdMapLoader
from src.infrastructure.storage.choreo_sqlite_store import ChoreoSqliteStore
from src.infrastructure.storage.group_trajectory_sqlite_adapter import GroupTrajectorySqliteAdapter
from src.infrastructure.storage.show_project_repository import ShowProjectRepository
from src.infrastructure.storage.stage_map_sqlite_adapter import StageMapSqliteAdapter
from src.infrastructure.storage.trajectory_sqlite_adapter import TrajectorySqliteAdapter
from src.ui.choreo_page.stage_canvas_2d import StageCanvas2D


@pytest.fixture
def test_env(tmp_path):
    db_file = str(tmp_path / "studio_p2_test.db")
    map_dir = str(tmp_path / "stage_maps")
    os.makedirs(map_dir, exist_ok=True)
    store = ChoreoSqliteStore(db_file)
    return {"db_file": db_file, "map_dir": map_dir, "store": store, "tmp_path": tmp_path}


def test_01_pcd_format_support_and_rejection(test_env):
    tmp = test_env["tmp_path"]

    # 1. 正常 ASCII PCD
    ascii_pcd = str(tmp / "sample_ascii.pcd")
    with open(ascii_pcd, "w", encoding="utf-8") as f:
        f.write("# .PCD v.7 - Point Cloud Data\nVERSION .7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\nWIDTH 3\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS 3\nDATA ascii\n0.0 0.0 0.0\n1.0 2.0 0.5\n-1.0 -2.0 0.2\n")

    pts = PcdMapLoader.load_pcd(ascii_pcd)
    assert len(pts) == 3
    assert pytest.approx(pts[1, 0]) == 1.0

    # 2. 正常 Binary PCD
    bin_pcd = str(tmp / "sample_binary.pcd")
    raw_data = np.array([[0.0, 0.0, 0.0], [2.0, 3.0, 1.0]], dtype=np.float32)
    header_str = "# .PCD v.7 - Point Cloud Data\nVERSION .7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\nWIDTH 2\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS 2\nDATA binary\n"
    with open(bin_pcd, "wb") as f:
        f.write(header_str.encode("utf-8"))
        f.write(raw_data.tobytes())

    pts_bin = PcdMapLoader.load_pcd(bin_pcd)
    assert len(pts_bin) == 2
    assert pytest.approx(pts_bin[1, 1]) == 3.0

    # 3. binary_compressed 格式必须被明确拒绝
    compressed_pcd = str(tmp / "sample_compressed.pcd")
    with open(compressed_pcd, "w", encoding="utf-8") as f:
        f.write("VERSION .7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\nWIDTH 1\nHEIGHT 1\nPOINTS 1\nDATA binary_compressed\n")
    with pytest.raises(UnsupportedPcdFormatError, match="binary_compressed PCD 暂不支持"):
        PcdMapLoader.load_pcd(compressed_pcd)

    # 4. 0 字节文件被拒绝
    empty_pcd = str(tmp / "empty.pcd")
    open(empty_pcd, "w").close()
    with pytest.raises(InvalidPcdFileError, match="为空"):
        validate_pcd_file(empty_pcd)


def test_02_map_controller_import_and_reference_protection(test_env):
    ctrl = StageMapController(db_path=test_env["db_file"], map_dir=test_env["map_dir"])
    tmp = test_env["tmp_path"]

    sample_pcd = str(tmp / "stage_arena.pcd")
    with open(sample_pcd, "w", encoding="utf-8") as f:
        f.write("VERSION .7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\nWIDTH 4\nHEIGHT 1\nPOINTS 4\nDATA ascii\n-5.0 -5.0 0.0\n5.0 -5.0 0.0\n5.0 5.0 0.0\n-5.0 5.0 0.0\n")

    # 导入
    asset = ctrl.import_pcd_file(sample_pcd, custom_name="中央演播大厅")
    assert asset.name == "中央演播大厅"
    assert asset.point_count == 4
    assert os.path.exists(asset.file_path)

    # 在用保护 1: 当前舞台正在加载的地图不可删
    ctrl.set_active_map_id(asset.map_id)
    ok, msg = ctrl.delete_map(asset.map_id)
    assert ok is False
    assert "正在加载" in msg

    # 在用保护 2: 绑定在 show_projects 中的地图不可删
    ctrl.set_active_map_id(None)
    proj_repo = ShowProjectRepository(test_env["db_file"])
    proj = ShowProject(project_id="proj_01", name="开场工程", current_map_id=asset.map_id)
    proj_repo.save_project(proj)

    ok2, msg2 = ctrl.delete_map(asset.map_id)
    assert ok2 is False
    assert "正在引用" in msg2

    # 解除工程引用后成功删除
    proj.current_map_id = ""
    proj_repo.save_project(proj)
    ok3, msg3 = ctrl.delete_map(asset.map_id)
    assert ok3 is True
    assert not os.path.exists(asset.file_path)


def test_03_single_robot_trajectory_2d_workflow(test_env):
    store = test_env["store"]
    canvas = StageCanvas2D(None, store=store)
    canvas.select_robot("Robot_1")
    canvas.set_draw_mode("DRAW_TRAJECTORY")

    # 屏幕中心 (400, 300) 对应世界 (0, 0)，缩放 scale=40px/m
    canvas.resize(800, 600)
    # 模拟增加控制点 (0, 0), (2, 0), (2, 3)
    p0 = canvas.stage_to_screen(0.0, 0.0)
    p1 = canvas.stage_to_screen(2.0, 0.0)
    p2 = canvas.stage_to_screen(2.0, 3.0)

    canvas._active_waypoints = [(0.0, 0.0), (2.0, 0.0), (2.0, 3.0)]
    assert canvas.finish_trajectory() is True

    # 验证完成后的轨迹在 _completed_trajectories
    assert len(canvas._completed_trajectories) >= 1
    traj = canvas._completed_trajectories[-1]
    traj_id = traj["id"]

    # 持久化到 SQLite
    assert canvas.save_current_trajectory(traj_id) is True

    # 重新从 SQLite 读取验证数据一致性
    reloaded_asset = TrajectorySqliteAdapter.load_asset(store, traj_id)
    assert reloaded_asset is not None
    assert len(reloaded_asset.control_points) == 3
    assert reloaded_asset.control_points[0] == (0.0, 0.0)
    assert reloaded_asset.control_points[2] == (2.0, 3.0)
    assert reloaded_asset.length_m > 4.5


def test_04_group_trajectory_derived_member_poses(test_env):
    store = test_env["store"]

    # 1. 先保存一条参考主干轨迹
    ref_asset = TrajectoryAsset(
        trajectory_id="ref_main_path",
        name="领航中心线",
        control_points=[(0.0, 0.0), (5.0, 0.0)],
        sampled_points=[
            TrajectoryPoint(0.0, 0.0, 0.0, 0.0),
            TrajectoryPoint(5.0, 0.0, 0.0, 5.0),
        ],
        length_m=5.0
    )
    TrajectorySqliteAdapter.save_asset(store, ref_asset)

    # 2. 建立包含 2 台机器人的群组与横队局部偏移 (Robot_1 在左 1m, Robot_2 在右 1m)
    m1 = GroupTrajectoryMember("Robot_1", offset_x_m=0.0, offset_y_m=1.0, delta_yaw_deg=0.0)
    m2 = GroupTrajectoryMember("Robot_2", offset_x_m=0.0, offset_y_m=-1.0, delta_yaw_deg=0.0)
    group = GroupTrajectory(
        group_trajectory_id="grp_line_01",
        name="双机横队",
        reference_trajectory_id="ref_main_path",
        members=(m1, m2)
    )

    # 3. 持久化并重读
    GroupTrajectorySqliteAdapter.save_group(store, group)
    loaded_group = GroupTrajectorySqliteAdapter.get_group(store, "grp_line_01")
    assert loaded_group is not None
    assert len(loaded_group.members) == 2
    assert loaded_group.members[0].robot_id == "Robot_1"
    assert loaded_group.members[0].offset_y_m == 1.0
    assert loaded_group.members[1].robot_id == "Robot_2"
    assert loaded_group.members[1].offset_y_m == -1.0
