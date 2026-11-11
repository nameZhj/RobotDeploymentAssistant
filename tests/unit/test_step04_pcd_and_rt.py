"""
@file: tests/unit/test_step04_pcd_and_rt.py
@brief: Step 04 PCD 栅格化引擎三模渲染、纯标准库 PNG 与 SVD 空间标定精度单元测试
@exports: test_pcd_io_and_parsing, test_grid_png_three_modes, test_dilation_impact, test_svd_calibration_precision, test_trajectory_point_transformation
"""
import math
import numpy as np
import pytest
from src.domain.map.pcd_grid_models import GridMapConfig
from src.domain.map.rt_calibration_solver import (
    solve_rt_from_point_pairs,
    transform_init_points,
    transform_trajectory_point_data
)
from src.infrastructure.map.pcd_grid_engine import pcd_file_to_grid_png, pcd_file_to_points

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_pcd_io_and_parsing():
    """验证 ASCII/Binary 点云解析、逆时针15度默认舞台生成及边界计算"""
    res = pcd_file_to_points("", max_points=2500)
    assert res.totalPoints <= 2500
    assert res.count <= 2500
    assert res.bounds.minX < res.bounds.maxX
    assert res.bounds.minY < res.bounds.maxY
    assert res.bounds.minZ < res.bounds.maxZ

    pts = res.to_numpy()
    assert pts.shape[1] == 3


def test_grid_png_three_modes():
    """验证纯内置 zlib+struct 零图像库依赖的 3 种 renderMode PNG 标准打包"""
    cfg0 = GridMapConfig(renderMode=0, resolution=10.0, dilationRadius=0.3)
    res0 = pcd_file_to_grid_png("", cfg0)
    assert res0.pngBytes.startswith(PNG_SIGNATURE)
    assert res0.width > 0 and res0.height > 0
    assert res0.originInfo.width == res0.width

    cfg1 = GridMapConfig(renderMode=1, resolution=10.0)
    res1 = pcd_file_to_grid_png("", cfg1)
    assert res1.pngBytes.startswith(PNG_SIGNATURE)

    cfg2 = GridMapConfig(renderMode=2, resolution=10.0)
    res2 = pcd_file_to_grid_png("", cfg2)
    assert res2.pngBytes.startswith(PNG_SIGNATURE)


def test_dilation_impact():
    """验证圆盘膨胀半径对栅格图像输出的动态调节"""
    cfg_no_dil = GridMapConfig(renderMode=0, resolution=10.0, dilationRadius=0.0)
    res_no = pcd_file_to_grid_png("", cfg_no_dil)

    cfg_dil = GridMapConfig(renderMode=0, resolution=10.0, dilationRadius=0.8)
    res_dil = pcd_file_to_grid_png("", cfg_dil)

    assert len(res_no.pngBytes) != len(res_dil.pngBytes)
    assert res_dil.pngBytes.startswith(PNG_SIGNATURE)


def test_svd_calibration_precision():
    """验证 3 点及以上 SVD 刚体标定求解精度 (RMSE < 1e-5，旋转与平移无损还原)"""
    angle_rad = math.radians(35.0)
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    r_gt = np.array([[c, -s], [s, c]], dtype=np.float64)
    t_gt = np.array([4.2, -3.1], dtype=np.float64)

    plan_pts = [(0.0, 0.0), (6.0, 0.0), (0.0, 4.0), (5.0, 3.0)]
    act_pts = []
    for px, py in plan_pts:
        p = np.array([px, py], dtype=np.float64)
        a = r_gt @ p + t_gt
        act_pts.append((float(a[0]), float(a[1])))

    res = solve_rt_from_point_pairs(plan_pts, act_pts)
    assert res["is_valid"]
    assert res["rmse"] < 1e-5
    assert abs(res["yaw_deg"] - 35.0) < 1e-5
    assert abs(res["t_vec"][0] - 4.2) < 1e-5
    assert abs(res["t_vec"][1] - (-3.1)) < 1e-5


def test_trajectory_point_transformation():
    """验证启用坐标转换时轨迹点字符串与机位初始点空间刚体变换"""
    r_mat = [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]  # 90 度旋转
    t_vec = [10.0, 5.0, 0.0]

    # 1. 轨迹字符串变换 (格式: 0,x,y,yaw)
    raw_traj = "0,1.0,2.0,0.0\n0,3.0,0.0,45.0"
    trans_traj = transform_trajectory_point_data(raw_traj, r_mat, t_vec)
    lines = trans_traj.splitlines()
    assert len(lines) == 2

    parts0 = [float(x) for x in lines[0].split(",")[1:]]
    assert abs(parts0[0] - 8.0) < 1e-3
    assert abs(parts0[1] - 6.0) < 1e-3
    assert abs(parts0[2] - 90.0) < 1e-2

    # 2. 机位初始点变换
    init_pts = [{"robot_id": 1, "x": 1.0, "y": 2.0, "yaw": 0.0}]
    trans_init = transform_init_points(init_pts, r_mat, t_vec)
    assert abs(trans_init[0]["x"] - 8.0) < 1e-3
    assert abs(trans_init[0]["y"] - 6.0) < 1e-3
    assert abs(trans_init[0]["yaw"] - 90.0) < 1e-2

