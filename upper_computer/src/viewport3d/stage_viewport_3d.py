# @file: src/viewport3d/stage_viewport_3d.py
# @brief: Real-time 3D OpenGL stage viewport rendering articulated 29-DOF Unitree G1 robots, spline paths, and PCD clouds.
# @exports: StageViewport3D

from __future__ import annotations

import math
from typing import Dict, Optional, Set, Tuple
import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QMouseEvent, QWheelEvent
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from src.core.event_bus import StudioEvent
from src.core.paths import get_paths
from src.services.studio_state_service import StudioStateService
from src.viewport3d.dance_motion_player import DanceMotionPlayer, procedural_gait_angles
from src.viewport3d.g1_kinematics_chain import get_g1_kinematics
from src.viewport3d.orbit_camera import OrbitCamera
from src.viewport3d.stl_vbo_cache import StlVboCache, g1_link_material_rgb

try:
    from OpenGL import GL, GLU
    _HAS_GL = True
except Exception:  # pragma: no cover
    _HAS_GL = False


def _hex_rgb(hex_color: str) -> Tuple[float, float, float]:
    c = QColor(hex_color or "#45B5AA")
    return (c.redF(), c.greenF(), c.blueF())


class StageViewport3D(QOpenGLWidget):
    """Articulated 3D G1 stage preview synchronized with StudioStateService playhead."""

    def __init__(self, state: StudioStateService, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.camera = OrbitCamera()
        self._kinematics = get_g1_kinematics()
        self._stl_cache = StlVboCache(get_paths().g1_urdf_dir)
        self._motion_player = DanceMotionPlayer()
        self._last_pos: Optional[QPoint] = None
        self._pcd_xyz: Optional[np.ndarray] = None
        self._pcd_rgb: Optional[np.ndarray] = None
        self._gl_vbos: Dict[str, Tuple[int, int]] = {}
        self.setMinimumSize(240, 180)
        for ev in (
            StudioEvent.PLAYHEAD_MOVED,
            StudioEvent.SCENE_CHANGED,
            StudioEvent.TIMELINE_UPDATED,
            StudioEvent.TRACKS_UPDATED,
            StudioEvent.TRAJECTORY_LIB_UPDATED,
        ):
            state.bus.subscribe(ev, lambda _p: self.update())
        state.bus.subscribe(StudioEvent.MAP_LOADED, lambda _p: self.sync_active_map_cloud())
        self.sync_active_map_cloud()

    def sync_active_map_cloud(self) -> None:
        """Load active calibrated PCD map points into 3D viewport when MAP_LOADED fires."""
        m = self.state.active_map
        if m is None or not m.file_path:
            self.set_point_cloud(None, None)
            return
        from pathlib import Path
        p = Path(m.file_path)
        if not p.exists():
            self.set_point_cloud(None, None)
            return
        from src.persistence.pcd_parser import load_pcd
        cloud = load_pcd(p, max_points=60000)
        pts = cloud.points_xyz
        if len(pts) > 0 and isinstance(m.calib_matrix, dict) and "rot_2x2" in m.calib_matrix and "trans_2" in m.calib_matrix:
            rot = np.asarray(m.calib_matrix["rot_2x2"], dtype=np.float64).reshape(2, 2)
            trans = np.asarray(m.calib_matrix["trans_2"], dtype=np.float64).reshape(2)
            pts = pts.copy()
            pts[:, :2] = ((rot @ pts[:, :2].astype(np.float64).T).T + trans).astype(np.float32)
        self.set_point_cloud(pts, cloud.colors_rgb)

    def reset_view(self, preset: str = "iso") -> None:
        self.camera.reset_preset(preset)
        self.update()

    def set_point_cloud(self, points_xyz: Optional[np.ndarray], colors_rgb: Optional[np.ndarray] = None) -> None:
        if points_xyz is None or len(points_xyz) == 0:
            self._pcd_xyz, self._pcd_rgb = None, None
        else:
            self._pcd_xyz = np.ascontiguousarray(points_xyz[:, :3], dtype=np.float32)
            self._pcd_rgb = (
                np.ascontiguousarray(colors_rgb[:, :3], dtype=np.float32)
                if colors_rgb is not None and len(colors_rgb) == len(points_xyz)
                else None
            )
        self.update()

    def initializeGL(self) -> None:
        if not _HAS_GL:
            return
        GL.glClearColor(0.024, 0.027, 0.031, 1.0)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_NORMALIZE)
        GL.glEnable(GL.GL_LIGHTING)
        GL.glEnable(GL.GL_LIGHT0)
        GL.glEnable(GL.GL_LIGHT1)
        GL.glEnable(GL.GL_COLOR_MATERIAL)
        GL.glLightModeli(GL.GL_LIGHT_MODEL_TWO_SIDE, GL.GL_TRUE)
        GL.glColorMaterial(GL.GL_FRONT_AND_BACK, GL.GL_AMBIENT_AND_DIFFUSE)
        GL.glMaterialfv(GL.GL_FRONT_AND_BACK, GL.GL_SPECULAR, [0.45, 0.48, 0.54, 1.0])
        GL.glMaterialf(GL.GL_FRONT_AND_BACK, GL.GL_SHININESS, 42.0)
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_POSITION, [6.0, -7.0, 12.0, 1.0])
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_DIFFUSE, [0.95, 0.96, 0.98, 1.0])
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_AMBIENT, [0.30, 0.32, 0.36, 1.0])
        GL.glLightfv(GL.GL_LIGHT1, GL.GL_POSITION, [-6.0, 6.0, 5.0, 1.0])
        GL.glLightfv(GL.GL_LIGHT1, GL.GL_DIFFUSE, [0.40, 0.45, 0.55, 1.0])

    def resizeGL(self, w: int, h: int) -> None:
        if not _HAS_GL:
            return
        GL.glViewport(0, 0, max(1, w), max(1, h))

    def paintGL(self) -> None:
        if not _HAS_GL:
            return
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        w, h = max(1, self.width()), max(1, self.height())
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        GLU.gluPerspective(45.0, w / float(h), 0.1, 220.0)
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()
        ex, ey, ez = self.camera.eye_position()
        GLU.gluLookAt(ex, ey, ez, self.camera.target_x, self.camera.target_y, self.camera.target_z, 0.0, 0.0, 1.0)

        self._draw_stage_grid()
        self._draw_point_cloud()
        self._draw_trajectories()
        self._draw_robots()

    def _draw_stage_grid(self) -> None:
        GL.glDisable(GL.GL_LIGHTING)
        length = float(self.state.scene.stage_width or 12.0)
        width = float(self.state.scene.stage_height or 8.0)
        hx, hy = length * 0.5, width * 0.5
        GL.glLineWidth(1.0)
        GL.glBegin(GL.GL_LINES)
        GL.glColor3f(0.14, 0.16, 0.20)
        for ix in range(-int(hx) - 1, int(hx) + 2):
            GL.glVertex3f(float(ix), -hy, 0.0)
            GL.glVertex3f(float(ix), hy, 0.0)
        for iy in range(-int(hy) - 1, int(hy) + 2):
            GL.glVertex3f(-hx, float(iy), 0.0)
            GL.glVertex3f(hx, float(iy), 0.0)
        GL.glEnd()
        # Stage border
        GL.glLineWidth(1.6)
        GL.glBegin(GL.GL_LINE_LOOP)
        GL.glColor3f(0.27, 0.71, 0.67)
        for vx, vy in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)):
            GL.glVertex3f(vx, vy, 0.005)
        GL.glEnd()

    def _draw_point_cloud(self) -> None:
        if self._pcd_xyz is None or len(self._pcd_xyz) == 0:
            return
        GL.glDisable(GL.GL_LIGHTING)
        GL.glPointSize(2.0)
        GL.glEnableClientState(GL.GL_VERTEX_ARRAY)
        GL.glVertexPointer(3, GL.GL_FLOAT, 0, self._pcd_xyz)
        if self._pcd_rgb is not None:
            GL.glEnableClientState(GL.GL_COLOR_ARRAY)
            GL.glColorPointer(3, GL.GL_FLOAT, 0, self._pcd_rgb)
        else:
            GL.glColor3f(0.35, 0.65, 0.78)
        GL.glDrawArrays(GL.GL_POINTS, 0, len(self._pcd_xyz))
        if self._pcd_rgb is not None:
            GL.glDisableClientState(GL.GL_COLOR_ARRAY)
        GL.glDisableClientState(GL.GL_VERTEX_ARRAY)

    def _draw_trajectories(self) -> None:
        GL.glDisable(GL.GL_LIGHTING)
        GL.glLineWidth(2.2)
        by_no = {t.track_no: t for t in self.state.tracks}
        for tid, pts in self.state.sampled_trajs.items():
            if len(pts) < 2:
                continue
            traj = self.state.trajectories.get(tid)
            if traj is not None and not traj.visible_on_map:
                continue
            track_match = next(
                (t for t in self.state.tracks if any(b.track_id == t.id and b.block_type == "trajectory" and b.ref_id == tid for b in self.state.blocks)),
                None,
            )
            if track_match is None and traj and traj.bound_track_nos:
                track_match = by_no.get(traj.bound_track_nos[0])
            r, g, b = _hex_rgb(track_match.color_hex if track_match else "#60A5FA")
            GL.glColor3f(r, g, b)
            GL.glBegin(GL.GL_LINE_STRIP)
            for row in pts[::max(1, len(pts) // 80)]:
                GL.glVertex3f(float(row[1]), float(row[2]), 0.02)
            GL.glVertex3f(float(pts[-1, 1]), float(pts[-1, 2]), 0.02)
            GL.glEnd()

    def _draw_robots(self) -> None:
        t = self.state.playhead_s
        colliding: Set[str] = {
            c.track_a for c in self.state.collisions if c.start_time <= t <= c.end_time
        } | {
            c.track_b for c in self.state.collisions if c.start_time <= t <= c.end_time
        }
        GL.glEnable(GL.GL_LIGHTING)
        GL.glEnableClientState(GL.GL_VERTEX_ARRAY)
        GL.glEnableClientState(GL.GL_NORMAL_ARRAY)

        for track in self.state.tracks:
            x, y, yaw = self.state.evaluate_robot_pose(track, t)
            root_z, joints = self._resolve_robot_motion(track, t)
            track_rgb = _hex_rgb(track.color_hex)
            is_colliding = track.name in colliding
            self._draw_robot_meshes(x, y, yaw, root_z, joints, track_rgb, is_colliding)
            self._draw_footprint_ring(x, y, 0.38, is_colliding, track_rgb)

        GL.glDisableClientState(GL.GL_VERTEX_ARRAY)
        GL.glDisableClientState(GL.GL_NORMAL_ARRAY)

    def _resolve_robot_motion(self, track, t: float) -> Tuple[float, np.ndarray]:
        action = self.state.active_action_at(track, t)
        if action is not None:
            blk = next(
                (
                    b for b in self.state.blocks
                    if b.track_id == track.id and not b.is_ignored and b.block_type == "action" and b.start_time <= t <= b.end_time
                ),
                None,
            )
            local_t = max(0.0, t - blk.start_time) if blk is not None else t
            clip = self._motion_player.get_clip_for_action(
                action.motion_file_path, lrmp_code=action.lrmp_code, action_no=action.no
            )
            return clip.sample_at(local_t)
        x0, y0, _ = self.state.evaluate_robot_pose(track, max(0.0, t - 0.05))
        x1, y1, _ = self.state.evaluate_robot_pose(track, t + 0.05)
        speed = math.hypot(x1 - x0, y1 - y0) / 0.1
        return procedural_gait_angles(t, speed)

    def _draw_robot_meshes(
        self,
        x: float,
        y: float,
        yaw: float,
        root_z: float,
        joints: np.ndarray,
        track_rgb: Tuple[float, float, float],
        colliding: bool,
    ) -> None:
        parts = self._kinematics.solve_fk(x, y, yaw, root_z, joints)
        for rel_path, mat4 in parts:
            mesh = self._stl_cache.get_mesh(rel_path)
            if mesh is None or mesh.vertex_count == 0:
                continue
            GL.glColor3f(*g1_link_material_rgb(rel_path, track_rgb, colliding))
            GL.glPushMatrix()
            GL.glMultMatrixf(np.ascontiguousarray(mat4.T, dtype=np.float32))
            GL.glVertexPointer(3, GL.GL_FLOAT, 0, mesh.vertices)
            GL.glNormalPointer(GL.GL_FLOAT, 0, mesh.normals)
            GL.glDrawArrays(GL.GL_TRIANGLES, 0, mesh.vertex_count)
            GL.glPopMatrix()

    def _draw_footprint_ring(self, x: float, y: float, radius: float, error: bool, rgb: Tuple[float, float, float]) -> None:
        GL.glDisable(GL.GL_LIGHTING)
        GL.glColor3f(0.95, 0.25, 0.25) if error else GL.glColor3f(*rgb)
        GL.glLineWidth(2.0 if error else 1.4)
        GL.glBegin(GL.GL_LINE_LOOP)
        for i in range(24):
            a = 2.0 * math.pi * i / 24.0
            GL.glVertex3f(x + radius * math.cos(a), y + radius * math.sin(a), 0.015)
        GL.glEnd()
        GL.glEnable(GL.GL_LIGHTING)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._last_pos = event.position().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._last_pos is None:
            return
        cur = event.position().toPoint()
        dx, dy = cur.x() - self._last_pos.x(), cur.y() - self._last_pos.y()
        self._last_pos = cur
        if event.buttons() & Qt.MouseButton.LeftButton and not (event.modifiers() & Qt.KeyboardModifier.AltModifier):
            self.camera.orbit(dx, dy)
        else:
            self.camera.pan(dx, dy)
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        self.camera.zoom(event.angleDelta().y())
        self.update()
