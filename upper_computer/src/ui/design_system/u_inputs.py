# @file: src/ui/design_system/u_inputs.py
# @brief: Numeric, timecode, dropdown, and search input controls conforming to desktop v3 dark styling.
# @exports: UInputNumber, UTimeInput, USearchInput, USelect

from __future__ import annotations

from typing import Optional, Sequence, Tuple
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QWidget,
)

from src.ui.design_system.tokens import C_ACCENT, C_CONTROL, C_TEXT_1, C_TEXT_3, FONT_MONO, H_BTN_SM


class UInputNumber(QWidget):
    """Floating-point spinbox with optional right-aligned physical unit suffix (e.g. m, s, rad)."""

    valueChanged = Signal(float)

    def __init__(
        self,
        value: float = 0.0,
        min_val: float = -999.0,
        max_val: float = 999.0,
        step: float = 0.1,
        decimals: int = 2,
        unit: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setFixedHeight(max(28, H_BTN_SM))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        box = QFrame(self)
        box.setObjectName("uNumBox")
        box.setFixedHeight(26)
        box_lay = QHBoxLayout(box)
        box_lay.setContentsMargins(6, 1, 6, 1)
        box_lay.setSpacing(0)

        self.spin = QDoubleSpinBox(box)
        self.spin.setFrame(False)
        pal = self.spin.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(C_CONTROL))
        pal.setColor(QPalette.ColorRole.Text, QColor(C_TEXT_1))
        pal.setColor(QPalette.ColorRole.Window, QColor(C_CONTROL))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(C_TEXT_1))
        pal.setColor(QPalette.ColorRole.Highlight, QColor(C_ACCENT))
        self.spin.setPalette(pal)
        self.spin.setRange(min_val, max_val)
        self.spin.setSingleStep(step)
        self.spin.setDecimals(decimals)
        self.spin.setValue(value)
        self.spin.valueChanged.connect(self.valueChanged.emit)
        box_lay.addWidget(self.spin, 1)
        layout.addWidget(box, 1)

        if unit:
            lbl = QLabel(unit, self)
            lbl.setStyleSheet(f"color: {C_TEXT_3}; font-size: 11px;")
            layout.addWidget(lbl)

    def value(self) -> float:
        return float(self.spin.value())

    def setValue(self, val: float) -> None:
        self.spin.setValue(float(val))


class UTimeInput(QLineEdit):
    """Monospaced MM:SS.ms / seconds formatter input control."""

    secondsChanged = Signal(float)

    def __init__(self, seconds: float = 0.0, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(H_BTN_SM)
        self.setStyleSheet(f"font-family: {FONT_MONO}; font-size: 12px;")
        self._seconds = max(0.0, float(seconds))
        self.setText(self.format_seconds(self._seconds))
        self.editingFinished.connect(self._on_commit)

    @staticmethod
    def format_seconds(sec: float) -> str:
        safe = max(0.0, float(sec))
        mins = int(safe // 60)
        rem = safe - mins * 60
        return f"{mins:02d}:{rem:05.2f}"

    def seconds(self) -> float:
        return self._seconds

    def set_seconds(self, sec: float) -> None:
        self._seconds = max(0.0, float(sec))
        self.setText(self.format_seconds(self._seconds))

    def _on_commit(self) -> None:
        txt = self.text().strip()
        try:
            if ":" in txt:
                parts = txt.split(":", 1)
                parsed = float(parts[0]) * 60.0 + float(parts[1])
            else:
                parsed = float(txt)
            self._seconds = max(0.0, parsed)
        except ValueError:
            pass
        self.setText(self.format_seconds(self._seconds))
        self.secondsChanged.emit(self._seconds)


class USearchInput(QLineEdit):
    """Compact filter search input with clear button."""

    def __init__(self, placeholder: str = "搜索编号 / 名称...", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(H_BTN_SM)
        self.setClearButtonEnabled(True)
        self.setPlaceholderText(placeholder)


class USelect(QComboBox):
    """Consistent height dropdown selector supporting (label, data) pairs or strings."""

    def __init__(
        self,
        items: Sequence[Tuple[str, object] | str] = (),
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setFixedHeight(H_BTN_SM)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        for item in items:
            if isinstance(item, tuple):
                self.addItem(item[0], item[1])
            else:
                self.addItem(str(item), item)

    def current_data(self) -> object:
        return self.currentData()

    def set_current_data(self, value: object) -> None:
        idx = self.findData(value)
        if idx >= 0:
            self.setCurrentIndex(idx)
