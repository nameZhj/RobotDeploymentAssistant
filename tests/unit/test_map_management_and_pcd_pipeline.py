"""
@file: tests/unit/test_map_management_and_pcd_pipeline.py
@brief: PCD 地图解析引擎、存储安全、异步导入与生命周期管道单元测试
@exports: test_pcd_loader_ascii_and_binary_parsers, test_pcd_rejection_of_invalid_and_compressed, test_map_storage_path_traversal_protection, test_map_import_lifecycle_and_deduplication, test_map_deletion_active_protection, test_map_export_and_rename
"""
import os
import struct
import pytest
import numpy as np

from src.application.stage_director.stage_map_controller import StageMapController
from src.core.pcd_loader import PcdLoader
from src.domain.map.map_storage_service import MapStorageService
from src.domain.map.stage_map_asset import (
    DuplicateMapError,
    InvalidPcdFileError,
    UnsupportedPcdFormatError,
    validate_pcd_file,
)
from src.infrastructure.storage.migration_engine import MigrationEngine
from src.infrastructure.storage.stage_map_sqlite_adapter import StageMapSqliteAdapter


def _create_ascii_pcd(path: str, points: list[tuple[float, float, float]]) -> None:
    lines = [
        "# .PCD v0.7 - Point Cloud Data",
        "VERSION 0.7",
        "FIELDS x y z",
        "SIZE 4 4 4",
        "TYPE F F F",
        "COUNT 1 1 1",
        f"WIDTH {len(points)}",
        "HEIGHT 1",
        "VIEWPOINT 0 0 0 1 0 0 0",
        f"POINTS {len(points)}",
        "DATA ascii",
    ]
    lines.extend(f"{p[0]} {p[1]} {p[2]}" for p in points)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _create_binary_pcd(path: str, points: list[tuple[float, float, float]]) -> None:
    header = (
        f"# .PCD v0.7\nVERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\n"
        f"WIDTH {len(points)}\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS {len(points)}\nDATA binary\n"
    )
    with open(path, "wb") as f:
        f.write(header.encode("utf-8"))
        for p in points:
            f.write(struct.pack("fff", p[0], p[1], p[2]))


def test_pcd_loader_ascii_and_binary_parsers(tmp_path):
    """验证 ASCII 与 Binary 双编码 PCD 点云解析的一致性与坐标正确性"""
    pts = [(1.0, 2.0, 3.0), (-4.0, 5.5, 0.0), (0.0, -1.2, 8.0)]
    ascii_file = str(tmp_path / "test_ascii.pcd")
    bin_file = str(tmp_path / "test_bin.pcd")

    _create_ascii_pcd(ascii_file, pts)
    _create_binary_pcd(bin_file, pts)

    data_ascii = PcdLoader.load_pcd(ascii_file)
    data_bin = PcdLoader.load_pcd(bin_file)

    assert data_ascii.point_count == 3
    assert data_bin.point_count == 3
    np.testing.assert_allclose(data_ascii.points, data_bin.points, rtol=1e-5)
    assert data_ascii.bounds["min_x"] == -4.0
    assert data_ascii.bounds["max_x"] == 1.0


def test_pcd_rejection_of_invalid_and_compressed(tmp_path):
    """验证非法 PCD 头部、空文件、缺少 XYZ 字段以及 binary_compressed 的明确拒绝"""
    # 1. 空文件
    empty_file = str(tmp_path / "empty.pcd")
    open(empty_file, "w").close()
    with pytest.raises(InvalidPcdFileError, match="为空"):
        validate_pcd_file(empty_file)

    # 2. 缺失 XYZ 字段
    bad_fields_file = str(tmp_path / "no_xyz.pcd")
    with open(bad_fields_file, "w") as f:
        f.write("VERSION 0.7\nFIELDS intensity\nSIZE 4\nTYPE F\nCOUNT 1\nWIDTH 1\nHEIGHT 1\nPOINTS 1\nDATA ascii\n100\n")
    with pytest.raises(InvalidPcdFileError, match="缺少必要的三维空间字段"):
        validate_pcd_file(bad_fields_file)

    # 3. binary_compressed
    comp_file = str(tmp_path / "comp.pcd")
    with open(comp_file, "w") as f:
        f.write("VERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\nWIDTH 1\nHEIGHT 1\nPOINTS 1\nDATA binary_compressed\n")
    with pytest.raises(UnsupportedPcdFormatError, match="binary_compressed"):
        validate_pcd_file(comp_file)


