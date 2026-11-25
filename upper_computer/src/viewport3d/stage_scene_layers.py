# @file: src/viewport3d/stage_scene_layers.py
# @brief: Static environment layers for StageViewport3D: calibrated PCD loading, spline trajectories, and nav overlay.
# @exports: load_calibrated_map_cloud, draw_trajectories, draw_live_nav_3d

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple
import numpy as np

from src.viewport3d.robot_render_style import draw_ground_positioning_ring


def load_calibrated_map_cloud(active_map) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """Load calibrated PCD points_xyz and colors_rgb from an active map entity."""
    if active_map is None or not active_map.file_path:
        return None, None
    p = Path(active_map.file_path)
    if not p.exists():
        return None, None
    from src.persistence.pcd_parser import load_pcd
    cloud = load_pcd(p, max_points=60000)
    pts = cloud.points_xyz
    if len(pts) > 0 and isinstance(active_map.calib_matrix, dict) and "rot_2x2" in active_map.calib_matrix and "trans_2" in active_map.calib_matrix:
        rot = np.asarray(active_map.calib_matrix["rot_2x2"], dtype=np.float64).reshape(2, 2)
        trans = np.asarray(active_map.calib_matrix["trans_2"], dtype=np.float64).reshape(2)
        pts = pts.copy()
        pts[:, :2] = ((rot @ pts[:, :2].astype(np.float64).T).T + trans).astype(np.float32)
    return pts, cloud.colors_rgb


def draw_trajectories(gl, state, hex_to_rgb: Callable[[str], Tuple[float, float, float]]) -> None:
    """Render visible 2D spline trajectories onto stage ground plane z=0.02m."""
    gl.glDisable(gl.GL_LIGHTING)
    gl.glLineWidth(2.2)
    by_no = {t.track_no: t for t in state.tracks}
    for tid, pts in state.sampled_trajs.items():
        if len(pts) < 2:
            continue
        traj = state.trajectories.get(tid)
        if traj is not None and not traj.visible_on_map:
            continue
        track_match = next(
            (t for t in state.tracks if any(b.track_id == t.id and b.block_type == "trajectory" and b.ref_id == tid for b in state.blocks)),
            None,
        ) or (by_no.get(traj.bound_track_nos[0]) if traj and traj.bound_track_nos else None)
        gl.glColor3f(*hex_to_rgb(track_match.color_hex if track_match else "#60A5FA"))
        gl.glBegin(gl.GL_LINE_STRIP)
        for row in pts[::max(1, len(pts) // 80)]:
            gl.glVertex3f(float(row[1]), float(row[2]), 0.02)
        gl.glVertex3f(float(pts[-1, 1]), float(pts[-1, 2]), 0.02)
        gl.glEnd()


def draw_live_nav_3d(gl, live_pose: Optional[Tuple[float, float, float]], live_path: Sequence[Tuple[float, float]]) -> None:
    """Render live single-robot ROS global path and emerald navigation halo ring."""
    if live_path and len(live_path) >= 2:
        gl.glDisable(gl.GL_LIGHTING)
        gl.glColor3f(0.13, 0.83, 0.93)
        gl.glLineWidth(2.4)
        gl.glBegin(gl.GL_LINE_STRIP)
        for px, py in live_path:
            gl.glVertex3f(px, py, 0.04)
        gl.glEnd()
    if live_pose is not None:
        draw_ground_positioning_ring(gl, live_pose[0], live_pose[1], live_pose[2], 0.42, (0.06, 0.72, 0.51), False)
