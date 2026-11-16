# @file: src/ui/design_system/u_dialog.py
# @brief: Floating-surface UDialog, push UDrawer, and translucent UFloatBar canvas overlay components.
# @exports: UDialog, UDrawer, UFloatBar

from __future__ import annotations

from typing import Optional
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from src.ui.design_system.tokens import (
    C_CARD,
    C_FLOAT,
    C_FLOAT_EDGE,
    C_PANEL,
    C_TEXT_1,
    H_BTN,
    LINE,
    R_CARD,
)
from src.ui.design_system.u_buttons import UButton


class UDialog(QDialog):
    """Consistent floating modal dialog with #0e0f12 surface and [Cancel / Confirm] footer."""

    def __init__(
        self,
        title: str,
        width: int = 460,
        height: int = 340,
        confirm_text: str = "确定",
        cancel_text: str = "取消",
        show_footer: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("uDialog", True)
        self.setWindowTitle(title)
        self.resize(width, height)
        self.setModal(True)
        self.setStyleSheet(f"QDialog {{ background-color: {C_FLOAT}; border: 1px solid {C_FLOAT_EDGE}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        head = QFrame(self)
        head.setFixedHeight(40)
        head.setStyleSheet(f"background: {C_CARD}; border-bottom: 1px solid {LINE};")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(14, 0, 12, 0)
        self.header_title = QLabel(title, head)
        self.header_title.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {C_TEXT_1};")
        hl.addWidget(self.header_title)
        hl.addStretch(1)
        root.addWidget(head)

        self.body_widget = QWidget(self)
        self.body_layout = QVBoxLayout(self.body_widget)
        self.body_layout.setContentsMargins(16, 14, 16, 14)
        self.body_layout.setSpacing(10)
        root.addWidget(self.body_widget, 1)

        self.cancel_btn: Optional[UButton] = None
        self.confirm_btn: Optional[UButton] = None
        if show_footer:
            foot = QFrame(self)
            foot.setFixedHeight(50)
            foot.setStyleSheet(f"background: {C_PANEL}; border-top: 1px solid {LINE};")
            fl = QHBoxLayout(foot)
            fl.setContentsMargins(14, 0, 14, 0)
            fl.setSpacing(8)
            fl.addStretch(1)
            if cancel_text:
                self.cancel_btn = UButton(cancel_text, variant="default", size="sm", parent=foot)
                self.cancel_btn.setFixedHeight(H_BTN)
                self.cancel_btn.clicked.connect(self.reject)
                fl.addWidget(self.cancel_btn)
            if confirm_text:
                self.confirm_btn = UButton(confirm_text, variant="primary", size="sm", parent=foot)
                self.confirm_btn.setFixedHeight(H_BTN)
                self.confirm_btn.clicked.connect(self.accept)
                fl.addWidget(self.confirm_btn)
            root.addWidget(foot)


class UDrawer(QFrame):
    """Collapsible right-side push drawer for AI / batch choreography tools."""

    def __init__(self, title: str, width: int = 300, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(width)
        self.setStyleSheet(f"UDrawer {{ background: {C_PANEL}; border-left: 1px solid {LINE}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        head = QFrame(self)
        head.setFixedHeight(34)
        head.setStyleSheet(f"background: {C_CARD}; border-bottom: 1px solid {LINE};")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(10, 0, 8, 0)
        lbl = QLabel(title, head)
        lbl.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {C_TEXT_1};")
        hl.addWidget(lbl)
        hl.addStretch(1)
        root.addWidget(head)

        self.body_widget = QWidget(self)
        self.body_layout = QVBoxLayout(self.body_widget)
        self.body_layout.setContentsMargins(10, 10, 10, 10)
        self.body_layout.setSpacing(8)
        root.addWidget(self.body_widget, 1)


class UFloatBar(QFrame):
    """Translucent floating pill bar anchored inside 2D/3D stage viewports."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"UFloatBar {{ background: rgba(14, 15, 18, 0.88); "
            f"border: 1px solid {C_FLOAT_EDGE}; border-radius: {R_CARD}px; }}"
        )
        self.bar_layout = QHBoxLayout(self)
        self.bar_layout.setContentsMargins(8, 4, 8, 4)
        self.bar_layout.setSpacing(6)
