"""
@file: src/ui/map_manager_panel.py
@brief: 地图管理与 PCD 点云加载交互面板，支持本地地图增删改查及建图预留接口
@exports: MapManagerPanel
"""
import json
import logging
import os
import shutil
import time
from typing import Any, Dict, List, Optional
import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)
from src.core.pcd_loader import PcdData, PcdLoader
from src.core.robot_gateway import remote_mapping_gateway
from src.core.storage_manager import storage_manager

logger = logging.getLogger("MapManagerPanel")


class MapManagerPanel(QWidget):
    """本地 PCD 地图管理与机器人建图预留交互面板"""

    sig_map_loaded = Signal(dict, object)  # (map_meta, points_xyz_ndarray)
    sig_map_unloaded = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_loaded_map_id: Optional[str] = None
        self._init_ui()
        self.refresh_maps()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. 地图列表区
        lbl_list = QLabel("🗺️ 场地地图列表 (PCD):")
        lbl_list.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 11px;")
        layout.addWidget(lbl_list)

        self.list_maps = QListWidget()
        self.list_maps.setStyleSheet("background: #111827; border: 1px solid #1f2937; border-radius: 4px; color: #e2e8f0;")
        self.list_maps.itemClicked.connect(self._on_map_item_clicked)
        layout.addWidget(self.list_maps, 1)

        # 2. 地图操作按钮行
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

        # 3. 详细元数据信息卡片
        self.box_info = QGroupBox("📋 地图元信息")
        self.box_info.setStyleSheet("QGroupBox { color: #94a3b8; font-size: 11px; font-weight: bold; border: 1px solid #1e293b; border-radius: 4px; margin-top: 4px; padding-top: 6px; }")
        info_layout = QVBoxLayout(self.box_info)
        info_layout.setSpacing(3)
        self.lbl_info_name = QLabel("文件名称: -")
        self.lbl_info_pts = QLabel("点云数量: -")
        self.lbl_info_span = QLabel("跨度尺寸: -")
        self.lbl_info_enc = QLabel("编码格式: -")
        for w in [self.lbl_info_name, self.lbl_info_pts, self.lbl_info_span, self.lbl_info_enc]:
            w.setStyleSheet("color: #cbd5e1; font-size: 10px;")
            info_layout.addWidget(w)
        layout.addWidget(self.box_info)

        # 4. 遥控机器人建图（预留）折叠区
        layout.addWidget(self._build_teleop_mapping_box())

    def _build_teleop_mapping_box(self) -> QGroupBox:
        box = QGroupBox("🛰️ 遥控建图 (预留接口)")
        box.setStyleSheet("QGroupBox { color: #f59e0b; font-size: 11px; font-weight: bold; border: 1px dashed #d97706; border-radius: 4px; margin-top: 4px; padding-top: 6px; }")
        vbox = QVBoxLayout(box)
        vbox.setSpacing(4)

        grid = QGridLayout()
        grid.setSpacing(3)
        directions = [
            ("⬆️ 前进", 0, 1, 0.5, 0.0, 0.0),
            ("⬅️ 左移", 1, 0, 0.0, 0.4, 0.0),
            ("🛑 停止", 1, 1, 0.0, 0.0, 0.0),
            ("➡️ 右移", 1, 2, 0.0, -0.4, 0.0),
            ("⬇️ 后退", 2, 1, -0.5, 0.0, 0.0),
            ("↺ 左旋", 0, 0, 0.0, 0.0, 0.5),
            ("↻ 右旋", 0, 2, 0.0, 0.0, -0.5),
        ]
        for name, r, c, vx, vy, wz in directions:
            btn = QPushButton(name)
            btn.setStyleSheet("background: #1e293b; color: #f8fafc; font-size: 10px; padding: 3px;")
            btn.clicked.connect(lambda _, x=vx, y=vy, z=wz: self._on_teleop_click(x, y, z))
            grid.addWidget(btn, r, c)
        vbox.addLayout(grid)

        sess_row = QHBoxLayout()
        btn_start_map = QPushButton("▶ 开始建图")
        btn_start_map.setStyleSheet("background: #b45309; color: white; font-size: 10px; font-weight: bold; padding: 4px;")
        btn_start_map.clicked.connect(self._on_start_remote_mapping)
        sess_row.addWidget(btn_start_map)

        btn_save_map = QPushButton("💾 保存到本地")
        btn_save_map.setStyleSheet("background: #475569; color: white; font-size: 10px; font-weight: bold; padding: 4px;")
        btn_save_map.clicked.connect(self._on_save_remote_mapping)
        sess_row.addWidget(btn_save_map)
        vbox.addLayout(sess_row)

        self.lbl_teleop_msg = QLabel("提示: 预留通信网关，点击按键触发真实接口状态。")
        self.lbl_teleop_msg.setWordWrap(True)
        self.lbl_teleop_msg.setStyleSheet("color: #f59e0b; font-size: 9px;")
        vbox.addWidget(self.lbl_teleop_msg)
        return box

    def refresh_maps(self) -> None:
        self.list_maps.clear()
        idx_data = storage_manager.get_maps_index()
        maps = idx_data.get("maps", [])
        for m in maps:
            item = QListWidgetItem(f"{m.get('name', 'map')} ({m.get('map_id')})")
            item.setData(Qt.UserRole, m)
            self.list_maps.addItem(item)
        if self.list_maps.count() > 0:
            self.list_maps.setCurrentRow(0)
            self._on_map_item_clicked(self.list_maps.item(0))

    def _on_map_item_clicked(self, item: Optional[QListWidgetItem]) -> None:
        if not item:
            return
        m = item.data(Qt.UserRole)
        b = m.get("bounds", {})
        dx = round(b.get("max_x", 0.0) - b.get("min_x", 0.0), 2)
        dy = round(b.get("max_y", 0.0) - b.get("min_y", 0.0), 2)
        self.lbl_info_name.setText(f"文件名称: {m.get('name', '-')}")
        self.lbl_info_pts.setText(f"点云数量: {m.get('point_count', 0)} 点")
        self.lbl_info_span.setText(f"跨度尺寸: {dx}m × {dy}m (X:[{b.get('min_x', 0):.1f},{b.get('max_x', 0):.1f}])")
        self.lbl_info_enc.setText(f"编码格式: {m.get('encoding', 'ascii').upper()}")

    def _upload_map_dialog(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "选择本地 PCD 点云", "", "PCD Files (*.pcd)")
        if not file_path:
            return
        try:
            pcd_data: PcdData = PcdLoader.load_pcd(file_path)
            map_id = f"map_{int(time.time() * 1000)}"
            dest_pcd = os.path.join(storage_manager.maps_dir, f"{map_id}.pcd")
            shutil.copyfile(file_path, dest_pcd)

            idx_data = storage_manager.get_maps_index()
            map_meta = {
                "map_id": map_id,
                "name": os.path.basename(file_path),
                "file_path": os.path.relpath(dest_pcd, storage_manager.base_dir).replace("\\", "/"),
                "encoding": pcd_data.header.data_mode,
                "point_count": pcd_data.point_count,
                "bounds": pcd_data.bounds,
                "origin": {"x": 0.0, "y": 0.0, "yaw": 0.0},
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            idx_data.setdefault("maps", []).append(map_meta)
            storage_manager.update_maps_index(idx_data)
            self.refresh_maps()
            QMessageBox.information(self, "上传成功", f"地图 {map_meta['name']} 已导入为 {map_id}.pcd！")
        except Exception as e:
            QMessageBox.warning(self, "解析失败", f"PCD 文件解析失败: {e}")

    def _load_selected_map(self) -> None:
        item = self.list_maps.currentItem()
        if not item:
            QMessageBox.warning(self, "未选择", "请先在列表中选中一张地图！")
            return
        meta = item.data(Qt.UserRole)
        map_id = meta.get("map_id", "")
        file_path = os.path.join(storage_manager.base_dir, meta.get("file_path", ""))
        if not os.path.exists(file_path):
            file_path = os.path.join(storage_manager.maps_dir, f"{map_id}.pcd")

        if not os.path.exists(file_path):
            QMessageBox.warning(self, "文件缺失", f"地图文件未在磁盘中找到: {file_path}")
            return

        try:
            pcd_data = PcdLoader.load_pcd(file_path)
            points = PcdLoader.downsample(pcd_data.points, max_points=30000)
            self._current_loaded_map_id = map_id

            # 更新激活地图
            idx_data = storage_manager.get_maps_index()
            idx_data["active_map_id"] = map_id
            storage_manager.update_maps_index(idx_data)

            self.sig_map_loaded.emit(meta, points)
            logger.info(f"地图 {map_id} 成功加载到工作区 (点数: {len(points)})")
        except Exception as e:
            QMessageBox.warning(self, "加载失败", f"加载点云失败: {e}")

    def _delete_selected_map(self) -> None:
        item = self.list_maps.currentItem()
        if not item:
            return
        meta = item.data(Qt.UserRole)
        map_id = meta.get("map_id")

        # 检查引用
        with storage_manager.get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) FROM trajectories WHERE scene_id IN (SELECT scene_id FROM scenes WHERE active_map_id=?)", (map_id,)).fetchone()
            ref_count = row[0] if row else 0

        if ref_count > 0:
            res = QMessageBox.question(self, "地图引用提示", f"地图 {map_id} 正被 {ref_count} 条场景轨迹引用，确认强制删除吗？", QMessageBox.Yes | QMessageBox.No)
            if res != QMessageBox.Yes:
                return

        # 执行删除
        file_path = os.path.join(storage_manager.base_dir, meta.get("file_path", ""))
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError as ex:
                logger.error(f"删除物理 PCD 失败: {ex}")

        idx_data = storage_manager.get_maps_index()
        idx_data["maps"] = [m for m in idx_data.get("maps", []) if m.get("map_id") != map_id]
        if idx_data.get("active_map_id") == map_id:
            idx_data["active_map_id"] = ""
        storage_manager.update_maps_index(idx_data)

        if self._current_loaded_map_id == map_id:
            self._current_loaded_map_id = None
            self.sig_map_unloaded.emit()

        self.refresh_maps()
        QMessageBox.information(self, "删除成功", f"地图 {map_id} 已删除！")

    def _on_teleop_click(self, vx: float, vy: float, wz: float) -> None:
        res = remote_mapping_gateway.send_teleop_velocity("A", vx, vy, wz)
        self.lbl_teleop_msg.setText(res.get("message", ""))

    def _on_start_remote_mapping(self) -> None:
        res = remote_mapping_gateway.start_mapping_session("A")
        self.lbl_teleop_msg.setText(res.get("message", ""))

    def _on_save_remote_mapping(self) -> None:
        res = remote_mapping_gateway.finish_and_save_pcd("sess_A_stub", "data/maps/remote_scan.pcd")
        self.lbl_teleop_msg.setText(res.get("message", ""))
