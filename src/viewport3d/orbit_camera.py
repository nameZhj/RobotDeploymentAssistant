# @file: src/viewport3d/orbit_camera.py
# @brief: 3D spherical orbit, pan, and preset viewpoint camera controller for the StageViewport3D OpenGL scene.
# @exports: OrbitCamera

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Tuple


@dataclass
class OrbitCamera:
    """Z-up spherical orbit camera with preset stage viewpoints."""

    target_x: float = 0.0
    target_y: float = -0.8
    target_z: float = 0.65
    distance: float = 6.2
    yaw_deg: float = -45.0
    pitch_deg: float = 22.0

    def orbit(self, dx: float, dy: float) -> None:
        self.yaw_deg = (self.yaw_deg - dx * 0.45) % 360.0
        self.pitch_deg = max(5.0, min(88.0, self.pitch_deg + dy * 0.35))

    def pan(self, dx: float, dy: float) -> None:
        scale = self.distance * 0.0018
        rad = math.radians(self.yaw_deg)
        right_x, right_y = -math.sin(rad), math.cos(rad)
        fwd_x, fwd_y = math.cos(rad), math.sin(rad)
        self.target_x -= (right_x * dx - fwd_x * dy) * scale
        self.target_y -= (right_y * dx - fwd_y * dy) * scale

    def zoom(self, wheel_delta: float) -> None:
        factor = 0.90 if wheel_delta > 0 else 1.11
        self.distance = max(2.0, min(60.0, self.distance * factor))

    def reset_preset(self, preset: str = "iso") -> None:
        self.target_x, self.target_y, self.target_z = 0.0, -0.8, 0.65
        if preset == "top":
            self.yaw_deg, self.pitch_deg, self.distance = -90.0, 88.0, 12.0
        elif preset == "front":
            self.yaw_deg, self.pitch_deg, self.distance = -90.0, 14.0, 6.2
        else:
            self.yaw_deg, self.pitch_deg, self.distance = -45.0, 22.0, 6.2

    def eye_position(self) -> Tuple[float, float, float]:
        ry = math.radians(self.yaw_deg)
        rp = math.radians(self.pitch_deg)
        ex = self.target_x + self.distance * math.cos(rp) * math.cos(ry)
        ey = self.target_y + self.distance * math.cos(rp) * math.sin(ry)
        ez = self.target_z + self.distance * math.sin(rp)
        return (ex, ey, ez)
