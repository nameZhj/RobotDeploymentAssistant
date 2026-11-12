"""
@file: src/ui/canvas_2d_renderer.py
@brief: 2D 交互式画布专用图形渲染器（网格坐标轴、PCD投影散点、机器人图标与轨迹样条）
@exports: Canvas2DRenderer
"""
import math
from typing import Any, Callable, Dict, List, Optional
import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen


class Canvas2DRenderer:
    """负责 2D 舞台交互画布图元的高效绘制与样式渲染"""

    @classmethod
    def draw_grid_and_axes(cls, p: QPainter, w: int, h: int, p0: QPointF, scale: float, to_screen: Callable[[float, float], QPointF]) -> None:
        p.setPen(QPen(QColor("#1e293b"), 1, Qt.DotLine))
        if scale >= 8:
            start_x = int(-w / 2.0 / scale) - 2
            end_x = int(w / 2.0 / scale) + 2
            for i in range(start_x, end_x):
                sp = to_screen(i, 0)
                p.drawLine(QPointF(sp.x(), 0), QPointF(sp.x(), h))
            start_y = int(-h / 2.0 / scale) - 2
            end_y = int(h / 2.0 / scale) + 2
            for i in range(start_y, end_y):
                sp = to_screen(0, i)
                p.drawLine(QPointF(0, sp.y()), QPointF(w, sp.y()))

        # 原点坐标红绿十字轴
        p.setPen(QPen(QColor("#ef4444"), 2))
        p.drawLine(p0, QPointF(p0.x() + 35, p0.y()))  # X 轴向右 (红)
        p.setPen(QPen(QColor("#22c55e"), 2))
        p.drawLine(p0, QPointF(p0.x(), p0.y() - 35))  # Y 轴向上 (绿)

    @classmethod
    def draw_pcd_scatter(cls, p: QPainter, points: Optional[np.ndarray], to_screen: Callable[[float, float], QPointF]) -> None:
        if points is None or len(points) == 0:
            return
        p.setPen(QPen(QColor(56, 189, 248, 110), 2))
        step = max(1, len(points) // 4000)
        for pt in points[::step]:
            sp = to_screen(float(pt[0]), float(pt[1]))
            p.drawPoint(sp)

    @classmethod
    def draw_robots(cls, p: QPainter, robots: Dict[str, Dict[str, Any]], scale: float, to_screen: Callable[[float, float], QPointF]) -> None:
        for r_id, r in robots.items():
            sp = to_screen(float(r["x"]), float(r["y"]))
            rad = max(6.0, 0.28 * scale)
            p.setBrush(QBrush(QColor(r.get("color", "#38bdf8"))))
            p.setPen(QPen(QColor("#ffffff"), 1.5))
            p.drawEllipse(sp, rad, rad)
            # 朝向标线
            yaw = float(r.get("yaw", 0.0))
            hx = sp.x() + rad * 1.5 * math.cos(yaw)
            hy = sp.y() - rad * 1.5 * math.sin(yaw)
            p.drawLine(sp, QPointF(hx, hy))
            p.drawText(QPointF(sp.x() - 5, sp.y() + 4), r_id)

    @classmethod
    def draw_trajectory(
        cls,
        p: QPainter,
        control_points: List[Dict[str, Any]],
        sampled_points: List[Dict[str, Any]],
        selected_idx: int,
        target_type: str,
        to_screen: Callable[[float, float], QPointF],
    ) -> None:
        if not control_points:
            return

        # 1. 密集插值曲线
        if len(sampled_points) >= 2:
            path = QPainterPath()
            path.moveTo(to_screen(sampled_points[0]["x"], sampled_points[0]["y"]))
            for pt in sampled_points[1:]:
                path.lineTo(to_screen(pt["x"], pt["y"]))
            color = QColor("#38bdf8") if target_type == "single" else QColor("#f59e0b")
            p.setPen(QPen(color, 2.5))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)

        # 2. 控制点与朝向手柄
        for idx, cp in enumerate(control_points):
            sp = to_screen(cp["x"], cp["y"])
            is_sel = (idx == selected_idx)
            if idx == 0:
                p.setBrush(QBrush(QColor("#22c55e")))  # 起点绿色
            elif idx == len(control_points) - 1:
                p.setBrush(QBrush(QColor("#ef4444")))  # 终点红色
            else:
                p.setBrush(QBrush(QColor("#0284c7") if not is_sel else QColor("#ec4899")))
            p.setPen(QPen(QColor("#ffffff"), 1.5))
            p.drawEllipse(sp, 6, 6)

            # 朝向箭头与黄色调节手柄
            yaw = float(cp.get("yaw", 0.0))
            hx = cp["x"] + 0.45 * math.cos(yaw)
            hy = cp["y"] + 0.45 * math.sin(yaw)
            shp = to_screen(hx, hy)
            p.setPen(QPen(QColor("#facc15"), 1.5, Qt.DashLine))
            p.drawLine(sp, shp)
            p.setBrush(QBrush(QColor("#facc15")))
            p.drawEllipse(shp, 3.5, 3.5)
            p.setPen(QPen(QColor("#cbd5e1"), 1))
            p.drawText(QPointF(sp.x() + 8, sp.y() - 8), f"P{idx}")

    @classmethod
    def draw_formation(
        cls,
        p: QPainter,
        formation: Optional[Dict[str, Any]],
        scale: float,
        to_screen: Callable[[float, float], QPointF],
    ) -> None:
        if not formation or "members" not in formation:
            return
        members = formation.get("members", [])
        if not members:
            return

        center = formation.get("center", {})
        cx = float(center.get("x", 0.0))
        cy = float(center.get("y", 0.0))
        cyaw = float(center.get("yaw", 0.0))
        scp = to_screen(cx, cy)

        # 1. 阵型外框（包络虚线矩形）
        pts_x = [float(m.get("world_x", cx + m.get("offset_x", 0.0))) for m in members]
        pts_y = [float(m.get("world_y", cy + m.get("offset_y", 0.0))) for m in members]
        min_x, max_x = min(pts_x) - 0.35, max(pts_x) + 0.35
        min_y, max_y = min(pts_y) - 0.35, max(pts_y) + 0.35
        p1 = to_screen(min_x, max_y)
        p2 = to_screen(max_x, min_y)
        p.setPen(QPen(QColor(245, 158, 11, 160), 1.2, Qt.DashLine))
        p.setBrush(QBrush(QColor(245, 158, 11, 25)))
        p.drawRect(p1.x(), p1.y(), p2.x() - p1.x(), p2.y() - p1.y())

        # 2. 阵型中心菱形与航向指示手柄
        p.setPen(QPen(QColor("#ffffff"), 1.5))
        p.setBrush(QBrush(QColor("#f59e0b")))
        p.drawPolygon([QPointF(scp.x(), scp.y() - 6), QPointF(scp.x() + 6, scp.y()), QPointF(scp.x(), scp.y() + 6), QPointF(scp.x() - 6, scp.y())])
        shx = scp.x() + 0.8 * scale * math.cos(cyaw)
        shy = scp.y() - 0.8 * scale * math.sin(cyaw)
        p.setPen(QPen(QColor("#f59e0b"), 2))
        p.drawLine(scp, QPointF(shx, shy))
        p.drawEllipse(QPointF(shx, shy), 3.5, 3.5)

        # 3. 碰撞告警红线
        warn_set = set()
        pos_map: Dict[str, QPointF] = {}
        for m in members:
            rid = str(m.get("robot_id", ""))
            wx = float(m.get("world_x", cx + m.get("offset_x", 0.0)))
            wy = float(m.get("world_y", cy + m.get("offset_y", 0.0)))
            pos_map[rid] = to_screen(wx, wy)

        for w in formation.get("warnings", []):
            ra, rb = str(w.get("robot_a")), str(w.get("robot_b"))
            warn_set.add(ra)
            warn_set.add(rb)
            if ra in pos_map and rb in pos_map:
                p.setPen(QPen(QColor("#ef4444"), 2, Qt.DashLine))
                p.drawLine(pos_map[ra], pos_map[rb])
                mid = QPointF((pos_map[ra].x() + pos_map[rb].x()) / 2.0, (pos_map[ra].y() + pos_map[rb].y()) / 2.0)
                p.setPen(QPen(QColor("#f87171"), 1))
                p.drawText(mid, f"⚠️ {w.get('distance', 0.0)}m")

        # 4. 成员机器人圆盘与朝向
        rad = max(7.0, 0.28 * scale)
        for m in members:
            rid = str(m.get("robot_id", ""))
            sp = pos_map.get(rid, scp)
            is_warn = rid in warn_set
            p.setBrush(QBrush(QColor("#ef4444") if is_warn else QColor("#06b6d4")))
            p.setPen(QPen(QColor("#ffffff"), 1.8 if is_warn else 1.2))
            p.drawEllipse(sp, rad, rad)
            yaw = float(m.get("world_yaw", cyaw + m.get("offset_yaw", 0.0)))
            hx = sp.x() + rad * 1.4 * math.cos(yaw)
            hy = sp.y() - rad * 1.4 * math.sin(yaw)
            p.setPen(QPen(QColor("#ffffff"), 1.5))
            p.drawLine(sp, QPointF(hx, hy))
            p.setPen(QPen(QColor("#ffffff"), 1))
            p.drawText(QPointF(sp.x() - 4, sp.y() + 4), rid)
