import logging
from typing import Any, Dict, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger("RobotVitalCard")


class RobotVitalCard(QFrame):
    """
    1:1 Telemetry vital card for a single robot in the fleet.
    Displays alias, online status dot, battery level (with low-battery warning & substitute),
    temperature, coordinates (x, y, theta), authority lease, and choreography step.
    """

    selectionChanged = Signal(str, bool)
    cardClicked = Signal(str)
    substituteRequested = Signal(str)

    def __init__(self, alias: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.alias = alias.strip().upper()
        self._is_online = True
        self._battery_pct = 100
        self._temp_c = 36.5
        self._authority = "FREE"
        self._choreo_step = 0
        self._pose = (0.0, 0.0, 0.0)

        self._init_ui()

    def _init_ui(self) -> None:
        self.setObjectName("robotVitalCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QFrame#robotVitalCard {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px;
            }
            QFrame#robotVitalCard:hover {
                border: 1px solid #0ea5e9;
            }
            QLabel { color: #e2e8f0; font-size: 11px; }
            QLabel.title { font-weight: 700; font-size: 13px; color: #38bdf8; }
            QPushButton.sub-btn {
                background: #ef4444; color: #ffffff;
                font-size: 10px; font-weight: 700;
                padding: 2px 6px; border-radius: 3px; border: none;
            }
            QPushButton.sub-btn:hover { background: #dc2626; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        row1 = QHBoxLayout()
        self.chk_select = QCheckBox(self)
        self.chk_select.setChecked(True)
        self.chk_select.toggled.connect(lambda checked: self.selectionChanged.emit(self.alias, checked))
        row1.addWidget(self.chk_select)

        self.lbl_alias = QLabel(f"🤖 机甲 {self.alias}", self)
        self.lbl_alias.setProperty("class", "title")
        row1.addWidget(self.lbl_alias)

        self.lbl_dot = QLabel("● 在线", self)
        self.lbl_dot.setStyleSheet("color: #10b981; font-weight: 700;")
        row1.addWidget(self.lbl_dot)

        row1.addStretch(1)
        self.lbl_auth = QLabel(f"[{self._authority}]", self)
        self.lbl_auth.setStyleSheet("color: #94a3b8; font-weight: 600;")
        row1.addWidget(self.lbl_auth)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        lbl_bat_title = QLabel("电量:", self)
        row2.addWidget(lbl_bat_title)

        self.bat_bar = QProgressBar(self)
        self.bat_bar.setRange(0, 100)
        self.bat_bar.setValue(self._battery_pct)
        self.bat_bar.setFixedHeight(12)
        self.bat_bar.setTextVisible(True)
        self.bat_bar.setFormat("%p%")
        self.bat_bar.setStyleSheet("""
            QProgressBar {
                background: #0f172a; border: 1px solid #475569;
                border-radius: 3px; text-align: center; color: #ffffff; font-size: 9px;
            }
            QProgressBar::chunk { background-color: #10b981; border-radius: 2px; }
        """)
        row2.addWidget(self.bat_bar, 1)

        self.btn_substitute = QPushButton("替补换人", self)
        self.btn_substitute.setProperty("class", "sub-btn")
        self.btn_substitute.setVisible(False)
        self.btn_substitute.clicked.connect(lambda: self.substituteRequested.emit(self.alias))
        row2.addWidget(self.btn_substitute)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        self.lbl_temp = QLabel(f"🌡️ {self._temp_c:.1f}°C", self)
        row3.addWidget(self.lbl_temp)

        self.lbl_pose = QLabel("📍 (0.00, 0.00, 0°)", self)
        row3.addWidget(self.lbl_pose)

        row3.addStretch(1)
        self.lbl_step = QLabel(f"Step: {self._choreo_step}", self)
        self.lbl_step.setStyleSheet("color: #fbbf24; font-weight: 600;")
        row3.addWidget(self.lbl_step)
        layout.addLayout(row3)

    def mousePressEvent(self, event) -> None:
        self.cardClicked.emit(self.alias)
        super().mousePressEvent(event)

    def update_telemetry(self, data: Dict[str, Any]) -> None:
        self._is_online = data.get("is_online", self._is_online)
        self.lbl_dot.setText("● 在线" if self._is_online else "○ 离线")
        self.lbl_dot.setStyleSheet("color: #10b981; font-weight: 700;" if self._is_online else "color: #64748b;")

        if "battery" in data:
            self._battery_pct = int(data["battery"])
            self.bat_bar.setValue(self._battery_pct)
            if self._battery_pct <= 20:
                self.bat_bar.setStyleSheet("""
                    QProgressBar { background: #450a0a; border: 1px solid #ef4444; border-radius: 3px; text-align: center; color: #fff; font-size: 9px; }
                    QProgressBar::chunk { background-color: #ef4444; border-radius: 2px; }
                """)
                self.btn_substitute.setVisible(True)
            else:
                self.bat_bar.setStyleSheet("""
                    QProgressBar { background: #0f172a; border: 1px solid #475569; border-radius: 3px; text-align: center; color: #fff; font-size: 9px; }
                    QProgressBar::chunk { background-color: #10b981; border-radius: 2px; }
                """)
                self.btn_substitute.setVisible(False)

        if "temperature" in data:
            self._temp_c = float(data["temperature"])
            self.lbl_temp.setText(f"🌡️ {self._temp_c:.1f}°C")

        if "authority" in data:
            self._authority = str(data["authority"]).upper()
            self.lbl_auth.setText(f"[{self._authority}]")

        if "pose" in data:
            x, y, th = data["pose"]
            self._pose = (x, y, th)
            self.lbl_pose.setText(f"📍 ({x:.2f}, {y:.2f}, {int(th)}°)")

        if "step" in data:
            self._choreo_step = int(data["step"])
            self.lbl_step.setText(f"Step: {self._choreo_step}")

