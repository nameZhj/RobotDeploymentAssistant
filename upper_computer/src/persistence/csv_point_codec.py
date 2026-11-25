# @file: src/persistence/csv_point_codec.py
# @brief: Encoder and decoder for stage trajectoryPointData CSV strings ("t,x,y,yaw\n...").
# @exports: CsvPointCodec

from __future__ import annotations

from typing import Iterable, List, Tuple
import numpy as np


class CsvPointCodec:
    """Converts between (t, x, y, yaw) point arrays and stage CSV strings."""

    @staticmethod
    def encode_points(samples: Iterable[Tuple[float, float, float, float]]) -> str:
        """Format iterable of (t, x, y, yaw) tuples as compact CSV lines."""
        lines: List[str] = []
        for row in samples:
            t, x, y, yaw = float(row[0]), float(row[1]), float(row[2]), float(row[3])
            lines.append(f"{t:.3f},{x:.4f},{y:.4f},{yaw:.4f}")
        return "\n".join(lines)

    @staticmethod
    def decode_points(csv_text: str) -> np.ndarray:
        """Parse 't,x,y,yaw' CSV lines into float64 numpy array of shape (N, 4)."""
        if not csv_text or not csv_text.strip():
            return np.zeros((0, 4), dtype=np.float64)
        rows: List[List[float]] = []
        for raw_line in csv_text.strip().splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                continue
            t = float(parts[0])
            x = float(parts[1])
            y = float(parts[2])
            yaw = float(parts[3]) if len(parts) >= 4 else 0.0
            rows.append([t, x, y, yaw])
        if not rows:
            return np.zeros((0, 4), dtype=np.float64)
        return np.asarray(rows, dtype=np.float64)
