# @file: src/ui/theme/studio_dark_theme.py
# @brief: Applies complete desktop design-system QSS and dark Fusion palette to QApplication.
# @exports: apply_studio_theme

from __future__ import annotations

from typing import Any
from PySide6.QtGui import QColor, QPalette

from src.ui.design_system.tokens import C_ACCENT, C_BASE, C_CARD, C_CONTROL, C_PANEL, C_TEXT_1
from src.ui.design_system.ugc_v3_qss import build_ugc_v3_stylesheet


def apply_studio_theme(app: Any) -> None:
    """Configure Qt Fusion style, dark QPalette, and global studio stylesheet."""
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(C_BASE))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(C_TEXT_1))
    pal.setColor(QPalette.ColorRole.Base, QColor(C_PANEL))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(C_CARD))
    pal.setColor(QPalette.ColorRole.Button, QColor(C_CONTROL))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(C_TEXT_1))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(C_ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(pal)
    app.setStyleSheet(build_ugc_v3_stylesheet())
