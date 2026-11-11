"""
@file: src/ui/dialogs/stage_map_dialog.py
@brief: 本地 PCD 地图管理对话框：文件导入、列表展示、元信息查看、安全删除与 2D 加载
@exports: StageMapDialog
"""
import os
import time
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSplitter, QVBoxLayout, QWidget,
)
from src.application.stage_director.stage_map_controller import StageMapController
from src.application.stage_director.stage_map_worker import (
    StageMapImportWorker,
    StageMapLoadWorker,
)
from src.domain.map.stage_map_asset import StageMapAsset


class StageMapDialog(QDialog):
    """本地 PCD 地图管理交互弹窗，提供异步文件导入、详情预览、在用删除保护与 2D 舞台加载"""

    mapLoadedToStage = Signal(object, dict, dict)
    mapUnloadedFromStage = Signal()

    def __init__(self, parent: Optional[QWidget] = None, controller: Optional[StageMapController] = None) -> None:
        super().__init__(parent)
        self.controller = controller or StageMapController()
        self._current_worker: Optional[Any] = None
        self._current_thread: Optional[QThread] = None
        self._maps_cache: List[StageMapAsset] = []

        self.setWindowTitle("🗺️ 本地 PCD 地图管理 (STAGE MAPS)")
        self.resize(780, 520)
        self.setMinimumSize(660, 440)
        self._init_ui()
        self.refresh_maps_list()

    def _init_ui(self) -> None:
        self.setStyleSheet("""
            QDialog { background-color: #0b0f19; color: #e2e8f0; font-family: 'Segoe UI', sans-serif; }
            QFrame.box-panel { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 6px; }
            QGroupBox {
                color: #94a3b8; font-weight: 700; font-size: 11px;
                border: 1px solid #1e293b; border-radius: 6px; margin-top: 10px;
                padding-top: 12px; background-color: #0f172a;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QLabel { color: #cbd5e1; font-size: 11px; }
            QLabel.val-label { color: #38bdf8; font-weight: 600; }
            QListWidget {
                background-color: #090d16; border: 1px solid #1e293b; border-radius: 4px;
                color: #e2e8f0; font-size: 11px;
            }
            QListWidget::item { padding: 8px 10px; border-bottom: 1px solid #1e293b; }
            QListWidget::item:selected { background-color: #1e3a8a; color: #60a5fa; font-weight: 700; }
            QPushButton {
                background-color: #1e293b; color: #e2e8f0; border: 1px solid #334155;
                border-radius: 4px; padding: 6px 12px; font-size: 11px; font-weight: 600;
            }
            QPushButton:hover { background-color: #26334d; border-color: #38bdf8; color: #38bdf8; }
            QPushButton.primary-btn { background-color: #0284c7; color: #ffffff; border: 1px solid #38bdf8; }
            QPushButton.primary-btn:hover { background-color: #0369a1; }
            QPushButton.danger-btn { background-color: #991b1b; color: #fee2e2; border: 1px solid #ef4444; }
            QPushButton.danger-btn:hover { background-color: #b91c1c; }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # 顶栏
        top_bar = QHBoxLayout()
        lbl_head = QLabel("本地 PCD 舞台点云地图列表与管理")
        lbl_head.setStyleSheet("font-size: 13px; font-weight: 700; color: #38bdf8;")
        top_bar.addWidget(lbl_head)
        top_bar.addStretch()
        self.btn_import = QPushButton("➕ 导入本地 PCD", self)
        self.btn_import.setProperty("class", "primary-btn")
        self.btn_import.clicked.connect(self._on_import_clicked)
        top_bar.addWidget(self.btn_import)
        root.addLayout(top_bar)

        # 中部左右分栏
        splitter = QSplitter(Qt.Horizontal, self)
        root.addWidget(splitter, 1)

        # 左侧列表
        left_widget = QWidget(splitter)
        v_left = QVBoxLayout(left_widget)
        v_left.setContentsMargins(0, 0, 0, 0)
        v_left.addWidget(QLabel("已导入地图资产:"))
        self.list_maps = QListWidget(left_widget)
        self.list_maps.currentRowChanged.connect(self._on_map_selection_changed)
        v_left.addWidget(self.list_maps)
        splitter.addWidget(left_widget)

        # 右侧元信息详情
        self.right_widget = QWidget(splitter)
        v_right = QVBoxLayout(self.right_widget)
        v_right.setContentsMargins(0, 0, 0, 0)
        grp_meta = QGroupBox("📊 地图元信息 (METADATA)", self.right_widget)
        f_meta = QFormLayout(grp_meta)
        f_meta.setContentsMargins(10, 12, 10, 10)
        f_meta.setSpacing(6)
        self.lbl_name = QLabel("—", grp_meta); self.lbl_name.setProperty("class", "val-label")
        f_meta.addRow("地图名称:", self.lbl_name)
        self.lbl_path = QLabel("—", grp_meta); self.lbl_path.setWordWrap(True)
        f_meta.addRow("文件路径:", self.lbl_path)
        self.lbl_size = QLabel("—", grp_meta); self.lbl_size.setProperty("class", "val-label")
        f_meta.addRow("文件大小:", self.lbl_size)
        self.lbl_points = QLabel("—", grp_meta); self.lbl_points.setProperty("class", "val-label")
        f_meta.addRow("点云数量:", self.lbl_points)
        self.lbl_bounds = QLabel("—", grp_meta)
        f_meta.addRow("场景包围盒:", self.lbl_bounds)
        self.lbl_dimensions = QLabel("—", grp_meta); self.lbl_dimensions.setProperty("class", "val-label")
        f_meta.addRow("物理尺寸:", self.lbl_dimensions)
        self.lbl_res = QLabel("—", grp_meta)
        f_meta.addRow("栅格分辨率:", self.lbl_res)
        self.lbl_origin = QLabel("—", grp_meta)
        f_meta.addRow("舞台原点:", self.lbl_origin)
        self.lbl_status = QLabel("—", grp_meta)
        f_meta.addRow("加载状态:", self.lbl_status)
        v_right.addWidget(grp_meta, 1)
        splitter.addWidget(self.right_widget)
        splitter.setSizes([300, 460])

        # 底栏操作与状态
        bottom_bar = QHBoxLayout()
        self.lbl_progress = QLabel("就绪")
        self.lbl_progress.setStyleSheet("color: #94a3b8; font-size: 11px;")
        bottom_bar.addWidget(self.lbl_progress, 1)

        self.btn_load = QPushButton("🚀 加载到 2D 舞台", self)
        self.btn_load.setProperty("class", "primary-btn")
        self.btn_load.clicked.connect(self._on_load_clicked)
        bottom_bar.addWidget(self.btn_load)

        self.btn_unload = QPushButton("✕ 卸载地图", self)
        self.btn_unload.clicked.connect(self._on_unload_clicked)
        bottom_bar.addWidget(self.btn_unload)

        self.btn_delete = QPushButton("🗑️ 删除地图", self)
        self.btn_delete.setProperty("class", "danger-btn")
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        bottom_bar.addWidget(self.btn_delete)

        self.btn_close = QPushButton("关闭", self)
        self.btn_close.clicked.connect(self.accept)
        bottom_bar.addWidget(self.btn_close)
        root.addLayout(bottom_bar)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.btn_import.setEnabled(not busy)
        self.btn_load.setEnabled(not busy)
        self.btn_unload.setEnabled(not busy)
        self.btn_delete.setEnabled(not busy)
        self.lbl_progress.setText(message if busy else (message or "就绪"))

    def refresh_maps_list(self, select_map_id: Optional[str] = None) -> None:
        self._maps_cache = self.controller.list_maps()
        active_id = self.controller.get_active_map_id()
        self.list_maps.clear()
        target_row = 0
        for i, m in enumerate(self._maps_cache):
            is_active = (m.map_id == active_id)
            tag = " [已加载]" if is_active else ""
            item = QListWidgetItem(f"🗺️ {m.name} ({m.formatted_file_size()}){tag}")
            if is_active:
                item.setForeground(Qt.cyan)
            self.list_maps.addItem(item)
            if select_map_id and m.map_id == select_map_id:
                target_row = i
        if self._maps_cache:
            self.list_maps.setCurrentRow(target_row)
        else:
            self._clear_detail_view()

    def _on_map_selection_changed(self, row: int) -> None:
        if 0 <= row < len(self._maps_cache):
            m = self._maps_cache[row]
            is_active = (m.map_id == self.controller.get_active_map_id())
            self.lbl_name.setText(m.name)
            self.lbl_path.setText(m.file_path)
            self.lbl_size.setText(m.formatted_file_size())
            self.lbl_points.setText(f"{m.point_count:,} 点")
            self.lbl_bounds.setText(f"X:[{m.min_x:.1f}, {m.max_x:.1f}] Y:[{m.min_y:.1f}, {m.max_y:.1f}] Z:[{m.min_z:.1f}, {m.max_z:.1f}]")
            self.lbl_dimensions.setText(m.formatted_dimensions())
            self.lbl_res.setText(f"{m.resolution}m/格")
            self.lbl_origin.setText(f"({m.origin_x:.1f}, {m.origin_y:.1f})")
            self.lbl_status.setText("● 当前舞台已加载" if is_active else "○ 未加载")
            self.lbl_status.setStyleSheet("color: #10b981; font-weight: 700;" if is_active else "color: #94a3b8;")
        else:
            self._clear_detail_view()

    def _clear_detail_view(self) -> None:
        for lbl in (self.lbl_name, self.lbl_path, self.lbl_size, self.lbl_points, self.lbl_bounds,
                    self.lbl_dimensions, self.lbl_res, self.lbl_origin, self.lbl_status):
            lbl.setText("—")

    def _on_import_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择本地 PCD 地图文件", "", "PCD Files (*.pcd);;All Files (*.*)")
        if not path:
            return
        self._set_busy(True, "正在导入 PCD 地图...")
        self._current_thread = QThread(self)
        self._current_worker = StageMapImportWorker(self.controller, path)
        self._current_worker.moveToThread(self._current_thread)
        self._current_thread.started.connect(self._current_worker.run)
        self._current_worker.progress.connect(lambda msg: self.lbl_progress.setText(msg))
        self._current_worker.finished.connect(self._on_import_success)
        self._current_worker.failed.connect(self._on_import_failed)
        self._current_worker.finished.connect(self._current_thread.quit)
        self._current_worker.failed.connect(self._current_thread.quit)
        self._current_worker.finished.connect(self._current_worker.deleteLater)
        self._current_worker.failed.connect(self._current_worker.deleteLater)
        self._current_thread.finished.connect(self._current_thread.deleteLater)
        self._current_thread.start()

    def _on_import_success(self, asset: StageMapAsset) -> None:
        self._set_busy(False, f"地图 '{asset.name}' 导入成功")
        self.refresh_maps_list(select_map_id=asset.map_id)

    def _on_import_failed(self, error_msg: str) -> None:
        self._set_busy(False, "导入失败")
        QMessageBox.warning(self, "导入失败", f"无法导入所选 PCD 地图:\n{error_msg}")

    def _on_load_clicked(self) -> None:
        row = self.list_maps.currentRow()
        if not (0 <= row < len(self._maps_cache)):
            QMessageBox.information(self, "未选择地图", "请先在左侧选择要加载的地图。")
            return
        map_id = self._maps_cache[row].map_id
        self._set_busy(True, "正在加载地图到舞台...")
        self._current_thread = QThread(self)
        self._current_worker = StageMapLoadWorker(self.controller, map_id)
        self._current_worker.moveToThread(self._current_thread)
        self._current_thread.started.connect(self._current_worker.run)
        self._current_worker.progress.connect(lambda msg: self.lbl_progress.setText(msg))
        self._current_worker.finished.connect(self._on_load_success)
        self._current_worker.failed.connect(self._on_load_failed)
        self._current_worker.finished.connect(self._current_thread.quit)
        self._current_worker.failed.connect(self._current_thread.quit)
        self._current_worker.finished.connect(self._current_worker.deleteLater)
        self._current_worker.failed.connect(self._current_worker.deleteLater)
        self._current_thread.finished.connect(self._current_thread.deleteLater)
        self._current_thread.start()

    def _on_load_success(self, img: Any, info: dict, meta: dict) -> None:
        self._set_busy(False, f"地图 '{meta.get('name')}' 已加载到舞台")
        self.mapLoadedToStage.emit(img, info, meta)
        self.refresh_maps_list(select_map_id=meta.get("map_id"))

    def _on_load_failed(self, err: str) -> None:
        self._set_busy(False, "加载失败")
        QMessageBox.critical(self, "加载失败", f"加载地图到舞台失败:\n{err}")

    def _on_unload_clicked(self) -> None:
        self.controller.unload_map()
        self.mapUnloadedFromStage.emit()
        self.refresh_maps_list()
        self.lbl_progress.setText("已卸载当前舞台地图")

    def _on_delete_clicked(self) -> None:
        row = self.list_maps.currentRow()
        if not (0 <= row < len(self._maps_cache)):
            return
        asset = self._maps_cache[row]
        if self.controller.get_active_map_id() == asset.map_id:
            QMessageBox.warning(self, "禁止删除", "当前舞台正在加载该地图，无法直接删除。\n请先卸载或切换至其他地图。")
            return
        ans = QMessageBox.question(self, "确认删除", f"确定要永久删除地图资产 '{asset.name}' 吗？\n该操作不可撤销。", QMessageBox.Yes | QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        ok, msg = self.controller.delete_map(asset.map_id)
        if ok:
            self.refresh_maps_list()
            self.lbl_progress.setText(f"已删除地图 '{asset.name}'")
        else:
            QMessageBox.warning(self, "删除失败", msg)

    def closeEvent(self, event) -> None:
        if self._current_thread and self._current_thread.isRunning():
            if self._current_worker and hasattr(self._current_worker, "cancel"):
                self._current_worker.cancel()
            self._current_thread.quit()
            self._current_thread.wait(1000)
        super().closeEvent(event)
