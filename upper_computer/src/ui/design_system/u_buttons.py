# @file: src/ui/design_system/u_buttons.py
# @brief: Unified UButton, UIconButton, USegmented, and UBadge controls guaranteeing zero text truncation.
# @exports: UButton, UIconButton, USegmented, UBadge

from __future__ import annotations

from typing import List, Optional, Sequence
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from src.ui.design_system.svg_icons import render_svg_icon
from src.ui.design_system.tokens import (
    C_ACCENT,
    C_ACCENT_DIM,
    C_CONTROL,
    C_CONTROL_HOVER,
    C_DANGER,
    C_DANGER_DIM,
    C_OK,
    C_OK_DIM,
    C_TEXT_1,
    C_TEXT_2,
    C_WARN,
    C_WARN_DIM,
    H_BTN,
    H_BTN_SM,
    H_BTN_XS,
    LINE,
    R_BTN,
)

_SIZE_HEIGHTS = {"md": H_BTN, "sm": H_BTN_SM, "xs": H_BTN_XS}


class UButton(QPushButton):
    """Standard button constrained never to shrink below its full label sizeHint."""

    def __init__(
        self,
        text: str = "",
        variant: str = "default",
        size: str = "sm",
        icon_name: Optional[str] = None,
        tooltip: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(text, parent)
        self.setProperty("uBtn", True)
        self.setProperty("variant", variant)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        height = _SIZE_HEIGHTS.get(size, H_BTN_SM)
        self.setFixedHeight(height)
        if icon_name:
            icon_color = "#ffffff" if variant == "primary" else (C_DANGER if variant == "danger" else C_TEXT_1)
            self.setIcon(render_svg_icon(icon_name, color=icon_color, size=14))
            self.setIconSize(QSize(14, 14))
        self.setToolTip(tooltip or text)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        # Prevent text truncation by locking minimum width to intrinsic content width
        self.setMinimumWidth(max(height, self.sizeHint().width() + 4))


class UIconButton(QPushButton):
    """Square 24px/28px crisp vector SVG icon button with clean tooltip."""

    def __init__(
        self,
        icon_name: str,
        tooltip: str = "",
        size: int = H_BTN_SM,
        color: str = C_TEXT_1,
        checkable: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("", parent)
        self.setProperty("uBtn", True)
        self.setProperty("variant", "ghost")
        self.setCheckable(checkable)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(size, size)
        self.setIcon(render_svg_icon(icon_name, color=color, size=max(13, size - 12)))
        self.setIconSize(QSize(max(13, size - 12), max(13, size - 12)))
        if tooltip:
            self.setToolTip(tooltip)


class USegmented(QWidget):
    """Mutually exclusive compact capsule segmented switcher (e.g. 3D | 2D)."""

    currentChanged = Signal(str)

    def __init__(
        self,
        options: Sequence[str],
        default: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._buttons: List[QPushButton] = []
        self._current = default or (options[0] if options else "")
        self.setStyleSheet(
            f"USegmented {{ background: {C_CONTROL}; border: 1px solid {LINE}; border-radius: {R_BTN}px; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        for opt in options:
            btn = QPushButton(opt, self)
            btn.setCheckable(True)
            btn.setFixedHeight(H_BTN_XS)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setChecked(opt == self._current)
            btn.clicked.connect(lambda _chk=False, name=opt: self.set_current(name))
            self._buttons.append(btn)
            layout.addWidget(btn)
        self._refresh_styles()

    def current(self) -> str:
        return self._current

    def set_current(self, value: str) -> None:
        if value == self._current:
            for b in self._buttons:
                b.setChecked(b.text() == value)
            return
        self._current = value
        for b in self._buttons:
            b.setChecked(b.text() == value)
        self._refresh_styles()
        self.currentChanged.emit(value)

    def _refresh_styles(self) -> None:
        for b in self._buttons:
            if b.text() == self._current:
                b.setStyleSheet(
                    f"QPushButton {{ background: {C_ACCENT}; color: #ffffff; border: none; "
                    f"border-radius: 4px; padding: 0 10px; font-size: 12px; font-weight: 600; }}"
                )
            else:
                b.setStyleSheet(
                    f"QPushButton {{ background: transparent; color: {C_TEXT_2}; border: none; "
                    f"border-radius: 4px; padding: 0 10px; font-size: 12px; }} "
                    f"QPushButton:hover {{ color: {C_TEXT_1}; background: {C_CONTROL_HOVER}; }}"
                )


class UBadge(QLabel):
    """Compact semantic status pill (neutral / accent / ok / warn / danger)."""

    _STYLES = {
        "neutral": (C_CONTROL, C_TEXT_2, LINE),
        "accent": (C_ACCENT_DIM, C_ACCENT, "rgba(46, 123, 247, 0.45)"),
        "ok": (C_OK_DIM, C_OK, "rgba(43, 182, 115, 0.45)"),
        "warn": (C_WARN_DIM, C_WARN, "rgba(240, 162, 40, 0.45)"),
        "danger": (C_DANGER_DIM, C_DANGER, "rgba(238, 77, 90, 0.45)"),
    }

    def __init__(self, text: str = "", tone: str = "neutral", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        bg, fg, bd = self._STYLES.get(tone, self._STYLES["neutral"])
        self.setStyleSheet(
            f"QLabel {{ background: {bg}; color: {fg}; border: 1px solid {bd}; "
            f"border-radius: 4px; padding: 1px 7px; font-size: 11px; font-weight: 600; }}"
        )
