"""
导航地图多模式工作台 (NavMapWorkspace)
实现雷达建图、2D栅格地图、地图版本、分发下载与坐标标定 5 大模式及点云实时生成/标定
"""
import math
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from PySide6.QtCore import QPointF, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSlider,
    QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget
)

from src.domain.map.grid_projection_service import GridProjectionService
from src.infrastructure.map.pcd_parser_engine import PcdParserEngine


class NavMapCanvas(QWidget):
    """中央雷达点云与标定画布"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.scale, self.offset_x, self.offset_y = 20.0, 0.0, 0.0
        self.selected_robot: Optional[str] = None
        self.raw_points = np.zeros((0, 3), dtype=np.float32)
        self.calibrated_points = np.zeros((0, 3), dtype=np.float32)
        self.dx, self.dy, self.d_yaw = 0.0, 0.0, 0.0

    def set_robot(self, robot: Optional[str]) -> None:
        self.selected_robot = robot
        self.update()

    def set_points(self, points: np.ndarray) -> None:
        self.raw_points = points
        self.update_calibration(self.dx, self.dy, self.d_yaw)

    def update_calibration(self, dx: float, dy: float, d_yaw: float) -> None:
        self.dx, self.dy, self.d_yaw = dx, dy, d_yaw
        if len(self.raw_points) > 0:
            self.calibrated_points = GridProjectionService.apply_calibration(self.raw_points, dx, dy, d_yaw)
        else:
            self.calibrated_points = np.zeros((0, 3), dtype=np.float32)
        self.update()

    def world_to_screen(self, wx: float, wy: float) -> Tuple[float, float]:
        cx, cy = self.width() / 2.0 + self.offset_x, self.height() / 2.0 + self.offset_y
        return cx + wx * self.scale, cy - wy * self.scale

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("#090d16"))

        if not self.selected_robot:
            p.setPen(QPen(QColor("#475569"), 2))
            cx, cy = w / 2, h / 2
            p.drawEllipse(QPointF(cx, cy), 28, 28)
            p.drawLine(int(cx - 40), int(cy), int(cx + 40), int(cy))
            p.drawLine(int(cx), int(cy - 40), int(cx), int(cy + 40))
            p.setFont(QFont("Arial", 11))
            p.setPen(QColor("#94a3b8"))
            p.drawText(QRectF(0, cy + 40, w, 30), Qt.AlignCenter, "请在右侧选择机器人")
            return

        p.setPen(QPen(QColor("#1e293b"), 1))
        step = int(self.scale * 2)
        for x in range(0, w, step):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, step):
            p.drawLine(0, y, w, y)

        pts = self.calibrated_points if len(self.calibrated_points) > 0 else self.raw_points
        if len(pts) > 0:
            p.setPen(QPen(QColor(56, 189, 248, 160), 2))
            for pt in pts:
                sx, sy = self.world_to_screen(pt[0], pt[1])
                p.drawPoint(int(sx), int(sy))

        rx, ry = self.world_to_screen(0.0, 0.0)
        p.setBrush(QBrush(QColor("#ef4444")))
        p.setPen(QPen(Qt.white, 1.5))
        p.drawEllipse(QPointF(rx, ry), 5, 5)


class NavMapWorkspace(QWidget):
    """导航地图完整集成工作台"""

    mapSaved = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.is_mapping = False
        self.map_versions = [{"version": "MAP_DEFAULT_20261104", "points": 12000, "date": "2026-11-04 12:00"}]
        self._init_ui()
        self.map_timer = QTimer(self)
        self.map_timer.timeout.connect(self._on_map_tick)

    def _init_ui(self) -> None:
        main_lay = QHBoxLayout(self)
        main_lay.setContentsMargins(6, 6, 6, 6)
        splitter = QSplitter(Qt.Horizontal)

        # 1. 左侧功能树
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setFixedWidth(160)
        self.tree.setStyleSheet("QTreeWidget { background: #0c1017; border: 1px solid #1e293b; color: #cbd5e1; }")
        for gname, subs in [("生成", ["◎ 雷达建图", "▦ 2D 栅格地图"]), ("管理", ["📁 地图版本", "☍ 分发下载"]), ("对齐", ["⌖ 坐标标定"])]:
            grp = QTreeWidgetItem(self.tree, [gname])
            grp.setExpanded(True)
            for s in subs:
                QTreeWidgetItem(grp, [s])
        self.tree.itemClicked.connect(self._on_tree_select)
        splitter.addWidget(self.tree)

        # 2. 中央画布
        self.canvas = NavMapCanvas()
        splitter.addWidget(self.canvas)

        # 3. 右侧面板
        self.right_panel = QFrame()
        self.right_panel.setFixedWidth(230)
        self.right_panel.setStyleSheet("background: #0f172a; border: 1px solid #1e293b; border-radius: 6px; padding: 6px;")
        self._build_right_panel()
        splitter.addWidget(self.right_panel)

        splitter.setSizes([160, 700, 230])
        main_lay.addWidget(splitter)

    def _build_right_panel(self) -> None:
        vbox = QVBoxLayout(self.right_panel)
        vbox.setSpacing(8)
        lbl_t = QLabel("建图控制")
        lbl_t.setStyleSheet("font-weight: bold; color: #f8fafc; font-size: 13px;")
        vbox.addWidget(lbl_t)

        vbox.addWidget(QLabel("目标机器人:"))
        self.combo_robot = QComboBox()
        self.combo_robot.addItems(["-- 未选择 --", "Robot_1 (A)", "Robot_2 (B)"])
        self.combo_robot.currentIndexChanged.connect(self._on_robot_changed)
        vbox.addWidget(self.combo_robot)

        self.lbl_status = QLabel("建图状态: ● 未开始")
        self.lbl_status.setStyleSheet("color: #94a3b8;")
        vbox.addWidget(self.lbl_status)

        vbox.addWidget(QLabel("点云频率:"))
        self.combo_freq = QComboBox()
        self.combo_freq.addItems(["1 Hz", "2 Hz", "5 Hz"])
        self.combo_freq.setCurrentText("2 Hz")
        vbox.addWidget(self.combo_freq)

        self.btn_mapping = QPushButton("▷ 开始建图")
        self.btn_mapping.setStyleSheet("background: #0284c7; color: white; font-weight: bold; padding: 7px; border-radius: 4px;")
        self.btn_mapping.clicked.connect(self._toggle_mapping)
        vbox.addWidget(self.btn_mapping)

        self.frame_calib = QFrame()
        lay_c = QVBoxLayout(self.frame_calib)
        lay_c.setContentsMargins(0, 0, 0, 0)
        lay_c.setSpacing(4)
        for name, attr in [("ΔX 平移 (m):", "sl_dx"), ("ΔY 平移 (m):", "sl_dy"), ("Δθ 旋转 (°):", "sl_yaw")]:
            lay_c.addWidget(QLabel(name))
            sl = QSlider(Qt.Horizontal)
            sl.setRange(-180 if "θ" in name else -50, 180 if "θ" in name else 50)
            sl.setValue(0)
            sl.valueChanged.connect(self._on_calib_change)
            setattr(self, attr, sl)
            lay_c.addWidget(sl)
        self.frame_calib.hide()
        vbox.addWidget(self.frame_calib)
        vbox.addStretch()

    def _on_robot_changed(self, idx: int) -> None:
        if idx <= 0:
            self.canvas.set_robot(None)
        else:
            self.canvas.set_robot(self.combo_robot.currentText())
            self.canvas.set_points(PcdParserEngine.generate_default_point_cloud(num_points=3500))

    def _toggle_mapping(self) -> None:
        if not self.is_mapping:
            if self.combo_robot.currentIndex() <= 0:
                self.combo_robot.setCurrentIndex(1)
            self.is_mapping = True
            self.btn_mapping.setText("⏹ 停止并保存建图")
            self.btn_mapping.setStyleSheet("background: #dc2626; color: white; font-weight: bold; padding: 7px; border-radius: 4px;")
            self.lbl_status.setText("建图状态: ● 正在扫描采集 (2 Hz)")
            self.lbl_status.setStyleSheet("color: #22c55e;")
            self.map_timer.start(500)
        else:
            self.is_mapping = False
            self.map_timer.stop()
            self.btn_mapping.setText("▷ 开始建图")
            self.btn_mapping.setStyleSheet("background: #0284c7; color: white; font-weight: bold; padding: 7px; border-radius: 4px;")
            self.lbl_status.setText("建图状态: ● 已完成")
            self.lbl_status.setStyleSheet("color: #38bdf8;")
            ts = time.strftime("%Y%m%d_%H%M%S")
            vname = f"MAP_SCAN_{ts}"
            self.map_versions.append({"version": vname, "points": len(self.canvas.raw_points), "date": ts})
            self.mapSaved.emit(vname)

    def _on_map_tick(self) -> None:
        new_pts = np.random.uniform(-10.0, 2.0, (25, 3)).astype(np.float32)
        self.canvas.set_points(np.vstack((self.canvas.raw_points, new_pts)))

    def _on_tree_select(self, item: QTreeWidgetItem, col: int) -> None:
        text = item.text(0)
        self.frame_calib.setVisible("坐标标定" in text)
        if "2D" in text and len(self.canvas.raw_points) > 0:
            pts2d, _ = GridProjectionService.filter_and_project_2d(self.canvas.raw_points)
            self.canvas.set_points(np.column_stack((pts2d, np.zeros(len(pts2d), dtype=np.float32))))

    def _on_calib_change(self) -> None:
        dx = self.sl_dx.value() / 10.0
        dy = self.sl_dy.value() / 10.0
        yaw_rad = math.radians(self.sl_yaw.value())
        self.canvas.update_calibration(dx, dy, yaw_rad)
