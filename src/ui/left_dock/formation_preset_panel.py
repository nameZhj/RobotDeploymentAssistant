"""
@file: src/ui/left_dock/formation_preset_panel.py
@brief: N x M 矩阵队形规划与点云地图导入面板控件
@exports: FormationPresetPanel
"""
import logging
from typing import Dict, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger("FormationPresetPanel")


class FormationPresetPanel(QWidget):
    """
    Panel configuring N x M matrix formation layouts (rows, cols, intervals, offsets)
    and importing stage LiDAR pointcloud maps (.pcd/.ply).
    """

    formationApplied = Signal(dict)
    mapImported = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        self.setStyleSheet("""
            QGroupBox {
                color: #38bdf8; font-weight: 700; font-size: 11px;
                border: 1px solid #334155; border-radius: 6px; margin-top: 8px; padding-top: 10px;
            }
            QLabel { color: #cbd5e1; font-size: 11px; }
            QSpinBox, QDoubleSpinBox {
                background: #1e293b; color: #f8fafc; border: 1px solid #475569;
                border-radius: 4px; padding: 2px 4px; font-weight: 600;
            }
            QPushButton {
                background: #0284c7; color: #ffffff; border-radius: 4px;
                padding: 5px 10px; font-weight: 600; font-size: 11px;
            }
            QPushButton:hover { background: #0369a1; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        grp_matrix = QGroupBox("📐 N × M 矩阵队形规划", self)
        form_layout = QFormLayout(grp_matrix)
        form_layout.setContentsMargins(8, 8, 8, 8)
        form_layout.setSpacing(6)

        self.spin_rows = QSpinBox(grp_matrix)
        self.spin_rows.setRange(1, 10)
        self.spin_rows.setValue(2)
        form_layout.addRow("行数 (N):", self.spin_rows)

        self.spin_cols = QSpinBox(grp_matrix)
        self.spin_cols.setRange(1, 10)
        self.spin_cols.setValue(3)
        form_layout.addRow("列数 (M):", self.spin_cols)

        self.spin_row_gap = QDoubleSpinBox(grp_matrix)
        self.spin_row_gap.setRange(0.5, 10.0)
        self.spin_row_gap.setSingleStep(0.2)
        self.spin_row_gap.setValue(1.5)
        self.spin_row_gap.setSuffix(" m")
        form_layout.addRow("前后排距:", self.spin_row_gap)

        self.spin_col_gap = QDoubleSpinBox(grp_matrix)
        self.spin_col_gap.setRange(0.5, 10.0)
        self.spin_col_gap.setSingleStep(0.2)
        self.spin_col_gap.setValue(1.2)
        self.spin_col_gap.setSuffix(" m")
        form_layout.addRow("左右列距:", self.spin_col_gap)

        self.spin_rot = QDoubleSpinBox(grp_matrix)
        self.spin_rot.setRange(-180.0, 180.0)
        self.spin_rot.setValue(0.0)
        self.spin_rot.setSuffix(" °")
        form_layout.addRow("整体偏角:", self.spin_rot)

        self.btn_apply = QPushButton("✨ 生成并应用队形", grp_matrix)
        self.btn_apply.clicked.connect(self._apply_formation)
        form_layout.addRow(self.btn_apply)

        layout.addWidget(grp_matrix)

        grp_map = QGroupBox("🗺️ 舞台 LiDAR 点云地图导入", self)
        map_layout = QVBoxLayout(grp_map)
        map_layout.setContentsMargins(8, 8, 8, 8)
        map_layout.setSpacing(6)

        self.lbl_map_status = QLabel("当前地图: 未加载 (默认网格)", grp_map)
        self.lbl_map_status.setStyleSheet("color: #94a3b8; font-size: 10px;")
        map_layout.addWidget(self.lbl_map_status)

        self.btn_import_map = QPushButton("📂 导入点云 (.pcd / .ply)", grp_map)
        self.btn_import_map.setStyleSheet("background: #334155; color: #38bdf8;")
        self.btn_import_map.clicked.connect(self._browse_map_file)
        map_layout.addWidget(self.btn_import_map)

        layout.addWidget(grp_map)
        layout.addStretch(1)

    def _apply_formation(self) -> None:
        params = {
            "rows": self.spin_rows.value(),
            "cols": self.spin_cols.value(),
            "row_gap_m": self.spin_row_gap.value(),
            "col_gap_m": self.spin_col_gap.value(),
            "rotation_deg": self.spin_rot.value(),
            "total_count": self.spin_rows.value() * self.spin_cols.value(),
        }
        logger.info(f"Applying N x M formation preset: {params}")
        self.formationApplied.emit(params)

    def _browse_map_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择舞台点云地图文件", "", "LiDAR Point Cloud (*.pcd *.ply);;All Files (*)"
        )
        if file_path:
            self.lbl_map_status.setText(f"已加载: {file_path.split('/')[-1]}")
            self.lbl_map_status.setStyleSheet("color: #34d399; font-weight: 600; font-size: 10px;")
            self.mapImported.emit(file_path)

