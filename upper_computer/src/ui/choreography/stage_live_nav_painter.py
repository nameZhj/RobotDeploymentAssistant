# @file: src/ui/choreography/stage_live_nav_painter.py
# @brief: Renders real-time ROS robot pose, global path, /cad_scan contour, goal marker, and pose-drag arrow on 2D map.
# @exports: LiveNavOverlayState, paint_live_nav_overlay

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import List, Optional, Tuple
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF

from src.ui.choreography.stage_painters import world_to_screen


@dataclass
class LiveNavOverlayState:
    """Real-time ROS telemetry & interactive goal/initialpose drag state for 2D map."""

    pose: Optional[Tuple[float, float, float]] = None
    global_path: List[Tuple[float, float]] = field(default_factory=list)
    scan_xy: List[Tuple[float, float]] = field(default_factory=list)
    active_goal: Optional[Tuple[float, float, float]] = None
    drag_start: Optional[Tuple[float, float]] = None
    drag_end: Optional[Tuple[float, float]] = None
    drag_kind: str = ""  # "set_initialpose" | "set_nav_goal"


def _draw_arrow(p: QPainter, x: float, y: float, yaw: float, origin: QPointF, ppm: float, color: str, radius_px: float = 10.0) -> None:
    sc = world_to_screen(x, y, origin, ppm)
    p.setBrush(QColor(color))
    p.setPen(QPen(QColor("#ffffff"), 1.6))
    p.drawEllipse(sc, radius_px, radius_px)
    tip = world_to_screen(x + 0.65 * math.cos(yaw), y + 0.65 * math.sin(yaw), origin, ppm)
    p.setPen(QPen(QColor(color), 2.6))
    p.drawLine(sc, tip)


def paint_live_nav_overlay(p: QPainter, ov: LiveNavOverlayState, origin: QPointF, ppm: float) -> None:
    """Paint real ROS global planner path, scan points, active goal, live pose, and interactive drag arrow."""
    if ov.global_path and len(ov.global_path) >= 2:
        p.setPen(QPen(QColor("#22d3ee"), 2.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        poly = QPolygonF([world_to_screen(pt[0], pt[1], origin, ppm) for pt in ov.global_path])
        p.drawPolyline(poly)

    if ov.scan_xy:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#f59e0b"))
        for sx, sy in ov.scan_xy[:240]:
            pt = world_to_screen(sx, sy, origin, ppm)
            p.drawEllipse(pt, 2.2, 2.2)

    if ov.active_goal is not None:
        gx, gy, gyaw = ov.active_goal
        _draw_arrow(p, gx, gy, gyaw, origin, ppm, "#f43f5e", radius_px=7.5)
        sc = world_to_screen(gx, gy, origin, ppm)
        p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        p.setPen(QColor("#fda4af"))
        p.drawText(QRectF(sc.x() - 28, sc.y() - 24, 56, 14), Qt.AlignmentFlag.AlignCenter, "GOAL")

    if ov.pose is not None:
        px, py, pyaw = ov.pose
        _draw_arrow(p, px, py, pyaw, origin, ppm, "#10b981", radius_px=9.0)
        sc = world_to_screen(px, py, origin, ppm)
        p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        p.setPen(QColor("#6ee7b7"))
        p.drawText(QRectF(sc.x() - 32, sc.y() + 11, 64, 15), Qt.AlignmentFlag.AlignCenter, "REAL ROS")

    if ov.drag_start is not None and ov.drag_end is not None:
        x0, y0 = ov.drag_start
        x1, y1 = ov.drag_end
        yaw = math.atan2(y1 - y0, x1 - x0) if math.hypot(x1 - x0, y1 - y0) > 0.05 else 0.0
        col = "#34d399" if ov.drag_kind == "set_initialpose" else "#38bdf8"
        _draw_arrow(p, x0, y0, yaw, origin, ppm, col, radius_px=8.0)
