# @file: src/ui/mapping/pcd_map_library_dock.py
# @brief: Clean zero-overlap PCD Map Library dock supporting local upload, stage loading, rename, calibration, and delete.
# @exports: PcdMapLibraryDock

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Optional
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QWidget,
)

from src.core.event_bus import StudioEvent
from src.core.paths import get_paths
from src.domain.map_entities import PcdMapEntity
from src.persistence.pcd_grid_generator import generate_occupancy_grid_png
from src.persistence.pcd_parser import PcdPointCloud, load_pcd
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.tokens import C_CARD, C_TEXT_2, FONT_MONO, LINE
from src.ui.design_system.u_buttons import UButton
from src.ui.design_system.u_inputs import USearchInput
from src.ui.design_system.u_panels import UPanel
from src.ui.modals.coord_transform_modal import CoordTransformModal


class PcdMapLibraryDock(UPanel):
    """Left 300px PCD map asset manager with spacious multi-row controls and metadata viewer."""

    cloudLoaded = Signal(object, object)  # (PcdMapEntity, PcdPointCloud)

    def __init__(self, state: StudioStateService, parent: QWidget | None = None) -> None:
        super().__init__(
            title="场地地图",
            header_widgets=[],
            parent=parent,
            help_text="支持上传本地 .pcd 点云、从机器人拉取或推送地图，以及标定舞台坐标系。",
        )
        self.state = state
        self.active_robot_ip: str = ""
        self.setFixedWidth(306)
        self.body_layout.setSpacing(8)

        self.search = USearchInput("搜索地图...", self.body_widget)
        self.search.textChanged.connect(lambda _t: self.refresh())
        self.body_layout.addWidget(self.search)

        self.list_w = QListWidget(self.body_widget)
        self.list_w.currentRowChanged.connect(self._on_selection_changed)
        self.body_layout.addWidget(self.list_w, 1)

        # Spacious 2-row action grid (never cramped onto one line!)
        grid = QGridLayout()
        grid.setSpacing(6)
        up_b = UButton("上传本地 PCD", variant="primary", size="sm", icon_name="upload", parent=self.body_widget)
        up_b.clicked.connect(self.upload_pcd_dialog)
        pull_b = UButton("拉取机载 PCD", variant="default", size="sm", icon_name="download", parent=self.body_widget)
        pull_b.clicked.connect(self.sync_remote_pcd_dialog)
        load_b = UButton("加载到舞台", variant="default", size="sm", icon_name="map", parent=self.body_widget)
        load_b.clicked.connect(self.load_selected_to_stage)
        ren_b = UButton("重命名", variant="default", size="sm", icon_name="edit", parent=self.body_widget)
        ren_b.clicked.connect(self.rename_selected)
        cal_b = UButton("坐标系标定", variant="default", size="sm", icon_name="target", parent=self.body_widget)
        cal_b.clicked.connect(lambda: CoordTransformModal(self.state, self).exec())
        push_b = UButton("推送至机器人", variant="default", size="sm", icon_name="upload", parent=self.body_widget)
        push_b.clicked.connect(self.push_selected_to_robot)
        del_b = UButton("删除地图", variant="danger", size="sm", icon_name="trash", parent=self.body_widget)
        del_b.clicked.connect(self.delete_selected)

        grid.addWidget(up_b, 0, 0)
        grid.addWidget(pull_b, 0, 1)
        grid.addWidget(push_b, 1, 0)
        grid.addWidget(load_b, 1, 1)
        grid.addWidget(ren_b, 2, 0)
        grid.addWidget(cal_b, 2, 1)
        grid.addWidget(del_b, 3, 0, 1, 2)
        self.body_layout.addLayout(grid)

        self.meta_lbl = QLabel("未选择地图", self.body_widget)
        self.meta_lbl.setWordWrap(True)
        self.meta_lbl.setStyleSheet(
            f"background: {C_CARD}; border: 1px solid {LINE}; border-radius: 6px; "
            f"padding: 8px; color: {C_TEXT_2}; font-family: {FONT_MONO}; font-size: 11px;"
        )
        self.body_layout.addWidget(self.meta_lbl)

        state.bus.subscribe(StudioEvent.MAP_LIST_UPDATED, lambda _p: self.refresh())
        self._scan_existing_dir()
        self.refresh()

    def _scan_existing_dir(self) -> None:
        existing_paths = {Path(m.file_path).resolve() for m in self.state.map_repo.list_maps() if m.file_path}
        ignored_paths = {Path(p).resolve() for p in self.state.map_repo.list_deleted_map_paths() if p}
        for pcd_file in sorted(get_paths().maps_dir.glob("*.pcd")):
            rp = pcd_file.resolve()
            if rp not in existing_paths and rp not in ignored_paths:
                from src.persistence.pcd_parser import parse_pcd_header
                hdr = parse_pcd_header(pcd_file)
                ent = PcdMapEntity(
                    name=pcd_file.stem,
                    file_path=str(pcd_file),
                    file_size=pcd_file.stat().st_size,
                    point_count=hdr.points,
                )
                self.state.map_repo.upsert_map(ent)

    def refresh(self) -> None:
        kw = self.search.text().strip().lower()
        self.list_w.clear()
        for m in self.state.map_repo.list_maps():
            if kw and kw not in m.name.lower() and kw not in m.file_path.lower():
                continue
            active_tag = " [已加载]" if self.state.scene.active_map_id == m.id else ""
            sz_mb = m.file_size / (1024 * 1024)
            it = QListWidgetItem(f"{m.name}{active_tag} · {m.point_count:,}点 ({sz_mb:.1f}MB)")
            it.setData(256, m.id)
            self.list_w.addItem(it)
            if self.state.scene.active_map_id == m.id:
                self.list_w.setCurrentItem(it)

    def _selected_entity(self) -> Optional[PcdMapEntity]:
        cur = self.list_w.currentItem()
        if not cur:
            return None
        return self.state.map_repo.get_map(int(cur.data(256)))

    def _on_selection_changed(self, _row: int) -> None:
        m = self._selected_entity()
        if not m:
            self.meta_lbl.setText("未选择地图")
            return
        self.meta_lbl.setText(
            f"名称: {m.name}\n点数: {m.point_count:,} | 大小: {m.file_size / (1024*1024):.2f} MB\n"
            f"栅格原点: ({m.origin_x:.2f}, {m.origin_y:.2f}) | {m.resolution:.3f} m/px\n"
            f"路径: {Path(m.file_path).name}"
        )

    def push_selected_to_robot(self, restart_localization: Optional[bool] = None) -> bool:
        """Push selected local .pcd file to active robot's discovered onboard map dir via Wi-Fi HTTP."""
        m = self._selected_entity()
        if not m or not m.file_path or not Path(m.file_path).exists():
            self.state.notify("请先选择有效的本地 PCD 地图", "warn")
            return False
        robot_ip = self.active_robot_ip.strip() or next((tr.robot_ip.strip() for tr in self.state.tracks if tr.robot_ip), "")
        if not robot_ip:
            self.state.notify("请先添加配置了 Wi-Fi IP 的机器人轨道", "warn")
            return False
        if restart_localization is None:
            ans = QMessageBox.question(
                self,
                "推送 PCD 至机器人",
                f"将 [{m.name}.pcd] 推送到 {robot_ip} 后，是否立即执行 navctl restart localization？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.No,
            )
            if ans == QMessageBox.StandardButton.Cancel:
                return False
            restart_localization = ans == QMessageBox.StandardButton.Yes
        res = self.state.http_rpc.upload_slam_pcd(robot_ip, Path(m.file_path), restart_localization=bool(restart_localization))
        self.state.notify(res.message, "ok" if res.ok else "warn")
        return res.ok

    def upload_pcd_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "上传本地 PCD 地图", "", "PCD Files (*.pcd)")
        if path:
            self.import_pcd_file(Path(path), activate=True)

    def sync_remote_pcd_dialog(self) -> Optional[PcdMapEntity]:
        """Discover onboard .pcd maps over Wi-Fi HTTP and download selected real map."""
        robot_ip = self.active_robot_ip.strip() or next((tr.robot_ip.strip() for tr in self.state.tracks if tr.robot_ip), "")
        if not robot_ip:
            self.state.notify("请先添加配置了 Wi-Fi IP 的机器人轨道", "warn")
            return None
        res = self.state.http_rpc.list_remote_maps(robot_ip)
        maps = (res.data.get("maps") or []) if res.ok else []
        if not maps:
            self.state.notify(f"未在机器人端动态发现 .pcd 地图 ({res.message})", "warn")
            return None
        choices = [f"{m['name']}.pcd ({round(m['size_bytes'] / (1024 * 1024), 2)}MB) — {m['path']}" for m in maps]
        if len(choices) == 1:
            idx = 0
        else:
            picked, ok = QInputDialog.getItem(self, "选择机载真实 PCD 地图", "动态发现的机载地图:", choices, 0, False)
            if not ok or picked not in choices:
                return None
            idx = choices.index(picked)
        remote_p = str(maps[idx]["path"])
        dst = get_paths().maps_dir / Path(remote_p).name
        dl = self.state.http_rpc.download_slam_pcd(robot_ip, dst, remote_path=remote_p)
        if not dl.ok:
            self.state.notify(f"下载机载 PCD 失败: {dl.message}", "warn")
            return None
        return self.import_pcd_file(dst, activate=True)

    def import_pcd_file(self, src: Path, activate: bool = True) -> PcdMapEntity:
        dst = get_paths().maps_dir / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        self.state.map_repo.unmark_deleted_map_path(str(dst))
        cloud = load_pcd(dst, max_points=100000)
        png = get_paths().pcd_cache_dir / f"{dst.stem}_grid.png"
        grid = generate_occupancy_grid_png(cloud, png)
        ent = PcdMapEntity(
            name=dst.stem,
            file_path=str(dst),
            file_size=dst.stat().st_size,
            point_count=cloud.header.points,
            grid_png_path=grid.png_path,
            resolution=grid.resolution,
            origin_x=grid.origin_x,
            origin_y=grid.origin_y,
        )
        saved = self.state.map_repo.upsert_map(ent)
        if activate:
            self._activate_map(saved, cloud)
        self.refresh()
        return saved

    def load_selected_to_stage(self) -> None:
        m = self._selected_entity()
        if not m or not Path(m.file_path).exists():
            return
        cloud = load_pcd(Path(m.file_path), max_points=100000)
        if not m.grid_png_path or not Path(m.grid_png_path).exists():
            png = get_paths().pcd_cache_dir / f"{Path(m.file_path).stem}_grid.png"
            grid = generate_occupancy_grid_png(cloud, png)
            m.grid_png_path = grid.png_path
            m.origin_x, m.origin_y, m.resolution = grid.origin_x, grid.origin_y, grid.resolution
            m = self.state.map_repo.upsert_map(m)
        self._activate_map(m, cloud)

    def _activate_map(self, m: PcdMapEntity, cloud: PcdPointCloud) -> None:
        self.state.scene.active_map_id = m.id
        self.state.scene_repo.update_scene(self.state.scene)
        self.state.reload_all()
        self.state.bus.publish(StudioEvent.MAP_LIST_UPDATED, m.id)
        self.state.bus.publish(StudioEvent.MAP_LOADED, m.id)
        self.cloudLoaded.emit(m, cloud)
        self.state.notify(f"已加载地图 {m.name} 到 2D/3D 舞台", "ok")

    def rename_selected(self) -> None:
        m = self._selected_entity()
        if not m:
            return
        new_name, ok = QInputDialog.getText(self, "重命名地图", "地图显示名称:", text=m.name)
        if ok and new_name.strip():
            m.name = new_name.strip()
            self.state.map_repo.upsert_map(m)
            self.refresh()

    def delete_selected(self) -> None:
        m = self._selected_entity()
        if not m or m.id is None:
            return
        grid_png = Path(m.grid_png_path) if m.grid_png_path else None
        self.state.map_repo.delete_map(m.id, record_ignored_path=True)
        if grid_png and grid_png.exists():
            try:
                grid_png.unlink()
            except OSError:
                pass
        self.state.reload_all()
        self.state.bus.publish(StudioEvent.MAP_LIST_UPDATED, None)
        self.state.bus.publish(StudioEvent.MAP_LOADED, None)
        self.refresh()
        self.state.notify(f"已删除地图 [{m.name}]", "info")
