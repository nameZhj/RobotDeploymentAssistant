"""
@file: tests/unit/test_task05a_pcd_map_management.py
@brief: 微任务 05A 本地 PCD 地图导入、管理、在用删除保护与加载到舞台全套单元测试
@exports: 全套 05A 自动化验收测试用例
"""
import os
import shutil
import time
import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from src.application.stage_director.stage_map_controller import StageMapController
from src.application.stage_director.stage_map_worker import (
    StageMapImportWorker,
    StageMapLoadWorker,
)
from src.domain.map.stage_map_asset import (
    InvalidPcdFileError,
    StageMapAsset,
    UnsupportedPcdFormatError,
    validate_pcd_file,
)
from src.infrastructure.map.pcd_io_engine import PcdMapLoader
from src.infrastructure.storage.stage_map_sqlite_adapter import (
    StageMapSqliteAdapter,
    atomic_copy_pcd,
)
from src.ui.choreo_page.stage_canvas_2d import StageCanvas2D
from src.ui.dialogs.stage_map_dialog import StageMapDialog
from src.ui.map_page.navigation_map_page import NavigationMapPage
from src.ui.windows.main_studio_window import MainStudioWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def temp_env(tmp_path):
    db_path = str(tmp_path / "test_studio_data.db")
    map_dir = str(tmp_path / "stage_maps")
    os.makedirs(map_dir, exist_ok=True)
    return db_path, map_dir


def create_sample_ascii_pcd(file_path: str, points_count: int = 20) -> str:
    lines = [
        "# .PCD v.7 - Point Cloud Data\n",
        "VERSION .7\n",
        "FIELDS x y z\n",
        "SIZE 4 4 4\n",
        "TYPE F F F\n",
        "COUNT 1 1 1\n",
        f"WIDTH {points_count}\n",
        "HEIGHT 1\n",
        "VIEWPOINT 0 0 0 1 0 0 0\n",
        f"POINTS {points_count}\n",
        "DATA ascii\n",
    ]
    for i in range(points_count):
        x = round(float(i * 0.5 - 5.0), 3)
        y = round(float(np.sin(i * 0.4) * 3.0), 3)
        z = round(float(0.5 + (i % 5) * 0.2), 3)
        lines.append(f"{x} {y} {z}\n")
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return file_path


def create_sample_compressed_pcd(file_path: str) -> str:
    content = (
        "# .PCD v.7 - Point Cloud Data\n"
        "VERSION .7\n"
        "FIELDS x y z\n"
        "SIZE 4 4 4\n"
        "TYPE F F F\n"
        "COUNT 1 1 1\n"
        "WIDTH 10\n"
        "HEIGHT 1\n"
        "VIEWPOINT 0 0 0 1 0 0 0\n"
        "POINTS 10\n"
        "DATA binary_compressed\n"
        "FAKE_COMPRESSED_DATA_BYTES"
    )
    with open(file_path, "wb") as f:
        f.write(content.encode("utf-8"))
    return file_path


# 1. 成功导入合法 ASCII 与 Binary PCD
def test_01_import_valid_ascii_and_binary_pcd(temp_env, tmp_path):
    db_path, map_dir = temp_env
    controller = StageMapController(db_path=db_path, map_dir=map_dir)

    # ASCII PCD
    ascii_src = str(tmp_path / "stage_north.pcd")
    create_sample_ascii_pcd(ascii_src, points_count=30)
    asset_ascii = controller.import_pcd_file(ascii_src, custom_name="北区舞台")
    assert asset_ascii.name == "北区舞台"
    assert asset_ascii.point_count == 30
    assert os.path.exists(asset_ascii.file_path)
    assert asset_ascii.file_size_bytes > 0
    assert asset_ascii.width > 0
    assert asset_ascii.height > 0

    # Binary PCD
    bin_src = str(tmp_path / "stage_south.pcd")
    pts = np.array([[1.0, 2.0, 0.5], [3.0, 4.0, 0.8], [-2.0, 1.0, 1.2]], dtype=np.float32)
    PcdMapLoader.save_binary(bin_src, pts)
    asset_bin = controller.import_pcd_file(bin_src, custom_name="南区展厅")
    assert asset_bin.name == "南区展厅"
    assert asset_bin.point_count == 3
    assert os.path.exists(asset_bin.file_path)


