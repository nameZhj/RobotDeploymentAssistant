# @file: src/protocol/virtual_slam_generator.py
# @brief: Virtual SLAM scan synthesizer generating realistic ASCII PCD files driven by teleop pose integration.
# @exports: VirtualSlamGenerator

from __future__ import annotations

import math
from pathlib import Path
from typing import List, Tuple

import numpy as np


class VirtualSlamGenerator:
    """Simulates a 2.5D LiDAR stage scan stream when no live robot SLAM daemon is attached."""

    def __init__(self, stage_width: float = 12.0, stage_height: float = 8.0) -> None:
        self.stage_width = stage_width
        self.stage_height = stage_height
        self.robot_pose = [0.0, 0.0, 0.0]  # x, y, yaw
        self._accumulated_chunks: List[np.ndarray] = []
        self._seed_perimeter_walls()

    def _seed_perimeter_walls(self) -> None:
        hw, hh = self.stage_width * 0.5, self.stage_height * 0.5
        xs = np.linspace(-hw, hw, 80)
        ys = np.linspace(-hh, hh, 60)
        zs = np.array([0.2, 0.6, 1.0, 1.4], dtype=np.float32)
        pts = []
        for z in zs:
            for x in xs:
                pts.append((x, -hh, z))
                pts.append((x, hh, z))
            for y in ys:
                pts.append((-hw, y, z))
                pts.append((hw, y, z))
        self._accumulated_chunks.append(np.asarray(pts, dtype=np.float32))

    def step_motion(self, vx: float, vy: float, vyaw: float, duration_s: float) -> Tuple[float, float, float]:
        """Integrate virtual robot odometry pose and capture a local LiDAR scan ring."""
        x, y, yaw = self.robot_pose
        c, s = math.cos(yaw), math.sin(yaw)
        x += (vx * c - vy * s) * duration_s
        y += (vx * s + vy * c) * duration_s
        yaw += vyaw * duration_s
        self.robot_pose = [round(x, 4), round(y, 4), round(yaw, 4)]

        angles = np.linspace(0.0, 2.0 * math.pi, 72, endpoint=False)
        rng = np.random.default_rng(int(abs(x * 100 + y * 37)) + 7)
        radii = 2.2 + rng.uniform(-0.15, 0.15, size=len(angles))
        sx = x + radii * np.cos(angles + yaw)
        sy = y + radii * np.sin(angles + yaw)
        sz = np.full_like(sx, 0.75)
        self._accumulated_chunks.append(np.column_stack((sx, sy, sz)).astype(np.float32))
        return (self.robot_pose[0], self.robot_pose[1], self.robot_pose[2])

    def get_points(self) -> np.ndarray:
        """Return merged (N, 3) float32 scan cloud accumulated so far."""
        if not self._accumulated_chunks:
            return np.zeros((0, 3), dtype=np.float32)
        return np.vstack(self._accumulated_chunks)

    def save_ascii_pcd(self, out_path: Path) -> Path:
        """Persist current point cloud to standard ASCII PCD v0.7 format."""
        pts = self.get_points()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        header = (
            "# .PCD v0.7 - Point Cloud Data file format\n"
            "VERSION 0.7\n"
            "FIELDS x y z\n"
            "SIZE 4 4 4\n"
            "TYPE F F F\n"
            "COUNT 1 1 1\n"
            f"WIDTH {len(pts)}\n"
            "HEIGHT 1\n"
            "VIEWPOINT 0 0 0 1 0 0 0\n"
            f"POINTS {len(pts)}\n"
            "DATA ascii\n"
        )
        with out_path.open("w", encoding="utf-8") as f:
            f.write(header)
            for row in pts:
                f.write(f"{row[0]:.4f} {row[1]:.4f} {row[2]:.4f}\n")
        return out_path
