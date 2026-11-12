"""
@file: tests/unit/test_f03_rt_calibration.py
@brief: 空间坐标 R/t 三点标定解算、单位阵识别与轨迹数据转换单元测试
@exports: test_svd_3point_and_multipoint_calibration, test_identity_check_and_reset, test_pose_and_trajectory_transformation
"""
import math
import pytest
from src.domain.map.rt_calibration_engine import RtCalibrationEngine, rt_calibration_engine


def test_svd_3point_and_multipoint_calibration() -> None:
    engine = RtCalibrationEngine()

    # 1. 验证少于 3 个点抛出异常
    with pytest.raises(ValueError, match="至少需要 3 组点对"):
        engine.solve_rt_from_point_pairs([(0.0, 0.0), (1.0, 1.0)], [(0.0, 0.0), (1.0, 1.0)])

    # 2. 构造已知刚体变换：旋转 +45 度，平移 (3.0, -2.0)
    theta = math.radians(45.0)
    c, s = math.cos(theta), math.sin(theta)
    tx_true, ty_true = 3.0, -2.0

    plan_pts = [
        (0.0, 0.0),
        (5.0, 0.0),
        (0.0, 4.0),
        (3.0, 3.0),
        (-2.0, 1.0)
    ]

    actual_pts = [
        (x * c - y * s + tx_true, x * s + y * c + ty_true)
        for x, y in plan_pts
    ]

    res = engine.solve_rt_from_point_pairs(plan_pts, actual_pts)
    assert res.is_valid is True
    assert res.rmse < 1e-5
    assert abs(res.yaw_deg - 45.0) < 1e-4
    assert abs(res.t_vec[0] - 3.0) < 1e-4
    assert abs(res.t_vec[1] - (-2.0)) < 1e-4
    assert engine.needs_grid_regenerate is True

    # 3. 验证近乎共线点集的警告信息
    collinear_plan = [(0.0, 0.0), (1.0, 0.00001), (2.0, 0.0)]
    collinear_actual = [(1.0, 2.0), (2.0, 2.0), (3.0, 2.0)]
    res_warn = engine.solve_rt_from_point_pairs(collinear_plan, collinear_actual)
    assert "共线" in res_warn.warning


def test_identity_check_and_reset() -> None:
    engine = RtCalibrationEngine()
    ident = engine.get_default_identity()
    assert engine.is_default_identity(ident.r_mat, ident.t_vec) is True

    # 求解非单位阵后再次检查
    engine.solve_rt_from_point_pairs(
        [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
        [(1.0, 1.0), (2.0, 1.0), (1.0, 2.0)]
    )
    assert engine.is_default_identity(engine.current_result.r_mat, engine.current_result.t_vec) is False

    # 导出 JSON 并重新导入
    exported_json = engine.export_json()
    imported_res = engine.import_json(exported_json)
    assert abs(imported_res.t_vec[0] - 1.0) < 1e-4

    # 恢复默认
    reset_res = engine.reset_to_identity()
    assert engine.is_default_identity(reset_res.r_mat, reset_res.t_vec) is True


def test_pose_and_trajectory_transformation() -> None:
    engine = RtCalibrationEngine()
    # 构造旋转 90 度，平移 (10.0, 5.0)
    theta = math.radians(90.0)
    r_mat = [
        [math.cos(theta), -math.sin(theta), 0.0],
        [math.sin(theta), math.cos(theta), 0.0],
        [0.0, 0.0, 1.0]
    ]
    t_vec = [10.0, 5.0, 0.0]

    # 单点 (1, 0, 0度) 变换后应为 (10, 6, 90度)
    nx, ny, nyaw = engine.transform_pose_2d(1.0, 0.0, 0.0, r_mat, t_vec)
    assert abs(nx - 10.0) < 1e-4
    assert abs(ny - 6.0) < 1e-4
    assert abs(nyaw - 90.0) < 1e-4

    # 批量轨迹字符串转换
    raw_traj_str = (
        "0,0.0,0.0,0.0\n"
        "1,2.0,0.0,45.0\n"
        "2,2.0,3.0,90.0"
    )
    transformed_str = engine.transform_trajectory_data_str(raw_traj_str, r_mat, t_vec)
    lines = transformed_str.splitlines()
    assert len(lines) == 3

    # 检查第0点 (0,0) -> (10, 5)
    p0 = [float(v) for v in lines[0].split(",")]
    assert abs(p0[1] - 10.0) < 1e-3
    assert abs(p0[2] - 5.0) < 1e-3
    assert abs(p0[3] - 90.0) < 1e-2

    # 检查第1点 (2,0) -> (10, 7)
    p1 = [float(v) for v in lines[1].split(",")]
    assert abs(p1[1] - 10.0) < 1e-3
    assert abs(p1[2] - 7.0) < 1e-3
    assert abs(p1[3] - 135.0) < 1e-2

