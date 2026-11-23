# @file: src/ui/choreography/timeline_block_painter.py
# @brief: High-contrast QPainter renderers for task-chain flow bar, robot lanes, and chained pure-name blocks.
# @exports: RULER_H, LANE_H, compute_chain_block_width, paint_ruler, paint_track_sidebar, paint_lane_blocks, paint_empty_timeline_hint

from __future__ import annotations

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

RULER_H = 26
LANE_H = 44


def compute_chain_block_width(title: str, duration: float, pps: float) -> float:
    """Compute legible task-chain node width guaranteeing Chinese/ASCII action names never clip."""
    est_text_w = sum(13.0 if ord(ch) > 127 else 7.5 for ch in (title or "")) + 20.0
    return max(56.0, est_text_w, duration * pps - 10.0)


def paint_ruler(
    p: QPainter, x0: int, width: int, pps: float, scroll_x: int, playhead_s: float
) -> None:
    """Render clean task-chain flow header without second-based timestamps or step numbers."""
    p.fillRect(x0, 0, width, RULER_H, QColor(C_CARD))
    p.setPen(QColor(LINE))
    p.drawLine(x0, RULER_H - 1, x0 + width, RULER_H - 1)

    p.setFont(QFont("Microsoft YaHei UI", 8))
    p.setPen(QColor(C_TEXT_3))
    p.drawText(QRectF(x0 + 10, 0, max(120, width - 20), RULER_H), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "任务链顺序流向 (到点触发下一动作) ➔")

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

        p.fillRect(4, ry + 7, 4, LANE_H - 14, QColor(tr.color_hex))

        p.setFont(font_b)
        p.setPen(QColor(C_TEXT_1))
        p.drawText(QRectF(14, ry + 3, w - 58, 17), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, tr.name)

        p.setFont(font_s)
        p.setPen(QColor(C_ACCENT))
        p.drawText(QRectF(w - 44, ry + 4, 36, 15), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"[{tr.target_id}]")

        p.setPen(QColor(C_TEXT_3))
        flags = f"{'M ' if tr.muted else ''}{'L ' if tr.locked else ''}"
        p.drawText(
            QRectF(14, ry + 21, w - 20, 15),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{flags}({tr.init_x:.1f},{tr.init_y:.1f}) {tr.robot_ip.split('.')[-1]}",
        )


def paint_empty_timeline_hint(p: QPainter, x0: int, w: int, y_top: int, tracks: List[TrackEntity]) -> None:
    if tracks:
        return
    p.setFont(QFont("Microsoft YaHei UI", 10))
    p.setPen(QColor(C_TEXT_3))
    p.drawText(
        QRectF(x0 + 12, y_top + 18, max(120, w - 24), 48),
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
    """Render each track's blocks as a connected task chain: '导航到点1' - '太极' - '街舞' - '导航到点2'."""
    row_map: Dict[int, int] = {tr.id: idx for idx, tr in enumerate(tracks) if tr.id is not None}
    color_map: Dict[int, str] = {tr.id: tr.color_hex for tr in tracks if tr.id is not None}

    for idx, _tr in enumerate(tracks):
        ry = y_top + idx * LANE_H
        p.fillRect(x0, ry, w, LANE_H - 1, QColor(C_BASE if idx % 2 == 0 else "#0d0f13"))
        p.setPen(QColor(LINE))
        p.drawLine(x0, ry + LANE_H - 1, x0 + w, ry + LANE_H - 1)

    blocks_by_track: Dict[int, List[TimelineBlockEntity]] = {}
    for blk in blocks:
        if blk.track_id in row_map:
            blocks_by_track.setdefault(blk.track_id, []).append(blk)

    font_t = QFont("Microsoft YaHei UI", 8, QFont.Weight.DemiBold)
    link_font = QFont("Consolas", 10, QFont.Weight.Bold)
    for track_id, tr_blocks in blocks_by_track.items():
        ridx = row_map[track_id]
        tr_blocks.sort(key=lambda b: (round(b.start_time, 4), b.id or 0))
        sub_y = y_top + ridx * LANE_H + 7
        sub_h = LANE_H - 14
        prev_right: Optional[float] = None

        for blk in tr_blocks:
            is_action = blk.block_type == "action"
            bx0 = x0 + blk.start_time * pps - scroll_x
            bw = compute_chain_block_width(blk.title, blk.duration, pps)
            if prev_right is not None and bx0 < prev_right + 10.0:
                bx0 = prev_right + 10.0
            if prev_right is not None and bx0 > x0 and prev_right < x0 + w:
                mid_y = sub_y + sub_h * 0.5
                p.setPen(QPen(QColor(C_TEXT_2), 1.5))
                p.drawLine(int(prev_right), int(mid_y), int(bx0), int(mid_y))
                p.setFont(link_font)
                p.drawText(QRectF(prev_right, sub_y, bx0 - prev_right, sub_h), Qt.AlignmentFlag.AlignCenter, "-")
            prev_right = bx0 + bw

            if bx0 + bw < x0 or bx0 > x0 + w:
                continue

            rect = QRectF(bx0, sub_y, bw, sub_h)
            base_col = QColor("#8b5cf6" if is_action else color_map.get(blk.track_id, C_ACCENT))
            fill = QColor(base_col)
            fill.setAlpha(65 if blk.is_ignored else 165)
            p.setBrush(fill)

            is_sel = blk.id is not None and blk.id == selected_block_id
            is_err = (blk.id in overlap_ids) if blk.id is not None else False
            border_col = QColor(C_DANGER if is_err else ("#ffffff" if is_sel else base_col.name()))
            p.setPen(QPen(border_col, 2.0 if (is_sel or is_err) else 1.2))
            p.drawRoundedRect(rect, 5, 5)

            p.setFont(font_t)
            p.setPen(QColor("#ffffff"))
            p.drawText(rect.adjusted(7, 0, -7, 0), Qt.AlignmentFlag.AlignCenter, blk.title)

    ph_x = int(x0 + playhead_s * pps - scroll_x)
    if x0 <= ph_x <= x0 + width_safe(w):
        p.setPen(QPen(QColor(C_DANGER), 1.5))
        p.drawLine(ph_x, y_top, ph_x, y_top + len(tracks) * LANE_H + 40)


def width_safe(w: int) -> int:
    return max(1, w)