# 2. 无效或损坏 PCD 拒绝导入
def test_02_invalid_or_corrupt_pcd_rejected(temp_env, tmp_path):
    db_path, map_dir = temp_env
    controller = StageMapController(db_path=db_path, map_dir=map_dir)

    # 缺少 FIELDS
    corrupt_src = str(tmp_path / "corrupt.pcd")
    with open(corrupt_src, "w") as f:
        f.write("# .PCD v.7\nVERSION .7\nPOINTS 10\nDATA ascii\n1 2 3\n")
    with pytest.raises(InvalidPcdFileError):
        controller.import_pcd_file(corrupt_src)

    # 非 .pcd 扩展名
    txt_file = str(tmp_path / "wrong_ext.txt")
    with open(txt_file, "w") as f:
        f.write("hello")
    with pytest.raises(InvalidPcdFileError):
        controller.import_pcd_file(txt_file)


# 3. binary_compressed PCD 拒绝导入并给出明确提示
def test_03_binary_compressed_pcd_rejected(temp_env, tmp_path):
    db_path, map_dir = temp_env
    controller = StageMapController(db_path=db_path, map_dir=map_dir)

    comp_src = str(tmp_path / "compressed.pcd")
    create_sample_compressed_pcd(comp_src)
    with pytest.raises(UnsupportedPcdFormatError) as exc_info:
        controller.import_pcd_file(comp_src)
    assert "binary_compressed" in str(exc_info.value)


# 4. 空文件与不存在文件拦截
def test_04_empty_or_nonexistent_file_rejected(temp_env, tmp_path):
    db_path, map_dir = temp_env
    controller = StageMapController(db_path=db_path, map_dir=map_dir)

    # 文件不存在
    with pytest.raises(FileNotFoundError):
        controller.import_pcd_file(str(tmp_path / "not_exist.pcd"))

    # 空文件
    empty_src = str(tmp_path / "empty.pcd")
    with open(empty_src, "wb") as f:
        pass
    with pytest.raises(InvalidPcdFileError) as exc_info:
        controller.import_pcd_file(empty_src)
    assert "空" in str(exc_info.value)


# 5. 重复导入与同名文件处理
def test_05_duplicate_and_same_name_pcd_handled_cleanly(temp_env, tmp_path):
    db_path, map_dir = temp_env
    controller = StageMapController(db_path=db_path, map_dir=map_dir)

    src1 = str(tmp_path / "arena.pcd")
    create_sample_ascii_pcd(src1, points_count=10)
    asset1 = controller.import_pcd_file(src1, custom_name="场馆1")

    # 再次导入同名文件（不覆盖已存在物理文件，生成独立副本与唯一记录）
    asset2 = controller.import_pcd_file(src1, custom_name="场馆2")
    assert asset1.map_id != asset2.map_id
    assert asset1.file_path != asset2.file_path
    assert os.path.exists(asset1.file_path)
    assert os.path.exists(asset2.file_path)


# 6. 地图列表与元信息读取
def test_06_list_maps_and_metadata_verification(temp_env, tmp_path):
    db_path, map_dir = temp_env
    controller = StageMapController(db_path=db_path, map_dir=map_dir)

    src = str(tmp_path / "auditorium.pcd")
    create_sample_ascii_pcd(src, points_count=25)
    controller.import_pcd_file(src, custom_name="大会堂")

    maps = controller.list_maps()
    assert len(maps) == 1
    m = maps[0]
    assert m.name == "大会堂"
    assert m.point_count == 25
    assert "KB" in m.formatted_file_size() or "B" in m.formatted_file_size()
    assert "m" in m.formatted_dimensions()


# 7. 删除地图与数据库一致性
def test_07_delete_map_consistency(temp_env, tmp_path):
    db_path, map_dir = temp_env
    controller = StageMapController(db_path=db_path, map_dir=map_dir)

    src = str(tmp_path / "to_delete.pcd")
    create_sample_ascii_pcd(src, points_count=10)
    asset = controller.import_pcd_file(src, custom_name="待删除地图")
    target_path = asset.file_path
    assert os.path.exists(target_path)

    ok, msg = controller.delete_map(asset.map_id)
    assert ok is True
    assert not os.path.exists(target_path)
    assert controller.get_map(asset.map_id) is None
    assert len(controller.list_maps()) == 0


