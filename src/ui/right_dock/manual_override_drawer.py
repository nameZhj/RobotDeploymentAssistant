import logging
from typing import Optional
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from src.application.services.direct_motion_svc import direct_motion_svc
from src.application.services.fleet_onboarding_svc import fleet_onboarding_svc
from src.core.config_loader import config_loader
from src.infrastructure.serial.lora_serial_port import lora_port

logger = logging.getLogger("ManualOverrideDrawer")


class ManualOverrideDrawer(QFrame):
    """
    Collapsible manual override & deployment drawer for a selected target robot.
    Encapsulates SETUP 8-step progress, DEPLOY, basic jog/posture commands,
    and admin-whitelist protected legacy/compatibility commands.
    """

    commandDispatched = Signal(str, str)
    setupProgressChanged = Signal(int, int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.target: str = "A"
        self._setup_step: int = 0
        self._setup_timer = QTimer(self)
        self._setup_timer.timeout.connect(self._on_setup_tick)
        self._target_delim = config_loader.get_target_delimiter()
        self._init_ui()

    def set_target(self, target_alias: str) -> None:
        self.target = target_alias.strip().upper()
        self.lbl_target.setText(f"🎮 手动控制抽屉 - 目标: {self.target}")

    def _init_ui(self) -> None:
        self.setStyleSheet("""
            QFrame { background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; }
            QPushButton {
                background-color: #1e293b; color: #f1f5f9; border: 1px solid #475569;
                border-radius: 4px; padding: 5px 8px; font-size: 11px; font-weight: 600;
            }
            QPushButton:hover { background-color: #334155; color: #38bdf8; }
            QPushButton.primary { background-color: #0284c7; border-color: #38bdf8; }
            QPushButton.primary:hover { background-color: #0369a1; }
            QPushButton.warn { background-color: #b45309; border-color: #f59e0b; }
            QPushButton.warn:hover { background-color: #92400e; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.lbl_target = QLabel(f"🎮 手动控制抽屉 - 目标: {self.target}", self)
        self.lbl_target.setStyleSheet("font-weight: 700; color: #38bdf8; font-size: 12px;")
        layout.addWidget(self.lbl_target)

        sec1_layout = QHBoxLayout()
        self.btn_setup = QPushButton("⚡ 执行 SETUP", self)
        self.btn_setup.clicked.connect(self._start_setup_sequence)
        sec1_layout.addWidget(self.btn_setup)

        self.btn_deploy = QPushButton("🚀 部署 DEPLOY", self)
        self.btn_deploy.setProperty("class", "primary")
        self.btn_deploy.clicked.connect(self._trigger_deploy)
        sec1_layout.addWidget(self.btn_deploy)
        layout.addLayout(sec1_layout)

        self.setup_bar = QProgressBar(self)
        self.setup_bar.setRange(0, 8)
        self.setup_bar.setValue(0)
        self.setup_bar.setFixedHeight(12)
        self.setup_bar.setTextVisible(True)
        self.setup_bar.setFormat("自检进度: %v/8 步")
        self.setup_bar.setStyleSheet("""
            QProgressBar { background: #1e293b; border-radius: 3px; text-align: center; color: #ffffff; font-size: 9px; }
            QProgressBar::chunk { background-color: #0ea5e9; }
        """)
        layout.addWidget(self.setup_bar)

        grid = QGridLayout()
        grid.setSpacing(4)
        motions = [
            ("🚶 STAND", "STAND"), ("⚡ GAIT", "GAIT"),
            ("🛑 PASSIVE", "PASSIVE"), ("💃 DANCE", "DANCE"),
            ("⬆️ MOVE_F", "FORWARD"), ("🔓 RELEASE", "RELEASE")
        ]
        for idx, (label, cmd) in enumerate(motions):
            btn = QPushButton(label, self)
            btn.clicked.connect(lambda _, c=cmd: self._send_motion(c))
            if cmd == "RELEASE":
                btn.setProperty("class", "warn")
            grid.addWidget(btn, idx // 2, idx % 2)
        layout.addLayout(grid)

        self.chk_admin = QCheckBox("🛡️ 解锁管理员兼容扩展指令 (需白名单)", self)
        self.chk_admin.setStyleSheet("color: #94a3b8; font-size: 10px;")
        self.chk_admin.toggled.connect(self._toggle_admin_panel)
        layout.addWidget(self.chk_admin)

        self.admin_panel = QFrame(self)
        self.admin_panel.setVisible(False)
        self.admin_panel.setStyleSheet("background-color: #1a1a2e; border: 1px dashed #64748b; padding: 4px;")
        admin_layout = QGridLayout(self.admin_panel)
        admin_layout.setSpacing(4)

        legacy_cmds = ["GROUP1", "GROUP2", "GROUP3", "OPENING", "BUTTON", "MASK"]
        for idx, l_cmd in enumerate(legacy_cmds):
            btn_l = QPushButton(l_cmd, self.admin_panel)
            btn_l.setStyleSheet("font-size: 10px; padding: 3px;")
            btn_l.clicked.connect(lambda _, c=l_cmd: self._send_legacy(c))
            admin_layout.addWidget(btn_l, idx // 3, idx % 3)
        layout.addWidget(self.admin_panel)

    def _start_setup_sequence(self) -> None:
        self._setup_step = 0
        self.setup_bar.setValue(0)
        self.btn_setup.setEnabled(False)
        self._setup_timer.start(120)

    def _on_setup_tick(self) -> None:
        self._setup_step += 1
        self.setup_bar.setValue(self._setup_step)
        self.setupProgressChanged.emit(self._setup_step, 8)
        if self._setup_step >= 8:
            self._setup_timer.stop()
            self.btn_setup.setEnabled(True)
            fleet_onboarding_svc.send_setup(self.target, "601")
            self.commandDispatched.emit(self.target, "SETUP,601")

    def _trigger_deploy(self) -> None:
        lora_port.send_raw(f"{self.target}{self._target_delim}DEPLOY", src_id="CTRL", dst_id=self.target)
        self.commandDispatched.emit(self.target, "DEPLOY")

    def _send_motion(self, cmd_key: str) -> None:
        if cmd_key == "FORWARD":
            direct_motion_svc.send_continuous_move(self.target, forward=0.5, left=0.0, turn=0.0, duration_s=0.5)
        elif cmd_key == "DANCE":
            direct_motion_svc.execute_dance(self.target, "KUNGFU")
        else:
            direct_motion_svc.send_basic_command(self.target, cmd_key)
        self.commandDispatched.emit(self.target, cmd_key)

    def _toggle_admin_panel(self, enabled: bool) -> None:
        self.admin_panel.setVisible(enabled)

    def _send_legacy(self, legacy_cmd: str) -> None:
        raw_cmd = f"{self.target}{self._target_delim}{legacy_cmd}"
        lora_port.send_raw(raw_cmd, src_id="CTRL", dst_id=self.target)
        self.commandDispatched.emit(self.target, legacy_cmd)

