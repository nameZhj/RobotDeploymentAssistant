"""
@file: src/domain/transform/stage_coordinate_transform.py
@brief: 统一时空坐标系转换服务（Canvas 像素、PCD 点云、3D 视口与 URDF 世界坐标互转）
@exports: StageCoordinateTransform, CanvasTransformConfig, deg_to_rad, rad_to_deg, normalize_yaw_rad, normalize_yaw_deg
"""
from dataclasses import dataclass
import math
from typing import Optional, Sequence, Tuple, Union


def deg_to_rad(deg: float) -> float:
    return math.radians(float(deg))


def rad_to_deg(rad: float) -> float:
    return math.degrees(float(rad))


def normalize_yaw_rad(yaw_rad: float) -> float:
    """规范化弧度角至 [-pi, pi) 区间"""
    if not math.isfinite(yaw_rad):
        raise ValueError(f"角度禁止为 NaN/Inf: {yaw_rad}")
    normalized = ((yaw_rad + math.pi) % (2.0 * math.pi)) - math.pi
    return 0.0 if abs(normalized) < 1e-12 else normalized


def normalize_yaw_deg(yaw_deg: float) -> float:
    """规范化角度值至 [-180.0, 180.0) 区间"""
    if not math.isfinite(yaw_deg):
        raise ValueError(f"角度禁止为 NaN/Inf: {yaw_deg}")
    normalized = ((yaw_deg + 180.0) % 360.0) - 180.0
    return 0.0 if abs(normalized) < 1e-12 else normalized


@dataclass
class CanvasTransformConfig:
    """2D Canvas 视口缩放与平移配置"""
    width: float = 800.0
    height: float = 600.0
    scale_px_per_m: float = 40.0
    offset_x_px: float = 0.0
    offset_y_px: float = 0.0


class StageCoordinateTransform:
    """
    统一舞台空间几何变换权威服务
    约定坐标轴：
    - 舞台世界坐标：X 轴朝右 (米), Y 轴朝前 (米), Z 轴朝上 (米)
    - 朝向角零度：沿 +X 轴，逆时针绕 +Z 轴旋转至 +Y 轴为正
    - 2D Canvas 屏幕坐标：水平往右为 +px，垂直往下为 +py (因此屏幕 Y 轴需与世界 Y 轴反相)
    """

    @staticmethod
    def canvas_px_to_world_m(
        px: float, py: float, config: CanvasTransformConfig
    ) -> Tuple[float, float]:
        """将 2D 画布屏幕像素坐标转换为舞台世界平面物理坐标 (x_m, y_m)"""
        scale = max(1e-4, float(config.scale_px_per_m))
        cx = config.width / 2.0 + config.offset_x_px
        cy = config.height / 2.0 + config.offset_y_px
        x_m = (px - cx) / scale
        y_m = -(py - cy) / scale
        return round(x_m, 4), round(y_m, 4)

    @staticmethod
    def world_m_to_canvas_px(
        x_m: float, y_m: float, config: CanvasTransformConfig
    ) -> Tuple[float, float]:
        """将舞台世界物理坐标 (x_m, y_m) 映射为画布屏幕像素坐标 (px, py)"""
        scale = float(config.scale_px_per_m)
        cx = config.width / 2.0 + config.offset_x_px
        cy = config.height / 2.0 + config.offset_y_px
        px = cx + x_m * scale
        py = cy - y_m * scale
        return round(px, 2), round(py, 2)

    @staticmethod
    def pcd_to_world_m(
        pcd_x: float, pcd_y: float, pcd_z: float,
        origin_x: float = 0.0, origin_y: float = 0.0, origin_z: float = 0.0,
        yaw_rad: float = 0.0
    ) -> Tuple[float, float, float]:
        """将 PCD 点云原生局部坐标平移并旋转至舞台世界坐标系"""
        dx = float(pcd_x) - float(origin_x)
        dy = float(pcd_y) - float(origin_y)
        dz = float(pcd_z) - float(origin_z)
        if abs(yaw_rad) < 1e-8:
            return round(dx, 4), round(dy, 4), round(dz, 4)
        cos_y, sin_y = math.cos(yaw_rad), math.sin(yaw_rad)
        wx = dx * cos_y - dy * sin_y
        wy = dx * sin_y + dy * cos_y
        return round(wx, 4), round(wy, 4), round(dz, 4)

    @staticmethod
    def world_m_to_pcd(
        wx: float, wy: float, wz: float,
        origin_x: float = 0.0, origin_y: float = 0.0, origin_z: float = 0.0,
        yaw_rad: float = 0.0
    ) -> Tuple[float, float, float]:
        """舞台世界坐标反算回 PCD 点云坐标"""
        if abs(yaw_rad) < 1e-8:
            return round(wx + origin_x, 4), round(wy + origin_y, 4), round(wz + origin_z, 4)
        cos_y, sin_y = math.cos(-yaw_rad), math.sin(-yaw_rad)
        dx = wx * cos_y - wy * sin_y
        dy = wx * sin_y + wy * cos_y
        return round(dx + origin_x, 4), round(dy + origin_y, 4), round(wz + origin_z, 4)

    @staticmethod
    def world_pose_to_urdf_root(
        x_m: float, y_m: float, yaw_deg: float, floor_height_m: float = 0.75
    ) -> Tuple[Tuple[float, float, float], float]:
        """将地面 2D 走位转换为 G1 URDF pelvis 根关节 3D 位姿 ((x, y, z), yaw_deg)"""
        return (round(float(x_m), 4), round(float(y_m), 4), round(float(floor_height_m), 4)), float(yaw_deg)

    @staticmethod
    def seconds_to_ms(seconds: float) -> int:
        return max(0, int(round(float(seconds) * 1000.0)))

    @staticmethod
    def ms_to_seconds(ms: int) -> float:
        return round(max(0, int(ms)) / 1000.0, 3)
