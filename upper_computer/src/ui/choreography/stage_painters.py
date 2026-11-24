# @file: src/ui/choreography/stage_painters.py
# @brief: Modular QPainter render helpers for 2D stage grid, occupancy PNGs, splines, draft drawing, sketches, and robots.
# @exports: world_to_screen, screen_to_world, paint_grid_and_stage, paint_occupancy_map, paint_trajectories, paint_robots_and_collisions, paint_draft_trajectory, paint_sketches, paint_empty_stage_hint

from __future__ import annotations

import math
from typing import Dict, List, Optional, Set, Tuple
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF

from src.domain.trajectory_entities import ControlPoint2D
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.tokens import C_ACCENT, C_CANVAS, C_DANGER, C_OK, C_TEXT_2, C_TEXT_3, C_WARN


def world_to_screen(wx: float, wy: float, origin_px: QPointF, ppm: float) -> QPointF:
    """Transform Z-up metric world (x, y) to Qt Y-down pixel coordinates."""
    return QPointF(origin_px.x() + wx * ppm, origin_px.y() - wy * ppm)


def screen_to_world(sx: float, sy: float, origin_px: QPointF, ppm: float) -> tuple[float, float]:
    """Transform Qt pixel coordinates back to metric stage (x, y)."""
    safe_ppm = max(4.0, ppm)
    return ((sx - origin_px.x()) / safe_ppm, (origin_px.y() - sy) / safe_ppm)


def paint_grid_and_stage(
    p: QPainter, w: int, h: int, origin: QPointF, ppm: float, stage_len: float, stage_wid: float
) -> None:
    p.fillRect(0, 0, w, h, QColor(C_CANVAS))
    # Metric grid lines
    min_wx, max_wy = screen_to_world(0, 0, origin, ppm)
    max_wx, min_wy = screen_to_world(w, h, origin, ppm)
    step = 1.0 if ppm >= 22 else (2.0 if ppm >= 10 else 5.0)

    minor_pen = QPen(QColor("#14171d"), 1.0)
    major_pen = QPen(QColor("#1d232c"), 1.2)
    ix0, ix1 = int(math.floor(min_wx / step)), int(math.ceil(max_wx / step))
    iy0, iy1 = int(math.floor(min_wy / step)), int(math.ceil(max_wy / step))

    for ix in range(ix0, ix1 + 1):
        wx = ix * step
        pt = world_to_screen(wx, 0.0, origin, ppm)
        p.setPen(major_pen if ix % 5 == 0 else minor_pen)
        p.drawLine(int(pt.x()), 0, int(pt.x()), h)
    for iy in range(iy0, iy1 + 1):
        wy = iy * step
        pt = world_to_screen(0.0, wy, origin, ppm)
        p.setPen(major_pen if iy % 5 == 0 else minor_pen)
        p.drawLine(0, int(pt.y()), w, int(pt.y()))

    # Origin axes
    p.setPen(QPen(QColor("#ef4444"), 1.4))
    p.drawLine(int(origin.x()), int(origin.y()), int(origin.x() + 0.8 * ppm), int(origin.y()))
    p.setPen(QPen(QColor("#22c55e"), 1.4))
    p.drawLine(int(origin.x()), int(origin.y()), int(origin.x()), int(origin.y() - 0.8 * ppm))

    # Stage boundary rectangle
    tl = world_to_screen(-stage_len * 0.5, stage_wid * 0.5, origin, ppm)
    br = world_to_screen(stage_len * 0.5, -stage_wid * 0.5, origin, ppm)
    p.setPen(QPen(QColor(C_ACCENT), 1.6, Qt.PenStyle.DashLine))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(tl, br))


def paint_occupancy_map(
    p: QPainter,
    grid_img: Optional[QImage],
    ox: float,
    oy: float,
    res: float,
    origin: QPointF,
    ppm: float,
) -> None:
    if grid_img is None or grid_img.isNull():
        return
    wm = grid_img.width() * res
    hm = grid_img.height() * res
    tl = world_to_screen(ox, oy + hm, origin, ppm)
    br = world_to_screen(ox + wm, oy, origin, ppm)
    p.setOpacity(0.75)
    p.drawImage(QRectF(tl, br), grid_img)
    p.setOpacity(1.0)


