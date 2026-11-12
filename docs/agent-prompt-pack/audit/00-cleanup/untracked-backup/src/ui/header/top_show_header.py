from typing import Optional
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)
from src.core.config_loader import config_loader
from src.core.event_bus import event_bus
from src.ui.header.swarm_emergency_brake import SwarmEmergencyBrake


class TopShowHeader(QWidget):
    """
    Studio header bar orchestrating project actions (new, import, save),
    show execution modes, clock synchronization quality status, T0 countdown, and emergency brake.
    """

    modeChanged = Signal(str)
    newProjectRequested = Signal()
    importProjectRequested = Signal()
    saveProjectRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._app_info = config_loader.get_app_info()
        self._countdown_ms = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)

        self._init_ui()
        self._subscribe_events()

    def _init_ui(self) -> None:
        self.setFixedHeight(56)
        self.setStyleSheet("""
            QWidget {
                background-color: #0f172a;
                border-bottom: 1px solid #1e293b;
            }
            QPushButton {
                background: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { background: #334155; color: #38bdf8; }
            QComboBox {
                background: #1e293b;
                color: #38bdf8;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 4px 10px;
                font-weight: 600;
                font-size: 12px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(12)

        # 1. Project Management (New, Import, Save/Export)
        self.btn_new = QPushButton("📄 新建", self)
        self.btn_new.clicked.connect(self.newProjectRequested.emit)
        self.btn_import = QPushButton("📂 导入", self)
        self.btn_import.clicked.connect(self.importProjectRequested.emit)
        self.btn_save = QPushButton("💾 保存", self)
        self.btn_save.clicked.connect(self.saveProjectRequested.emit)

        layout.addWidget(self.btn_new)
        layout.addWidget(self.btn_import)
        layout.addWidget(self.btn_save)

        # 2. Show Mode Selector
        lbl_mode = QLabel("模式:", self)
        lbl_mode.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(lbl_mode)

        self.mode_combo = QComboBox(self)
        self.mode_combo.addItem("🎵 音乐同步模式 (MUSIC_SYNC)", "MUSIC_SYNC")
        self.mode_combo.addItem("💃 舞蹈排练模式 (REHEARSAL)", "REHEARSAL")
        self.mode_combo.addItem("🔁 循环路演模式 (LOOP_SHOW)", "LOOP_SHOW")
        self.mode_combo.currentIndexChanged.connect(
            lambda idx: self.modeChanged.emit(self.mode_combo.currentData())
        )
        layout.addWidget(self.mode_combo)

        layout.addStretch(1)

        # 3. Global Clock Quality Indicator
        self.lbl_clock_status = QLabel("⏱️ CLOCK: 质量优 (<20ms)", self)
        self.lbl_clock_status.setStyleSheet("""
            QLabel {
                color: #34d399;
                background: rgba(16, 185, 129, 0.15);
                border: 1px solid #10b981;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 700;
            }
        """)
        layout.addWidget(self.lbl_clock_status)

        # 4. T0 Countdown Timer
        self.lbl_countdown = QLabel("T0: 就绪", self)
        self.lbl_countdown.setStyleSheet("""
            QLabel {
                color: #fbbf24;
                font-family: monospace;
                font-size: 13px;
                font-weight: 800;
                padding: 4px 8px;
            }
        """)
        layout.addWidget(self.lbl_countdown)

        # 5. Right Emergency Brake
        self.emergency_brake = SwarmEmergencyBrake(self)
        layout.addWidget(self.emergency_brake)

    def _subscribe_events(self) -> None:
        event_bus.subscribe("CLOCK_QUALITY_UPDATED", self._update_clock_ui)

    def _update_clock_ui(self, data: dict) -> None:
        skew_ms = abs(data.get("skew_ms", 0.0))
        if skew_ms <= 20.0:
            self.lbl_clock_status.setText(f"⏱️ CLOCK: 优 ({skew_ms:.1f}ms)")
            self.lbl_clock_status.setStyleSheet("color: #34d399; background: rgba(16, 185, 129, 0.15); border: 1px solid #10b981; padding: 4px 10px; border-radius: 4px;")
        else:
            self.lbl_clock_status.setText(f"⚠️ CLOCK: 偏大 ({skew_ms:.1f}ms)")
            self.lbl_clock_status.setStyleSheet("color: #fbbf24; background: rgba(245, 158, 11, 0.15); border: 1px solid #f59e0b; padding: 4px 10px; border-radius: 4px;")

    def start_countdown(self, lead_time_ms: int = 3000) -> None:
        """Start countdown towards T0 benchmark moment."""
        self._countdown_ms = lead_time_ms
        self.lbl_countdown.setText(f"T-{self._countdown_ms / 1000.0:.1f}s")
        self._timer.start(100)

    def _on_tick(self) -> None:
        self._countdown_ms -= 100
        if self._countdown_ms > 0:
            self.lbl_countdown.setText(f"T-{self._countdown_ms / 1000.0:.1f}s")
        else:
            self.lbl_countdown.setText("T0: 演播中")
            self._timer.stop()
