# @file: src/ui/choreography/stage_draw_overlay.py
# @brief: UniUni-style inline stage drawing toolbar (轨迹绘制, 草图笔, 清空草图, 清空轨迹, 保存轨迹) and coord HUD.
# @exports: StageDrawToolbar, StageHintFooter

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from src.ui.design_system.tokens import C_CARD, C_FLOAT, C_FLOAT_EDGE, C_TEXT_1, C_TEXT_2, FONT_MONO, LINE
from src.ui.design_system.u_buttons import UButton, UIconButton


class StageDrawToolbar(QFrame):
    """Inline 2D trajectory & sketch drawing control bar mounted above StageCanvas2D."""

    modeChanged = Signal(str)  # "view" | "draw_traj" | "sketch"
    clearSketchClicked = Signal()
    clearDraftClicked = Signal()
    saveDraftClicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setStyleSheet(f"StageDrawToolbar {{ background: {C_CARD}; border-bottom: 1px solid {LINE}; }}")

        hl = QHBoxLayout(self)
        hl.setContentsMargins(8, 2, 8, 2)
        hl.setSpacing(6)

        self.draw_btn = UButton("轨迹绘制", variant="default", size="xs", icon_name="edit", parent=self)
        self.draw_btn.setCheckable(True)
        self.draw_btn.clicked.connect(self._on_draw_toggled)

        self.sketch_btn = UButton("草图笔", variant="default", size="xs", icon_name="sliders", parent=self)
        self.sketch_btn.setCheckable(True)
        self.sketch_btn.clicked.connect(self._on_sketch_toggled)

        self.clr_sketch_btn = UButton("清空草图", variant="ghost", size="xs", parent=self)
        self.clr_sketch_btn.clicked.connect(self.clearSketchClicked.emit)

        self.clr_traj_btn = UButton("清空轨迹", variant="ghost", size="xs", parent=self)
        self.clr_traj_btn.clicked.connect(self.clearDraftClicked.emit)

        self.save_traj_btn = UButton("保存轨迹", variant="primary", size="xs", icon_name="save", parent=self)
        self.save_traj_btn.setEnabled(False)
        self.save_traj_btn.clicked.connect(self.saveDraftClicked.emit)

        for b in (self.draw_btn, self.sketch_btn, self.clr_sketch_btn, self.clr_traj_btn, self.save_traj_btn):
            hl.addWidget(b)

        hl.addStretch(1)
        self.count_lbl = QLabel("未激活绘制", self)
        self.count_lbl.setStyleSheet(f"color: {C_TEXT_2}; font-size: 11px;")
        self.coord_lbl = QLabel("X: 0.00  Y: 0.00 m", self)
        self.coord_lbl.setStyleSheet(f"font-family: {FONT_MONO}; font-size: 11px; color: {C_TEXT_1};")
        hl.addWidget(self.count_lbl)
        hl.addWidget(self.coord_lbl)

    def _on_draw_toggled(self, checked: bool) -> None:
        if checked:
            self.sketch_btn.setChecked(False)
            self.modeChanged.emit("draw_traj")
            self.count_lbl.setText("左键落点 · 右键保存")
        else:
            self.modeChanged.emit("view")
            self.count_lbl.setText("浏览/拖拽机器人")

    def _on_sketch_toggled(self, checked: bool) -> None:
        if checked:
            self.draw_btn.setChecked(False)
            self.modeChanged.emit("sketch")
            self.count_lbl.setText("左键手绘草图")
        else:
            self.modeChanged.emit("view")
            self.count_lbl.setText("浏览/拖拽机器人")

    def reset_to_view(self) -> None:
        self.draw_btn.setChecked(False)
        self.sketch_btn.setChecked(False)
        self.modeChanged.emit("view")
        self.count_lbl.setText("浏览/拖拽机器人")

    def update_coord(self, wx: float, wy: float) -> None:
        self.coord_lbl.setText(f"X:{wx:6.2f}  Y:{wy:6.2f} m")

    def update_draft_status(self, point_count: int) -> None:
        self.save_traj_btn.setEnabled(point_count >= 2)
        if self.draw_btn.isChecked():
            self.count_lbl.setText(f"已绘 {point_count} 点 · 右键完成" if point_count else "左键落点 · 右键完成")


class StageHintFooter(QFrame):
    """Compact UniUni mouse gesture cheat-sheet bar with dismiss button."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(24)
        self.setStyleSheet(f"StageHintFooter {{ background: {C_FLOAT}; border-top: 1px solid {C_FLOAT_EDGE}; }}")
        hl = QHBoxLayout(self)
        hl.setContentsMargins(8, 0, 6, 0)
        hl.setSpacing(6)
        lbl = QLabel(
            "左键: 选点/落点/调站位  |  右键: 完成轨迹并保存  |  Alt+左键或中键: 拖动画布  |  滚轮: 缩放  |  Ctrl+Z: 撤回点",
            self,
        )
        lbl.setStyleSheet(f"color: {C_TEXT_2}; font-size: 10px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        close_b = UIconButton("close", tooltip="隐藏手势提示", size=18, parent=self)
        close_b.clicked.connect(self.hide)
        hl.addWidget(lbl, 1)
        hl.addWidget(close_b)
