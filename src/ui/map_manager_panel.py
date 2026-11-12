"""
@file: src/ui/map_manager_panel.py
@brief: 地图管理与 PCD 点云加载交互面板，支持本地地图增删改查及建图预留接口
@exports: MapManagerPanel
"""
import logging
import os
import time
from typing import Any, Dict, List, Optional
import numpy as np
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QGroupBox, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)
from src.application.stage_director.stage_map_controller import StageMapController
from src.application.stage_director.stage_map_worker import StageMapImportWorker
from src.core.pcd_loader import PcdData, PcdLoader
from src.core.storage_manager import storage_manager
from src.domain.map.stage_map_asset import (
    DuplicateMapError,
    InvalidPcdFileError,
    StageMapAsset,
    UnsupportedPcdFormatError,
    validate_pcd_file,
)

logger = logging.getLogger("MapManagerPanel")


class MapManagerPanel(QWidget):
    """本地 PCD 地图管理交互面板，严格依赖 StageMapController 与 Canonical 数据库"""

    sig_map_loaded = Signal(dict, object)  # (map_meta, points_xyz_ndarray)
    sig_map_unloaded = Signal()

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        controller: Optional[StageMapController] = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller or StageMapController(map_dir=storage_manager.maps_dir)
        self._current_loaded_map_id: Optional[str] = None
        self._import_thread: Optional[QThread] = None
        self._import_worker: Optional[StageMapImportWorker] = None
        self._init_ui()
        self.refresh_maps()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. 列表区
        lbl_list = QLabel("🗺️ 场地地图列表 (PCD):")
        lbl_list.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 11px;")
        layout.addWidget(lbl_list)

        self.list_maps = QListWidget()
        self.list_maps.setStyleSheet("background: #111827; border: 1px solid #1f2937; border-radius: 4px; color: #e2e8f0;")
        self.list_maps.itemClicked.connect(self._on_map_item_clicked)
        layout.addWidget(self.list_maps, 1)

        # 2. 操作按钮行
        btn_layout = QHBoxLayout()
        self.btn_upload = QPushButton("📂 上传地图")
        self.btn_upload.setStyleSheet("background: #0284c7; color: white; font-weight: 600; padding: 5px;")
        self.btn_upload.clicked.connect(self._upload_map_dialog)
        btn_layout.addWidget(self.btn_upload)

        self.btn_load = QPushButton("📌 加载到界面")
        self.btn_load.setStyleSheet("background: #10b981; color: white; font-weight: 600; padding: 5px;")
        self.btn_load.clicked.connect(self._load_selected_map)
        btn_layout.addWidget(self.btn_load)

        self.btn_delete = QPushButton("🗑️ 删除地图")
        self.btn_delete.setStyleSheet("background: #ef4444; color: white; font-weight: 600; padding: 5px;")
        self.btn_delete.clicked.connect(self._delete_selected_map)
        btn_layout.addWidget(self.btn_delete)
        layout.addLayout(btn_layout)

        # 3. 元信息卡片
        self.box_info = QGroupBox("📋 地图元信息")
        self.box_info.setStyleSheet("QGroupBox { color: #94a3b8; font-size: 11px; font-weight: bold; border: 1px solid #1e293b; border-radius: 4px; margin-top: 4px; padding-top: 6px; }")
        info_layout = QVBoxLayout(self.box_info)
        info_layout.setSpacing(3)
        self.lbl_info_name = QLabel("文件名称: -")
        self.lbl_info_pts = QLabel("点云数量: -")
        self.lbl_info_span = QLabel("跨度尺寸: -")
        self.lbl_info_enc = QLabel("编码格式: -")
        self.lbl_info_status = QLabel("资源状态: -")
        for w in [self.lbl_info_name, self.lbl_info_pts, self.lbl_info_span, self.lbl_info_enc, self.lbl_info_status]:
            w.setStyleSheet("color: #cbd5e1; font-size: 10px;")
            info_layout.addWidget(w)
        layout.addWidget(self.box_info)

    def refresh_maps(self) -> None:
        self.list_maps.clear()
        maps = self.controller.list_maps()
        if not maps:
            empty_item = QListWidgetItem("尚无地图。点击上传 PCD 添加一张地图。")
            empty_item.setFlags(Qt.NoItemFlags)
            self.list_maps.addItem(empty_item)
            self._reset_info_labels()
            return

        for m in maps:
            status_tag = " [就绪]" if os.path.exists(m.file_path) else " [缺失]"
            item = QListWidgetItem(f"{m.name} ({m.map_id}){status_tag}")
            item.setData(Qt.UserRole, m)
            self.list_maps.addItem(item)

        if self.list_maps.count() > 0:
            self.list_maps.setCurrentRow(0)
            self._on_map_item_clicked(self.list_maps.item(0))

    def _reset_info_labels(self) -> None:
        self.lbl_info_name.setText("文件名称: -")
        self.lbl_info_pts.setText("点云数量: -")
        self.lbl_info_span.setText("跨度尺寸: -")
        self.lbl_info_enc.setText("编码格式: -")
        self.lbl_info_status.setText("资源状态: -")

    def _on_map_item_clicked(self, item: Optional[QListWidgetItem]) -> None:
        if not item:
            return
        asset = item.data(Qt.UserRole)
        if not isinstance(asset, StageMapAsset):
            return
        dx = round(asset.max_x - asset.min_x, 2)
        dy = round(asset.max_y - asset.min_y, 2)
        exists = os.path.exists(asset.file_path)
        self.lbl_info_name.setText(f"文件名称: {asset.name}")
        self.lbl_info_pts.setText(f"点云数量: {asset.point_count} 点")
        self.lbl_info_span.setText(f"跨度尺寸: {dx}m × {dy}m (X:[{asset.min_x:.1f},{asset.max_x:.1f}])")
        self.lbl_info_enc.setText(f"编码格式: {getattr(asset, 'pcd_encoding', 'ascii').upper()}")
        self.lbl_info_status.setText(f"资源状态: {'● 就绪' if exists else '● 磁盘文件缺失'}")
        self.lbl_info_status.setStyleSheet("color: #10b981; font-size: 10px;" if exists else "color: #f97316; font-size: 10px;")

    def _upload_map_dialog(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "选择本地 PCD 点云", "", "PCD Files (*.pcd)")
        if not file_path:
            return
        try:
            meta_hdr = validate_pcd_file(file_path)
        except Exception as e:
            QMessageBox.warning(self, "格式校验失败", f"所选文件未通过 PCD 格式预检:\n{e}")
            return

        stem = os.path.splitext(os.path.basename(file_path))[0]
        pts = meta_hdr.get("declared_points", 0)
        mode = meta_hdr.get("data_mode", "ascii").upper()
        size_kb = round(meta_hdr.get("file_size", 0) / 1024.0, 1)

        msg = f"准备导入 PCD 点云地图:\n\n• 名称: {stem}\n• 编码模式: {mode}\n• 声明点数: {pts}\n• 文件大小: {size_kb} KB\n\n是否确认导入？"
        if QMessageBox.question(self, "导入确认", msg, QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        self._start_import_worker(file_path, stem, allow_duplicate=False)

    def _start_import_worker(self, src_path: str, custom_name: str, allow_duplicate: bool) -> None:
        self.btn_upload.setEnabled(False)
        self.btn_upload.setText("⏳ 导入中...")

        self._import_thread = QThread(self)
        self._import_worker = StageMapImportWorker(
            self.controller, src_path, custom_name, allow_duplicate=allow_duplicate
        )
        self._import_worker.moveToThread(self._import_thread)
        self._import_thread.started.connect(self._import_worker.run)
        self._import_worker.finished.connect(self._on_import_success)
        self._import_worker.failed.connect(self._on_import_failed)
        self._import_worker.duplicate_detected.connect(lambda eid, ename: self._on_duplicate_map(src_path, custom_name, eid, ename))

        self._import_worker.finished.connect(self._import_thread.quit)
        self._import_worker.failed.connect(self._import_thread.quit)
        self._import_thread.finished.connect(self._on_import_thread_finished)
        self._import_thread.start()

    def _on_import_success(self, asset: StageMapAsset) -> None:
        self.refresh_maps()
        self._sync_maps_index_legacy(asset)
        QMessageBox.information(self, "导入成功", f"地图 '{asset.name}' 已成功导入并持久化！")

    def _on_import_failed(self, err_msg: str) -> None:
        QMessageBox.critical(self, "导入失败", f"导入地图时发生错误:\n{err_msg}")

    def _on_duplicate_map(self, src_path: str, custom_name: str, eid: str, ename: str) -> None:
        self._import_thread.quit()
        res = QMessageBox.question(
            self,
            "地图哈希已存在",
            f"检测到内容完全一致的地图已经存在:\n\n名称: {ename} (ID: {eid})\n\n是否仍作为新副本导入？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if res == QMessageBox.Yes:
            self._start_import_worker(src_path, f"{custom_name}_copy", allow_duplicate=True)

    def _on_import_thread_finished(self) -> None:
        self.btn_upload.setEnabled(True)
        self.btn_upload.setText("📂 上传地图")
        self._import_worker = None
        self._import_thread = None

    def _sync_maps_index_legacy(self, asset: StageMapAsset) -> None:
        try:
            idx = storage_manager.get_maps_index()
            maps = idx.setdefault("maps", [])
            if not any(m.get("map_id") == asset.map_id for m in maps):
                maps.append({
                    "map_id": asset.map_id,
                    "name": asset.name,
                    "file_path": os.path.relpath(asset.file_path, storage_manager.base_dir).replace("\\", "/"),
                    "encoding": getattr(asset, "pcd_encoding", "ascii"),
                    "point_count": asset.point_count,
                    "bounds": {"min_x": asset.min_x, "max_x": asset.max_x, "min_y": asset.min_y, "max_y": asset.max_y, "min_z": asset.min_z, "max_z": asset.max_z},
                    "origin": {"x": asset.origin_x, "y": asset.origin_y, "yaw": 0.0},
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                })
                storage_manager.update_maps_index(idx)
        except Exception:
            pass

    def _load_selected_map(self) -> None:
        item = self.list_maps.currentItem()
        if not item:
            QMessageBox.warning(self, "未选择", "请先在列表中选中一张地图！")
            return
        asset = item.data(Qt.UserRole)
        if not isinstance(asset, StageMapAsset):
            return

        if not os.path.exists(asset.file_path):
            QMessageBox.warning(self, "文件缺失", f"地图文件在磁盘中未找到:\n{asset.file_path}")
            return

        try:
            pcd_data = PcdLoader.load_pcd(asset.file_path)
            points = PcdLoader.downsample(pcd_data.points, max_points=30000)
            self._current_loaded_map_id = asset.map_id
            self.controller.set_active_map_id(asset.map_id)

            meta = {
                "map_id": asset.map_id,
                "name": asset.name,
                "file_path": asset.file_path,
                "point_count": asset.point_count,
                "bounds": {"min_x": asset.min_x, "max_x": asset.max_x, "min_y": asset.min_y, "max_y": asset.max_y, "min_z": asset.min_z, "max_z": asset.max_z},
                "origin": {"x": asset.origin_x, "y": asset.origin_y, "yaw": 0.0},
            }
            self.sig_map_loaded.emit(meta, points)
            logger.info(f"地图 {asset.map_id} 成功加载到工作区 (点数: {len(points)})")
        except Exception as e:
            QMessageBox.warning(self, "加载失败", f"加载点云失败: {e}")

    def _delete_selected_map(self) -> None:
        item = self.list_maps.currentItem()
        if not item:
            return
        asset = item.data(Qt.UserRole)
        if not isinstance(asset, StageMapAsset):
            return

        if QMessageBox.question(self, "确认删除", f"确定删除地图 '{asset.name}' 吗？", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        ok, msg = self.controller.delete_map(asset.map_id)
        if not ok:
            QMessageBox.warning(self, "无法删除", msg)
            return

        if self._current_loaded_map_id == asset.map_id:
            self._current_loaded_map_id = None
            self.sig_map_unloaded.emit()

        self.refresh_maps()
        QMessageBox.information(self, "删除成功", f"地图 '{asset.name}' 已删除！")
