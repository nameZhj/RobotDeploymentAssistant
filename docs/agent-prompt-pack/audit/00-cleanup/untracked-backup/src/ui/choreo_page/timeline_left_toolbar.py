import logging
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger("TimelineLeftToolbar")


class TrackHeaderItem(QFrame):
    """Single robot track header showing ID, robot model/alias, and colored status dot."""

    clicked = Signal(int)

    def __init__(self, track_id: int, robot_name: str, dot_color: str = "#38BDF8", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.track_id = track_id
        self.setFixedHeight(56)  # Height matching upper action + lower trajectory subtracks
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #171A21;
                border-bottom: 1px solid #232733;
                border-right: 1px solid #232733;
            }}
            QFrame:hover {{ background-color: #1C2230; }}
            QLabel {{ color: #E2E8F0; font-size: 11px; font-weight: 600; }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        lbl_dot = QLabel("●", self)
        lbl_dot.setStyleSheet(f"color: {dot_color}; font-size: 14px;")
        layout.addWidget(lbl_dot)

        lbl_title = QLabel(f"ID: {track_id} {robot_name}", self)
        layout.addWidget(lbl_title, 1)

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self.track_id)
        super().mousePressEvent(event)


class TimelineLeftToolbar(QFrame):
    """
    Timeline header and left-dock toolbar composite:
    1. Top Header: [▷ 播放], [💾 保存编辑], [默认任务1 ▾]
    2. Vertical Icon Toolbar: Play, Undo, Redo, Split, Delete, Zoom slider, Snap, Loop
    3. Track Header column: Robot channel badges with colored dots.
    """

    playToggled = Signal(bool)
    saveClicked = Signal()
    taskChanged = Signal(str)
    undoClicked = Signal()
    redoClicked = Signal()
    splitClicked = Signal()
    deleteClicked = Signal()
    zoomChanged = Signal(int)
    snapToggled = Signal(bool)
    loopToggled = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        self.setObjectName("timelineLeftToolbar")
        self.setStyleSheet("""
            QFrame#timelineLeftToolbar {
                background-color: #111318;
                border-right: 1px solid #232733;
            }
            QPushButton.top-btn {
                background-color: #1C2230; color: #F1F5F9; border: 1px solid #2B3448;
                border-radius: 4px; padding: 4px 10px; font-size: 11px; font-weight: 700;
            }
            QPushButton.top-btn:hover { background-color: #263147; border-color: #1E6FFF; color: #60A5FA; }
            QPushButton.icon-btn {
                background-color: #171A21; color: #CBD5E1; border: 1px solid #232733;
                border-radius: 4px; font-size: 12px; font-weight: 700; padding: 4px; min-width: 26px; min-height: 24px;
            }
            QPushButton.icon-btn:hover { background-color: #1E6FFF; color: #FFFFFF; }
            QPushButton.icon-btn:checked { background-color: #1E6FFF; color: #FFFFFF; }
            QComboBox {
                background-color: #171A21; color: #38BDF8; border: 1px solid #2B3448;
                border-radius: 4px; padding: 3px 6px; font-weight: 700; font-size: 11px;
            }
        """)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Timeline Top Control Bar (Height 34)
        top_bar = QFrame(self)
        top_bar.setFixedHeight(34)
        top_bar.setStyleSheet("background-color: #171A21; border-bottom: 1px solid #232733;")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(8, 2, 8, 2)
        top_layout.setSpacing(8)

        self.btn_play = QPushButton("▷ 播放", top_bar)
        self.btn_play.setProperty("class", "top-btn")
        self.btn_play.setCheckable(True)
        self.btn_play.toggled.connect(self._on_play_toggled)
        top_layout.addWidget(self.btn_play)

        self.btn_save = QPushButton("💾 保存编辑", top_bar)
        self.btn_save.setProperty("class", "top-btn")
        self.btn_save.clicked.connect(self.saveClicked.emit)
        top_layout.addWidget(self.btn_save)

        self.combo_task = QComboBox(top_bar)
        self.combo_task.addItems(["主舞台编排 (Default)"])
        self.combo_task.currentIndexChanged.connect(lambda: self.taskChanged.emit(self.combo_task.currentText()))
        top_layout.addWidget(self.combo_task)

        top_layout.addStretch(1)
        root_layout.addWidget(top_bar)

        # 2. Main Body: Left Vertical Icon Bar + Right Track Headers
        body = QWidget(self)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # 2.1 Vertical Icon Toolbar (Width 36)
        v_toolbar = QFrame(body)
        v_toolbar.setFixedWidth(36)
        v_toolbar.setStyleSheet("background-color: #13161D; border-right: 1px solid #232733;")
        v_layout = QVBoxLayout(v_toolbar)
        v_layout.setContentsMargins(3, 6, 3, 6)
        v_layout.setSpacing(4)

        icons = [
            ("↩", "撤销 (Ctrl+Z)", self.undoClicked),
            ("↪", "重做 (Ctrl+Y)", self.redoClicked),
            ("✂", "分割动作块 (C)", self.splitClicked),
            ("🗑️", "删除选中 (Del)", self.deleteClicked),
        ]
        for sym, tip, sig in icons:
            btn = QPushButton(sym, v_toolbar)
            btn.setProperty("class", "icon-btn")
            btn.setToolTip(tip)
            btn.clicked.connect(sig.emit)
            v_layout.addWidget(btn)

        # Snap Magnetic Alignment
        self.btn_snap = QPushButton("🧲", v_toolbar)
        self.btn_snap.setProperty("class", "icon-btn")
        self.btn_snap.setCheckable(True)
        self.btn_snap.setChecked(True)
        self.btn_snap.setToolTip("开启/关闭 网格吸附")
        self.btn_snap.toggled.connect(self.snapToggled.emit)
        v_layout.addWidget(self.btn_snap)

        # Loop Playback
        self.btn_loop = QPushButton("🔁", v_toolbar)
        self.btn_loop.setProperty("class", "icon-btn")
        self.btn_loop.setCheckable(True)
        self.btn_loop.setToolTip("开启/关闭 循环播放")
        self.btn_loop.toggled.connect(self.loopToggled.emit)
        v_layout.addWidget(self.btn_loop)

        # Zoom Slider
        v_layout.addSpacing(6)
        lbl_zoom = QLabel("🔍", v_toolbar)
        lbl_zoom.setAlignment(Qt.AlignCenter)
        v_layout.addWidget(lbl_zoom)

        self.slider_zoom = QSlider(Qt.Vertical, v_toolbar)
        self.slider_zoom.setRange(50, 200)
        self.slider_zoom.setValue(100)
        self.slider_zoom.setToolTip("时间轴缩放比例")
        self.slider_zoom.valueChanged.connect(self.zoomChanged.emit)
        v_layout.addWidget(self.slider_zoom, 1)

        body_layout.addWidget(v_toolbar)

        # 2.2 Robot Track Header Stack (Width 160)
        self.track_header_container = QWidget(body)
        self.track_header_container.setFixedWidth(160)
        self.track_header_layout = QVBoxLayout(self.track_header_container)
        self.track_header_layout.setContentsMargins(0, 0, 0, 0)
        self.track_header_layout.setSpacing(0)

        # Default track headers: G1 Robot_A, G1 Robot_B
        self.track_header_layout.addWidget(TrackHeaderItem(1, "G1 Robot_A", "#38BDF8", self.track_header_container))
        self.track_header_layout.addWidget(TrackHeaderItem(2, "G1 Robot_B", "#10B981", self.track_header_container))
        self.track_header_layout.addStretch(1)

        body_layout.addWidget(self.track_header_container)
        root_layout.addWidget(body, 1)

    def _on_play_toggled(self, checked: bool) -> None:
        self.btn_play.setText("⏸ 暂停" if checked else "▷ 播放")
        self.btn_play.setStyleSheet("background-color: #1E6FFF; color: #FFF;" if checked else "")
        self.playToggled.emit(checked)

