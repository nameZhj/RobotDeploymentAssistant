"""
@file: src/ui/choreo_page/choreo_toolbar.py
@brief: 舞台编导主操作工具栏：工程管理、地图加载、轨迹编辑与安全急停
@exports: ChoreoToolbar
"""
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)


class ChoreoToolbar(QWidget):
    """提供工程操作、地图载入、选择/绘轨模式切换、轨迹撤销完成及安全急停工具栏"""

    newRequested = Signal()
    importRequested = Signal()
    saveRequested = Signal()
    loadMapRequested = Signal()
    modeChanged = Signal(str)
    undoRequested = Signal()
    clearRequested = Signal()
    finishRequested = Signal()
    resetViewRequested = Signal()
    emergencyStopRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_mode = "DRAW_TRAJECTORY"
        self._init_ui()

    def _init_ui(self) -> None:
        self.setFixedHeight(46)
        self.setStyleSheet("""
            QWidget {
                background-color: #0F172A;
                border-bottom: 1px solid #1E293B;
            }
            QPushButton {
                background-color: #1E293B;
                color: #E2E8F0;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #26334D;
                border-color: #38BDF8;
                color: #38BDF8;
            }
            QPushButton:checked {
                background-color: #0284C7;
                border-color: #38BDF8;
                color: #FFFFFF;
            }
            QPushButton.estop-btn {
                background-color: #991B1B;
                border: 1px solid #DC2626;
                color: #FEF2F2;
                font-weight: 700;
            }
            QPushButton.estop-btn:hover {
                background-color: #DC2626;
                color: #FFFFFF;
            }
            QFrame.v-divider {
                background-color: #334155;
                width: 1px;
                max-width: 1px;
                margin: 4px 2px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(6)

        # 1. Project Management
        self.btn_new = QPushButton("📄 新建", self)
        self.btn_new.clicked.connect(self.newRequested.emit)
        self.btn_import = QPushButton("📂 导入", self)
        self.btn_import.clicked.connect(self.importRequested.emit)
        self.btn_save = QPushButton("💾 保存", self)
        self.btn_save.clicked.connect(self.saveRequested.emit)
        layout.addWidget(self.btn_new)
        layout.addWidget(self.btn_import)
        layout.addWidget(self.btn_save)

        self._add_divider(layout)

        # 2. Map Operation
        self.btn_load_map = QPushButton("🗺️ 载入地图", self)
        self.btn_load_map.setToolTip("载入 PCD 舞台地图或使用默认高精度舞台")
        self.btn_load_map.clicked.connect(self.loadMapRequested.emit)
        layout.addWidget(self.btn_load_map)

        self._add_divider(layout)

        # 3. Mode Toggle (Select vs Draw Trajectory)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)

        self.btn_select = QPushButton("👆 选择", self)
        self.btn_select.setCheckable(True)
        self.mode_group.addButton(self.btn_select)
        layout.addWidget(self.btn_select)

        self.btn_draw = QPushButton("✏️ 绘制轨迹", self)
        self.btn_draw.setCheckable(True)
        self.btn_draw.setChecked(True)
        self.mode_group.addButton(self.btn_draw)
        layout.addWidget(self.btn_draw)

        self.btn_select.clicked.connect(lambda: self._set_mode("SELECT"))
        self.btn_draw.clicked.connect(lambda: self._set_mode("DRAW_TRAJECTORY"))

        self._add_divider(layout)

        # 4. Trajectory Editing Tools
        self.btn_undo = QPushButton("↩️ 撤销点", self)
        self.btn_undo.setToolTip("撤销最后一个轨迹点 (Ctrl+Z)")
        self.btn_undo.clicked.connect(self.undoRequested.emit)
        layout.addWidget(self.btn_undo)

        self.btn_clear = QPushButton("🗑️ 清空", self)
        self.btn_clear.setToolTip("清空当前所有绘制路径")
        self.btn_clear.clicked.connect(self.clearRequested.emit)
        layout.addWidget(self.btn_clear)

        self.btn_finish = QPushButton("✅ 完成", self)
        self.btn_finish.setToolTip("完成当前轨迹绘制并生成样条路径")
        self.btn_finish.clicked.connect(self.finishRequested.emit)
        layout.addWidget(self.btn_finish)

        self._add_divider(layout)

        # 5. View Reset
        self.btn_reset_view = QPushButton("🎯 重置视角", self)
        self.btn_reset_view.clicked.connect(self.resetViewRequested.emit)
        layout.addWidget(self.btn_reset_view)

        layout.addStretch(1)

        # 6. Global Emergency Brake
        self.btn_estop = QPushButton("🛑 硬件急停", self)
        self.btn_estop.setProperty("class", "estop-btn")
        self.btn_estop.setToolTip("物理安全保护：向全体机群下发紧急停车制动指令")
        self.btn_estop.clicked.connect(self.emergencyStopRequested.emit)
        layout.addWidget(self.btn_estop)

    def _add_divider(self, layout: QHBoxLayout) -> None:
        div = QFrame(self)
        div.setFrameShape(QFrame.VLine)
        div.setProperty("class", "v-divider")
        layout.addWidget(div)

    def _set_mode(self, mode: str) -> None:
        self._current_mode = mode
        self.modeChanged.emit(mode)

    def set_active_mode(self, mode: str) -> None:
        mode_upper = mode.upper()
        if "DRAW" in mode_upper or "TRAJ" in mode_upper:
            self.btn_draw.setChecked(True)
            self._current_mode = "DRAW_TRAJECTORY"
        else:
            self.btn_select.setChecked(True)
            self._current_mode = "SELECT"