def test_map_storage_path_traversal_protection(tmp_path):
    """验证 MapStorageService 对 ../ 路径逃逸的越界访问拦截"""
    storage = MapStorageService(base_dir=str(tmp_path / "managed_maps"))
    safe_target = storage.resolve_safe_path("stage_1.pcd")
    assert safe_target.startswith(str(tmp_path / "managed_maps"))

    with pytest.raises(PermissionError, match="检测到路径遍历非法访问"):
        storage.resolve_safe_path("../../windows/system32/cmd.exe")


def test_map_import_lifecycle_and_deduplication(tmp_path):
    """验证地图从源文件导入、哈希计算、防重校验与原子持久化全链路"""
    db_file = str(tmp_path / "test_choreo.db")
    map_dir = str(tmp_path / "managed_maps")
    adapter = StageMapSqliteAdapter(db_path=db_file)
    with adapter.get_connection() as conn:
        MigrationEngine.apply_all(conn)

    ctrl = StageMapController(db_path=db_file, map_dir=map_dir)
    src_pcd = str(tmp_path / "src_sample.pcd")
    _create_ascii_pcd(src_pcd, [(0.0, 0.0, 0.0), (1.0, 1.0, 0.5), (2.0, 0.0, 1.0)])

    # 首次导入
    asset1 = ctrl.import_pcd_file(src_pcd, custom_name="主舞台A")
    assert asset1.name == "主舞台A"
    assert asset1.point_count == 3
    assert len(asset1.sha256) == 64
    assert os.path.exists(asset1.file_path)

    # 重复导入相同文件拦截
    with pytest.raises(DuplicateMapError, match="已存在相同哈希"):
        ctrl.import_pcd_file(src_pcd, custom_name="主舞台A_重名", check_duplicate=True, allow_duplicate=False)

    # 允许作为副本导入
    asset2 = ctrl.import_pcd_file(src_pcd, custom_name="主舞台A_副本", allow_duplicate=True)
    assert asset2.map_id != asset1.map_id
    assert len(ctrl.list_maps()) == 2


def test_map_deletion_active_protection(tmp_path):
    """验证地图删除时的活跃保护机制与非活跃安全删除"""
    db_file = str(tmp_path / "test_choreo.db")
    map_dir = str(tmp_path / "managed_maps")
    adapter = StageMapSqliteAdapter(db_path=db_file)
    with adapter.get_connection() as conn:
        MigrationEngine.apply_all(conn)

    ctrl = StageMapController(db_path=db_file, map_dir=map_dir)
    src_pcd = str(tmp_path / "stage_active.pcd")
    _create_ascii_pcd(src_pcd, [(0.0, 0.0, 0.0)])
    asset = ctrl.import_pcd_file(src_pcd, custom_name="演播厅地图")

    # 设为活跃地图时尝试删除被拦截
    ctrl.set_active_map_id(asset.map_id)
    ok, msg = ctrl.delete_map(asset.map_id)
    assert not ok
    assert "正在加载该地图" in msg

    # 卸载后成功删除，物理文件同步移除
    ctrl.unload_map()
    ok, msg = ctrl.delete_map(asset.map_id)
    assert ok
    assert not os.path.exists(asset.file_path)
    assert ctrl.get_map(asset.map_id) is None


def test_map_export_and_rename(tmp_path):
    """验证地图导出完整副本与安全重命名功能"""
    db_file = str(tmp_path / "test_choreo.db")
    map_dir = str(tmp_path / "managed_maps")
    adapter = StageMapSqliteAdapter(db_path=db_file)
    with adapter.get_connection() as conn:
        MigrationEngine.apply_all(conn)

    ctrl = StageMapController(db_path=db_file, map_dir=map_dir)
    src_pcd = str(tmp_path / "orig.pcd")
    _create_ascii_pcd(src_pcd, [(1.0, 2.0, 3.0)])
    asset = ctrl.import_pcd_file(src_pcd, custom_name="原始名")

    # 重命名
    assert ctrl.rename_map(asset.map_id, "修改后名称")
    updated = ctrl.get_map(asset.map_id)
    assert updated.name == "修改后名称"

    # 导出副本
    export_dest = str(tmp_path / "exported" / "backup.pcd")
    ctrl.export_map(asset.map_id, export_dest)
    assert os.path.exists(export_dest)
    exported_data = PcdLoader.load_pcd(export_dest)
    assert exported_data.point_count == 1
