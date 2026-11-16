# @file: src/ui/shell/u_statusbar.py
# @brief: UniUni v3 28px bottom status bar displaying version, scene, init points, music, timecode, IP, and alerts.
# @exports: UStatusBar

from __future__ import annotations

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


class UStatusBar(QFrame):
    """Exact 28px bottom global status bar mirroring UniUni LAYOUT.md §2."""

    initPointsClicked = Signal()
    musicClicked = Signal()

    def __init__(self, version: str = "3.2.0", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("UStatusBar")
        self.setFixedHeight(H_STATUS)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(12)

        self.lbl_version = self._meta_label(f"v{version}")
        self.lbl_scene = self._meta_label("场景: 默认舞台")
        self.btn_init = self._link_button("初始化点: 默认开场站位", self.initPointsClicked.emit)
        self.btn_music = self._link_button("音乐: 未加载", self.musicClicked.emit)
        self.lbl_timecode = QLabel("00:00.00 / 00:30.00", self)
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
            self.btn_music,
            self._sep(),
            self.lbl_timecode,
        ):
            layout.addWidget(widget)

        layout.addStretch(1)

        self.lbl_net = QLabel("● 就绪", self)
        self.lbl_net.setStyleSheet(f"color: {C_OK}; font-size: 11px;")
        self.lbl_ip = self._meta_label("IP: 127.0.0.1")
        self.lbl_robots = self._meta_label("机器人: 4 轨道")
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

    def set_timecode(self, current_s: float, total_s: float) -> None:
        self.lbl_timecode.setText(f"{self._fmt(current_s)} / {self._fmt(total_s)}")

    def set_scene_summary(
        self, scene_name: str, track_count: int, music_name: str = "", init_label: str = ""
    ) -> None:
        self.lbl_scene.setText(f"场景: {scene_name}")
        self.lbl_robots.setText(f"机器人: {track_count} 轨道")
        self.btn_music.setText(f"音乐: {music_name or '未加载'}")
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
