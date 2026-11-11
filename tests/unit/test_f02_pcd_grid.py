"""
@file: tests/unit/test_f02_pcd_grid.py
@brief: PCD 点云解析、三模 2D 栅格投射、膨胀半径与坐标映射单元测试
@exports: test_pcd_file_to_points, test_three_render_modes, test_dilation_radius_impact, test_origin_info_and_crop
"""
import io
import numpy as np
from PIL import Image
from src.domain.map.pcd_grid_models import GridMapConfig
from src.infrastructure.map.pcd_grid_engine import pcd_file_to_grid_png, pcd_file_to_points


def test_pcd_file_to_points() -> None:
    res = pcd_file_to_points("")
    assert res.totalPoints > 0
    assert res.bounds.minX < res.bounds.maxX
    assert res.bounds.minY < res.bounds.maxY

    arr = res.to_numpy()
    assert arr.ndim == 2
    assert arr.shape[1] == 3

    res_sampled = pcd_file_to_points("", max_points=1000)
    assert res_sampled.totalPoints <= 1000
    assert res_sampled.count <= 1000


def test_three_render_modes() -> None:
    png_sig = b"\x89PNG\r\n\x1a\n"

    # 1. 模式 0: 障碍物灰度
    cfg_mode0 = GridMapConfig(renderMode=0, resolution=10.0)
    res0 = pcd_file_to_grid_png("", cfg_mode0)
    assert res0.pngBytes.startswith(png_sig)
    img0 = Image.open(io.BytesIO(res0.pngBytes))
    assert img0.mode == "L"
    assert img0.size == (res0.width, res0.height)

    # 2. 模式 1: 高度灰度
    cfg_mode1 = GridMapConfig(renderMode=1, resolution=10.0)
    res1 = pcd_file_to_grid_png("", cfg_mode1)
    assert res1.pngBytes.startswith(png_sig)
    img1 = Image.open(io.BytesIO(res1.pngBytes))
    assert img1.mode == "L"

    # 3. 模式 2: 原始 RGB (伪彩色谱)
    cfg_mode2 = GridMapConfig(renderMode=2, resolution=10.0)
    res2 = pcd_file_to_grid_png("", cfg_mode2)
    assert res2.pngBytes.startswith(png_sig)
    img2 = Image.open(io.BytesIO(res2.pngBytes))
    assert img2.mode == "RGB"


def test_dilation_radius_impact() -> None:
    cfg_no_dil = GridMapConfig(renderMode=0, dilationRadius=0.0, resolution=15.0)
    res_no_dil = pcd_file_to_grid_png("", cfg_no_dil)
    arr_no_dil = np.array(Image.open(io.BytesIO(res_no_dil.pngBytes)))
    obs_no_dil = np.sum(arr_no_dil == 0)

    cfg_with_dil = GridMapConfig(renderMode=0, dilationRadius=0.4, resolution=15.0)
    res_with_dil = pcd_file_to_grid_png("", cfg_with_dil)
    arr_with_dil = np.array(Image.open(io.BytesIO(res_with_dil.pngBytes)))
    obs_with_dil = np.sum(arr_with_dil == 0)

    assert obs_with_dil > obs_no_dil


def test_origin_info_and_crop() -> None:
    cfg = GridMapConfig(
        resolution=20.0,
        originRotation=45.0,
        originCenterX=2.0,
        originCenterY=-1.0,
        cropCenterX=0.0,
        cropCenterY=0.0,
        cropWidth=12.0,
        cropHeight=8.0
    )
    res = pcd_file_to_grid_png("", cfg)
    info = res.originInfo
    assert info.resolution == 20.0
    assert info.width == res.width
    assert info.height == res.height
    assert abs(info.originPosInThreeX - (res.bounds.minX + res.bounds.maxX) / 2.0) < 1e-4
    assert abs(info.originPosInThreeY - (res.bounds.minY + res.bounds.maxY) / 2.0) < 1e-4

    info_dict = info.to_dict()
    assert "originPosInThreeX" in info_dict
    assert "width" in info_dict

