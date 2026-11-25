# @file: src/viewport3d/robot_render_style.py
# @brief: Official G1 URDF+rubber_hand materials, ground positioning halo ring, and single-QPainter HiDPI ID badges.
# @exports: draw_stage_grid, robot_link_material, robot_link_style, draw_ground_positioning_ring, collect_robot_label, draw_robot_id_labels, project_to_screen

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPen

from src.viewport3d.stl_vbo_cache import g1_link_material_rgb

try:
    from OpenGL import GL, GLU
    _HAS_GL = True
except Exception:  # pragma: no cover
    _HAS_GL = False

_SILVER_SPECULAR = (0.85, 0.88, 0.92)
_DARK_SPECULAR = (0.30, 0.32, 0.36)
_RUBBER_SPECULAR = (0.12, 0.12, 0.13)


def draw_stage_grid(gl, stage_width: float, stage_height: float) -> None:
    """Stage floor grid and teal perimeter border with lighting disabled cleanly."""
    gl.glDisable(gl.GL_LIGHTING)
    hx, hy = float(stage_width) * 0.5, float(stage_height) * 0.5
    gl.glLineWidth(1.0)
    gl.glBegin(gl.GL_LINES)
    gl.glColor3f(0.16, 0.19, 0.25)
    for ix in range(-int(hx) - 1, int(hx) + 2):
        gl.glVertex3f(float(ix), -hy, 0.0)
        gl.glVertex3f(float(ix), hy, 0.0)
    for iy in range(-int(hy) - 1, int(hy) + 2):
        gl.glVertex3f(-hx, float(iy), 0.0)
        gl.glVertex3f(hx, float(iy), 0.0)
    gl.glEnd()
    gl.glLineWidth(1.8)
    gl.glBegin(gl.GL_LINE_LOOP)
    gl.glColor3f(0.24, 0.72, 0.68)
    for vx, vy in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)):
        gl.glVertex3f(vx, vy, 0.005)
    gl.glEnd()


def robot_link_material(
    kinematics, mesh_rel_path: str, colliding: bool
) -> Tuple[Tuple[float, float, float], float, float, Tuple[float, float, float]]:
    """Resolve official G1 PBR-like studio material: (base_rgb, metallic, roughness, emissive).

    Follows user preference 1A: URDF <material> defines 'white' satin silver-grey aluminum and
    'dark' matte charcoal joints/pelvis/feet/visor/logo, while *_rubber_hand.STL uses dark charcoal rubber.
    """
    if colliding:
        return (0.92, 0.28, 0.30), 0.25, 0.45, (0.18, 0.02, 0.02)
    if "rubber_hand" in mesh_rel_path.lower():
        return (0.15, 0.16, 0.18), 0.06, 0.84, (0.0, 0.0, 0.0)
    rgba = getattr(kinematics, "mesh_material_rgba", {}).get(mesh_rel_path)
    if rgba is not None:
        lum = (float(rgba[0]) + float(rgba[1]) + float(rgba[2])) / 3.0
        if lum > 0.45:
            return (0.75, 0.77, 0.80), 0.58, 0.32, (0.0, 0.0, 0.0)
        return (0.17, 0.18, 0.21), 0.22, 0.58, (0.0, 0.0, 0.0)
    fb = g1_link_material_rgb(mesh_rel_path, (0.5, 0.5, 0.5), False)
    is_light = (sum(fb) / 3.0) > 0.45
    return fb, (0.55 if is_light else 0.18), (0.34 if is_light else 0.62), (0.0, 0.0, 0.0)