def paint_trajectories(p: QPainter, state: StudioStateService, origin: QPointF, ppm: float, show_all: bool) -> None:
    if not show_all:
        return
    by_no = {t.track_no: t for t in state.tracks}
    track_colors: Dict[int, str] = {}
    for blk in state.blocks:
        if blk.block_type == "trajectory":
            tr = next((t for t in state.tracks if t.id == blk.track_id), None)
            if tr:
                track_colors[blk.ref_id] = tr.color_hex

    font = QFont("Consolas", 8)
    for tid, pts in state.sampled_trajs.items():
        if len(pts) < 2:
            continue
        traj = state.trajectories.get(tid)
        if traj is not None and not traj.visible_on_map:
            continue
        color_hex = track_colors.get(tid, "")
        if not color_hex and traj and traj.bound_track_nos:
            bound_tr = by_no.get(traj.bound_track_nos[0])
            if bound_tr:
                color_hex = bound_tr.color_hex
        col = QColor(color_hex or "#60a5fa")
        p.setPen(QPen(col, 2.0))
        step = max(1, len(pts) // 80)
        poly = QPolygonF([world_to_screen(float(r[1]), float(r[2]), origin, ppm) for r in pts[::step]])
        poly.append(world_to_screen(float(pts[-1, 1]), float(pts[-1, 2]), origin, ppm))
        p.drawPolyline(poly)
        if traj and traj.bound_track_nos:
            tag = ",".join(by_no[n].target_id or f"M{n}" for n in traj.bound_track_nos if n in by_no) or ",".join(f"M{n}" for n in traj.bound_track_nos)
            if tag:
                p.setFont(font)
                p.setPen(col)
                p0 = world_to_screen(float(pts[0, 1]), float(pts[0, 2]), origin, ppm)
                p.drawText(QPointF(p0.x() + 6, p0.y() - 6), f"[{tag}]")


def paint_robots_and_collisions(
    p: QPainter,
    state: StudioStateService,
    origin: QPointF,
    ppm: float,
    safety_dist: float,
    highlight_track_id: Optional[int] = None,
) -> None:
    t = state.playhead_s
    active_colls = [c for c in state.collisions if c.start_time <= t <= c.end_time]
    colliding: Set[str] = {c.track_a for c in active_colls} | {c.track_b for c in active_colls}

    font = QFont("Microsoft YaHei UI", 9)
    font.setBold(True)
    p.setFont(font)

    poses: Dict[str, tuple[float, float, float]] = {}
    for track in state.tracks:
        x, y, yaw = state.evaluate_robot_pose(track, t)
        poses[track.name] = (x, y, yaw)
        sc = world_to_screen(x, y, origin, ppm)
        is_err = track.name in colliding
        is_sel = highlight_track_id is not None and track.id == highlight_track_id
        rad_px = max(8.0, 0.32 * ppm)
        safety_px = max(rad_px + 3.0, (safety_dist * 0.5) * ppm)

        # Safety halo
        halo_col = QColor(C_DANGER if is_err else track.color_hex)
        halo_col.setAlpha(45 if is_err else 22)
        p.setBrush(halo_col)
        p.setPen(QPen(QColor(C_DANGER if is_err else "#303640"), 1.0, Qt.PenStyle.DotLine))
        p.drawEllipse(sc, safety_px, safety_px)

        if is_sel:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#fbbf24"), 2.2))
            p.drawEllipse(sc, rad_px + 5.0, rad_px + 5.0)

        # Robot body circle + heading arrow
        body_col = QColor(C_DANGER if is_err else track.color_hex)
        p.setBrush(body_col)
        p.setPen(QPen(QColor("#ffffff"), 1.5))
        p.drawEllipse(sc, rad_px, rad_px)
        hx = sc.x() + (rad_px + 6.0) * math.cos(yaw)
        hy = sc.y() - (rad_px + 6.0) * math.sin(yaw)
        p.drawLine(sc, QPointF(hx, hy))

        p.setPen(QColor("#eef0f4"))
        p.drawText(QRectF(sc.x() - 22, sc.y() + rad_px + 2, 44, 15), Qt.AlignmentFlag.AlignCenter, f"{track.target_id}")

    # Collision warning links
    p.setPen(QPen(QColor(C_DANGER), 2.0, Qt.PenStyle.DashLine))
    for c in active_colls:
        pa, pb = poses.get(c.track_a), poses.get(c.track_b)
        if pa and pb:
            p.drawLine(world_to_screen(pa[0], pa[1], origin, ppm), world_to_screen(pb[0], pb[1], origin, ppm))

    from src.services.task_chain_normalizer import active_chain_node_label
    p.setPen(QColor(C_TEXT_3))
    p.drawText(12, 22, f"{active_chain_node_label(state.blocks, t)} | {len(state.tracks)} 台 G1")


def paint_sketches(
    p: QPainter,
    origin: QPointF,
    ppm: float,
    strokes: List[List[Tuple[float, float]]],
    active_stroke: List[Tuple[float, float]],
) -> None:
    """Render freehand reference sketch strokes on 2D stage."""
    pen = QPen(QColor("#a78bfa"), 2.0, Qt.PenStyle.DashDotLine)
    p.setPen(pen)
    for stroke in list(strokes) + ([active_stroke] if len(active_stroke) >= 2 else []):
        if len(stroke) < 2:
            continue
        poly = QPolygonF([world_to_screen(x, y, origin, ppm) for x, y in stroke])
        p.drawPolyline(poly)


def paint_draft_trajectory(
    p: QPainter,
    origin: QPointF,
    ppm: float,
    control_points: List[ControlPoint2D],
    sampled_pts: object,
    hover_world: Optional[Tuple[float, float]] = None,
) -> None:
    """Render active inline trajectory drawing spline, rubber-band leg, and numbered waypoints."""
    if sampled_pts is not None and len(sampled_pts) >= 2:
        p.setPen(QPen(QColor("#f43f5e"), 2.6))
        step = max(1, len(sampled_pts) // 100)
        poly = QPolygonF([world_to_screen(float(r[1]), float(r[2]), origin, ppm) for r in sampled_pts[::step]])
        poly.append(world_to_screen(float(sampled_pts[-1, 1]), float(sampled_pts[-1, 2]), origin, ppm))
        p.drawPolyline(poly)

    if control_points and hover_world is not None:
        last = control_points[-1]
        p.setPen(QPen(QColor(C_WARN), 1.4, Qt.PenStyle.DashLine))
        p.drawLine(world_to_screen(last.x, last.y, origin, ppm), world_to_screen(hover_world[0], hover_world[1], origin, ppm))

    font = QFont("Consolas", 8, QFont.Weight.Bold)
    p.setFont(font)
    for idx, cp in enumerate(control_points):
        sc = world_to_screen(cp.x, cp.y, origin, ppm)
        fill = QColor(C_OK if idx == 0 else C_WARN)
        p.setBrush(fill)
        p.setPen(QPen(QColor("#111317"), 1.6))
        p.drawEllipse(sc, 7.5, 7.5)
        p.setPen(QColor("#090b0f"))
        p.drawText(QRectF(sc.x() - 7, sc.y() - 7, 14, 14), Qt.AlignmentFlag.AlignCenter, str(idx + 1))


def paint_empty_stage_hint(p: QPainter, w: int, h: int, track_count: int) -> None:
    if track_count > 0:
        return
    p.setFont(QFont("Microsoft YaHei UI", 10))
    p.setPen(QColor(C_TEXT_2))
    p.drawText(
        QRectF(20, h - 42, max(120, w - 40), 28),
        Qt.AlignmentFlag.AlignCenter,
        "暂无机器人轨道，请先添加",
    )
