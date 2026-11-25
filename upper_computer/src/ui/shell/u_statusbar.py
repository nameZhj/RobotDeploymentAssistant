# @file: src/ui/shell/u_statusbar.py
# @brief: desktop v3 28px bottom status bar displaying version, scene, init points, task status, local LAN IP, and alerts.
# @exports: UStatusBar

from __future__ import annotations

import socket
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from src.ui.design_system.tokens import (
    C_ACCENT_BRIGHT,
    C_OK,
    C_TEXT_2,
    C_TEXT_3,
    C_WARN,
    FONT_MONO,
    H_STATUS,
    LINE,
)


def _detect_local_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.168.1.1", 80))
            ip = s.getsockname()[0]
            if ip:
                return ip
    except OSError:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


class UStatusBar(QFrame):
    """Exact 28px bottom global status bar mirroring stage LAYOUT.md §2."""

    initPointsClicked = Signal()

    def __init__(self, version: str = "3.2.0", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("UStatusBar")
        self.setFixedHeight(H_STATUS)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(12)

        self.lbl_version = self._meta_label(f"v{version}")
        self.lbl_scene = self._meta_label("场景: 默认舞台")
        self.btn_init = self._link_button("初始化点: 未添加机器人", self.initPointsClicked.emit)
        self.lbl_timecode = QLabel("任务链: 原点待命", self)
        self.lbl_timecode.setStyleSheet(
            f"font-family: {FONT_MONO}; font-size: 11px; color: {C_ACCENT_BRIGHT}; font-weight: 600;"
        )

        for widget in (
            self.lbl_version,
            self._sep(),
            self.lbl_scene,
            self._sep(),
            self.btn_init,
            self._sep(),
            self.lbl_timecode,
        ):
            layout.addWidget(widget)

        layout.addStretch(1)

        self.lbl_net = QLabel("● Wi-Fi HTTP", self)
        self.lbl_net.setStyleSheet(f"color: {C_OK}; font-size: 11px;")
        self.lbl_ip = self._meta_label(f"本机 IP: {_detect_local_lan_ip()}")
        self.lbl_robots = self._meta_label("机器人: 0 轨道")
        self.lbl_notice = QLabel("系统就绪", self)
        self.lbl_notice.setStyleSheet(f"color: {C_TEXT_2}; font-size: 11px;")

        for widget in (
            self.lbl_net,
            self._sep(),
            self.lbl_ip,
            self._sep(),
            self.lbl_robots,
            self._sep(),
            self.lbl_notice,
        ):
            layout.addWidget(widget)

    def _meta_label(self, text: str) -> QLabel:
        lbl = QLabel(text, self)
        lbl.setStyleSheet(f"color: {C_TEXT_2}; font-size: 11px;")
        return lbl

    def _link_button(self, text: str, slot: object) -> QPushButton:
        btn = QPushButton(text, self)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; color: {C_ACCENT_BRIGHT}; "
            f"font-size: 11px; padding: 0 2px; }} QPushButton:hover {{ text-decoration: underline; }}"
        )
        btn.clicked.connect(slot)  # type: ignore[arg-type]
        return btn

    def _sep(self) -> QFrame:
        line = QFrame(self)
        line.setFixedSize(1, 14)
        line.setStyleSheet(f"background: {LINE};")
        return line

    def set_timecode(self, current_s: float, total_s: float, chain_label: str = "") -> None:
        if chain_label:
            self.lbl_timecode.setText(f"任务链: {chain_label}")
        elif current_s <= 1e-6:
            self.lbl_timecode.setText("任务链: 原点待命")
        else:
            pct = int(min(100.0, max(0.0, (current_s / max(0.5, total_s)) * 100.0)))
            self.lbl_timecode.setText(f"任务链执行中 ({pct}%)")

    def set_scene_summary(
        self, scene_name: str, track_count: int, music_name: str = "", init_label: str = ""
    ) -> None:
        _ = music_name
        self.lbl_scene.setText(f"场景: {scene_name}")
        self.lbl_robots.setText(f"机器人: {track_count} 轨道")
        if init_label:
            self.btn_init.setText(f"初始化点: {init_label}")
        elif track_count == 0:
            self.btn_init.setText("初始化点: 未添加机器人")
        else:
            self.btn_init.setText(f"初始化点: {track_count} 机已就绪")

    def set_notification(self, text: str, tone: str = "info") -> None:
        color = C_WARN if tone == "warn" else (C_OK if tone == "ok" else C_TEXT_3)
        if tone == "info":
            color = C_TEXT_2
        self.lbl_notice.setStyleSheet(f"color: {color}; font-size: 11px;")
        self.lbl_notice.setText(text[:48])

    @staticmethod
    def _fmt(sec: float) -> str:
        safe = max(0.0, float(sec))
        m = int(safe // 60)
        s = safe - m * 60
        return f"{m:02d}:{s:05.2f}"