def robot_link_style(
    kinematics, mesh_rel_path: str, track_rgb: Tuple[float, float, float], colliding: bool
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], float]:
    """Fixed-function material fallback without artificial darkening; keeps silver-grey & charcoal look."""
    if colliding:
        return (0.94, 0.28, 0.30), _DARK_SPECULAR, 32.0
    if "rubber_hand" in mesh_rel_path.lower():
        return (0.15, 0.16, 0.18), _RUBBER_SPECULAR, 12.0
    rgba = getattr(kinematics, "mesh_material_rgba", {}).get(mesh_rel_path)
    if rgba is None:
        col = g1_link_material_rgb(mesh_rel_path, track_rgb, False)
        return col, (_SILVER_SPECULAR if sum(col) > 1.2 else _DARK_SPECULAR), 42.0
    lum = (float(rgba[0]) + float(rgba[1]) + float(rgba[2])) / 3.0
    if lum > 0.45:
        return (0.76, 0.78, 0.81), _SILVER_SPECULAR, 56.0
    return (0.20, 0.21, 0.24), _DARK_SPECULAR, 24.0


def draw_ground_positioning_ring(
    gl_mod, x: float, y: float, yaw: float, radius: float,
    rgb: Tuple[float, float, float], colliding: bool = False,
) -> None:
    """Draw multi-layer ground positioning halo ring + forward heading chevron under robot feet."""
    if hasattr(gl_mod, "glUseProgram"):
        try:
            gl_mod.glUseProgram(0)
        except Exception:
            pass
    gl_mod.glDisable(gl_mod.GL_LIGHTING)
    gl_mod.glEnable(gl_mod.GL_BLEND)
    gl_mod.glBlendFunc(gl_mod.GL_SRC_ALPHA, gl_mod.GL_ONE_MINUS_SRC_ALPHA)
    gl_mod.glDepthMask(gl_mod.GL_FALSE)

    r, g, b = (0.96, 0.26, 0.28) if colliding else (float(rgb[0]), float(rgb[1]), float(rgb[2]))
    segs = 56

    # Layer 1: translucent ground halo disc
    gl_mod.glBegin(gl_mod.GL_TRIANGLE_FAN)
    gl_mod.glColor4f(r, g, b, 0.04)
    gl_mod.glVertex3f(x, y, 0.008)
    gl_mod.glColor4f(r, g, b, 0.26 if colliding else 0.20)
    for i in range(segs + 1):
        a = 2.0 * math.pi * i / segs
        gl_mod.glVertex3f(x + radius * math.cos(a), y + radius * math.sin(a), 0.008)
    gl_mod.glEnd()

    # Layer 2: crisp outer ring
    gl_mod.glLineWidth(2.6 if colliding else 2.1)
    gl_mod.glColor4f(r, g, b, 0.96)
    gl_mod.glBegin(gl_mod.GL_LINE_LOOP)
    for i in range(segs):
        a = 2.0 * math.pi * i / segs
        gl_mod.glVertex3f(x + radius * math.cos(a), y + radius * math.sin(a), 0.012)
    gl_mod.glEnd()

    # Layer 3: inner accent ring
    gl_mod.glLineWidth(1.2)
    gl_mod.glColor4f(min(1.0, r + 0.2), min(1.0, g + 0.2), min(1.0, b + 0.2), 0.50)
    gl_mod.glBegin(gl_mod.GL_LINE_LOOP)
    r_in = radius * 0.72
    for i in range(44):
        a = 2.0 * math.pi * i / 44.0
        gl_mod.glVertex3f(x + r_in * math.cos(a), y + r_in * math.sin(a), 0.011)
    gl_mod.glEnd()

    # Layer 4: forward yaw heading chevron
    cy, sy = math.cos(yaw), math.sin(yaw)
    lx, ly = -sy, cy
    tip = radius + 0.14
    base = radius + 0.01
    half_w = 0.065
    gl_mod.glColor4f(min(1.0, r + 0.15), min(1.0, g + 0.15), min(1.0, b + 0.15), 0.95)
    gl_mod.glBegin(gl_mod.GL_TRIANGLES)
    gl_mod.glVertex3f(x + cy * tip, y + sy * tip, 0.014)
    gl_mod.glVertex3f(x + cy * base + lx * half_w, y + sy * base + ly * half_w, 0.014)
    gl_mod.glVertex3f(x + cy * base - lx * half_w, y + sy * base - ly * half_w, 0.014)
    gl_mod.glEnd()

    gl_mod.glDepthMask(gl_mod.GL_TRUE)
    gl_mod.glDisable(gl_mod.GL_BLEND)