# 8. 当前加载地图删除保护
def test_08_active_loaded_map_deletion_protected(temp_env, tmp_path):
    db_path, map_dir = temp_env
    controller = StageMapController(db_path=db_path, map_dir=map_dir)

    src = str(tmp_path / "stage_live.pcd")
    create_sample_ascii_pcd(src, points_count=15)
    asset = controller.import_pcd_file(src, custom_name="正在使用的舞台")

    # 加载到舞台
    img, info, meta = controller.load_map_to_stage(asset.map_id)
    assert controller.get_active_map_id() == asset.map_id

    # 尝试删除在用地图：严格拦截！
    ok, err = controller.delete_map(asset.map_id)
    assert ok is False
    assert "正在加载" in err
    assert os.path.exists(asset.file_path)
    assert controller.get_map(asset.map_id) is not None

    # 卸载后再删除：允许
    controller.unload_map()
    assert controller.get_active_map_id() is None
    ok2, _ = controller.delete_map(asset.map_id)
    assert ok2 is True
    assert not os.path.exists(asset.file_path)


# 9. 程序重启后地图仍存在
def test_09_persistence_survives_restart(temp_env, tmp_path):
    db_path, map_dir = temp_env
    c1 = StageMapController(db_path=db_path, map_dir=map_dir)
    src = str(tmp_path / "persistent.pcd")
    create_sample_ascii_pcd(src, points_count=18)
    asset1 = c1.import_pcd_file(src, custom_name="持久化地图")

    # 模拟应用重启，实例化新控制器
    c2 = StageMapController(db_path=db_path, map_dir=map_dir)
    loaded = c2.get_map(asset1.map_id)
    assert loaded is not None
    assert loaded.name == "持久化地图"
    assert loaded.point_count == 18
    assert os.path.exists(loaded.file_path)


# 10. 地图加载到 2D 舞台画布，坐标与图层完整性
def test_10_load_map_to_stage_canvas_preserves_trajectories(qapp, temp_env, tmp_path):
    db_path, map_dir = temp_env
    controller = StageMapController(db_path=db_path, map_dir=map_dir)

    src = str(tmp_path / "visual_stage.pcd")
    create_sample_ascii_pcd(src, points_count=20)
    asset = controller.import_pcd_file(src, custom_name="视觉验证舞台")

    canvas = StageCanvas2D()
    # 模拟已有机器人轨迹
    canvas._completed_trajectories = [{"id": "traj_01", "name": "轨迹1", "waypoints": [(0.0, 0.0), (2.0, 2.0)]}]

    # 加载地图
    img, info, meta = controller.load_map_to_stage(asset.map_id)
    assert isinstance(img, QImage)
    assert img.width() > 0 and img.height() > 0
    assert "origin_x" in info and "resolution" in info

    canvas.set_grid_data(img, info, meta)
    assert canvas._grid_image is not None
    assert canvas._grid_info == info
    # 验证单机器人已有轨迹图层未被清空
    assert len(canvas._completed_trajectories) == 1
    assert canvas._completed_trajectories[0]["name"] == "轨迹1"

    # 卸载地图
    canvas.set_grid_data(None, None, None)
    assert canvas._grid_image is None
    assert canvas._grid_info is None
    assert len(canvas._completed_trajectories) == 1


# 11. 异步后台工作器与取消支持
def test_11_async_workers_threading_and_cancellation(qapp, temp_env, tmp_path):
    db_path, map_dir = temp_env
    controller = StageMapController(db_path=db_path, map_dir=map_dir)
    src = str(tmp_path / "async_pcd.pcd")
    create_sample_ascii_pcd(src, points_count=15)

    # 1. 导入工作器
    worker_import = StageMapImportWorker(controller, src, "异步导入")
    result_asset = []
    worker_import.finished.connect(lambda a: result_asset.append(a))
    worker_import.run()
    assert len(result_asset) == 1
    asset = result_asset[0]

    # 2. 加载工作器
    worker_load = StageMapLoadWorker(controller, asset.map_id)
    load_results = []
    worker_load.finished.connect(lambda img, inf, m: load_results.append((img, inf, m)))
    worker_load.run()
    assert len(load_results) == 1
    img, info, meta = load_results[0]
    assert img is not None

    # 3. 取消支持
    worker_cancel = StageMapImportWorker(controller, src, "取消测试")
    worker_cancel.cancel()
    cancelled_results = []
    worker_cancel.finished.connect(lambda a: cancelled_results.append(a))
    worker_cancel.run()
    assert len(cancelled_results) == 0


