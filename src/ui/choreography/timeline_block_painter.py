# @file: src/ui/choreography/timeline_block_painter.py
# @brief: High-contrast QPainter renderers for the time ruler, playhead, robot track headers, and timeline blocks.
# @exports: RULER_H, LANE_H, paint_ruler, paint_track_sidebar, paint_lane_blocks, paint_empty_timeline_hint

from __future__ import annotations

import math
from typing import Dict, List, Optional, Set
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from src.domain.timeline_entities import TimelineBlockEntity
from src.domain.track_entities import TrackEntity
from src.ui.design_system.tokens import (
    C_ACCENT,
    C_BASE,
    C_CARD,
    C_DANGER,
    C_PANEL,
    C_TEXT_1,
    C_TEXT_2,
    C_TEXT_3,
    LINE,
)

RULER_H = 28
LANE_H = 54


def paint_ruler(
    p: QPainter, x0: int, width: int, pps: float, scroll_x: int, playhead_s: float
) -> None:
    p.fillRect(x0, 0, width, RULER_H, QColor(C_CARD))
    p.setPen(QColor(LINE))
    p.drawLine(x0, RULER_H - 1, x0 + width, RULER_H - 1)

    t_min = max(0, int(math.floor(scroll_x / max(4.0, pps))))
    t_max = int(math.ceil((scroll_x + width) / max(4.0, pps))) + 1
    major = 1 if pps >= 28 else (2 if pps >= 14 else 5)

    font = QFont("Consolas", 9)
    p.setFont(font)
    for sec in range(t_min, t_max + 1):
        px = int(x0 + sec * pps - scroll_x)
        if px < x0 or px > x0 + width:
            continue
        is_maj = sec % major == 0
        p.setPen(QColor(C_TEXT_2 if is_maj else LINE))
        p.drawLine(px, RULER_H - (11 if is_maj else 6), px, RULER_H - 1)
        if is_maj:
            p.setPen(QColor(C_TEXT_2))
            p.drawText(px + 3, 14, f"{sec}s")

    # Playhead marker triangle
    ph_x = int(x0 + playhead_s * pps - scroll_x)
    if x0 <= ph_x <= x0 + width:
        p.setPen(QPen(QColor(C_DANGER), 2.0))
        p.drawLine(ph_x, 0, ph_x, RULER_H)


