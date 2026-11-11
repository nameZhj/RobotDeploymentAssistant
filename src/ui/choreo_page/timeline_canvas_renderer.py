"""
@file: src/ui/choreo_page/timeline_canvas_renderer.py
@brief: 编排时间轴背景网格、双子层轨道、Clip 块、障碍线与游标绘制渲染器
@exports: TimelineCanvasRenderer
"""
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen


class TimelineCanvasRenderer:
    """提供时间轴刻度标尺、多机双层轨道网格、Clip 块与红光游标渲染服务"""

    @staticmethod
    def draw_grid_and_tracks(p: QPainter, tracks: List[Dict[str, str]], ruler_h: int, track_h: int, w: int) -> None:
        pen_grid = QPen(QColor("#1F2430"), 1)
        p.setFont(QFont("Segoe UI", 9, QFont.Bold))
        for i, trk in enumerate(tracks):
            y = ruler_h + i * track_h
            p.setPen(pen_grid)
            p.drawLine(0, y, w, y)
            p.setPen(QPen(QColor("#191C24"), 1, Qt.DashLine))
            p.drawLine(0, y + track_h // 2, w, y + track_h // 2)
            p.setPen(QColor("#475569"))
            p.drawText(8, y + 16, trk["name"])
        bottom_y = ruler_h + len(tracks) * track_h
        p.setPen(pen_grid)
        p.drawLine(0, bottom_y, w, bottom_y)

    @staticmethod
    def draw_blocks(
        p: QPainter, blocks: list, tracks: List[Dict[str, str]], ruler_h: int,
        track_h: int, px_per_sec: float, selected_block: Any
    ) -> None:
        track_map = {trk["id"]: i for i, trk in enumerate(tracks)}
        for b in blocks:
            t_idx = track_map.get(b.track_id, 0)
            x = (b.start_ms / 1000.0) * px_per_sec
            bw = max(8.0, (b.duration_ms / 1000.0) * px_per_sec)
            top = ruler_h + t_idx * track_h
            sub_h = track_h // 2 - 2
            y = top + 2 if b.is_upper_action else top + track_h // 2 + 1
            rect = QRectF(x, y, bw, sub_h)

            if b.is_group:
                color_fill = QColor("#7C3AED")
            elif b.is_upper_action:
                color_fill = QColor("#1E6FFF")
            else:
                color_fill = QColor("#059669")

            is_sel = (b == selected_block)
            p.setPen(QPen(QColor("#FBBF24"), 2) if is_sel else QPen(color_fill.lighter(130), 1))
            p.setBrush(QBrush(color_fill))
            p.drawRoundedRect(rect, 3, 3)

            if is_sel and b.allow_stretch:
                p.setPen(QPen(QColor("#FBBF24"), 2))
                p.drawLine(int(rect.right() - 2), int(rect.top() + 3), int(rect.right() - 2), int(rect.bottom() - 3))

            p.setPen(QColor("#FFFFFF"))
            p.setFont(QFont("Segoe UI", 9, QFont.Bold))
            p.drawText(rect.adjusted(6, 0, -8, 0), Qt.AlignVCenter | Qt.AlignLeft, b.name)

    @staticmethod
    def draw_barriers(p: QPainter, barriers: list, ruler_h: int, px_per_sec: float, h: int) -> None:
        for bar in barriers:
            bx = (bar.time_ms / 1000.0) * px_per_sec
            p.setPen(QPen(QColor("#F59E0B"), 2, Qt.DashLine))
            p.drawLine(int(bx), ruler_h, int(bx), h)
            p.setPen(QColor("#F59E0B"))
            p.setFont(QFont("Segoe UI", 8, QFont.Bold))
            p.drawText(int(bx) + 4, ruler_h + 14, f"⚡ {bar.barrier_id}")

    @staticmethod
    def draw_ruler(p: QPainter, ruler_h: int, px_per_sec: float, w: int) -> None:
        p.fillRect(0, 0, w, ruler_h, QColor("#171A21"))
        p.setPen(QPen(QColor("#2B3448"), 1))
        p.drawLine(0, ruler_h, w, ruler_h)
        p.setFont(QFont("Segoe UI", 9))
        p.setPen(QColor("#94A3B8"))
        step_s = 5 if px_per_sec < 60 else (2 if px_per_sec < 120 else 1)
        for s in range(0, int((w / px_per_sec) + 1), step_s):
            x = s * px_per_sec
            p.drawLine(int(x), ruler_h - 8, int(x), ruler_h)
            mm, ss = divmod(s, 60)
            p.drawText(int(x) + 3, ruler_h - 10, f"{mm:02d}:{ss:02d}")

    @staticmethod
    def draw_cursor(p: QPainter, current_time_ms: int, px_per_sec: float, h: int) -> None:
        cx = (current_time_ms / 1000.0) * px_per_sec
        p.setPen(QPen(QColor("#EF4444"), 2))
        p.drawLine(int(cx), 0, int(cx), h)
        sec_total = current_time_ms / 1000.0
        badge = f"{int(sec_total // 60):02d}:{sec_total % 60:06.3f}"
        p.setPen(Qt.NoPen); p.setBrush(QColor("#EF4444"))
        p.drawRoundedRect(QRectF(cx - 36, 2, 72, 18), 3, 3)
        p.setPen(QColor("#FFFFFF")); p.setFont(QFont("Consolas", 9, QFont.Bold))
        p.drawText(QRectF(cx - 36, 2, 72, 18), Qt.AlignCenter, badge)