# 12. 导入失败不留下半成品文件
def test_12_failed_import_leaves_no_debris(temp_env, tmp_path):
    db_path, map_dir = temp_env
    controller = StageMapController(db_path=db_path, map_dir=map_dir)

    corrupt_src = str(tmp_path / "broken.pcd")
    with open(corrupt_src, "w") as f:
        f.write("# .PCD v.7\nVERSION .7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\nWIDTH 0\nPOINTS 0\nDATA ascii\n")

    files_before = set(os.listdir(map_dir))
    with pytest.raises(InvalidPcdFileError):
        controller.import_pcd_file(corrupt_src)
    files_after = set(os.listdir(map_dir))
    # 确保没有留下 .tmp 或未注册孤儿文件
    assert files_before == files_after


# 13. 不影响现有 NavigationMapPage
def test_13_navigation_map_page_no_regression(qapp):
    nav_page = NavigationMapPage()
    assert nav_page.feature == "RADAR_MAPPING"
    assert nav_page.selected_robot is None
    assert nav_page.is_mapping is False

    nav_page._on_feature_changed("GRID_MAP")
    assert nav_page.feature == "GRID_MAP"
    nav_page._on_feature_changed("CALIBRATION")
    assert nav_page.feature == "CALIBRATION"
    assert not nav_page.frame_calib.isHidden()


# 14. StageMapDialog UI 交互与信号联动
def test_14_stage_map_dialog_ui_and_signals(qapp, temp_env, tmp_path):
    db_path, map_dir = temp_env
    controller = StageMapController(db_path=db_path, map_dir=map_dir)

    src = str(tmp_path / "dialog_test.pcd")
    create_sample_ascii_pcd(src, points_count=12)
    asset = controller.import_pcd_file(src, custom_name="弹窗测试地图")

    dlg = StageMapDialog(controller=controller)
    assert dlg.list_maps.count() == 1
    assert "弹窗测试地图" in dlg.list_maps.item(0).text()
    assert dlg.lbl_name.text() == "弹窗测试地图"
    assert "12 点" in dlg.lbl_points.text()

    loaded_payload = []
    dlg.mapLoadedToStage.connect(lambda img, inf, m: loaded_payload.append(m))
    dlg._on_load_success(QImage(), {}, {"name": "弹窗测试地图", "map_id": asset.map_id})
    assert len(loaded_payload) == 1
    assert loaded_payload[0]["name"] == "弹窗测试地图"

    unloaded = []
    dlg.mapUnloadedFromStage.connect(lambda: unloaded.append(True))
    dlg._on_unload_clicked()
    assert len(unloaded) == 1
    assert controller.get_active_map_id() is None


# 15. MainStudioWindow 工具栏载入地图与 2D/Dock 联动
def test_15_main_studio_window_map_integration(qapp, temp_env, tmp_path):
    win = MainStudioWindow()
    assert hasattr(win, "map_controller")
    assert win.toolbar.btn_load_map is not None

    meta = {
        "name": "演播厅实测地图",
        "map_file": "studio_test.pcd",
        "dimensions": "30.0m × 20.0m",
        "resolution": 0.05,
        "origin": "(0.0, 0.0)",
        "status": "已加载 (Loaded)",
    }
    dummy_img = QImage(100, 100, QImage.Format_RGBA8888)
    dummy_info = {"origin_x": -5.0, "origin_y": -5.0, "resolution": 0.05, "width": 100, "height": 100}

    win.stage_2d.set_grid_data(dummy_img, dummy_info, meta)
    assert win.stage_2d._grid_image is not None
    assert win.stage_dock.lbl_scene_name.text() == "演播厅实测地图"
    assert win.stage_dock.lbl_map_file.text() == "studio_test.pcd"
    assert win.stage_dock.lbl_dimensions.text() == "30.0m × 20.0m"

    # 卸载地图
    win.stage_2d.set_grid_data(None, None, None)
    assert win.stage_2d._grid_image is None


