"""
@file: tests/compatibility/test_map_data_contracts.py
@brief: PCD 地图解析与空间坐标契约测试 (2026-10-01 前基线)
@exports: test_pcd_loader_ascii_format, test_pcd_loader_rejects_missing_file
"""
import os
import pytest
from src.core.pcd_loader import PcdLoader


def test_pcd_loader_ascii_format(tmp_path):
    """验证标准 ASCII PCD 地图文件解析，包含点坐标、边界与点数量契约。"""
    sample_pcd = tmp_path / "stage_test.pcd"
    content = (
        "# .PCD v0.7 - Point Cloud Data\n"
        "VERSION 0.7\n"
        "FIELDS x y z\n"
        "SIZE 4 4 4\n"
        "TYPE F F F\n"
        "COUNT 1 1 1\n"
        "WIDTH 3\n"
        "HEIGHT 1\n"
        "VIEWPOINT 0 0 0 1 0 0 0\n"
        "POINTS 3\n"
        "DATA ascii\n"
        "-2.5 1.0 0.0\n"
        "0.0 0.0 0.2\n"
        "2.5 -1.0 0.5\n"
    )
    sample_pcd.write_text(content, encoding="utf-8")

    data = PcdLoader.load_pcd(str(sample_pcd))
    assert data.point_count == 3
    assert data.points.shape == (3, 3)
    assert data.bounds["min_x"] == -2.5
    assert data.bounds["max_x"] == 2.5
    assert data.bounds["min_y"] == -1.0
    assert data.bounds["max_y"] == 1.0


def test_pcd_loader_rejects_missing_file():
    """验证当 PCD 文件不存在时抛出标准 FileNotFoundError，不静默假装成功。"""
    with pytest.raises(FileNotFoundError):
        PcdLoader.load_pcd("non_existent_map_file.pcd")
