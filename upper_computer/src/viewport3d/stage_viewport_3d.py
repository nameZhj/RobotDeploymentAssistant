# @file: src/viewport3d/stage_viewport_3d.py
# @brief: Real-time 3D OpenGL stage viewport rendering G1 robots with VBOs, GLSL shader, ground halo rings & IDs.
# @exports: StageViewport3D

from __future__ import annotations

import time
from typing import Dict, List, Optional, Set, Tuple
import numpy as np
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QWheelEvent
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from src.core.event_bus import StudioEvent
from src.core.paths import get_paths
from src.services.studio_state_service import StudioStateService
from src.viewport3d.dance_motion_player import DanceMotionPlayer
from src.viewport3d.g1_kinematics_chain import get_g1_kinematics
from src.viewport3d.g1_studio_shader import G1StudioShader
from src.viewport3d.live_motion_controller import LiveMotionController
from src.viewport3d.orbit_camera import OrbitCamera
from src.viewport3d.robot_render_style import (
    collect_robot_label, draw_ground_positioning_ring, draw_robot_id_labels,
    draw_stage_grid, robot_link_material, robot_link_style,
)
from src.viewport3d.stage_scene_layers import draw_live_nav_3d, draw_trajectories, load_calibrated_map_cloud
from src.viewport3d.stl_vbo_cache import PointCloudVbo, StlGpuVboPool, StlVboCache

try:
    from OpenGL import GL, GLU
    _HAS_GL = True
except Exception:  # pragma: no cover
    _HAS_GL = False


def _hex_rgb(hex_color: str) -> Tuple[float, float, float]:
    c = QColor(hex_color or "#45B5AA")
    return (c.redF(), c.greenF(), c.blueF())


