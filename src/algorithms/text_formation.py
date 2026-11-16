# @file: src/algorithms/text_formation.py
# @brief: Character/text glyph bitmap sampler converting any Chinese or ASCII text into evenly spaced 2D targets.
# @exports: generate_text_formation

from __future__ import annotations

import math
from typing import List, Tuple
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter

Point2D = Tuple[float, float]


def generate_text_formation(text: str, count: int, width_m: float = 5.0) -> List[Point2D]:
    """Sample count evenly separated (x, y) target slots shaped like the given text."""
    n = max(1, count)
    label = (text or "G1").strip() or "G1"
    w_px, h_px = max(96, 48 * len(label)), 96
    img = QImage(w_px, h_px, QImage.Format.Format_Grayscale8)
    img.fill(0)
    p = QPainter(img)
    p.setPen(QColor(255, 255, 255))
    font = QFont("Microsoft YaHei UI", 54, QFont.Weight.Bold)
    p.setFont(font)
    p.drawText(img.rect(), Qt.AlignmentFlag.AlignCenter, label)
    p.end()

    ptr = img.bits()
    arr = np.frombuffer(ptr, dtype=np.uint8, count=img.sizeInBytes()).reshape((h_px, img.bytesPerLine()))[:, :w_px]
    ys, xs = np.where(arr > 120)
    if len(xs) == 0:
        return [(i * 0.8 - (n - 1) * 0.4, 0.0) for i in range(n)]

    cx, cy = float(xs.mean()), float(ys.mean())
    scale = max(1.0, float(width_m)) / max(1.0, float(xs.max() - xs.min() + 1))
    coords = np.column_stack(((xs - cx) * scale, -(ys - cy) * scale))
    if len(coords) <= n:
        pts = [(round(float(r[0]), 3), round(float(r[1]), 3)) for r in coords]
        while len(pts) < n:
            pts.append(pts[len(pts) % len(coords)])
        return pts

    # Farthest-point greedy selection guarantees maximal uniform separation across strokes
    chosen = [int(np.argmin(coords[:, 0] ** 2 + coords[:, 1] ** 2))]
    min_d2 = np.sum((coords - coords[chosen[0]]) ** 2, axis=1)
    for _ in range(1, n):
        nxt = int(np.argmax(min_d2))
        chosen.append(nxt)
        d2 = np.sum((coords - coords[nxt]) ** 2, axis=1)
        min_d2 = np.minimum(min_d2, d2)
    pts = [(round(float(coords[i, 0]), 3), round(float(coords[i, 1]), 3)) for i in chosen]
    pts.sort(key=lambda pt: (round(pt[1], 1), pt[0]))
    _ = math.hypot
    return pts