def project_to_screen(x: float, y: float, z: float, dpr: float = 1.0) -> Optional[Tuple[float, float]]:
    """Project world point using active GL matrices into Qt logical pixel coordinates (top-left origin)."""
    model = GL.glGetDoublev(GL.GL_MODELVIEW_MATRIX).flatten().tolist()
    proj = GL.glGetDoublev(GL.GL_PROJECTION_MATRIX).flatten().tolist()
    viewport = [int(v) for v in GL.glGetIntegerv(GL.GL_VIEWPORT)]
    win_x, win_y, win_z = GLU.gluProject(float(x), float(y), float(z), model, proj, viewport)
    if float(win_z) < 0.0 or float(win_z) > 1.0:
        return None
    scale = max(1.0, float(dpr))
    return (float(win_x) / scale, (float(viewport[3]) - float(win_y)) / scale)


def collect_robot_label(
    store: List[Tuple[str, float, float, Tuple[float, float, float], str, bool]],
    target_id: str,
    x: float,
    y: float,
    rgb: Tuple[float, float, float],
    eye_xy: Optional[Tuple[float, float]] = None,
    radius: float = 0.42,
    dpr: float = 1.0,
    status_tag: str = "",
    colliding: bool = False,
) -> None:
    """Project ground-ring front edge toward camera (2A) into logical screen coordinates and queue ID pill badge."""
    if not _HAS_GL:
        return
    dx, dy = (0.0, -1.0)
    if eye_xy is not None:
        vx, vy = float(eye_xy[0]) - float(x), float(eye_xy[1]) - float(y)
        dist = math.hypot(vx, vy)
        if dist > 1e-4:
            dx, dy = vx / dist, vy / dist
    ax, ay = float(x) + dx * (float(radius) + 0.14), float(y) + dy * (float(radius) + 0.14)
    scr = project_to_screen(ax, ay, 0.02, dpr=dpr)
    if scr is not None:
        store.append((str(target_id), scr[0], scr[1], rgb, str(status_tag), bool(colliding)))


def draw_robot_id_labels(painter: QPainter, labels: Sequence[Tuple]) -> None:
    """Render high-contrast Robot ID pill badges onto the ALREADY-ACTIVE QPainter (no second painter!)."""
    if not labels or not painter.isActive():
        return
    painter.save()
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        font = QFont()
        font.setBold(True)
        font.setPointSizeF(9.5)
        painter.setFont(font)
        fm = QFontMetricsF(font)
        for item in labels:
            text, sx, sy, rgb = item[0], float(item[1]), float(item[2]), item[3]
            tag = str(item[4]) if len(item) > 4 else ""
            colliding = bool(item[5]) if len(item) > 5 else False
            display = f"{text} · {tag}" if tag else str(text)
            tw = fm.horizontalAdvance(display)
            th = fm.height()
            pad_l, pad_r, pad_v = 18.0, 9.0, 3.0
            bw, bh = tw + pad_l + pad_r, max(19.0, th + pad_v * 2.0)
            rect = QRectF(sx - bw * 0.5, sy - bh * 0.5, bw, bh)

            accent = QColor(244, 70, 76) if colliding else QColor(
                int(min(255.0, max(40.0, rgb[0] * 255.0))),
                int(min(255.0, max(40.0, rgb[1] * 255.0))),
                int(min(255.0, max(40.0, rgb[2] * 255.0))),
            )
            painter.setPen(QPen(accent, 1.4))
            painter.setBrush(QBrush(QColor(11, 15, 24, 224)))
            painter.drawRoundedRect(rect, bh * 0.5, bh * 0.5)

            dot_r = 3.5
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(accent))
            painter.drawEllipse(QRectF(rect.left() + 6.5, rect.center().y() - dot_r, dot_r * 2.0, dot_r * 2.0))

            painter.setPen(QColor(242, 246, 252))
            text_rect = QRectF(rect.left() + pad_l - 2.0, rect.top(), bw - pad_l - pad_r + 4.0, bh)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, display)
    finally:
        painter.restore()
