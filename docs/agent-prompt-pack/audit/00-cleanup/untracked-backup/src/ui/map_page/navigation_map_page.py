"""
@file: src/ui/map_page/navigation_map_page.py
@brief: 1:1 导航地图工作台（雷达建图、2D栅格、地图版本、分发及坐标标定微调保存）
@exports: NavigationMapPage
"""
import math
import os
from typing import Any, List, Optional, Tuple
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QSlider, QVBoxLayout, QWidget
)
from src.domain.map.grid_and_calibration import MapGridProcessor
from src.infrastructure.storage.studio_repository import StudioRepository


class NavigationMapPage(QWidget):
    """1:1 导航地图工作台：雷达建图、2D栅格、版本管理与坐标标定"""
    mappingToggled = Signal(bool, str, int)

    def __init__(self, parent: Optional[QWidget] = None, controller: Optional[Any] = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.repo = StudioRepository()
        self.grid_proc = MapGridProcessor()
        self.feature = "RADAR_MAPPING"
        self.selected_robot: Optional[str] = None
        self.is_mapping, self.freq_hz, self.scan_ang = False, 2, 0.0
        self.pts: List[Tuple[float, float]] = []
        self.calib = [0.0, 0.0, 0.0]  # dx, dy, dyaw_deg

        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._on_scan_tick)
        self._init_ui()

    def _init_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        root.addWidget(self._create_left_dock())

        self.viewport = QFrame(self)
        self.viewport.paintEvent = self._paint_viewport
        root.addWidget(self.viewport, 1)

        root.addWidget(self._create_right_panel())

    def _create_left_dock(self) -> QFrame:
        dock = QFrame(self)
        dock.setFixedWidth(175)
        layout = QVBoxLayout(dock)
        layout.setContentsMargins(4, 6, 4, 6)
        layout.setSpacing(2)
        lbl = QLabel("地图功能")
        lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #fff;")
        layout.addWidget(lbl)

        self.nav_grp = QButtonGroup(self)
        groups = [("生成", [("◎ 雷达建图", "RADAR_MAPPING"), ("▦ 2D 栅格地图", "GRID_MAP")]),
                  ("管理", [("📁 地图版本", "MAP_VERSIONS"), ("☍ 分发下载", "DISTRIBUTE")]),
                  ("对齐", [("⌖ 坐标标定", "CALIBRATION")])]
        for g_title, items in groups:
            h = QLabel(g_title)
            h.setStyleSheet("color: #64748b; font-size: 11px; font-weight: bold; padding-top: 4px;")
            layout.addWidget(h)
            for title, code in items:
                b = QPushButton(title)
                b.setCheckable(True)
                b.setChecked(code == "RADAR_MAPPING")
                b.clicked.connect(lambda _, c=code: self._on_feature_changed(c))
                self.nav_grp.addButton(b)
                layout.addWidget(b)
        layout.addStretch()
        return dock

    def _create_right_panel(self) -> QFrame:
        p = QFrame(self)
        p.setFixedWidth(260)
        v = QVBoxLayout(p)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)
        v.addWidget(QLabel("目标机器人:"))
        self.combo_robot = QComboBox()
        self.combo_robot.addItems(["-- 请在右侧选择机器人 --", "Robot_1 (A)", "Robot_2 (B)"])
        self.combo_robot.currentIndexChanged.connect(self._on_robot_changed)
        v.addWidget(self.combo_robot)

        self.lbl_status = QLabel("建图状态: ● 未开始")
        v.addWidget(self.lbl_status)
        v.addWidget(QLabel("点云频率:"))
        self.combo_freq = QComboBox()
        self.combo_freq.addItems(["1 Hz", "2 Hz", "3 Hz", "4 Hz", "5 Hz"])
        self.combo_freq.setCurrentIndex(1)
        self.combo_freq.currentIndexChanged.connect(lambda i: setattr(self, "freq_hz", i + 1))
        v.addWidget(self.combo_freq)

        self.frame_calib = self._create_calib_box()
        v.addWidget(self.frame_calib)
        v.addStretch()

        self.btn_mapping = QPushButton("[▷ 开始建图]")
        self.btn_mapping.setStyleSheet("background-color: #1976d2; color: white; font-weight: bold; min-height: 32px;")
        self.btn_mapping.clicked.connect(self._toggle_mapping)
        v.addWidget(self.btn_mapping)
        return p

    def _create_calib_box(self) -> QFrame:
        box = QFrame()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(4)
        self.spins = []
        for name in ["ΔX 平移 (m):", "ΔY 平移 (m):", "ΔYaw 旋转 (°):"]:
            lay.addWidget(QLabel(name))
            sb = QDoubleSpinBox()
            sb.setRange(-50.0, 50.0 if "平移" in name else 180.0)
            if "旋转" in name:
                sb.setMinimum(-180.0)
            sb.valueChanged.connect(self._on_calib_changed)
            lay.addWidget(sb)
            self.spins.append(sb)

        btn_save = QPushButton("保存坐标标定到地图")
        btn_save.clicked.connect(self._save_calibration)
        lay.addWidget(btn_save)
        box.hide()
        return box

    def _on_feature_changed(self, code: str) -> None:
        self.feature = code
        self.frame_calib.setVisible(code == "CALIBRATION")
        self.viewport.update()

    def _on_robot_changed(self, idx: int) -> None:
        self.selected_robot = self.combo_robot.currentText() if idx > 0 else None
        if self.selected_robot and not self.pts:
            for i in range(120):
                ang = math.radians(i * 3.0)
                r = 3.5 + 0.8 * math.sin(ang * 4.0)
                self.pts.append((r * math.cos(ang), r * math.sin(ang)))
        self.viewport.update()

    def _toggle_mapping(self) -> None:
        if not self.selected_robot:
            if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
                QMessageBox.warning(self, "未选择机器人", "请先在下拉列表中选择目标机器人！")
            return
        self.is_mapping = not self.is_mapping
        if self.is_mapping:
            self.lbl_status.setText(f"建图状态: ● 建图中 ({self.freq_hz} Hz)")
            self.lbl_status.setStyleSheet("color: #10b981; font-weight: bold;")
            self.btn_mapping.setText("[⏹ 停止建图]")
            self.btn_mapping.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold; min-height: 32px;")
            self.timer.start()
        else:
            self.lbl_status.setText("建图状态: ● 未开始")
            self.lbl_status.setStyleSheet("color: #94a3b8;")
            self.btn_mapping.setText("[▷ 开始建图]")
            self.btn_mapping.setStyleSheet("background-color: #1976d2; color: white; font-weight: bold; min-height: 32px;")
            self.timer.stop()
        self.mappingToggled.emit(self.is_mapping, self.selected_robot, self.freq_hz)
        self.viewport.update()

    def _on_scan_tick(self) -> None:
        self.scan_ang = (self.scan_ang + 15.0) % 360.0
        rad = math.radians(self.scan_ang)
        r = 1.0 + (len(self.pts) % 60) * 0.05
        self.pts.append((r * math.cos(rad), r * math.sin(rad)))
        self.viewport.update()

    def _on_calib_changed(self) -> None:
        self.calib = [sb.value() for sb in self.spins]
        self.viewport.update()

    def _save_calibration(self) -> None:
        dx, dy, dyaw = self.calib
        self.repo.update_map_calibration("map_default", dx, dy, dyaw)
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            QMessageBox.information(self, "标定保存", f"已保存地图标定偏移: dx={dx:.2f}, dy={dy:.2f}, yaw={dyaw:.1f}°")

    def _paint_viewport(self, _) -> None:
        p = QPainter(self.viewport)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.viewport.width(), self.viewport.height()
        cx, cy = w * 0.5, h * 0.5
        p.fillRect(0, 0, w, h, QColor("#090d16"))

        p.setPen(QPen(QColor("#151c2c"), 1))
        for x in range(0, w, 28):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, 28):
            p.drawLine(0, y, w, y)

        if not self.selected_robot:
            p.setPen(QPen(QColor("#334155"), 2))
            p.drawEllipse(QPointF(cx, cy - 20), 30, 30)
            p.drawLine(QPointF(cx - 40, cy - 20), QPointF(cx + 40, cy - 20))
            p.drawLine(QPointF(cx, cy - 60), QPointF(cx, cy + 20))
            p.setPen(QPen(QColor("#94a3b8")))
            p.setFont(QFont("Segoe UI", 12, QFont.Bold))
            p.drawText(QRectF(0, cy + 24, w, 36), Qt.AlignCenter, "请在右侧选择机器人")
            return

        rad = math.radians(self.calib[2])
        cos_y, sin_y = math.cos(rad), math.sin(rad)
        p.setPen(QPen(QColor(56, 189, 248, 160), 2))
        for px, py in self.pts:
            rx = px * cos_y - py * sin_y + self.calib[0]
            ry = px * sin_y + py * cos_y + self.calib[1]
            p.drawPoint(int(cx + rx * 35.0), int(cy - ry * 35.0))

        p.setBrush(QBrush(QColor("#10b981" if self.is_mapping else "#38bdf8")))
        p.setPen(QPen(Qt.white, 1.5))
        p.drawEllipse(QPointF(cx, cy), 8, 8)

        if self.is_mapping:
            s_rad = math.radians(self.scan_ang)
            p.setPen(QPen(QColor(16, 185, 129, 140), 2))
            p.drawLine(QPointF(cx, cy), QPointF(cx + 160 * math.cos(s_rad), cy + 160 * math.sin(s_rad)))

        p.setBrush(QBrush(QColor("#1e2430")))
        p.setPen(QPen(QColor("#10b981"), 1))
        p.drawRoundedRect(QRectF(14, 14, 210, 26), 4, 4)
        p.setPen(QPen(QColor("#10b981")))
        p.setFont(QFont("Segoe UI", 9, QFont.Bold))
        p.drawText(QRectF(14, 14, 210, 26), Qt.AlignCenter, f"● {self.feature} · {self.combo_freq.currentText()}")
