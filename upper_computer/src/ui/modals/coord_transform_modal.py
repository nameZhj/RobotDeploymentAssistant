# @file: src/ui/modals/coord_transform_modal.py
# @brief: 2D SVD Kabsch coordinate calibration dialog aligning stage frame with scanned PCD map frame.
# @exports: CoordTransformModal

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QHBoxLayout, QLabel, QTableWidgetItem, QWidget

from src.core.event_bus import StudioEvent
from src.math.rigid_transform_svd import solve_kabsch_2d
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.tokens import FONT_MONO
from src.ui.design_system.u_buttons import UButton
from src.ui.design_system.u_dialog import UDialog
from src.ui.design_system.u_panels import UTable


class CoordTransformModal(UDialog):
    """Solves 2D rigid alignment (R, t, RMSE) between stage markers and PCD map coordinates."""

    def __init__(self, state: StudioStateService, parent: QWidget | None = None) -> None:
        super().__init__("舞台-点云坐标系 SVD 标定", width=620, height=400, confirm_text="关闭", cancel_text="", parent=parent)
        self.state = state
        self.table = UTable(["点云 X", "点云 Y", "舞台目标 X", "舞台目标 Y"], self)
        defaults = [(0.0, 0.0, 0.0, 0.0), (4.0, 0.0, 4.0, 0.0), (4.0, 3.0, 4.0, 3.0)]
        self.table.setRowCount(len(defaults))
        for r, vals in enumerate(defaults):
            for c, v in enumerate(vals):
                self.table.setItem(r, c, QTableWidgetItem(f"{v:.3f}"))
        self.body_layout.addWidget(self.table, 1)

        row = QHBoxLayout()
        calc_b = UButton("求解刚体变换 (SVD)", variant="primary", size="sm", icon_name="target", parent=self)
        calc_b.clicked.connect(self._solve)
        self.res_lbl = QLabel("旋转角: 0.00° | 平移: (0.00, 0.00) | RMSE: 0.000m", self)
        self.res_lbl.setStyleSheet(f"font-family: {FONT_MONO}; font-size: 11px;")
        row.addWidget(calc_b)
        row.addWidget(self.res_lbl, 1)
        self.body_layout.addLayout(row)

    def _solve(self) -> None:
        src, dst = [], []
        for r in range(self.table.rowCount()):
            src.append([float(self.table.item(r, 0).text()), float(self.table.item(r, 1).text())])
            dst.append([float(self.table.item(r, 2).text()), float(self.table.item(r, 3).text())])
        cal = solve_kabsch_2d(np.asarray(src), np.asarray(dst))
        self.res_lbl.setText(
            f"旋转角: {cal.yaw_deg:.2f}° | 平移: ({cal.trans_2[0]:.2f}, {cal.trans_2[1]:.2f}) | RMSE: {cal.rmse_m:.4f}m"
        )
        if self.state.active_map:
            m = self.state.active_map
            m.calib_matrix = {
                "rot_2x2": cal.rot_2x2.tolist(),
                "trans_2": cal.trans_2.tolist(),
                "yaw_deg": float(cal.yaw_deg),
                "rmse_m": float(cal.rmse_m),
            }
            from pathlib import Path
            from src.core.paths import get_paths
            from src.persistence.pcd_grid_generator import generate_occupancy_grid_png
            from src.persistence.pcd_parser import load_pcd

            if m.file_path and Path(m.file_path).exists():
                cloud = load_pcd(Path(m.file_path), max_points=100000)
                png = get_paths().pcd_cache_dir / f"{Path(m.file_path).stem}_grid.png"
                grid = generate_occupancy_grid_png(cloud, png, calib_matrix=m.calib_matrix)
                m.grid_png_path = grid.png_path
                m.origin_x, m.origin_y, m.resolution = grid.origin_x, grid.origin_y, grid.resolution
            else:
                m.origin_x += float(cal.trans_2[0])
                m.origin_y += float(cal.trans_2[1])
            self.state.map_repo.upsert_map(m)
            self.state.reload_all()
            self.state.bus.publish(StudioEvent.MAP_LOADED, m.id)
        self.state.notify(f"SVD 标定完成 (旋转 {cal.yaw_deg:.1f}°, RMSE={cal.rmse_m:.4f}m)", "ok")
