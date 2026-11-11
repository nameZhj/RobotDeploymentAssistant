import logging
from typing import List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import QPushButton, QWidget
from src.core.config_loader import config_loader
from src.core.event_bus import event_bus
from src.domain.arbitration.control_arbiter import control_arbiter
from src.infrastructure.serial.lora_serial_port import lora_port

logger = logging.getLogger("SwarmEmergencyBrake")


class SwarmEmergencyBrake(QWidget):
    """
    High-visibility emergency stop widget for swarm fleet.
    Triggers immediate broadcast STOP, interrupts CHOREO/MANUAL leases, and resets velocities.
    Binds global Space and Escape shortcuts.
    """

    emergencyTriggered = Signal(list)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._target_delim = config_loader.get_target_delimiter()
        self._targets: List[str] = ["A", "B", "C"]
        self._is_active = False

        self._init_ui()
        self._bind_shortcuts()

    def set_controlled_targets(self, targets: List[str]) -> None:
        """Update active fleet targets for brake expansion."""
        self._targets = [t.strip().upper() for t in targets if t.strip()]

    def _init_ui(self) -> None:
        self.btn_brake = QPushButton("🛑 全员急停 (ESC/SPACE)", self)
        self.btn_brake.setCursor(Qt.PointingHandCursor)
        self.btn_brake.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #dc2626, stop:1 #991b1b);
                color: #ffffff;
                font-weight: 800;
                font-size: 13px;
                padding: 8px 18px;
                border-radius: 6px;
                border: 1px solid #ef4444;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ef4444, stop:1 #b91c1c);
                border: 1px solid #f87171;
            }
            QPushButton:pressed {
                background: #7f1d1d;
                border: 1px solid #450a0a;
            }
        """)
        self.btn_brake.clicked.connect(self.trigger_brake)

    def _bind_shortcuts(self) -> None:
        """Bind Space and Escape as global emergency trigger shortcuts."""
        self._shortcut_esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self._shortcut_esc.activated.connect(self.trigger_brake)

        self._shortcut_space = QShortcut(QKeySequence(Qt.Key_Space), self)
        self._shortcut_space.activated.connect(self.trigger_brake)

    def trigger_brake(self) -> None:
        """Dispatches STOP command to all controlled targets and revokes authority."""
        logger.warning(f"SwarmEmergencyBrake activated! Interrupting {self._targets}...")
        targets = self._targets if self._targets else ["ALL"]

        for target in targets:
            cmd = f"{target}{self._target_delim}STOP"
            lora_port.send_raw(cmd, src_id="CTRL", dst_id=target)
            control_arbiter.handle_stop(target)

        self._is_active = True
        self.btn_brake.setText("⚠️ 急停已锁定 (点击复位)")
        self.btn_brake.setStyleSheet("""
            QPushButton {
                background: #450a0a;
                color: #fca5a5;
                font-weight: 800;
                font-size: 13px;
                padding: 8px 18px;
                border-radius: 6px;
                border: 2px solid #ef4444;
            }
        """)

        event_bus.publish("SWARM_EMERGENCY_STOP_TRIGGERED", {"targets": targets})
        self.emergencyTriggered.emit(targets)

    def reset_brake(self) -> None:
        """Clear emergency latch state."""
        self._is_active = False
        self.btn_brake.setText("🛑 全员急停 (ESC/SPACE)")
        self.btn_brake.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #dc2626, stop:1 #991b1b);
                color: #ffffff;
                font-weight: 800;
                font-size: 13px;
                padding: 8px 18px;
                border-radius: 6px;
                border: 1px solid #ef4444;
            }
        """)

