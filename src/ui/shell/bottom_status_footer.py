import logging
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)
from src.core.config_loader import config_loader

logger = logging.getLogger("BottomStatusFooter")


class BottomStatusFooter(QFrame):
    """
    Bottom preflight diagnostic footer displaying user credentials, license tier,
    scene context, initialization points, soundtrack status, network IP, and active robot counts.
    """

    initPointClicked = Signal()
    musicConfigClicked = Signal()
    robotOverviewClicked = Signal()
    notificationClicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._app_info = config_loader.get_app_info()
        self._init_ui()

    def _init_ui(self) -> None:
        self.setFixedHeight(30)
        self.setObjectName("bottomStatusFooter")
        self.setStyleSheet("""
            QFrame#bottomStatusFooter {
                background-color: #111318;
                border-top: 1px solid #232733;
            }
            QLabel { color: #94A3B8; font-size: 11px; }
            QPushButton.link-btn {
                background: transparent; border: none; color: #CBD5E1;
                font-size: 11px; padding: 2px 4px;
            }
            QPushButton.link-btn:hover { color: #38BDF8; }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(12)

        # 1. Left Cluster: Account, PRO Badge, Version, Scene, Init Point, Music
        self.lbl_user = QLabel("👤 admin", self)
        layout.addWidget(self.lbl_user)

        self.lbl_pro = QLabel("PRO", self)
        self.lbl_pro.setProperty("class", "badge-pro")
        self.lbl_pro.setStyleSheet("background: #D97706; color: #000; font-weight: 800; font-size: 9px; padding: 1px 4px; border-radius: 2px;")
        layout.addWidget(self.lbl_pro)

        ver = self._app_info.get("version", "v1.0.0")
        self.lbl_ver = QLabel(f"v{ver}" if not ver.startswith("v") else ver, self)
        layout.addWidget(self.lbl_ver)

        layout.addSpacing(6)

        self.lbl_scene_info = QLabel("场景: 默认演播大厅", self)
        layout.addWidget(self.lbl_scene_info)

        self.btn_init_point = QPushButton("📍 初始化点: 配置 1 ➕", self)
        self.btn_init_point.setProperty("class", "link-btn")
        self.btn_init_point.setCursor(Qt.PointingHandCursor)
        self.btn_init_point.clicked.connect(self.initPointClicked.emit)
        layout.addWidget(self.btn_init_point)

        self.btn_music = QPushButton("🎵 音乐: 未配置音乐", self)
        self.btn_music.setProperty("class", "link-btn")
        self.btn_music.setCursor(Qt.PointingHandCursor)
        self.btn_music.clicked.connect(self.musicConfigClicked.emit)
        layout.addWidget(self.btn_music)

        layout.addStretch(1)

        # 2. Right Cluster: Network Status Indicator, IP, Robot Count, Messages
        self.lbl_net_dot = QLabel("● 联网", self)
        self.lbl_net_dot.setStyleSheet("color: #10B981; font-weight: 700;")
        layout.addWidget(self.lbl_net_dot)

        self.lbl_ip = QLabel("IP: 172.18.0.1", self)
        layout.addWidget(self.lbl_ip)

        self.btn_robot_count = QPushButton("🤖 机器人: 0 台", self)
        self.btn_robot_count.setProperty("class", "link-btn")
        self.btn_robot_count.setCursor(Qt.PointingHandCursor)
        self.btn_robot_count.clicked.connect(self.robotOverviewClicked.emit)
        layout.addWidget(self.btn_robot_count)

        self.btn_notify = QPushButton("🔔 消息: 正常", self)
        self.btn_notify.setProperty("class", "link-btn")
        self.btn_notify.setCursor(Qt.PointingHandCursor)
        self.btn_notify.clicked.connect(self.notificationClicked.emit)
        layout.addWidget(self.btn_notify)

    def set_robot_count(self, count: int) -> None:
        self.btn_robot_count.setText(f"🤖 机器人 {count} 台")

    def set_emergency_alarm(self, is_alarm: bool = True) -> None:
        if is_alarm:
            self.btn_notify.setText("🔔 消息: 🚨 急停告警！")
            self.btn_notify.setStyleSheet("color: #EF4444; font-weight: 700;")
        else:
            self.btn_notify.setText("🔔 消息: 正常")
            self.btn_notify.setStyleSheet("color: #CBD5E1;")

    def set_music_title(self, title: str) -> None:
        clean = title.strip() if title else "未配置音乐"
        self.btn_music.setText(f"🎵 音乐: {clean}")

    def set_scene_name(self, name: str) -> None:
        self.lbl_scene_info.setText(f"场景: {name}")

    def set_network_status(self, is_online: bool, ip_address: str = "") -> None:
        if is_online:
            self.lbl_net_dot.setText("● 联网")
            self.lbl_net_dot.setStyleSheet("color: #10B981; font-weight: 700;")
        else:
            self.lbl_net_dot.setText("○ 离线")
            self.lbl_net_dot.setStyleSheet("color: #EF4444; font-weight: 700;")
        if ip_address:
            self.lbl_ip.setText(f"IP: {ip_address}")

