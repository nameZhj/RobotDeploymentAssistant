# @file: src/ui/modals/custom_map_modal.py
# @brief: Quick modal to import a local .pcd file with configurable occupancy grid slicing parameters.
# @exports: CustomMapModal

from __future__ import annotations

from pathlib import Path
import shutil
from PySide6.QtWidgets import QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QWidget

from src.core.event_bus import StudioEvent
from src.core.paths import get_paths
from src.domain.map_entities import PcdMapEntity
from src.persistence.pcd_grid_generator import generate_occupancy_grid_png
from src.persistence.pcd_parser import load_pcd
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.u_buttons import UButton
from src.ui.design_system.u_dialog import UDialog
from src.ui.design_system.u_inputs import UInputNumber


class CustomMapModal(UDialog):
    """Imports external .pcd point clouds, projects occupancy PNG, and activates it on stage."""

    def __init__(self, state: StudioStateService, parent: QWidget | None = None) -> None:
        super().__init__("导入并投影点云地图 (.pcd)", width=480, height=290, confirm_text="导入并加载", parent=parent)
        self.state = state
        form = QFormLayout()
        form.setSpacing(10)

        prow = QHBoxLayout()
        self.path_edit = QLineEdit("", self)
        brw = UButton("选择 .pcd...", variant="default", size="sm", parent=self)
        brw.clicked.connect(self._browse)
        prow.addWidget(self.path_edit, 1)
        prow.addWidget(brw)

        self.res_spin = UInputNumber(0.05, 0.02, 0.50, 0.01, 2, "m/格", self)
        self.zmin_spin = UInputNumber(0.15, -2.0, 5.0, 0.05, 2, "m", self)
        self.zmax_spin = UInputNumber(2.00, 0.3, 10.0, 0.1, 2, "m", self)
        form.addRow("PCD 文件", prow)
        form.addRow("栅格分辨率", self.res_spin)
        form.addRow("障碍最小高度", self.zmin_spin)
        form.addRow("障碍最大高度", self.zmax_spin)
        self.body_layout.addLayout(form)

        if self.confirm_btn:
            self.confirm_btn.clicked.disconnect()
            self.confirm_btn.clicked.connect(self._on_import)

    def _browse(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "选择 PCD 地图", str(get_paths().maps_dir), "PCD (*.pcd)")
        if p:
            self.path_edit.setText(p)

    def _on_import(self) -> None:
        src = Path(self.path_edit.text().strip())
        if not src.exists():
            self.state.notify("请选择有效的 .pcd 文件", "warn")
            return
        dst_pcd = get_paths().maps_dir / src.name
        dst_pcd.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != dst_pcd.resolve():
            shutil.copy2(src, dst_pcd)
        cloud = load_pcd(dst_pcd, max_points=120000)
        out_png = get_paths().pcd_cache_dir / f"{dst_pcd.stem}_grid.png"
        grid = generate_occupancy_grid_png(
            cloud, out_png, self.res_spin.value(), self.zmin_spin.value(), self.zmax_spin.value()
        )
        ent = PcdMapEntity(
            name=dst_pcd.stem,
            file_path=str(dst_pcd),
            file_size=dst_pcd.stat().st_size,
            grid_png_path=grid.png_path,
            point_count=cloud.header.points,
            resolution=grid.resolution,
            origin_x=grid.origin_x,
            origin_y=grid.origin_y,
        )
        saved = self.state.map_repo.upsert_map(ent)
        self.state.scene.active_map_id = saved.id
        self.state.scene_repo.update_scene(self.state.scene)
        self.state.reload_all()
        self.state.bus.publish(StudioEvent.MAP_LIST_UPDATED, saved.id)
        self.state.bus.publish(StudioEvent.MAP_LOADED, saved.id)
        self.accept()
