"""
@file: src/ui/choreo_page/map_canvas_renderer.py
@brief: 2D 舞台网格标尺、占据栅格与机器人姿态绘制渲染器
@exports: MapCanvasRenderer
"""
import math
from typing import Any, Dict, List, Optional, Tuple
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen


class MapCanvasRenderer:
    """提供 2D 舞台背景网格、刻度轴、点云切片栅格、轨迹样条与机器人航向绘制"""

    @staticmethod
    def draw_grid_and_axes(p: QPainter, w: int, h: int, cx: float, cy: float, scale: float) -> None:
        p.setPen(QPen(QColor("#1A202C"), 1))
        step = max(scale, 10.0)
        start_x = cx % step
        while start_x < w:
            p.drawLine(int(start_x), 0, int(start_x), h)
            start_x += step
        start_y = cy % step
        while start_y < h:
            p.drawLine(0, int(start_y), w, int(start_y))
            start_y += step

        # X-axis (Red, Y=0), Y-axis (Green, X=0)
        p.setPen(QPen(QColor("#EF4444"), 2))
        p.drawLine(0, int(cy), w, int(cy))
        p.setPen(QPen(QColor("#10B981"), 2))
        p.drawLine(int(cx), 0, int(cx), h)

        # Scale tick marks and numbers (meters)
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor("#64748B"))
        tick_interval = 5 if scale < 40 else 2
        for m in range(-40, 41, tick_interval):
            px = cx + m * scale
            if 0 <= px <= w:
                p.drawLine(int(px), int(cy) - 4, int(px), int(cy) + 4)
                p.drawText(int(px) - 8, int(cy) + 14, f"{m}")
            py = cy - m * scale
            if 0 <= py <= h and m != 0:
                p.drawLine(int(cx) - 4, int(py), int(cx) + 4, int(py))
                p.drawText(int(cx) + 6, int(py) + 4, f"{m}")

    @staticmethod
    def draw_occupancy_grid(
        p: QPainter, grid_img: Optional[QImage], grid_info: Optional[Dict[str, Any]],
        cx: float, cy: float, scale: float
    ) -> None:
        if grid_img is None or not grid_info:
            return
        ox = float(grid_info.get("origin_x", 0.0))
        oy = float(grid_info.get("origin_y", 0.0))
        res = float(grid_info.get("resolution", 0.05))
        gw = int(grid_info.get("width", grid_img.width()))
        gh = int(grid_info.get("height", grid_img.height()))

        max_x = ox + gw * res
        max_y = oy + gh * res

        top_left_x = cx + ox * scale
        top_left_y = cy - max_y * scale
        bottom_right_x = cx + max_x * scale
        bottom_right_y = cy - oy * scale

        target_rect = QRectF(
            QPointF(top_left_x, top_left_y),
            QPointF(bottom_right_x, bottom_right_y)
        )
        p.setOpacity(0.85)
        p.drawImage(target_rect, grid_img)
        p.setOpacity(1.0)

    @staticmethod
    def draw_robot_spawns(
        p: QPainter, robots: List[Dict[str, Any]], selected_id: Optional[str],
        cx: float, cy: float, scale: float, poses: Optional[Dict[Any, Any]] = None
    ) -> None:
        p.setFont(QFont("Segoe UI", 9, QFont.Bold))
        for r in robots:
            rid = str(r.get("id", ""))
            name = r.get("name", f"Robot_{rid}")
            color = QColor(r.get("color", "#38BDF8"))
            rx_m, ry_m = r.get("pos", (0.0, 0.0))
            yaw_deg = float(r.get("yaw_deg", 0.0))

            if poses and rid in poses:
                rx_m, ry_m = poses[rid][0], poses[rid][1]

            rx = cx + rx_m * scale
            ry = cy - ry_m * scale
            is_selected = (selected_id is not None and str(selected_id) == rid)

            # Robot circle
            if is_selected:
                p.setPen(QPen(QColor("#FBBF24"), 3))
                p.setBrush(QBrush(color.lighter(130)))
                p.drawEllipse(QPointF(rx, ry), 12, 12)
            else:
                p.setPen(QPen(color.lighter(140), 2))
                p.setBrush(QBrush(color))
                p.drawEllipse(QPointF(rx, ry), 9, 9)

            # Heading indicator
            rad = math.radians(yaw_deg)
            hx = rx + 16 * math.cos(rad)
            hy = ry - 16 * math.sin(rad)
            p.setPen(QPen(QColor("#F8FAFC"), 2))
            p.drawLine(QPointF(rx, ry), QPointF(hx, hy))

            # Label text
            p.setPen(QColor("#F8FAFC"))
            p.drawText(int(rx) + 14, int(ry) + 4, f"{name} ({rid})")

    @staticmethod
    def draw_spline_trajectory(
        p: QPainter, waypoints: List[Tuple[float, float]],
        spline_pts: Optional[List[Tuple[float, float]]],
        is_active: bool, cx: float, cy: float, scale: float,
        hover_pos: Optional[Tuple[float, float]] = None,
        is_selected: bool = False,
        drag_idx: Optional[int] = None
    ) -> None:
        pts = spline_pts if spline_pts and len(spline_pts) > 1 else waypoints
        if not pts and not (is_active and hover_pos):
            return

        # Curve
        if pts:
            if is_selected:
                pen_color, pen_w = QColor("#F59E0B"), 3
            elif is_active:
                pen_color, pen_w = QColor("#00D2FF"), 2
            else:
                pen_color, pen_w = QColor("#0284C7"), 2
            p.setPen(QPen(pen_color, pen_w, Qt.SolidLine))
            for i in range(1, len(pts)):
                p1 = QPointF(cx + pts[i - 1][0] * scale, cy - pts[i - 1][1] * scale)
                p2 = QPointF(cx + pts[i][0] * scale, cy - pts[i][1] * scale)
                p.drawLine(p1, p2)

            # Directional arrows on smooth curve
            MapCanvasRenderer._draw_direction_arrows(p, pts, cx, cy, scale)

        # Temporary hover line and preview dot
        if is_active and hover_pos and waypoints:
            last_wp = waypoints[-1]
            p_last = QPointF(cx + last_wp[0] * scale, cy - last_wp[1] * scale)
            p_hover = QPointF(cx + hover_pos[0] * scale, cy - hover_pos[1] * scale)
            p.setPen(QPen(QColor("#FBBF24"), 1.5, Qt.DashLine))
            p.drawLine(p_last, p_hover)
            p.setBrush(QBrush(QColor("#FBBF24")))
            p.setPen(QPen(Qt.white, 1))
            p.drawEllipse(p_hover, 4, 4)

        # Waypoint control dots
        for idx, (wx, wy) in enumerate(waypoints):
            px = cx + wx * scale
            py = cy - wy * scale
            is_being_dragged = (drag_idx is not None and drag_idx == idx)
            dot_r = 7 if is_being_dragged else (6 if is_selected else 5)
            p.setBrush(QBrush(QColor("#F59E0B") if (is_selected or is_active) else QColor("#38BDF8")))
            p.setPen(QPen(Qt.white if not is_being_dragged else QColor("#F59E0B"), 2 if is_selected else 1))
            p.drawEllipse(QPointF(px, py), dot_r, dot_r)
            p.setFont(QFont("Segoe UI", 7, QFont.Bold))
            p.setPen(QColor("#E2E8F0"))
            p.drawText(int(px) + 6, int(py) - 6, f"P{idx + 1}")

    @staticmethod
    def draw_status_toast(p: QPainter, w: int, text: str, level: str = "info") -> None:
        """在画布顶部中央渲染非侵入式状态与校验提示胶囊"""
        if not text:
            return
        p.save()
        p.setFont(QFont("Segoe UI", 9, QFont.Bold))
        metrics = p.fontMetrics()
        txt_w = metrics.horizontalAdvance(text) + 24
        txt_h = 28
        x = (w - txt_w) / 2.0
        rect = QRectF(x, 12.0, txt_w, txt_h)

        if level == "error":
            bg = QColor(220, 38, 38, 230)
            pen = QPen(QColor("#FCA5A5"), 1.5)
            text_color = Qt.white
        else:
            bg = QColor(15, 23, 42, 220)
            pen = QPen(QColor("#38BDF8"), 1.5)
            text_color = QColor("#38BDF8")

        p.setBrush(QBrush(bg))
        p.setPen(pen)
        p.drawRoundedRect(rect, 6, 6)
        p.setPen(text_color)
        p.drawText(rect, Qt.AlignCenter, text)
        p.restore()

    @staticmethod
    def load_pcd_grid_image(file_path: Optional[str] = None) -> Tuple[Optional[QImage], Optional[Dict[str, Any]], Dict[str, Any]]:
        """从 PCD 文件加载点云并生成占有栅格 QImage 与元数据字典"""
        from src.domain.map.grid_and_calibration import MapGridProcessor
        from src.infrastructure.map.pcd_io_engine import PcdMapLoader
        import numpy as np

        points = PcdMapLoader.load_pcd(file_path or "")
        _, inflated, info = MapGridProcessor.generate_2d_occupancy_grid(points)
        flipped = np.flipud(inflated)
        h, w = flipped.shape
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        rgba[flipped > 0] = [56, 189, 248, 140]
        img = QImage(rgba.data, w, h, w * 4, QImage.Format_RGBA8888).copy()
        meta = {
            "name": "PCD 舞台" if file_path else "默认数字舞台",
            "map_file": file_path or "default_stage.pcd",
            "dimensions": f"{info['width'] * info['resolution']:.1f}m × {info['height'] * info['resolution']:.1f}m",
            "resolution": info["resolution"],
            "origin": f"({info['origin_x']:.1f}, {info['origin_y']:.1f})",
            "status": "已加载 (Loaded)",
        }
        return img, info, meta

    @staticmethod
    def _draw_direction_arrows(
        p: QPainter, pts: List[Tuple[float, float]],
        cx: float, cy: float, scale: float
    ) -> None:
        if len(pts) < 2:
            return
        step = max(1, len(pts) // 6)
        p.setPen(QPen(QColor("#FBBF24"), 2))
        for i in range(step, len(pts), step):
            x0, y0 = pts[i - 1]
            x1, y1 = pts[i]
            sx0, sy0 = cx + x0 * scale, cy - y0 * scale
            sx1, sy1 = cx + x1 * scale, cy - y1 * scale
            ang = math.atan2(sy1 - sy0, sx1 - sx0)
            mx, my = (sx0 + sx1) / 2.0, (sy0 + sy1) / 2.0
            p.drawLine(QPointF(mx, my), QPointF(mx - 8 * math.cos(ang - 0.4), my - 8 * math.sin(ang - 0.4)))
            p.drawLine(QPointF(mx, my), QPointF(mx - 8 * math.cos(ang + 0.4), my - 8 * math.sin(ang + 0.4)))
