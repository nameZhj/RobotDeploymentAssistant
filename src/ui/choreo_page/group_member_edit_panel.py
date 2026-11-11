"""
@file: src/ui/choreo_page/group_member_edit_panel.py
@brief: 群组轨迹左侧控制面板：参考轨迹选择、阵型预设微调、成员增删与局部 Frenet 偏移编辑
@exports: GroupMemberEditPanel
"""
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.domain.trajectory.group_trajectory import GroupTrajectoryMember
from src.domain.trajectory.trajectory_asset import TrajectoryAsset


class GroupMemberEditPanel(QFrame):
    """群组轨迹左侧交互面板：提供参考线选择、方阵排布生成、成员增删及局部偏移输入。"""

    referenceSelected = Signal(str)
    formationApplied = Signal(str, int, int, float)
    memberAdded = Signal(str)
    memberRemoved = Signal(str)
    memberOffsetChanged = Signal(str, float, float, float)
    previewRequested = Signal()
    saveRequested = Signal()
    loadRequested = Signal()
    deleteRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(320)
        self.setProperty("class", "panel-box")
        self._members_cache: List[GroupTrajectoryMember] = []
        self._is_updating_ui = False
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. 参考轨迹选择
        grp_ref = QGroupBox("🎯 参考轨迹选择 (REFERENCE)", self)
        l_ref = QVBoxLayout(grp_ref)
        self.cbo_reference = QComboBox(grp_ref)
        self.cbo_reference.currentIndexChanged.connect(self._on_ref_combo_changed)
        l_ref.addWidget(self.cbo_reference)
        self.lbl_ref_info = QLabel("长度: — | 采样点: —", grp_ref)
        self.lbl_ref_info.setStyleSheet("color: #94a3b8; font-size: 10px;")
        l_ref.addWidget(self.lbl_ref_info)
        layout.addWidget(grp_ref)

        # 2. 阵型预设 (04C-D3)
        grp_form = QGroupBox("📐 阵型排布预设 (FORMATION)", self)
        f_form = QFormLayout(grp_form)
        f_form.setContentsMargins(6, 6, 6, 6)
        self.cbo_formation_type = QComboBox(grp_form)
        self.cbo_formation_type.addItem("方阵/网格 (Grid)", "GRID")
        self.cbo_formation_type.addItem("横队 (Line)", "LINE")
        self.cbo_formation_type.addItem("纵队 (Column)", "COLUMN")
        self.cbo_formation_type.addItem("圆阵 (Circle)", "CIRCLE")
        f_form.addRow("排布形态:", self.cbo_formation_type)
        self.spin_rows = QSpinBox(grp_form)
        self.spin_rows.setRange(1, 10); self.spin_rows.setValue(2)
        f_form.addRow("行数 (N):", self.spin_rows)
        self.spin_cols = QSpinBox(grp_form)
        self.spin_cols.setRange(1, 10); self.spin_cols.setValue(2)
        f_form.addRow("列数 (M):", self.spin_cols)
        self.spin_spacing = QDoubleSpinBox(grp_form)
        self.spin_spacing.setRange(0.4, 5.0); self.spin_spacing.setSingleStep(0.1); self.spin_spacing.setValue(1.2); self.spin_spacing.setSuffix(" m")
        f_form.addRow("机间距/半径:", self.spin_spacing)
        self.btn_apply_formation = QPushButton("⚡ 生成阵型初始偏移", grp_form)
        self.btn_apply_formation.clicked.connect(self._on_apply_formation_clicked)
        f_form.addRow(self.btn_apply_formation)
        layout.addWidget(grp_form)

        # 3. 机器人成员增删与局部偏移微调 (04C-D2)
        grp_mem = QGroupBox("🤖 成员与局部偏移 (MEMBERS)", self)
        l_mem = QVBoxLayout(grp_mem)
        h_add = QHBoxLayout()
        self.txt_robot_id = QLineEdit(grp_mem)
        self.txt_robot_id.setPlaceholderText("机器人编号 (如 Robot_1)")
        h_add.addWidget(self.txt_robot_id, 1)
        self.btn_add_robot = QPushButton("➕ 添加", grp_mem)
        self.btn_add_robot.clicked.connect(self._on_add_robot_clicked)
        h_add.addWidget(self.btn_add_robot)
        l_mem.addLayout(h_add)

        self.list_members = QListWidget(grp_mem)
        self.list_members.currentRowChanged.connect(self._on_member_selection_changed)
        l_mem.addWidget(self.list_members, 1)

        f_offsets = QFormLayout()
        self.spin_offset_x = QDoubleSpinBox(grp_mem)
        self.spin_offset_x.setRange(-50.0, 50.0); self.spin_offset_x.setSingleStep(0.1); self.spin_offset_x.setSuffix(" m")
        f_offsets.addRow("切向前向 (X):", self.spin_offset_x)
        self.spin_offset_y = QDoubleSpinBox(grp_mem)
        self.spin_offset_y.setRange(-50.0, 50.0); self.spin_offset_y.setSingleStep(0.1); self.spin_offset_y.setSuffix(" m")
        f_offsets.addRow("左侧法向 (Y):", self.spin_offset_y)
        self.spin_delta_yaw = QDoubleSpinBox(grp_mem)
        self.spin_delta_yaw.setRange(-180.0, 180.0); self.spin_delta_yaw.setSingleStep(5.0); self.spin_delta_yaw.setSuffix(" °")
        f_offsets.addRow("航向偏角 (Yaw):", self.spin_delta_yaw)
        for s in (self.spin_offset_x, self.spin_offset_y, self.spin_delta_yaw):
            s.valueChanged.connect(self._on_spin_offset_changed)
        l_mem.addLayout(f_offsets)

        self.btn_remove_robot = QPushButton("🗑️ 移除选中机器人", grp_mem)
        self.btn_remove_robot.clicked.connect(self._on_remove_robot_clicked)
        l_mem.addWidget(self.btn_remove_robot)
        layout.addWidget(grp_mem, 1)

        # 4. 预览与持久化按钮 (04C-D2 & 04C-D4)
        self.btn_generate_preview = QPushButton("✨ 生成群组轨迹预览", self)
        self.btn_generate_preview.setStyleSheet("background-color: #0284c7; font-weight: 700; padding: 7px;")
        self.btn_generate_preview.clicked.connect(self.previewRequested.emit)
        layout.addWidget(self.btn_generate_preview)

        h_persist = QHBoxLayout()
        self.btn_save = QPushButton("💾 保存", self); self.btn_save.clicked.connect(self.saveRequested.emit)
        self.btn_load = QPushButton("📂 加载", self); self.btn_load.clicked.connect(self.loadRequested.emit)
        self.btn_delete = QPushButton("🗑️ 删除", self); self.btn_delete.clicked.connect(self.deleteRequested.emit)
        for b in (self.btn_save, self.btn_load, self.btn_delete):
            h_persist.addWidget(b)
        layout.addLayout(h_persist)

    def set_available_references(self, references: List[TrajectoryAsset]) -> None:
        """更新可用参考轨迹下拉列表。"""
        self._is_updating_ui = True
        self.cbo_reference.clear()
        for ref in references:
            self.cbo_reference.addItem(f"{ref.name} ({ref.trajectory_id})", ref.trajectory_id)
        self._is_updating_ui = False
        if references:
            self.set_selected_reference(references[0])

    def set_selected_reference(self, ref: Optional[TrajectoryAsset]) -> None:
        if not ref:
            self.lbl_ref_info.setText("空状态: 尚未选择参考轨迹")
            return
        idx = self.cbo_reference.findData(ref.trajectory_id)
        if idx >= 0 and self.cbo_reference.currentIndex() != idx:
            self._is_updating_ui = True
            self.cbo_reference.setCurrentIndex(idx)
            self._is_updating_ui = False
        self.lbl_ref_info.setText(f"长度: {ref.length_m:.2f}m | 采样点: {len(ref.sampled_points)}")

    def set_members(self, members: List[GroupTrajectoryMember]) -> None:
        """刷新成员列表并保留选中态。"""
        self._members_cache = list(members)
        curr_row = self.list_members.currentRow()
        self._is_updating_ui = True
        self.list_members.clear()
        for m in self._members_cache:
            item = QListWidgetItem(f"🤖 {m.robot_id} (X={m.offset_x_m:+.2f}m, Y={m.offset_y_m:+.2f}m, Yaw={m.delta_yaw_deg:+.1f}°)")
            self.list_members.addItem(item)
        if 0 <= curr_row < len(self._members_cache):
            self.list_members.setCurrentRow(curr_row)
        elif self._members_cache:
            self.list_members.setCurrentRow(0)
        self._is_updating_ui = False
        self._update_offset_spinboxes()

    def _on_ref_combo_changed(self) -> None:
        if self._is_updating_ui: return
        tid = self.cbo_reference.currentData()
        if tid: self.referenceSelected.emit(str(tid))

    def _on_apply_formation_clicked(self) -> None:
        ftype = str(self.cbo_formation_type.currentData() or "GRID")
        self.formationApplied.emit(ftype, self.spin_rows.value(), self.spin_cols.value(), self.spin_spacing.value())

    def _on_add_robot_clicked(self) -> None:
        rid = self.txt_robot_id.text().strip()
        if rid:
            self.memberAdded.emit(rid)
            self.txt_robot_id.clear()

    def _on_remove_robot_clicked(self) -> None:
        row = self.list_members.currentRow()
        if 0 <= row < len(self._members_cache):
            self.memberRemoved.emit(self._members_cache[row].robot_id)

    def _on_member_selection_changed(self) -> None:
        if self._is_updating_ui: return
        self._update_offset_spinboxes()

    def _update_offset_spinboxes(self) -> None:
        row = self.list_members.currentRow()
        if 0 <= row < len(self._members_cache):
            m = self._members_cache[row]
            self._is_updating_ui = True
            self.spin_offset_x.setValue(m.offset_x_m)
            self.spin_offset_y.setValue(m.offset_y_m)
            self.spin_delta_yaw.setValue(m.delta_yaw_deg)
            self._is_updating_ui = False

    def _on_spin_offset_changed(self) -> None:
        if self._is_updating_ui: return
        row = self.list_members.currentRow()
        if 0 <= row < len(self._members_cache):
            rid = self._members_cache[row].robot_id
            self.memberOffsetChanged.emit(rid, self.spin_offset_x.value(), self.spin_offset_y.value(), self.spin_delta_yaw.value())
