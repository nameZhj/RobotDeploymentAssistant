# @file: tests/test_phase11_pcd_and_svd.py
# @brief: Verification for ASCII/binary PCD parsing, large synthetic PCD streaming load, grid PNG output, and Kabsch SVD.
# @exports: test_ascii_and_binary_pcd_grid_generation, test_large_binary_pcd_streaming, test_kabsch_svd_2d_and_3d

from __future__ import annotations

import math
import os
import struct
import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.math.rigid_transform_svd import apply_rigid_2d, solve_kabsch_2d, solve_kabsch_3d
from src.persistence.pcd_grid_generator import generate_occupancy_grid_png
from src.persistence.pcd_parser import load_pcd, parse_pcd_header, write_ascii_pcd


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_ascii_and_binary_pcd_grid_generation(tmp_path) -> None:
    _app()
    pts = np.array([[0.0, 0.0, 0.0], [2.0, 0.5, 0.6], [-2.0, -1.0, 0.8], [3.5, 1.5, 1.2]], dtype=np.float32)
    asc_path = write_ascii_pcd(tmp_path / "sample.pcd", pts)
    cloud = load_pcd(asc_path, max_points=100)
    assert len(cloud.points_xyz) == 4
    grid = generate_occupancy_grid_png(cloud, tmp_path / "grid.png", resolution=0.1)
    assert (tmp_path / "grid.png").exists()
    assert grid.width_px >= 8 and grid.height_px >= 8

    # Binary PCD test
    bin_path = tmp_path / "bin_sample.pcd"
    header = (
        "VERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\n"
        f"WIDTH {len(pts)}\nHEIGHT 1\nPOINTS {len(pts)}\nDATA binary\n"
    ).encode("ascii")
    payload = b"".join(struct.pack("<fff", *row) for row in pts)
    bin_path.write_bytes(header + payload)
    bcloud = load_pcd(bin_path, max_points=100)
    assert np.allclose(bcloud.points_xyz, pts, atol=1e-4)


def test_large_binary_pcd_streaming(tmp_path) -> None:
    _app()
    rng = np.random.default_rng(42)
    pts = rng.uniform(low=[-10.0, -8.0, 0.2], high=[10.0, 8.0, 1.8], size=(25000, 3)).astype(np.float32)
    pcd_path = tmp_path / "large_synthetic.pcd"
    header = (
        "VERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\n"
        f"WIDTH {len(pts)}\nHEIGHT 1\nPOINTS {len(pts)}\nDATA binary\n"
    ).encode("ascii")
    pcd_path.write_bytes(header + pts.tobytes())
    hdr = parse_pcd_header(pcd_path)
    assert hdr.points == 25000
    cloud = load_pcd(pcd_path, max_points=5000)
    assert 1000 < len(cloud.points_xyz) <= 5500
    grid = generate_occupancy_grid_png(cloud, tmp_path / "large_map_grid.png", resolution=0.1)
    assert (tmp_path / "large_map_grid.png").exists()


def test_kabsch_svd_2d_and_3d() -> None:
    src = np.array([[0.0, 0.0], [2.0, 0.0], [2.0, 1.5], [0.0, 1.5]])
    ang = math.radians(37.0)
    rot_gt = np.array([[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]])
    t_gt = np.array([1.25, -0.85])
    dst = (rot_gt @ src.T).T + t_gt
    cal = solve_kabsch_2d(src, dst)
    assert cal.rmse_m < 1e-6
    assert abs(cal.yaw_deg - 37.0) < 1e-4
    assert np.allclose(apply_rigid_2d(src, cal.rot_2x2, cal.trans_2), dst, atol=1e-6)

    s3 = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 1.5]])
    d3 = np.column_stack([((rot_gt @ s3[:, :2].T).T + t_gt), s3[:, 2] + 0.5])
    r3, t3, rmse3 = solve_kabsch_3d(s3, d3)
    assert rmse3 < 1e-6 and r3.shape == (3, 3) and t3.shape == (3,)
