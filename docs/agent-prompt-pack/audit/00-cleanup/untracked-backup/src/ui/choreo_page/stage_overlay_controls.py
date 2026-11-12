"""
@file: src/ui/choreo_page/stage_overlay_controls.py
@brief: 2D/3D 舞台视口悬浮工具栏、视口切换与虚拟预演控制层
@exports: StageOverlayControls
"""
import logging
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger("StageOverlayControls")


class StageOverlayControls(QWidget):
    """
    Floating overlay control layer over 2D/3D stage viewports:
    - Top-Left: Mode toolstrip (2D: Draw Trajectory, Sketch, Clear; 3D: Animate, Refresh, Sketch, Trajectory)
    - Top-Right: [Grid] toggle + 3D / 2D perspective switcher
    - Bottom-Left: Origin reset and frontal view quick-actions
    - Bottom-Right: Semi-transparent mouse & keyboard shortcut guidance card.
    """

    modeChanged = Signal(str)
    viewDimensionChanged = Signal(str)
    gridToggled = Signal(bool)
    resetOriginClicked = Signal()
    clearAllClicked = Signal()
    animationToggled = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_dim = "2D"
        self._init_ui()

    def _init_ui(self) -> None:
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setStyleSheet("""
            QFrame.overlay-panel {
                background-color: rgba(23, 26, 33, 0.85);
                border: 1px solid #2B3448;
                border-radius: 6px;
            }
            QPushButton.overlay-btn {
                background-color: #1C2230; color: #F1F5F9; border: 1px solid #2B3448;
                border-radius: 4px; padding: 4px 10px; font-size: 11px; font-weight: 700;
            }
            QPushButton.overlay-btn:hover { background-color: #263147; border-color: #1E6FFF; color: #60A5FA; }
            QPushButton.overlay-btn:checked { background-color: #1E6FFF; border-color: #3385FF; color: #FFFFFF; }
            QLabel.hint-text { color: #94A3B8; font-size: 10px; line-height: 14px; }
        """)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)

        # 1. Top Bar: Left Tools + Right 2D/3D Switcher
        top_row = QHBoxLayout()

        # 1.1 Left Toolstrip Panel
        self.tool_panel = QFrame(self)
        self.tool_panel.setProperty("class", "overlay-panel")
        self.tool_layout = QHBoxLayout(self.tool_panel)
        self.tool_layout.setContentsMargins(6, 4, 6, 4)
        self.tool_layout.setSpacing(6)
        top_row.addWidget(self.tool_panel)

        top_row.addStretch(1)

        # 1.2 Right View & Grid Switcher Panel
        view_panel = QFrame(self)
        view_panel.setProperty("class", "overlay-panel")
        view_layout = QHBoxLayout(view_panel)
        view_layout.setContentsMargins(6, 4, 6, 4)
        view_layout.setSpacing(6)

        self.btn_grid = QPushButton("网格", view_panel)
        self.btn_grid.setProperty("class", "overlay-btn")
        self.btn_grid.setCheckable(True)
        self.btn_grid.setChecked(True)
        self.btn_grid.toggled.connect(self.gridToggled.emit)
        view_layout.addWidget(self.btn_grid)

        # 3D / 2D Button Group
        self.dim_group = QButtonGroup(self)
        self.dim_group.setExclusive(True)

        self.btn_3d = QPushButton("3D", view_panel)
        self.btn_3d.setProperty("class", "overlay-btn")
        self.btn_3d.setCheckable(True)
        self.dim_group.addButton(self.btn_3d)
        view_layout.addWidget(self.btn_3d)

        self.btn_2d = QPushButton("2D", view_panel)
        self.btn_2d.setProperty("class", "overlay-btn")
        self.btn_2d.setCheckable(True)
        self.btn_2d.setChecked(True)
        self.dim_group.addButton(self.btn_2d)
        view_layout.addWidget(self.btn_2d)

        self.btn_3d.toggled.connect(lambda c: self._on_dim_changed("3D" if c else "2D"))
        self.btn_3d.clicked.connect(lambda: self._on_dim_changed("3D"))
        self.btn_2d.toggled.connect(lambda c: self._on_dim_changed("2D" if c else "3D"))
        self.btn_2d.clicked.connect(lambda: self._on_dim_changed("2D"))
        top_row.addWidget(view_panel)
        root_layout.addLayout(top_row)

        root_layout.addStretch(1)

        # 2. Bottom Bar: Left Reset Actions + Right Keyboard/Mouse Hint Card
        bottom_row = QHBoxLayout()

        # 2.1 Left Reset Group
        reset_panel = QFrame(self)
        reset_panel.setProperty("class", "overlay-panel")
        reset_layout = QHBoxLayout(reset_panel)
        reset_layout.setContentsMargins(6, 4, 6, 4)
        reset_layout.setSpacing(6)

        self.btn_reset_origin = QPushButton("🎯 原点重置", reset_panel)
        self.btn_reset_origin.setProperty("class", "overlay-btn")
        self.btn_reset_origin.clicked.connect(self.resetOriginClicked.emit)
        reset_layout.addWidget(self.btn_reset_origin)

        self.btn_front_view = QPushButton("🧭 正视视角", reset_panel)
        self.btn_front_view.setProperty("class", "overlay-btn")
        self.btn_front_view.clicked.connect(self.resetOriginClicked.emit)
        reset_layout.addWidget(self.btn_front_view)
        bottom_row.addWidget(reset_panel)

        bottom_row.addStretch(1)

        # 2.2 Right Semi-Transparent Hint Card
        hint_card = QFrame(self)
        hint_card.setProperty("class", "overlay-panel")
        hint_layout = QVBoxLayout(hint_card)
        hint_layout.setContentsMargins(8, 6, 8, 6)
        hint_layout.setSpacing(2)

        hints = [
            "• 左键: 添加轨迹点 / 选中",
            "• 右键: 结束当前绘制并保存",
            "• Alt+左键: 拖动画布视角",
            "• 滚轮: 缩放视图比例 (Ctrl+Z 撤回)",
        ]
        for h_text in hints:
            lbl = QLabel(h_text, hint_card)
            lbl.setProperty("class", "hint-text")
            hint_layout.addWidget(lbl)
        bottom_row.addWidget(hint_card)

        root_layout.addLayout(bottom_row)

        self._rebuild_toolstrip_buttons("2D")

    def _on_dim_changed(self, dimension: str) -> None:
        self._current_dim = dimension
        self._rebuild_toolstrip_buttons(dimension)
        self.viewDimensionChanged.emit(dimension)

    def _rebuild_toolstrip_buttons(self, dimension: str) -> None:
        # Clear existing buttons
        while self.tool_layout.count() > 0:
            item = self.tool_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if dimension == "2D":
            btn_draw_traj = QPushButton("轨迹绘制", self.tool_panel)
            btn_draw_traj.setProperty("class", "overlay-btn")
            btn_draw_traj.setCheckable(True)
            btn_draw_traj.setChecked(True)
            btn_draw_traj.clicked.connect(lambda: self.modeChanged.emit("TRAJ"))
            btn_draw_traj.toggled.connect(lambda c: self.modeChanged.emit("TRAJ" if c else "IDLE"))
            self.tool_layout.addWidget(btn_draw_traj)

            btn_sketch = QPushButton("草图笔", self.tool_panel)
            btn_sketch.setProperty("class", "overlay-btn")
            btn_sketch.setCheckable(True)
            btn_sketch.clicked.connect(lambda: self.modeChanged.emit("SKETCH"))
            btn_sketch.toggled.connect(lambda c: self.modeChanged.emit("SKETCH" if c else "IDLE"))
            self.tool_layout.addWidget(btn_sketch)

            btn_clear_sketch = QPushButton("清空草图", self.tool_panel)
            btn_clear_sketch.setProperty("class", "overlay-btn")
            btn_clear_sketch.clicked.connect(self.clearAllClicked.emit)
            self.tool_layout.addWidget(btn_clear_sketch)

            btn_clear_all = QPushButton("清空全部", self.tool_panel)
            btn_clear_all.setProperty("class", "overlay-btn")
            btn_clear_all.clicked.connect(self.clearAllClicked.emit)
            self.tool_layout.addWidget(btn_clear_all)
        else:
            btn_anim = QPushButton("▷ 虚拟预演", self.tool_panel)
            btn_anim.setProperty("class", "overlay-btn")
            btn_anim.setToolTip("60Hz 3D 舞台虚拟预演 (不向真机发送任何指令)")
            btn_anim.setCheckable(True)
            btn_anim.clicked.connect(lambda: self.animationToggled.emit(btn_anim.isChecked()))
            btn_anim.toggled.connect(self.animationToggled.emit)
            self.tool_layout.addWidget(btn_anim)

            btn_refresh = QPushButton("刷新", self.tool_panel)
            btn_refresh.setProperty("class", "overlay-btn")
            btn_refresh.clicked.connect(self.resetOriginClicked.emit)
            self.tool_layout.addWidget(btn_refresh)

