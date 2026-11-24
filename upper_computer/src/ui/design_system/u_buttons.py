# @file: src/ui/design_system/u_buttons.py
# @brief: Unified UButton, UIconButton, USegmented, UBadge, and UHelpIcon controls guaranteeing zero text truncation.
# @exports: UButton, UIconButton, USegmented, UBadge, UHelpIcon

from __future__ import annotations

from typing import List, Optional, Sequence
from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QEnterEvent, QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget
from src.ui.design_system import tokens as _t

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
        # Account for QSS horizontal padding (20px) + icon (18px) so buttons never overlap or clip
        text_w = self.fontMetrics().horizontalAdvance(text) if text else 0
        icon_w = 20 if icon_name else 0
        self.setMinimumWidth(max(height, self.sizeHint().width() + 8, text_w + icon_w + 24))

    def set_variant(self, variant: str) -> None:
        self.setProperty("variant", variant)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class UIconButton(QPushButton):
    """Square 24px/30px crisp vector SVG icon button with clean tooltip."""

    def __init__(
        self,
        icon_name: str,
        tooltip: str = "",
        size: int = H_BTN_SM,
        color: str = C_TEXT_1,
        checkable: bool = False,
        variant: str = "ghost",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("", parent)
        self.setProperty("uBtn", True)
        self.setProperty("variant", variant)
        self.setCheckable(checkable)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(size, size)
        self.setStyleSheet("QPushButton { padding: 0px; }")
        ico_px = max(14, size - 14)
        self.setIcon(render_svg_icon(icon_name, color=color, size=ico_px))
        self.setIconSize(QSize(ico_px, ico_px))
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


class _HelpPopupCard(QFrame):
    """Frameless floating help card shown when hovering a UHelpIcon."""

    def __init__(self) -> None:
        flags = Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setMaximumWidth(300)
        self.setStyleSheet(f"_HelpPopupCard {{ background: {_t.C_FLOAT_2}; border: 1px solid {_t.C_FLOAT_EDGE}; border-radius: 6px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)
        self._title_lbl = QLabel(self)
        self._title_lbl.setStyleSheet(f"color: {_t.C_TEXT_1}; font-size: 12px; font-weight: 600; border: none;")
        self._body_lbl = QLabel(self)
        self._body_lbl.setWordWrap(True)
        self._body_lbl.setStyleSheet(f"color: {_t.C_TEXT_2}; font-size: 11px; line-height: 1.45; border: none;")
        lay.addWidget(self._title_lbl)
        lay.addWidget(self._body_lbl)

    def set_content(self, title: str, text: str) -> None:
        self._title_lbl.setText(title)
        self._title_lbl.setVisible(bool(title))
        self._body_lbl.setText(text)
        self.adjustSize()


class UHelpIcon(QWidget):
    """Circular '?' button in top-right headers that opens a floating help popup on hover."""

    def __init__(self, help_text: str = "", title: str = "操作提示", size: int = 18, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._help_text, self._help_title, self._size = help_text.strip(), title.strip(), size
        self._popup: Optional[_HelpPopupCard] = None
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.WhatsThisCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAccessibleName(self._help_title or "操作提示")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._circle = QLabel("?", self)
        self._circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._circle.setFixedSize(size, size)
        lay.addWidget(self._circle)
        self._apply_circle_style(hovered=False)
        self.destroyed.connect(self._cleanup_popup)

    def set_help_text(self, help_text: str, title: Optional[str] = None) -> None:
        self._help_text = help_text.strip()
        if title is not None:
            self._help_title = title.strip()
        if self._popup is not None and self._popup.isVisible():
            self._popup.set_content(self._help_title, self._help_text)

    def _apply_circle_style(self, hovered: bool) -> None:
        bg, fg, bd = (_t.C_ACCENT_DIM, _t.C_TEXT_1, _t.C_ACCENT) if hovered else ("rgba(255,255,255,0.06)", _t.C_TEXT_2, _t.C_FLOAT_EDGE)
        self._circle.setStyleSheet(
            f"QLabel {{ background: {bg}; color: {fg}; border: 1px solid {bd}; "
            f"border-radius: {self._size // 2}px; font-size: 11px; font-weight: 700; }}"
        )

    def _show_popup(self) -> None:
        if not self._help_text:
            return
        if self._popup is None:
            self._popup = _HelpPopupCard()
        self._popup.set_content(self._help_title, self._help_text)
        anchor = self.mapToGlobal(QPoint(self.width(), self.height() + 6))
        x, y = anchor.x() - self._popup.width(), anchor.y()
        scr = self.screen() or QGuiApplication.screenAt(anchor)
        if scr is not None:
            geo = scr.availableGeometry()
            x = max(geo.left() + 6, min(x, geo.right() - self._popup.width() - 6))
            if y + self._popup.height() > geo.bottom() - 6:
                y = self.mapToGlobal(QPoint(0, -6)).y() - self._popup.height()
            y = max(geo.top() + 6, y)
        self._popup.move(x, y)
        self._popup.show()

    def _cleanup_popup(self) -> None:
        if self._popup is not None:
            self._popup.hide()
            self._popup.deleteLater()
            self._popup = None

    def enterEvent(self, event: QEnterEvent) -> None:
        self._apply_circle_style(hovered=True)
        self._show_popup()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._apply_circle_style(hovered=False)
        if self._popup is not None:
            self._popup.hide()
        super().leaveEvent(event)

    def hideEvent(self, event: QEvent) -> None:
        self._apply_circle_style(hovered=False)
        if self._popup is not None:
            self._popup.hide()
        super().hideEvent(event)