def paint_track_sidebar(
    p: QPainter, w: int, tracks: List[TrackEntity], y_top: int, selected_track_id: Optional[int]
) -> None:
    p.fillRect(0, y_top, w, len(tracks) * LANE_H + 80, QColor(C_PANEL))
    p.setPen(QColor(LINE))
    p.drawLine(w - 1, 0, w - 1, len(tracks) * LANE_H + 80)

    font_b = QFont("Microsoft YaHei UI", 9, QFont.Weight.Bold)
    font_s = QFont("Consolas", 8)
    for idx, tr in enumerate(tracks):
        ry = y_top + idx * LANE_H
        bg = QColor("#181b22" if tr.id == selected_track_id else C_CARD)
        p.fillRect(0, ry, w - 1, LANE_H - 1, bg)
        p.setPen(QColor(LINE))
        p.drawLine(0, ry + LANE_H - 1, w - 1, ry + LANE_H - 1)

        # Track color pill bar
        p.fillRect(4, ry + 8, 4, LANE_H - 16, QColor(tr.color_hex))

        p.setFont(font_b)
        p.setPen(QColor(C_TEXT_1))
        p.drawText(QRectF(14, ry + 5, w - 58, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, tr.name)

        # LRMP target badge
        p.setFont(font_s)
        p.setPen(QColor(C_ACCENT))
        p.drawText(QRectF(w - 44, ry + 6, 36, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"[{tr.target_id}]")

        p.setPen(QColor(C_TEXT_3))
        flags = f"{'M ' if tr.muted else ''}{'L ' if tr.locked else ''}"
        p.drawText(
            QRectF(14, ry + 24, w - 20, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{flags}({tr.init_x:.1f},{tr.init_y:.1f}) {tr.robot_ip.split('.')[-1]}",
        )


def paint_empty_timeline_hint(p: QPainter, x0: int, w: int, y_top: int, tracks: List[TrackEntity]) -> None:
    if tracks:
        return
    p.setFont(QFont("Microsoft YaHei UI", 10))
    p.setPen(QColor(C_TEXT_3))
    p.drawText(
        QRectF(x0 + 12, y_top + 24, max(120, w - 24), 48),
        Qt.AlignmentFlag.AlignCenter,
        "暂无真实机器人轨道 — 请点击上方『+ 轨道』按钮真实添加机器人",
    )


def paint_lane_blocks(
    p: QPainter,
    x0: int,
    w: int,
    y_top: int,
    tracks: List[TrackEntity],
    blocks: List[TimelineBlockEntity],
    overlap_ids: Set[int],
    pps: float,
    scroll_x: int,
    selected_block_id: Optional[int],
    playhead_s: float,
) -> None:
    row_map: Dict[int, int] = {tr.id: idx for idx, tr in enumerate(tracks) if tr.id is not None}
    color_map: Dict[int, str] = {tr.id: tr.color_hex for tr in tracks if tr.id is not None}

    for idx, _tr in enumerate(tracks):
        ry = y_top + idx * LANE_H
        p.fillRect(x0, ry, w, LANE_H - 1, QColor(C_BASE if idx % 2 == 0 else "#0d0f13"))
        p.setPen(QPen(QColor("#1a1e26"), 1.0, Qt.PenStyle.DotLine))
        p.drawLine(x0, ry + LANE_H // 2, x0 + w, ry + LANE_H // 2)
        p.setPen(QColor(LINE))
        p.drawLine(x0, ry + LANE_H - 1, x0 + w, ry + LANE_H - 1)

    font_t = QFont("Microsoft YaHei UI", 8, QFont.Weight.DemiBold)
    font_s = QFont("Consolas", 8)
    for blk in blocks:
        ridx = row_map.get(blk.track_id)
        if ridx is None:
            continue
        is_action = blk.block_type == "action"
        sub_y = y_top + ridx * LANE_H + (3 if is_action else (LANE_H // 2 + 2))
        sub_h = (LANE_H // 2) - 5
        bx0 = x0 + blk.start_time * pps - scroll_x
        bw = max(18.0, blk.duration * pps)
        if bx0 + bw < x0 or bx0 > x0 + w:
            continue

        rect = QRectF(bx0, sub_y, bw, sub_h)
        base_col = QColor("#8b5cf6" if is_action else color_map.get(blk.track_id, C_ACCENT))
        fill = QColor(base_col)
        fill.setAlpha(65 if blk.is_ignored else 155)
        p.setBrush(fill)

        is_sel = blk.id is not None and blk.id == selected_block_id
        is_err = (blk.id in overlap_ids) if blk.id is not None else False
        border_col = QColor(C_DANGER if is_err else ("#ffffff" if is_sel else base_col.name()))
        p.setPen(QPen(border_col, 2.0 if (is_sel or is_err) else 1.2))
        p.drawRoundedRect(rect, 4, 4)

        p.setFont(font_t)
        p.setPen(QColor("#ffffff"))
        tag = f"♪ {blk.title} · {blk.duration:.1f}s" if is_action else f"{blk.title} · {blk.duration:.1f}s"
        p.drawText(rect.adjusted(6, 0, -6, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, tag)
    _ = font_s

    # Full-height playhead line
    ph_x = int(x0 + playhead_s * pps - scroll_x)
    if x0 <= ph_x <= x0 + w:
        p.setPen(QPen(QColor(C_DANGER), 1.5))
        p.drawLine(ph_x, y_top, ph_x, y_top + len(tracks) * LANE_H + 40)
