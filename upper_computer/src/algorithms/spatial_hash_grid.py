# @file: src/algorithms/spatial_hash_grid.py
# @brief: O(1) spatial hash grid accelerating neighbor queries in potential-field and collision workers.
# @exports: SpatialHashGrid

from __future__ import annotations

from collections import defaultdict
import math
from typing import Dict, List, Sequence, Tuple


class SpatialHashGrid:
    """2D uniform grid spatial hash for fast proximity queries."""

    def __init__(self, cell_size: float) -> None:
        self.cell_size = max(0.05, float(cell_size))
        self._buckets: Dict[Tuple[int, int], List[int]] = defaultdict(list)

    def rebuild(self, positions: Sequence[Tuple[float, float]]) -> None:
        """Clear and index all 2D coordinates."""
        self._buckets.clear()
        cs = self.cell_size
        for idx, (x, y) in enumerate(positions):
            self._buckets[(math.floor(x / cs), math.floor(y / cs))].append(idx)

    def query_neighbors(self, x: float, y: float) -> List[int]:
        """Return candidate indices inside the 3x3 Moore neighborhood."""
        cs = self.cell_size
        cx, cy = math.floor(x / cs), math.floor(y / cs)
        out: List[int] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                bucket = self._buckets.get((cx + dx, cy + dy))
                if bucket:
                    out.extend(bucket)
        return out
