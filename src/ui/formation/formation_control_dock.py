# @file: src/ui/formation/formation_control_dock.py
# @brief: Right 310px UniUni controls.html-inspired formation parameter & potential-field solver control dock.
# @exports: FormationControlDock

from __future__ import annotations

import math
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFormLayout, QLabel, QLineEdit, QSlider, QWidget

from src.ui.design_system.tokens import C_TEXT_2, FONT_MONO
from src.ui.design_system.u_buttons import UBadge, UButton
from src.ui.design_system.u_inputs import UInputNumber, USelect
from src.ui.design_system.u_panels import UPanel


class FormationControlDock(UPanel):
    """Right dock housing formation templates, potential-field solver gains, and track export actions."""

    generateClicked = Signal()
    solveClicked = Signal()
    applyToChoreoClicked = Signal()
    previewSliderChanged = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(title="队形模板与避障规划", header_widgets=[], parent=parent)
        self.setFixedWidth(310)
        self.body_layout.setSpacing(8)

        form = QFormLayout()
        form.setSpacing(8)

        self.kind_sel = USelect(
            [
                ("方阵 (Grid)", "grid"),
                ("横排 (Line)", "line"),
                ("圆形 (Circle)", "circle"),
                ("楔形 (Wedge)", "wedge"),
                ("错列 (Staggered)", "staggered"),
                ("字符点阵 (Text)", "text"),
            ],
            self.body_widget,
        )
        self.text_edit = QLineEdit("G1", self.body_widget)
        self.spacing_spin = UInputNumber(1.4, 0.5, 6.0, 0.1, 2, "m", self.body_widget)
        self.radius_spin = UInputNumber(2.6, 0.8, 12.0, 0.2, 2, "m", self.body_widget)
        self.cols_spin = UInputNumber(2, 1, 20, 1, 0, "列", self.body_widget)
        self.rot_spin = UInputNumber(0.0, -180.0, 180.0, 15.0, 0, "°", self.body_widget)
        self.safety_spin = UInputNumber(0.65, 0.35, 3.0, 0.05, 2, "m", self.body_widget)
        self.speed_spin = UInputNumber(1.2, 0.3, 2.5, 0.1, 2, "m/s", self.body_widget)
        self.group_name_edit = QLineEdit("团队过渡阵型", self.body_widget)

        form.addRow("目标队形", self.kind_sel)
        form.addRow("字符内容", self.text_edit)
        form.addRow("个体间距", self.spacing_spin)
        form.addRow("圆阵半径", self.radius_spin)
        form.addRow("矩阵列数", self.cols_spin)
        form.addRow("整体朝向", self.rot_spin)
        form.addRow("避障半径", self.safety_spin)
        form.addRow("规划最大速度", self.speed_spin)
        form.addRow("输出组名", self.group_name_edit)
        self.body_layout.addLayout(form)

        gen_b = UButton("1. 生成目标阵型 & 2-Opt配对", variant="default", size="sm", icon_name="grid", parent=self.body_widget)
        gen_b.clicked.connect(self.generateClicked.emit)
        self.body_layout.addWidget(gen_b)

        ret_b = UButton("返回初始方阵目标", variant="ghost", size="xs", icon_name="undo", parent=self.body_widget)
        ret_b.clicked.connect(lambda: (self.kind_sel.set_current_data("grid"), self.generateClicked.emit()))
        self.body_layout.addWidget(ret_b)

        solve_b = UButton("2. 人工势场无碰撞路径规划", variant="primary", size="sm", icon_name="target", parent=self.body_widget)
        solve_b.clicked.connect(self.solveClicked.emit)
        self.body_layout.addWidget(solve_b)

        self.metrics_badge = UBadge("待规划", tone="neutral", parent=self.body_widget)
        self.metrics_lbl = QLabel("最小间距: -- | 规划耗时: --", self.body_widget)
        self.metrics_lbl.setStyleSheet(f"color: {C_TEXT_2}; font-size: 11px; font-family: {FONT_MONO};")
        self.body_layout.addWidget(self.metrics_badge)
        self.body_layout.addWidget(self.metrics_lbl)

        # Path animation scrubber
        sc_lbl = QLabel("预演进度滑块:", self.body_widget)
        sc_lbl.setStyleSheet(f"color: {C_TEXT_2}; font-size: 11px;")
        self.preview_slider = QSlider(Qt.Orientation.Horizontal, self.body_widget)
        self.preview_slider.setRange(0, 100)
        self.preview_slider.setValue(100)
        self.preview_slider.valueChanged.connect(lambda v: self.previewSliderChanged.emit(v / 100.0))
        self.body_layout.addWidget(sc_lbl)
        self.body_layout.addWidget(self.preview_slider)

        self.body_layout.addStretch(1)

        apply_b = UButton("3. 入库轨迹并同步至舞台编导", variant="primary", size="md", icon_name="check", parent=self.body_widget)
        apply_b.clicked.connect(self.applyToChoreoClicked.emit)
        self.body_layout.addWidget(apply_b)

    def rotation_rad(self) -> float:
        return math.radians(self.rot_spin.value())

    def set_metrics(self, min_dist: float, sim_time: float, converged: bool) -> None:
        self.metrics_badge.setText("安全无碰撞 ✓" if converged and min_dist >= 0.35 else "间距过近 / 未收敛 !")
        self.metrics_badge.set_tone("ok" if converged and min_dist >= 0.35 else "warn")
        d_txt = f"{min_dist:.2f}m" if math.isfinite(min_dist) else "∞"
        self.metrics_lbl.setText(f"最小间距: {d_txt} | 耗时: {sim_time:.2f}s")
