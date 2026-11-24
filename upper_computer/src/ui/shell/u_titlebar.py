# @file: src/ui/shell/u_titlebar.py
# @brief: UniUni v3 32px top navigation header (uniswarm logo, 5 core workspace tabs, global Device/Scene/Help actions).
# @exports: PAGE_DEFS, UTitlebar

from __future__ import annotations

from typing import Dict, Optional, Tuple
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from src.ui.design_system.tokens import C_ACCENT, C_TEXT_1, H_HEADER
from src.ui.design_system.u_buttons import UButton

PAGE_DEFS: Tuple[Tuple[str, str], ...] = (
    ("choreography", "舞蹈编排"),
    ("formation", "队形规划"),
    ("mapping", "导航地图"),
    ("monitoring", "表演监测"),
    ("network", "系统设置"),
)


class UTitlebar(QFrame):
    """Exact 32px top shell bar mirroring UniUni design-system/LAYOUT.md §2."""

    pageSelected = Signal(str)
    deviceOverviewClicked = Signal()
    sceneMenuClicked = Signal()
    helpMenuClicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("UTitlebar")
        self.setFixedHeight(H_HEADER)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(6)

        brand = QLabel("uniswarm", self)
        brand.setStyleSheet(f"color: {C_ACCENT}; font-size: 14px; font-weight: 700; padding-right: 10px;")
        layout.addWidget(brand)

        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)
        self._tab_buttons: Dict[str, QPushButton] = {}
        for key, label in PAGE_DEFS:
            btn = QPushButton(label, self)
            btn.setProperty("uNavTab", True)
            btn.setCheckable(True)
            btn.setFixedHeight(H_HEADER)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumWidth(btn.sizeHint().width() + 8)
            btn.clicked.connect(lambda _c=False, k=key: self.pageSelected.emit(k))
            self._btn_group.addButton(btn)
            self._tab_buttons[key] = btn
            layout.addWidget(btn)

        layout.addStretch(1)

        self.btn_devices = UButton("设备总览", variant="default", size="xs", icon_name="robots", parent=self)
        self.btn_devices.clicked.connect(self.deviceOverviewClicked.emit)
        layout.addWidget(self.btn_devices)

        self.btn_scene = UButton("场景配置", variant="default", size="xs", icon_name="map", parent=self)
        self.btn_scene.clicked.connect(self.sceneMenuClicked.emit)
        layout.addWidget(self.btn_scene)

        self.btn_help = UButton("帮助", variant="ghost", size="xs", parent=self)
        self.btn_help.clicked.connect(self.helpMenuClicked.emit)
        layout.addWidget(self.btn_help)

        self.set_active_page("choreography")

    def set_active_page(self, page_key: str) -> None:
        btn = self._tab_buttons.get(page_key)
        if btn is not None:
            btn.setChecked(True)
        if self.sender() != btn:
            pass
        _ = C_TEXT_1
