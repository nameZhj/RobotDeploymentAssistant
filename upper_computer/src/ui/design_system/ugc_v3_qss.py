# @file: src/ui/design_system/ugc_v3_qss.py
# @brief: Complete desktop QSS stylesheet eliminating colorful clutter and enforcing hairline borders.
# @exports: build_ugc_v3_stylesheet

from __future__ import annotations

from src.ui.design_system.tokens import (
    C_ACCENT,
    C_ACCENT_BORDER,
    C_ACCENT_DIM,
    C_BASE,
    C_CANVAS,
    C_CARD,
    C_CONTROL,
    C_CONTROL_HOVER,
    C_DANGER,
    C_DANGER_DIM,
    C_FLOAT,
    C_FLOAT_2,
    C_FLOAT_EDGE,
    C_ON_ACCENT,
    C_PANEL,
    C_TEXT_1,
    C_TEXT_2,
    C_TEXT_3,
    FONT_UI,
    LINE,
    LINE_STRONG,
    R_BTN,
    R_CARD,
    R_CTRL,
)


def build_ugc_v3_stylesheet() -> str:
    """Return global PySide6 QSS styling for dark desktop workspace."""
    return f"""
QWidget {{
    background-color: {C_BASE};
    color: {C_TEXT_1};
    font-family: {FONT_UI};
    font-size: 13px;
}}

QMainWindow, #StudioAppShell {{
    background-color: {C_BASE};
}}

UPanel, QFrame[studioPanel="true"] {{
    background-color: {C_PANEL};
    border: 1px solid {LINE};
    border-radius: {R_CARD}px;
}}

#StageCanvasContainer {{
    background-color: {C_CANVAS};
    border: 1px solid {LINE};
    border-radius: {R_CARD}px;
}}

#UTitlebar {{
    background-color: {C_PANEL};
    border-bottom: 1px solid {LINE};
}}

#UStatusBar {{
    background-color: {C_PANEL};
    border-top: 1px solid {LINE};
}}

QLabel {{
    background: transparent;
    border: none;
    color: {C_TEXT_1};
}}

QLabel[muted="true"] {{
    color: {C_TEXT_2};
}}

QLabel[dim="true"] {{
    color: {C_TEXT_3};
}}

QPushButton[uBtn="true"] {{
    background-color: {C_CONTROL};
    color: {C_TEXT_1};
    border: 1px solid {LINE};
    border-radius: {R_BTN}px;
    padding: 0 10px;
    font-size: 12px;
    font-weight: 500;
}}

QPushButton[uBtn="true"]:hover {{
    background-color: {C_CONTROL_HOVER};
    border-color: {LINE_STRONG};
}}

QPushButton[uBtn="true"][variant="primary"] {{
    background-color: {C_ACCENT};
    color: {C_ON_ACCENT};
    border: 1px solid {C_ACCENT};
    font-weight: 600;
}}

QPushButton[uBtn="true"][variant="primary"]:hover {{
    background-color: #3d87ff;
}}

QPushButton[uBtn="true"][variant="danger"] {{
    background-color: {C_DANGER_DIM};
    color: {C_DANGER};
    border: 1px solid rgba(238, 77, 90, 0.42);
}}

QPushButton[uBtn="true"][variant="danger"]:hover {{
    background-color: rgba(238, 77, 90, 0.28);
}}

QPushButton[uBtn="true"][variant="ghost"] {{
    background-color: transparent;
    border: 1px solid transparent;
    color: {C_TEXT_2};
}}

QPushButton[uBtn="true"][variant="ghost"]:hover {{
    background-color: {C_CONTROL_HOVER};
    color: {C_TEXT_1};
}}

QPushButton[uNavTab="true"] {{
    background-color: transparent;
    color: {C_TEXT_2};
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0px;
    padding: 0 12px;
    font-size: 12px;
    font-weight: 500;
}}

QPushButton[uNavTab="true"]:hover {{
    color: {C_TEXT_1};
    background-color: {C_CONTROL};
}}

QPushButton[uNavTab="true"]:checked {{
    color: {C_TEXT_1};
    background-color: {C_ACCENT_DIM};
    border-bottom: 2px solid {C_ACCENT};
    font-weight: 600;
}}

QLineEdit, QComboBox, QTextEdit, QPlainTextEdit {{
    background-color: {C_CONTROL};
    color: {C_TEXT_1};
    border: 1px solid {LINE};
    border-radius: {R_CTRL}px;
    padding: 3px 8px;
    min-height: 22px;
    selection-background-color: {C_ACCENT};
}}

QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {C_ACCENT_BORDER};
}}

QFrame#uNumBox {{
    background-color: {C_CONTROL};
    border: 1px solid {LINE};
    border-radius: {R_CTRL}px;
}}

QDoubleSpinBox, QSpinBox {{
    background-color: transparent;
    color: {C_TEXT_1};
    border: none;
    padding: 0px;
    margin: 0px;
    selection-background-color: {C_ACCENT};
}}

QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button {{
    width: 0px;
    height: 0px;
    border: none;
}}

QComboBox::drop-down {{
    border: none;
    width: 18px;
}}

QComboBox QAbstractItemView {{
    background-color: {C_FLOAT_2};
    color: {C_TEXT_1};
    border: 1px solid {C_FLOAT_EDGE};
    selection-background-color: {C_ACCENT_DIM};
}}

QTableWidget, QTreeWidget, QListWidget {{
    background-color: {C_PANEL};
    alternate-background-color: {C_CARD};
    color: {C_TEXT_1};
    border: 1px solid {LINE};
    border-radius: {R_CTRL}px;
    gridline-color: {LINE};
    outline: none;
}}

QHeaderView::section {{
    background-color: {C_CONTROL};
    color: {C_TEXT_2};
    border: none;
    border-bottom: 1px solid {LINE};
    border-right: 1px solid {LINE};
    padding: 4px 6px;
    font-size: 11px;
    font-weight: 600;
}}

QTableWidget::item:selected, QListWidget::item:selected {{
    background-color: {C_ACCENT_DIM};
    color: {C_TEXT_1};
}}

QCheckBox {{
    color: {C_TEXT_2};
    spacing: 6px;
    background: transparent;
}}

QSlider::groove:horizontal {{
    height: 4px;
    background: {C_CONTROL_HOVER};
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background: {C_ACCENT};
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}}

QScrollBar:vertical, QScrollBar:horizontal {{
    background: transparent;
    width: 8px;
    height: 8px;
    margin: 0;
}}

QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: rgba(236, 239, 243, 0.16);
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}}

QScrollBar::handle:hover {{
    background: rgba(236, 239, 243, 0.28);
}}

QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: none;
    border: none;
    width: 0;
    height: 0;
}}

QDialog[uDialog="true"] {{
    background-color: {C_FLOAT};
    border: 1px solid {C_FLOAT_EDGE};
    border-radius: {R_CARD}px;
}}

QToolTip {{
    background-color: {C_FLOAT_2};
    color: {C_TEXT_1};
    border: 1px solid {C_FLOAT_EDGE};
    padding: 4px 8px;
    font-size: 12px;
}}
"""
