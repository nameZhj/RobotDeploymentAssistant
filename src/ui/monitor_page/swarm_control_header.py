import logging
from typing import Any, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from src.core.event_bus import event_bus

logger = logging.getLogger("SwarmControlHeader")


class SwarmControlHeader(QFrame):
    """
    Monitor page top-right swarm execution & synchronization control console:
    Row 1: Play action, slide-to-brake red emergency stop, 3-mode switcher (Music/Debug/Loop).
    Row 2: Select all, orange initialize, sync actions (Task/Trajectory/Map).
    Row 3: Device management toolstrip (Overview, Batch Ops, Assign ID, Map Check, Music Check).
    """

    modeChanged = Signal(str)
    playTriggered = Signal(str)
    emergencyStopTriggered = Signal()
    selectAllToggled = Signal(bool)
    initClicked = Signal()
    syncActionClicked = Signal(str)
    deviceActionClicked = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None, controller: Optional[Any] = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._current_mode = "MUSIC"
        self._is_playing = False
        self._selected_count = 2
        self._total_count = 2

        self._init_ui()

    def _init_ui(self) -> None:
        self.setStyleSheet("""
            QFrame#swarmControlHeader {
                background-color: #111318; border: 1px solid #1E293B; border-radius: 6px;
            }
            QPushButton.primary-btn {
                background-color: #1E6FFF; color: #FFFFFF; border: none; border-radius: 4px;
                padding: 6px 14px; font-weight: 700; font-size: 12px;
            }
            QPushButton.primary-btn:hover { background-color: #3385FF; }
            QPushButton.init-btn {
                background-color: #EA580C; color: #FFFFFF; border: none; border-radius: 4px;
                padding: 5px 12px; font-weight: 700; font-size: 12px;
            }
            QPushButton.init-btn:hover { background-color: #C2410C; }
            QPushButton.sub-btn {
                background-color: #1E2430; color: #CBD5E1; border: 1px solid #334155;
                border-radius: 4px; padding: 4px 10px; font-size: 11px; font-weight: 600;
            }
            QPushButton.sub-btn:hover { background-color: #2D3748; color: #FFFFFF; }
            QPushButton.sub-btn:checked { background-color: #1E6FFF; color: #FFFFFF; border-color: #3B82F6; }
            QSlider::groove:horizontal {
                height: 24px; background: #3B1219; border: 1px solid #7F1D1D; border-radius: 12px;
            }
            QSlider::handle:horizontal {
                width: 28px; background: #EF4444; border-radius: 12px; margin: 0px 0;
            }
            QSlider::handle:horizontal:hover { background: #DC2626; }
        """)
        self.setObjectName("swarmControlHeader")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 8, 10, 8)
        root_layout.setSpacing(6)

        # Row 1: Play button, Slide brake, 3-mode switcher
        row1 = QHBoxLayout()
        self.btn_play = QPushButton("▷ 音乐伴奏", self)
        self.btn_play.setProperty("class", "primary-btn")
        self.btn_play.clicked.connect(self._on_play_clicked)
        row1.addWidget(self.btn_play)

        # Slide-to-brake container
        brake_box = QFrame(self)
        brake_layout = QHBoxLayout(brake_box)
        brake_layout.setContentsMargins(4, 0, 4, 0)
        brake_layout.setSpacing(4)
        lbl_brake = QLabel("● 右滑急停", brake_box)
        lbl_brake.setStyleSheet("color: #F87171; font-size: 10px; font-weight: 700;")
        lbl_brake.setCursor(Qt.PointingHandCursor)
        lbl_brake.mousePressEvent = lambda _: self._on_slider_value_changed(100)
        brake_layout.addWidget(lbl_brake)
        self.slider_brake = QSlider(Qt.Horizontal, brake_box)
        self.slider_brake.setRange(0, 100)
        self.slider_brake.setValue(0)
        self.slider_brake.setFixedWidth(100)
        self.slider_brake.sliderReleased.connect(self._on_slider_released)
        self.slider_brake.valueChanged.connect(self._on_slider_value_changed)
        brake_layout.addWidget(self.slider_brake)
        row1.addWidget(brake_box)

        row1.addStretch(1)

        # 3-Mode group
        self.mode_group = QButtonGroup(self)
        for mode_key, text in [("MUSIC", "音乐伴奏"), ("DEBUG", "舞蹈调试"), ("LOOP", "循环执行")]:
            btn_m = QPushButton(text, self)
            btn_m.setProperty("class", "sub-btn")
            btn_m.setCheckable(True)
            if mode_key == "MUSIC":
                btn_m.setChecked(True)
            btn_m.toggled.connect(lambda c, k=mode_key, t=text: self._on_mode_toggled(c, k, t))
            self.mode_group.addButton(btn_m)
            row1.addWidget(btn_m)
        root_layout.addLayout(row1)

        # Row 2: Select all, Initialize, Sync actions
        row2 = QHBoxLayout()
        self.btn_select_all = QPushButton("全选 (2/2)", self)
        self.btn_select_all.setProperty("class", "sub-btn")
        self.btn_select_all.setCheckable(True)
        self.btn_select_all.setChecked(True)
        self.btn_select_all.toggled.connect(self.selectAllToggled.emit)
        row2.addWidget(self.btn_select_all)

        self.btn_init = QPushButton("🎯 初始化", self)
        self.btn_init.setProperty("class", "init-btn")
        self.btn_init.clicked.connect(self.initClicked.emit)
        row2.addWidget(self.btn_init)

        row2.addStretch(1)

        for text, act in [("同步任务", "TASK"), ("同步轨迹", "TRAJECTORY"), ("同步地图", "MAP")]:
            b = QPushButton(text, self)
            b.setProperty("class", "sub-btn")
            b.clicked.connect(lambda _, a=act: self.syncActionClicked.emit(a))
            row2.addWidget(b)
        root_layout.addLayout(row2)

        # Row 3: Device tools (Overview, Batch, Assign ID, Map Check, Music Check)
        row3 = QHBoxLayout()
        actions = [("☷ 总览", "OVERVIEW"), ("批量操作", "BATCH_OPS"), ("分配ID", "ASSIGN_ID"),
                   ("地图检查", "MAP_CHECK"), ("音乐检查", "MUSIC_CHECK")]
        for text, code in actions:
            btn_dev = QPushButton(text, self)
            btn_dev.setProperty("class", "sub-btn")
            btn_dev.clicked.connect(lambda _, c=code: self.deviceActionClicked.emit(c))
            row3.addWidget(btn_dev)
        row3.addStretch(1)
        root_layout.addLayout(row3)

    def _on_play_clicked(self) -> None:
        self.playTriggered.emit(self._current_mode)

    def _on_mode_toggled(self, checked: bool, mode_key: str, label: str) -> None:
        if checked:
            self._current_mode = mode_key
            self.btn_play.setText(f"▷ {label}")
            self.modeChanged.emit(mode_key)

    def _on_slider_value_changed(self, val: int) -> None:
        if val >= 85:
            self.slider_brake.setValue(0)
            if self.controller:
                self.controller.send_lrmp(["A", "B"], "STOP")
                if self.controller.is_playing:
                    self.controller.toggle_playback()
                self.controller.swarm_status_changed.emit({"emergency_alarm": True, "status": "STOPPED"})
            self.emergencyStopTriggered.emit()
            event_bus.publish("SWARM_EMERGENCY_STOP", {"target": "ALL", "command": "ALL|STOP"})
            logger.warning("SwarmControlHeader: Slider emergency stop dispatched ALL|STOP!")

    def _on_slider_released(self) -> None:
        if self.slider_brake.value() < 85:
            self.slider_brake.setValue(0)

    def set_robot_selection_count(self, selected: int, total: int) -> None:
        self._selected_count = selected
        self._total_count = total
        self.btn_select_all.setText(f"全选 ({selected}/{total})")

    def set_is_playing(self, playing: bool) -> None:
        self._is_playing = playing
        mode_text = {"MUSIC": "音乐伴奏", "DEBUG": "舞蹈调试", "LOOP": "循环执行"}.get(self._current_mode, "执行")
        self.btn_play.setText(f"⏹ 停止{mode_text}" if playing else f"▷ {mode_text}")

