"""
@file: tests/unit/test_f02_map_and_rt.py
@brief: PCD 栅格地图三模渲染、膨胀与 SVD R/t 坐标标定精度单元测试
@exports: test_pcd_grid_pipeline, test_dilation_and_default_generation, test_rt_svd_and_trajectory_transforms
"""
import io
import math
import numpy as np
import pytest
from PIL import Image
from src.domain.map.pcd_grid_models import GridMapConfig
from src.domain.map.pcd_grid_service import generate_default_stage_pcd, pcd_file_to_grid_png, pcd_file_to_points
from src.domain.map.rt_calibration_solver import (
    RtCalibrationSolver, is_default_identity, solve_rt_from_pairs,
    transform_init_points, transform_trajectory_point_data
)


def test_pcd_grid_pipeline() -> None:
    # 1. 点云读取与降采样
    res = pcd_file_to_points("", max_points=2500)
    assert res.totalPoints <= 2500
    assert res.bounds.minX < res.bounds.maxX
    assert res.bounds.minY < res.bounds.maxY

    png_sig = b"\x89PNG\r\n\x1a\n"

    # 2. 模式 0: 障碍物二值灰度
    res0 = pcd_file_to_grid_png("", GridMapConfig(renderMode=0, resolution=10.0))
    assert res0.pngBytes.startswith(png_sig)
    img0 = Image.open(io.BytesIO(res0.pngBytes))
    assert img0.mode == "L"
    assert res0.originInfo.width == img0.width

    # 3. 模式 1: 高度灰度
    res1 = pcd_file_to_grid_png("", GridMapConfig(renderMode=1, resolution=10.0))
    assert res1.pngBytes.startswith(png_sig)
    img1 = Image.open(io.BytesIO(res1.pngBytes))
    assert img1.mode == "L"

    # 4. 模式 2: 伪彩原始 RGB
    res2 = pcd_file_to_grid_png("", GridMapConfig(renderMode=2, resolution=10.0))
    assert res2.pngBytes.startswith(png_sig)
    img2 = Image.open(io.BytesIO(res2.pngBytes))
    assert img2.mode == "RGB"


def test_dilation_and_default_generation(tmp_path) -> None:
    # 默认点云生成与缓存
    pcd_path = str(tmp_path / "stage_test.pcd")
    pts = generate_default_stage_pcd(pcd_path)
    assert len(pts) > 1000
    assert pts.shape[1] == 3

    # 膨胀半径对比
    res_no = pcd_file_to_grid_png(pcd_path, GridMapConfig(renderMode=0, dilationRadius=0.0, resolution=12.0))
    arr_no = np.array(Image.open(io.BytesIO(res_no.pngBytes)))
    obs_no = np.sum(arr_no == 0)

    res_dil = pcd_file_to_grid_png(pcd_path, GridMapConfig(renderMode=0, dilationRadius=0.45, resolution=12.0))
    arr_dil = np.array(Image.open(io.BytesIO(res_dil.pngBytes)))
    obs_dil = np.sum(arr_dil == 0)

    assert obs_dil > obs_no


def test_rt_svd_and_trajectory_transforms() -> None:
    # 1. 已知变换矩阵：旋转 +30 度，平移 (5.0, -3.0)
    theta = math.radians(30.0)
    c, s = math.cos(theta), math.sin(theta)
    tx_true, ty_true = 5.0, -3.0

    plan_pts = [(0.0, 0.0), (4.0, 0.0), (0.0, 3.0), (2.0, 2.0)]
    actual_pts = [(x * c - y * s + tx_true, x * s + y * c + ty_true) for x, y in plan_pts]

    rt_res = solve_rt_from_pairs(plan_pts, actual_pts)
    assert rt_res["is_valid"] is True
    assert rt_res["rmse"] < 1e-4
    assert abs(rt_res["yaw_deg"] - 30.0) < 1e-3
    assert abs(rt_res["t_vec"][0] - 5.0) < 1e-3
    assert abs(rt_res["t_vec"][1] - (-3.0)) < 1e-3

    # 共线点集触发告警
    collinear_p = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
    collinear_a = [(5.0, 5.0), (6.0, 5.0), (7.0, 5.0)]
    res_col = solve_rt_from_pairs(collinear_p, collinear_a)
    assert "共线" in res_col["warning"]

    # 2. 初始化点变换
    init_pts = [{"robot_id": 1, "x": 0.0, "y": 0.0, "yaw": 0.0}]
    trans_init = transform_init_points(init_pts, rt_res["r_mat"], rt_res["t_vec"])
    assert abs(trans_init[0]["x"] - 5.0) < 1e-3
    assert abs(trans_init[0]["y"] - (-3.0)) < 1e-3
    assert abs(trans_init[0]["yaw"] - 30.0) < 1e-2

    # 3. "0,x,y,yaw" 轨迹字符串变换
    traj_str = "0,0.0,0.0,0.0\n1,2.0,0.0,0.0"
    trans_traj = transform_trajectory_point_data(traj_str, rt_res["r_mat"], rt_res["t_vec"])
    lines = trans_traj.splitlines()
    assert len(lines) == 2
    p0 = [float(v) for v in lines[0].split(",")]
    assert abs(p0[1] - 5.0) < 1e-3
    assert abs(p0[2] - (-3.0)) < 1e-3

    # 4. 单位阵与 JSON 状态
    ident = RtCalibrationSolver.get_default_identity()
    assert RtCalibrationSolver.is_default_identity(ident["r_mat"], ident["t_vec"]) is True
    assert RtCalibrationSolver.is_default_identity(rt_res["r_mat"], rt_res["t_vec"]) is False
    json_str = RtCalibrationSolver.export_rt_json(rt_res)
    assert "r_mat" in json_str
    imported = RtCalibrationSolver.import_rt_json(json_str)
    assert abs(imported["yaw_deg"] - 30.0) < 1e-3