class StageViewport3D(QOpenGLWidget):
    """Articulated 3D G1 stage viewport supporting live ROS telemetry, walking gaits & NPZ dances."""

    def __init__(self, state: StudioStateService, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.camera = OrbitCamera()
        self._kinematics = get_g1_kinematics()
        self._stl_cache = StlVboCache(get_paths().g1_urdf_dir)
        self._mesh_vbos = StlGpuVboPool()
        self._shader = G1StudioShader()
        self._motion_player = DanceMotionPlayer()
        self._motion_ctrl = LiveMotionController(self._motion_player)
        self._last_pos: Optional[QPoint] = None
        self._pcd_xyz: Optional[np.ndarray] = None
        self._pcd_rgb: Optional[np.ndarray] = None
        self._live_pose: Optional[Tuple[float, float, float]] = None
        self._live_path: list = []
        self._cloud_vbo = PointCloudVbo()
        self._id_labels: List[Tuple] = []
        self._gl_cleanup_connected: bool = False
        self._live_anim_timer = QTimer(self)
        self._live_anim_timer.setInterval(33)
        self._live_anim_timer.timeout.connect(self._on_live_anim_tick)
        self.setMinimumSize(240, 180)
        for ev in (StudioEvent.PLAYHEAD_MOVED, StudioEvent.SCENE_CHANGED, StudioEvent.TIMELINE_UPDATED, StudioEvent.TRACKS_UPDATED, StudioEvent.TRAJECTORY_LIB_UPDATED):
            state.bus.subscribe(ev, lambda _p: self.update())
        state.bus.subscribe(StudioEvent.MAP_LOADED, lambda _p: self.sync_active_map_cloud())
        self.sync_active_map_cloud()

    @property
    def _live_robot_poses(self) -> Dict[str, Tuple[float, float, float]]:
        return self._motion_ctrl.live_poses

    @property
    def _live_robot_states(self) -> Dict[str, Dict[str, object]]:
        return self._motion_ctrl.live_states

    def _resolve_live_robot_motion(self, tid: str, st: Dict[str, object], now_mono: float):
        if st:
            self._motion_ctrl.live_states[tid] = st
        return self._motion_ctrl.resolve_live_motion(tid, now_mono)

    def sync_active_map_cloud(self) -> None:
        pts, rgb = load_calibrated_map_cloud(self.state.active_map)
        self.set_point_cloud(pts, rgb)

    def reset_view(self, preset: str = "iso") -> None:
        self.camera.reset_preset(preset)
        self.update()

    def set_point_cloud(self, points_xyz: Optional[np.ndarray], colors_rgb: Optional[np.ndarray] = None, repaint: bool = True) -> None:
        if points_xyz is None or len(points_xyz) == 0:
            self._pcd_xyz, self._pcd_rgb = None, None
            self._cloud_vbo.mark_dirty(0)
        else:
            step = max(1, len(points_xyz) // 100000)
            pts = points_xyz[::step]
            self._pcd_xyz = np.ascontiguousarray(pts[:, :3], dtype=np.float32)
            self._pcd_rgb = np.ascontiguousarray(colors_rgb[::step, :3], dtype=np.float32) if colors_rgb is not None and len(colors_rgb) == len(points_xyz) else None
            self._cloud_vbo.mark_dirty(len(self._pcd_xyz))
        if repaint:
            self.update()

    def set_live_nav_pose(self, pose: Optional[Tuple[float, float, float]], global_path=None) -> None:
        self._live_pose = pose
        if global_path is not None:
            self._live_path = [(float(pt[0]), float(pt[1])) for pt in global_path if len(pt) >= 2]
        self.update()

    def set_live_robot_poses(self, poses: Dict[str, Tuple[float, float, float]]) -> None:
        self._motion_ctrl.set_poses(poses)
        self._sync_live_timer()
        self.update()

    def set_live_robot_states(self, states: Dict[str, Dict[str, object]]) -> None:
        self._motion_ctrl.set_states(states)
        self._sync_live_timer()
        self.update()

    def _sync_live_timer(self) -> None:
        active = self._motion_ctrl.decay_and_check_active()
        if active and not self._live_anim_timer.isActive():
            self._live_anim_timer.start()
        elif not active and self._live_anim_timer.isActive():
            self._live_anim_timer.stop()

    def _on_live_anim_tick(self) -> None:
        self._sync_live_timer()
        self.update()

    def initializeGL(self) -> None:
        if not _HAS_GL:
            return
        ctx = self.context()
        if ctx is not None and not self._gl_cleanup_connected:
            ctx.aboutToBeDestroyed.connect(self._on_gl_context_destroyed)
            self._gl_cleanup_connected = True
        self._mesh_vbos.release_all(GL)
        self._shader.initialize(GL)
        GL.glClearColor(0.055, 0.068, 0.090, 1.0)
        GL.glLightModeli(GL.GL_LIGHT_MODEL_TWO_SIDE, GL.GL_TRUE)
        GL.glColorMaterial(GL.GL_FRONT_AND_BACK, GL.GL_AMBIENT_AND_DIFFUSE)
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_DIFFUSE, [0.98, 0.98, 0.96, 1.0])
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_AMBIENT, [0.34, 0.36, 0.40, 1.0])
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_SPECULAR, [0.90, 0.92, 0.95, 1.0])
        GL.glLightfv(GL.GL_LIGHT1, GL.GL_DIFFUSE, [0.46, 0.52, 0.62, 1.0])
        GL.glLightfv(GL.GL_LIGHT1, GL.GL_AMBIENT, [0.0, 0.0, 0.0, 1.0])

    def _on_gl_context_destroyed(self) -> None:
        if _HAS_GL:
            self._mesh_vbos.release_all(GL)
            self._cloud_vbo.release(GL)
            self._shader.release(GL)

    def resizeGL(self, w: int, h: int) -> None:
        if _HAS_GL:
            dpr = float(self.devicePixelRatioF() or 1.0)
            GL.glViewport(0, 0, max(1, int(round(w * dpr))), max(1, int(round(h * dpr))))

    def paintGL(self) -> None:
        if not _HAS_GL:
            return
        painter = QPainter(self)
        try:
            painter.beginNativePainting()
            GL.glPushAttrib(GL.GL_ALL_ATTRIB_BITS)
            GL.glPushClientAttrib(GL.GL_CLIENT_ALL_ATTRIB_BITS)
            try:
                self._render_scene()
            finally:
                self._shader.end(GL)
                GL.glDisable(GL.GL_DEPTH_TEST)
                GL.glPopClientAttrib()
                GL.glPopAttrib()
            painter.endNativePainting()
            draw_robot_id_labels(painter, self._id_labels)
        finally:
            painter.end()

    def _render_scene(self) -> None:
        dpr = float(self.devicePixelRatioF() or 1.0)
        pw, ph = max(1, int(round(self.width() * dpr))), max(1, int(round(self.height() * dpr)))
        GL.glViewport(0, 0, pw, ph)
        GL.glDisable(GL.GL_SCISSOR_TEST)
        GL.glDisable(GL.GL_BLEND)
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glEnable(GL.GL_NORMALIZE)
        GL.glShadeModel(GL.GL_SMOOTH)
        GL.glClearColor(0.055, 0.068, 0.090, 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        GLU.gluPerspective(45.0, pw / float(ph), 0.08, 220.0)
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()
        ex, ey, ez = self.camera.eye_position()
        GLU.gluLookAt(ex, ey, ez, self.camera.target_x, self.camera.target_y, self.camera.target_z, 0.0, 0.0, 1.0)
        view_mat = np.asarray(GL.glGetFloatv(GL.GL_MODELVIEW_MATRIX), dtype=np.float32).T
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_POSITION, [4.5, -6.8, 8.2, 0.0])
        GL.glLightfv(GL.GL_LIGHT1, GL.GL_POSITION, [-7.8, 4.2, 3.6, 0.0])

        draw_stage_grid(GL, float(self.state.scene.stage_width or 12.0), float(self.state.scene.stage_height or 8.0))
        self._draw_point_cloud()
        draw_trajectories(GL, self.state, _hex_rgb)
        draw_live_nav_3d(GL, self._live_pose, self._live_path)
        self._draw_robots(view_mat, (ex, ey), dpr)
        self._shader.end(GL)
        if hasattr(GL, "glBindBuffer"):
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        for state in (GL.GL_VERTEX_ARRAY, GL.GL_NORMAL_ARRAY, GL.GL_COLOR_ARRAY):
            GL.glDisableClientState(state)
        GL.glDisable(GL.GL_LIGHTING)
        GL.glDisable(GL.GL_BLEND)

    def _draw_point_cloud(self) -> None:
        if self._pcd_xyz is None or len(self._pcd_xyz) == 0:
            self._cloud_vbo.release(GL)
            return
        GL.glDisable(GL.GL_LIGHTING)
        GL.glPointSize(2.0)
        GL.glEnableClientState(GL.GL_VERTEX_ARRAY)
        self._cloud_vbo.draw(GL, self._pcd_xyz, self._pcd_rgb)
        GL.glDisableClientState(GL.GL_VERTEX_ARRAY)

    def _draw_robots(self, view_mat: np.ndarray, eye_xy: Tuple[float, float], dpr: float) -> None:
        t, now_mono = self.state.playhead_s, time.monotonic()
        self._id_labels = []
        colliding_names: Set[str] = {n for c in self.state.collisions if c.start_time <= t <= c.end_time for n in (c.track_a, c.track_b)}
        solved = []
        for track in self.state.tracks:
            tid = track.target_id.upper()
            live_p = self._motion_ctrl.live_poses.get(tid)
            live_st = self._motion_ctrl.live_states.get(tid, {})
            if live_p is not None:
                x, y, yaw = live_p
                rz, joints, rquat, tag = self._motion_ctrl.resolve_live_motion(tid, now_mono)
                is_fault = bool(live_st.get("fault")) or track.name in colliding_names
            else:
                x, y, yaw = self.state.evaluate_robot_pose(track, t)
                rz, joints, rquat, tag = self._motion_ctrl.resolve_timeline_motion(self.state, track, t)
                is_fault = track.name in colliding_names
            solved.append((track.target_id, x, y, yaw, _hex_rgb(track.color_hex), is_fault, tag, self._kinematics.solve_fk(x, y, yaw, rz, joints, rquat)))

        use_shader = self._shader.begin(GL, view_mat)
        if not use_shader:
            for cap in (GL.GL_LIGHTING, GL.GL_LIGHT0, GL.GL_LIGHT1, GL.GL_COLOR_MATERIAL):
                GL.glEnable(cap)
        GL.glEnableClientState(GL.GL_VERTEX_ARRAY)
        GL.glEnableClientState(GL.GL_NORMAL_ARRAY)
        for _tid, _x, _y, _yaw, trgb, is_fault, _tag, parts in solved:
            for rel_path, mat4 in parts:
                mesh = self._stl_cache.get_mesh(rel_path)
                if mesh is None or mesh.vertex_count == 0:
                    continue
                if use_shader:
                    self._shader.set_material(GL, *robot_link_material(self._kinematics, rel_path, is_fault))
                else:
                    rgb, spec, shin = robot_link_style(self._kinematics, rel_path, trgb, is_fault)
                    GL.glColor3f(*rgb)
                    GL.glMaterialfv(GL.GL_FRONT_AND_BACK, GL.GL_SPECULAR, [spec[0], spec[1], spec[2], 1.0])
                    GL.glMaterialf(GL.GL_FRONT_AND_BACK, GL.GL_SHININESS, shin)
                GL.glPushMatrix()
                GL.glMultMatrixf(np.ascontiguousarray(mat4.T, dtype=np.float32))
                self._mesh_vbos.draw(GL, rel_path, mesh)
                GL.glPopMatrix()
        GL.glDisableClientState(GL.GL_VERTEX_ARRAY)
        GL.glDisableClientState(GL.GL_NORMAL_ARRAY)
        self._shader.end(GL)

        for tid, x, y, yaw, trgb, is_fault, tag, _parts in solved:
            draw_ground_positioning_ring(GL, x, y, yaw, 0.42, trgb, colliding=is_fault)
            collect_robot_label(self._id_labels, tid, x, y, trgb, eye_xy=eye_xy, radius=0.42, dpr=dpr, status_tag=tag, colliding=is_fault)

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
