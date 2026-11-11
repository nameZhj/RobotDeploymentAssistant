"""
@file: src/ui/choreo_page/lib_panels_controller.py
@brief: 轨迹库与动作库面板控制器，支持动作、单机轨迹与群组轨迹多模式拖拽编排
@exports: LibPanelsController, DraggableTableWidget
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)
from src.infrastructure.storage.choreo_sqlite_store import ChoreoSqliteStore

logger = logging.getLogger("LibPanelsController")


class DraggableTableWidget(QTableWidget):
    """支持拖拽导出素材元数据的专用表格控件"""

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.LeftButton:
            row = self.currentRow()
            if row >= 0:
                id_item = self.item(row, 0)
                if id_item:
                    data = id_item.data(Qt.UserRole)
                    if data and isinstance(data, dict):
                        drag = QDrag(self)
                        mime = QMimeData()
                        mime.setData("application/x-choreo-asset", json.dumps(data).encode("utf-8"))
                        mime.setText(f"{data.get('asset_type', 'ASSET')}:{data.get('asset_id', '')}:{data.get('name', '')}")
                        drag.setMimeData(mime)
                        drag.exec_(Qt.CopyAction)
                        return
        super().mouseMoveEvent(event)


class LibPanelsController(QWidget):
    """轨迹库与动作库整合交互控制器：支持单机轨迹、群组轨迹与动作库的浏览与向时间轴拖放"""

    trajectorySelected = Signal(dict)
    trajectoryDeleted = Signal(str)
    actionSelected = Signal(dict)
    actionTriggered = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None, controller: Optional[Any] = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.store = ChoreoSqliteStore()
        self._traj_cache: Dict[str, dict] = {}
        self._act_cache: Dict[str, dict] = {}
        self._init_ui()
        self.refresh_trajectories()
        self.refresh_actions()
        if self.controller:
            self.controller.trajectories_changed.connect(self._on_trajectories_changed)
            self.controller.actions_changed.connect(self._on_actions_changed)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # 1. 轨迹库面板
        self.traj_frame = QFrame()
        self.traj_frame.setStyleSheet("background: #111318; border-radius: 6px; border: 1px solid #1f242d;")
        vbox_traj = QVBoxLayout(self.traj_frame)
        vbox_traj.setContentsMargins(8, 8, 8, 8)
        vbox_traj.setSpacing(6)

        hdr_traj = QHBoxLayout()
        lbl_t = QLabel("📐 轨迹库 (单机与群组)")
        lbl_t.setStyleSheet("font-weight: bold; color: #e2e8f0; font-size: 13px;")
        hdr_traj.addWidget(lbl_t)
        hdr_traj.addStretch()

        self.btn_bind = QPushButton("🔗 绑定")
        self.btn_export = QPushButton("导出")
        self.btn_del = QPushButton("删除")
        for b in (self.btn_bind, self.btn_export, self.btn_del):
            b.setStyleSheet("background: #1e2430; color: #94a3b8; border: 1px solid #334155; padding: 2px 8px; border-radius: 4px;")
            hdr_traj.addWidget(b)
        vbox_traj.addLayout(hdr_traj)

        self.table_traj = DraggableTableWidget(0, 3)
        self.table_traj.setHorizontalHeaderLabels(["编号", "名称", "时长"])
        self.table_traj.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_traj.setStyleSheet("QTableWidget { background: #0c0e12; color: #cbd5e1; border: none; } QTableWidget::item:selected { background: #1e293b; color: #38bdf8; }")
        vbox_traj.addWidget(self.table_traj)

        self.tree_traj = QTreeWidget()
        self.tree_traj.setHeaderLabels(["编号", "名称", "时长"])
        self.tree_traj.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tree_traj.setStyleSheet("QTreeWidget { background: #0c0e12; color: #cbd5e1; border: none; }")
        self.tree_traj.itemClicked.connect(self._on_tree_item_clicked)
        self.tree_traj.hide()
        vbox_traj.addWidget(self.tree_traj)
        layout.addWidget(self.traj_frame, stretch=1)

        # 2. 动作库面板
        self.action_frame = QFrame()
        self.action_frame.setStyleSheet("background: #111318; border-radius: 6px; border: 1px solid #1f242d;")
        vbox_act = QVBoxLayout(self.action_frame)
        vbox_act.setContentsMargins(8, 8, 8, 8)
        vbox_act.setSpacing(6)

        hdr_act = QHBoxLayout()
        lbl_a = QLabel("💃 动作库 (肢体与舞蹈)")
        lbl_a.setStyleSheet("font-weight: bold; color: #e2e8f0; font-size: 13px;")
        hdr_act.addWidget(lbl_a)
        hdr_act.addStretch()
        vbox_act.addLayout(hdr_act)

        filter_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索编号/名称...")
        self.search_input.setStyleSheet("background: #0c0e12; border: 1px solid #334155; color: #e2e8f0; padding: 4px 6px; border-radius: 4px;")
        self.search_input.textChanged.connect(self.refresh_actions)
        filter_row.addWidget(self.search_input, stretch=2)

        self.model_combo = QComboBox()
        self.model_combo.addItems(["全部型号", "A2-W"])
        self.model_combo.setStyleSheet("background: #0c0e12; border: 1px solid #334155; color: #e2e8f0; padding: 4px; border-radius: 4px;")
        self.model_combo.currentIndexChanged.connect(self.refresh_actions)
        filter_row.addWidget(self.model_combo, stretch=1)
        vbox_act.addLayout(filter_row)

        self.table_act = DraggableTableWidget(0, 3)
        self.table_act.setHorizontalHeaderLabels(["编号", "名称", "时长"])
        self.table_act.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_act.setStyleSheet("QTableWidget { background: #0c0e12; color: #cbd5e1; border: none; gridline-color: #1e2430; } QTableWidget::item:selected { background: #1e293b; color: #38bdf8; }")
        self.table_act.cellClicked.connect(self._on_table_cell_clicked)
        self.table_act.cellDoubleClicked.connect(self._on_table_cell_double_clicked)
        vbox_act.addWidget(self.table_act)
        layout.addWidget(self.action_frame, stretch=1)

        self.btn_del.clicked.connect(self._delete_selected_trajectory)
        self.btn_export.clicked.connect(self._export_selected_trajectory)

    def _on_trajectories_changed(self, trajs: list) -> None:
        self.refresh_trajectories()

    def _on_actions_changed(self, acts: list) -> None:
        self.refresh_actions()

    def refresh_trajectories(self) -> None:
        """刷新单机轨迹与群组轨迹列表并挂载拖拽元信息"""
        trajectories = self.store.list_trajectories()
        self.table_traj.setRowCount(0)
        self.tree_traj.clear()
        grp1 = QTreeWidgetItem(self.tree_traj, ["A2-W Robot_1 🔗轨道1", "", ""])
        grp2 = QTreeWidgetItem(self.tree_traj, ["A2-W Robot_2 🔗轨道2", "", ""])
        grp1.setExpanded(True); grp2.setExpanded(True)

        for r, t in enumerate(trajectories):
            tid = str(t.get("traj_id", ""))
            name = str(t.get("name", ""))
            dur = float(t.get("duration", 0.0))
            self._traj_cache[tid] = t
            t_data = {"asset_type": "TRAJECTORY", "asset_id": tid, "name": name, "duration": dur, "duration_ms": int(dur * 1000)}
            row_idx = self.table_traj.rowCount()
            self.table_traj.insertRow(row_idx)
            item_id = QTableWidgetItem(tid)
            item_id.setData(Qt.UserRole, t_data)
            self.table_traj.setItem(row_idx, 0, item_id)
            self.table_traj.setItem(row_idx, 1, QTableWidgetItem(name))
            self.table_traj.setItem(row_idx, 2, QTableWidgetItem(f"{dur:.2f}s"))

            target = grp1 if t.get("robot_group") == "Robot_1" else grp2
            leaf = QTreeWidgetItem(target, [tid, name, f"{dur:.2f}s"])
            leaf.setData(0, Qt.UserRole, t_data)

        # 注入群组轨迹
        try:
            from src.infrastructure.storage.group_trajectory_sqlite_adapter import GroupTrajectorySqliteAdapter
            groups = GroupTrajectorySqliteAdapter.list_groups(self.store)
            if groups:
                grp_tree = QTreeWidgetItem(self.tree_traj, ["👥 群组轨迹编队", "", ""])
                grp_tree.setExpanded(True)
                for g in groups:
                    gid = g.get("group_trajectory_id", "") if isinstance(g, dict) else getattr(g, "group_trajectory_id", "")
                    gname = g.get("name", "") if isinstance(g, dict) else getattr(g, "name", "")
                    g_data = {"asset_type": "GROUP_TRAJECTORY", "asset_id": gid, "name": gname, "duration": 5.0, "duration_ms": 5000, "is_group": True}
                    r_idx = self.table_traj.rowCount()
                    self.table_traj.insertRow(r_idx)
                    it = QTableWidgetItem(gid); it.setData(Qt.UserRole, g_data)
                    self.table_traj.setItem(r_idx, 0, it)
                    self.table_traj.setItem(r_idx, 1, QTableWidgetItem(f"👥 {gname}"))
                    self.table_traj.setItem(r_idx, 2, QTableWidgetItem("5.00s"))
                    lf = QTreeWidgetItem(grp_tree, [gid, f"👥 {gname}", "5.00s"])
                    lf.setData(0, Qt.UserRole, g_data)
        except Exception as e:
            logger.error("加载群组轨迹列表失败: %s", e, exc_info=True)

    def refresh_actions(self) -> None:
        """刷新动作库列表并挂载拖拽元信息"""
        search = self.search_input.text().strip()
        model_type = self.model_combo.currentText()
        actions = self.store.list_actions(search=search, model_type=model_type)
        self.table_act.setRowCount(len(actions))
        for r, act in enumerate(actions):
            aid = str(act.get("action_id", ""))
            name = str(act.get("name", ""))
            dur = float(act.get("duration", 0.0))
            anim_path = str(act.get("anim_path", ""))
            is_valid = bool(anim_path and os.path.exists(anim_path))
            self._act_cache[aid] = act
            act_data = {
                "asset_type": "ACTION",
                "asset_id": aid,
                "name": name,
                "duration": dur,
                "duration_ms": int(dur * 1000),
                "is_valid": is_valid,
                "anim_path": anim_path
            }
            item_id = QTableWidgetItem(aid)
            item_id.setData(Qt.UserRole, act_data)
            self.table_act.setItem(r, 0, item_id)
            display_name = f"💃 {name}" if is_valid else f"⚠️ {name} (缺失)"
            self.table_act.setItem(r, 1, QTableWidgetItem(display_name))
            self.table_act.setItem(r, 2, QTableWidgetItem(f"{dur:.2f}s"))

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        val = item.data(0, Qt.UserRole)
        data = val if isinstance(val, dict) else (self._traj_cache.get(str(val)) or {"traj_id": str(val)})
        self.trajectorySelected.emit(data)

    def _on_table_cell_clicked(self, row: int, col: int) -> None:
        item = self.table_act.item(row, 0)
        if item:
            aid = item.text()
            data = self._act_cache.get(aid) or {"action_id": aid}
            self.actionSelected.emit(data)

    def _on_table_cell_double_clicked(self, row: int, col: int) -> None:
        item = self.table_act.item(row, 0)
        if item:
            aid_str = item.text()
            data = self._act_cache.get(aid_str) or {}
            aid = int(aid_str) if aid_str.isdigit() else 0
            name = str(data.get("name") or (self.table_act.item(row, 1).text() if self.table_act.item(row, 1) else ""))
            dur_str = self.table_act.item(row, 2).text().replace("s", "") if self.table_act.item(row, 2) else "2.0"
            dur = float(dur_str)
            if self.controller and hasattr(self.controller, "add_action_to_timeline"):
                self.controller.add_action_to_timeline(aid, name, dur)
            self.actionTriggered.emit(data or {"action_id": aid, "name": name, "duration": dur})

    def _delete_selected_trajectory(self) -> None:
        item = self.tree_traj.currentItem() or self.table_traj.currentItem()
        if not item: return
        tid = item.data(0, Qt.UserRole) if hasattr(item, "data") else None
        if isinstance(tid, dict): tid = tid.get("asset_id")
        if tid:
            tid_str = str(tid)
            try:
                ok = self.store.delete_trajectory_asset(tid_str)
                if ok:
                    self.refresh_trajectories()
                    self.trajectoryDeleted.emit(tid_str)
            except Exception:
                pass

    def _export_selected_trajectory(self) -> None:
        item = self.tree_traj.currentItem()
        if not item: return
        tid = item.data(0, Qt.UserRole)
        if isinstance(tid, dict): tid = tid.get("asset_id")
        data = self._traj_cache.get(str(tid))
        if data and "waypoints_json" in data:
            path, _ = QFileDialog.getSaveFileName(self, "导出轨迹数据", f"{data.get('name', 'traj')}.json", "JSON (*.json)")
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(data["waypoints_json"])
