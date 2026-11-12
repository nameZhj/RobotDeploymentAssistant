"""
@file: src/ui/formation_panel.py
@brief: 机器人阵型设计面板，支持四类几何阵型生成、防碰撞安全告警、成员微调与2D联动
@exports: FormationPanel
"""
import glob
import json
import logging
import math
import os
import time
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)
from src.core.formation_calc import FormationCalculator
from src.core.models import FormationMember, FormationModel
from src.core.storage_manager import storage_manager

logger = logging.getLogger("FormationPanel")


class FormationPanel(QWidget):
    """阵型设计与防碰撞安全校验面板"""

    sig_formation_changed = Signal(dict)
    sig_formation_saved = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._updating_table = False
        self._current_members: List[Dict[str, Any]] = []
        self._init_ui()
        self.refresh_saved_list()
        self._on_type_or_param_changed()

    def _dspin(self, mn: float, mx: float, val: float, step: float, slot) -> QDoubleSpinBox:
        s = QDoubleSpinBox(); s.setRange(mn, mx); s.setValue(val); s.setSingleStep(step)
        s.valueChanged.connect(slot); return s

    def _ispin(self, mn: int, mx: int, val: int, slot) -> QSpinBox:
        s = QSpinBox(); s.setRange(mn, mx); s.setValue(val)
        s.valueChanged.connect(slot); return s

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4); layout.setSpacing(5)

        # 1. 基础信息配置
        box_base = QGroupBox("⚙️ 阵型基础与群组配置")
        box_base.setStyleSheet("QGroupBox { color: #38bdf8; font-weight: bold; }")
        flay_base = QFormLayout(box_base)
        self.txt_name = QLineEdit("4机菱形阵")
        self.combo_type = QComboBox(); self.combo_type.addItems(["line_row (横排)", "line_col (纵列)", "circle (圆形环阵)", "grid (矩形网格)"])
        self.combo_type.currentIndexChanged.connect(self._on_type_or_param_changed)
        self.combo_group = QComboBox(); self.combo_group.addItems(["group_1 (A, B, C, D)", "group_2 (E, F, G, H)", "自定义机器人"])
        self.combo_group.currentIndexChanged.connect(self._on_group_changed)
        self.txt_robot_ids = QLineEdit("A, B, C, D"); self.txt_robot_ids.editingFinished.connect(self._on_type_or_param_changed)
        flay_base.addRow("阵型名称:", self.txt_name); flay_base.addRow("阵型类型:", self.combo_type)
        flay_base.addRow("目标群组:", self.combo_group); flay_base.addRow("成员ID列表:", self.txt_robot_ids)
        layout.addWidget(box_base)

        # 2. 几何位姿参数
        box_geom = QGroupBox("📐 几何与中心位姿")
        box_geom.setStyleSheet("QGroupBox { color: #38bdf8; font-weight: bold; }")
        flay_geom = QFormLayout(box_geom)

        c_lay = QHBoxLayout()
        self.spin_cx = self._dspin(-50.0, 50.0, 0.0, 0.2, self._on_pose_param_changed)
        self.spin_cy = self._dspin(-50.0, 50.0, 0.0, 0.2, self._on_pose_param_changed)
        self.spin_cyaw = self._dspin(-180.0, 180.0, 0.0, 5.0, self._on_pose_param_changed)
        c_lay.addWidget(QLabel("X:")); c_lay.addWidget(self.spin_cx)
        c_lay.addWidget(QLabel("Y:")); c_lay.addWidget(self.spin_cy)
        c_lay.addWidget(QLabel("Yaw°:")); c_lay.addWidget(self.spin_cyaw)
        flay_geom.addRow("中心位姿:", c_lay)

        p_lay = QHBoxLayout()
        self.spin_spacing = self._dspin(0.2, 10.0, 1.2, 0.1, self._on_type_or_param_changed)
        self.spin_safe_dist = self._dspin(0.2, 5.0, 0.6, 0.05, self._on_pose_param_changed)
        p_lay.addWidget(QLabel("间距(m):")); p_lay.addWidget(self.spin_spacing)
        p_lay.addWidget(QLabel("安全阈值:")); p_lay.addWidget(self.spin_safe_dist)
        flay_geom.addRow("间距设置:", p_lay)

        ext_lay = QHBoxLayout()
        self.spin_rows = self._ispin(1, 10, 2, self._on_type_or_param_changed)
        self.spin_cols = self._ispin(1, 10, 2, self._on_type_or_param_changed)
        self.spin_radius = self._dspin(0.5, 20.0, 1.5, 0.2, self._on_type_or_param_changed)
        self.combo_facing = QComboBox(); self.combo_facing.addItems(["forward", "inward", "outward"])
        self.combo_facing.currentIndexChanged.connect(self._on_type_or_param_changed)
        ext_lay.addWidget(QLabel("行:")); ext_lay.addWidget(self.spin_rows)
        ext_lay.addWidget(QLabel("列:")); ext_lay.addWidget(self.spin_cols)
        ext_lay.addWidget(QLabel("半径:")); ext_lay.addWidget(self.spin_radius)
        ext_lay.addWidget(QLabel("朝向:")); ext_lay.addWidget(self.combo_facing)
        flay_geom.addRow("阵型特有:", ext_lay)
        layout.addWidget(box_geom)

        # 3. 成员微调与安全状态指示灯
        box_table = QGroupBox("📋 成员微调与防碰撞检测")
        box_table.setStyleSheet("QGroupBox { color: #38bdf8; font-weight: bold; }")
        t_lay = QVBoxLayout(box_table)
        self.lbl_safety = QLabel("🛡️ 安全间距正常")
        self.lbl_safety.setStyleSheet("background: #064e3b; color: #34d399; font-weight: bold; padding: 4px; border-radius: 4px;")
        t_lay.addWidget(self.lbl_safety)

        self.table_members = QTableWidget(0, 6)
        self.table_members.setHorizontalHeaderLabels(["ID", "偏移X", "偏移Y", "偏移Yaw°", "世界X", "世界Y"])
        self.table_members.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_members.setStyleSheet("background: #111827; color: #f1f5f9; gridline-color: #334155;")
        self.table_members.cellChanged.connect(self._on_cell_changed)
        t_lay.addWidget(self.table_members)
        layout.addWidget(box_table)

        # 4. 操作与已保存阵型列表
        self.btn_save = QPushButton("💾 保存阵型配置")
        self.btn_save.setStyleSheet("background: #0284c7; color: white; font-weight: bold; padding: 5px;")
        self.btn_save.clicked.connect(self._save_formation)
        layout.addWidget(self.btn_save)

        layout.addWidget(QLabel("已存阵型素材库 (点击加载):"))
        self.list_saved = QListWidget()
        self.list_saved.setStyleSheet("background: #111827; border: 1px solid #1f2937; color: #e2e8f0;")
        self.list_saved.itemClicked.connect(self._load_formation_item)
        layout.addWidget(self.list_saved, 1)

    def _get_robot_ids(self) -> List[str]:
        raw = self.txt_robot_ids.text().replace("，", ",")
        ids = [x.strip() for x in raw.split(",") if x.strip()]
        return ids or ["A", "B", "C", "D"]

    def _on_group_changed(self, idx: int) -> None:
        self.txt_robot_ids.setText("A, B, C, D" if idx == 0 else ("E, F, G, H" if idx == 1 else self.txt_robot_ids.text()))
        self._on_type_or_param_changed()

    def _on_type_or_param_changed(self) -> None:
        self._current_members = FormationCalculator.calculate_offsets(
            formation_type=self.combo_type.currentText().split()[0],
            robot_ids=self._get_robot_ids(), spacing=self.spin_spacing.value(),
            rows=self.spin_rows.value(), cols=self.spin_cols.value(),
            radius=self.spin_radius.value(), facing=self.combo_facing.currentText(),
        )
        self._recalculate_and_emit()

    def _on_pose_param_changed(self) -> None:
        self._recalculate_and_emit()

    def _recalculate_and_emit(self) -> None:
        cx, cy = self.spin_cx.value(), self.spin_cy.value()
        cyaw = math.radians(self.spin_cyaw.value())
        safe_dist = self.spin_safe_dist.value()

        world_mems = FormationCalculator.calculate_world_poses(self._current_members, cx, cy, cyaw)
        is_safe, warnings = FormationCalculator.check_safety_distances(world_mems, safe_dist)

        if is_safe:
            self.lbl_safety.setText(f"🛡️ 安全间距正常 (安全阈值: {safe_dist:.2f}m)")
            self.lbl_safety.setStyleSheet("background: #064e3b; color: #34d399; font-weight: bold; padding: 4px; border-radius: 4px;")
        else:
            w0 = warnings[0]
            self.lbl_safety.setText(f"⚠️ 防碰撞告警: {w0['robot_a']}与{w0['robot_b']} 间距{w0['distance']}m < {w0['safe_distance']}m")
            self.lbl_safety.setStyleSheet("background: #7f1d1d; color: #f87171; font-weight: bold; padding: 4px; border-radius: 4px;")

        self._updating_table = True
        self.table_members.setRowCount(len(world_mems))
        for row, m in enumerate(world_mems):
            self.table_members.setItem(row, 0, QTableWidgetItem(str(m["robot_id"])))
            self.table_members.setItem(row, 1, QTableWidgetItem(f"{m['offset_x']:.3f}"))
            self.table_members.setItem(row, 2, QTableWidgetItem(f"{m['offset_y']:.3f}"))
            self.table_members.setItem(row, 3, QTableWidgetItem(f"{math.degrees(m['offset_yaw']):.1f}"))
            self.table_members.setItem(row, 4, QTableWidgetItem(f"{m['world_x']:.3f}"))
            self.table_members.setItem(row, 5, QTableWidgetItem(f"{m['world_y']:.3f}"))
        self._updating_table = False

        self.sig_formation_changed.emit(self.get_formation_dict(world_mems, is_safe, warnings))

    def _on_cell_changed(self, row: int, col: int) -> None:
        if self._updating_table or row >= len(self._current_members): return
        item = self.table_members.item(row, col)
        if not item: return
        try:
            val = float(item.text())
            m = self._current_members[row]
            if col == 1: m["offset_x"] = val
            elif col == 2: m["offset_y"] = val
            elif col == 3: m["offset_yaw"] = math.radians(val)
            self._recalculate_and_emit()
        except ValueError: pass

    def sync_from_canvas(self, formation_dict: Dict[str, Any]) -> None:
        c = formation_dict.get("center", {})
        self.spin_cx.blockSignals(True); self.spin_cy.blockSignals(True); self.spin_cyaw.blockSignals(True)
        self.spin_cx.setValue(float(c.get("x", 0.0)))
        self.spin_cy.setValue(float(c.get("y", 0.0)))
        self.spin_cyaw.setValue(math.degrees(float(c.get("yaw", 0.0))))
        self.spin_cx.blockSignals(False); self.spin_cy.blockSignals(False); self.spin_cyaw.blockSignals(False)
        self._recalculate_and_emit()

    def get_formation_dict(
        self,
        world_mems: Optional[List[Dict[str, Any]]] = None,
        is_safe: bool = True,
        warnings: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        cx, cy = self.spin_cx.value(), self.spin_cy.value()
        cyaw = math.radians(self.spin_cyaw.value())
        if world_mems is None:
            world_mems = FormationCalculator.calculate_world_poses(self._current_members, cx, cy, cyaw)
            is_safe, warnings = FormationCalculator.check_safety_distances(world_mems, self.spin_safe_dist.value())
        return {
            "formation_id": f"form_{int(time.time())}",
            "name": self.txt_name.text(),
            "type": self.combo_type.currentText().split()[0],
            "center": {"x": cx, "y": cy, "yaw": cyaw},
            "params": {
                "spacing": self.spin_spacing.value(),
                "rows": self.spin_rows.value(),
                "cols": self.spin_cols.value(),
                "radius": self.spin_radius.value(),
                "facing": self.combo_facing.currentText(),
            },
            "members": world_mems,
            "is_safe": is_safe,
            "warnings": warnings or [],
        }

    def _save_formation(self) -> None:
        data = self.get_formation_dict()
        f_id = f"form_{int(time.time())}"
        data["formation_id"] = f_id
        members = [
            FormationMember(robot_id=str(m["robot_id"]), seq=i, offset_x=m["offset_x"], offset_y=m["offset_y"], offset_yaw=m.get("offset_yaw", 0.0))
            for i, m in enumerate(data["members"])
        ]
        model = FormationModel(
            formation_id=f_id, name=data["name"], type=data["type"],
            center=data["center"], params=data["params"], members=members,
        )
        storage_manager.save_formation(model)
        self.refresh_saved_list()
        self.sig_formation_saved.emit(f_id)
        QMessageBox.information(self, "保存成功", f"阵型 '{model.name}' 已保存至 data/formations/{f_id}.json")

    def refresh_saved_list(self) -> None:
        self.list_saved.clear()
        files = glob.glob(os.path.join(storage_manager.formations_dir, "*.json"))
        for f in files:
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    name = data.get("name", os.path.basename(f))
                    fid = data.get("formation_id", "")
                    item = QListWidgetItem(f"👥 {name} ({fid})")
                    item.setData(Qt.UserRole, data)
                    self.list_saved.addItem(item)
            except Exception as ex:
                logger.warning(f"读取阵型文件 {f} 失败: {ex}")

    def _load_formation_item(self, item: Optional[QListWidgetItem]) -> None:
        if not item or not item.data(Qt.UserRole): return
        data = item.data(Qt.UserRole)
        self.txt_name.setText(data.get("name", "已加载阵型"))
        ftype = data.get("type", "grid")
        for i in range(self.combo_type.count()):
            if ftype in self.combo_type.itemText(i):
                self.combo_type.setCurrentIndex(i); break
        c = data.get("center", {})
        self.spin_cx.setValue(float(c.get("x", 0.0)))
        self.spin_cy.setValue(float(c.get("y", 0.0)))
        self.spin_cyaw.setValue(math.degrees(float(c.get("yaw", 0.0))))
        params = data.get("params", {})
        self.spin_spacing.setValue(float(params.get("spacing", 1.2)))
        self.spin_rows.setValue(int(params.get("rows", 2)))
        self.spin_cols.setValue(int(params.get("cols", 2)))
        self.spin_radius.setValue(float(params.get("radius", 1.5)))
        mems = data.get("members", [])
        if mems:
            self._current_members = mems
            self.txt_robot_ids.setText(", ".join(str(m.get("robot_id")) for m in mems))
            self._recalculate_and_emit()
