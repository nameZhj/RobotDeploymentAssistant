import logging
from typing import Any, Optional
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger("MonitorMapPanel")


class AIDesignDialog(QDialog):
    """AI Choreo & Trajectory auto-generation modal dialog (ai_arrange workflow)."""

    planGenerated = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("✨ AI 预设计 - 智能编舞与轨迹排布")
        self.resize(420, 240)
        self.setStyleSheet("""
            QDialog { background-color: #171A21; color: #F1F5F9; }
            QLabel { color: #E2E8F0; font-size: 12px; font-weight: 600; }
            QLineEdit, QComboBox, QSpinBox { background-color: #232733; color: #FFF; border: 1px solid #334155; border-radius: 4px; padding: 5px; }
            QPushButton.primary-btn { background-color: #7C3AED; color: #FFF; border: none; border-radius: 4px; padding: 6px 14px; font-weight: 700; }
            QPushButton.primary-btn:hover { background-color: #6D28D9; }
            QPushButton.secondary-btn { background-color: #334155; color: #E2E8F0; border: none; border-radius: 4px; padding: 6px 14px; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        layout.addWidget(QLabel("自然语言编舞描述:"))
        self.edit_prompt = QLineEdit("6台机器人，2×3矩阵队形，一起跳功夫舞", self)
        layout.addWidget(self.edit_prompt)

        row = QHBoxLayout()
        row.addWidget(QLabel("队形模板:"))
        self.combo_formation = QComboBox(self)
        self.combo_formation.addItems(["2x3 矩阵队形", "一字水平列阵", "V字先锋队形", "圆形向心队形"])
        row.addWidget(self.combo_formation, 1)

        row.addWidget(QLabel("台数:"))
        self.spin_count = QSpinBox(self)
        self.spin_count.setRange(2, 16)
        self.spin_count.setValue(6)
        row.addWidget(self.spin_count)
        layout.addLayout(row)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_cancel = QPushButton("取消", self)
        btn_cancel.setProperty("class", "secondary-btn")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_submit = QPushButton("✨ 开始生成", self)
        btn_submit.setProperty("class", "primary-btn")
        btn_submit.clicked.connect(self._on_submit)
        btn_row.addWidget(btn_submit)
        layout.addLayout(btn_row)

    def _on_submit(self) -> None:
        self.planGenerated.emit({
            "prompt": self.edit_prompt.text().strip(),
            "formation": self.combo_formation.currentText(),
            "robot_count": self.spin_count.value(),
        })
        self.accept()


class MonitorMapPanel(QFrame):
    """Monitor page upper-left LiDAR stage map preview with floating toolbar and AI arrange popup."""

    aiDesignRequested = Signal(dict)
    collapsed = Signal()

    def __init__(self, parent: Optional[QWidget] = None, controller: Optional[Any] = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setMouseTracking(True)
        self.setStyleSheet("""
            QFrame { background-color: #0E121A; border: 1px solid #1E293B; border-radius: 6px; }
            QPushButton.map-tool-btn { background-color: rgba(23, 26, 33, 0.9); color: #CBD5E1; border: 1px solid #334155; border-radius: 4px; padding: 4px 8px; font-size: 11px; font-weight: 600; }
            QPushButton.map-tool-btn:hover { background-color: #263147; color: #FFF; }
            QPushButton.map-tool-btn:checked { background-color: #1E6FFF; color: #FFF; border-color: #3B82F6; }
            QPushButton.ai-design-btn { background-color: #7C3AED; color: #FFF; border: 1px solid #8B5CF6; border-radius: 4px; padding: 4px 10px; font-size: 11px; font-weight: 700; }
            QPushButton.ai-design-btn:hover { background-color: #6D28D9; }
        """)

        self._show_target_traj = True
        self._show_actual_traj = True
        self._show_ai_traj = True
        self._show_init_points = True
        self._scale, self._offset_x, self._offset_y = 22.0, 0.0, 0.0
        self._is_panning = False
        self._pan_start = QPointF()

        self._init_ui()

    def _init_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(6)

        btn_collapse = QPushButton("<", self)
        btn_collapse.setProperty("class", "map-tool-btn")
        btn_collapse.setFixedWidth(28)
        btn_collapse.clicked.connect(self.collapsed.emit)
        top_bar.addWidget(btn_collapse)

        self.btn_target = QPushButton("显示目标轨迹", self)
        self.btn_actual = QPushButton("显示轨迹", self)
        self.btn_ai = QPushButton("AI轨迹", self)
        self.btn_init = QPushButton("显示初始化点", self)

        for btn, attr in [(self.btn_target, "_show_target_traj"), (self.btn_actual, "_show_actual_traj"), (self.btn_ai, "_show_ai_traj")]:
            btn.setProperty("class", "map-tool-btn")
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.toggled.connect(lambda c, a=attr: self._set_flag(a, c))
            top_bar.addWidget(btn)

        btn_ai_design = QPushButton("✨ AI预设计", self)
        btn_ai_design.setProperty("class", "ai-design-btn")
        btn_ai_design.clicked.connect(self._open_ai_design_dialog)
        top_bar.addWidget(btn_ai_design)

        self.btn_init.setProperty("class", "map-tool-btn")
        self.btn_init.setCheckable(True)
        self.btn_init.setChecked(True)
        self.btn_init.toggled.connect(lambda c: self._set_flag("_show_init_points", c))
        top_bar.addWidget(self.btn_init)

        top_bar.addStretch(1)
        root_layout.addLayout(top_bar)
        root_layout.addStretch(1)

    def _set_flag(self, attr_name: str, val: bool) -> None:
        setattr(self, attr_name, val)
        self.update()

    def _open_ai_design_dialog(self) -> None:
        if self.controller:
            self.controller.generate_ai_formation()
        self.aiDesignRequested.emit({
            "prompt": "自动生成2机对称队形",
            "formation": "对称队形",
            "robot_count": 2,
        })
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() * 0.5 + self._offset_x, self.height() * 0.5 + self._offset_y

        p.setPen(QPen(QColor("#1E2430"), 1))
        step = int(self._scale)
        for x in range(int(cx % step), self.width(), step):
            p.drawLine(x, 42, x, self.height() - 4)
        for y in range(int(cy % step), self.height(), step):
            if y > 42:
                p.drawLine(4, y, self.width() - 4, y)

        p.setPen(QPen(QColor("#334155"), 2, Qt.DashLine))
        stage_w, stage_h = 14.0 * self._scale, 10.0 * self._scale
        p.drawRect(QRectF(cx - stage_w * 0.5, cy - stage_h * 0.5, stage_w, stage_h))

        if self._show_init_points:
            for sx, sy, lbl, col in [(-2.0, 0.0, "A", "#10B981"), (2.0, 0.0, "B", "#38BDF8")]:
                px, py = cx + sx * self._scale, cy - sy * self._scale
                p.setBrush(QBrush(QColor(col)))
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(px, py), 6, 6)
                p.setPen(QPen(QColor("#FFFFFF")))
                p.setFont(QFont("Segoe UI", 8, QFont.Bold))
                p.drawText(QPointF(px + 8, py + 4), lbl)

    def mousePressEvent(self, event) -> None:
        if event.button() in (Qt.LeftButton, Qt.MidButton):
            self._is_panning = True
            self._pan_start = event.pos()

    def mouseMoveEvent(self, event) -> None:
        if self._is_panning:
            delta = event.pos() - self._pan_start
            self._offset_x += delta.x()
            self._offset_y += delta.y()
            self._pan_start = event.pos()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        self._is_panning = False

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 0.85
        self._scale = max(10.0, min(80.0, self._scale * factor))
        self.update()
