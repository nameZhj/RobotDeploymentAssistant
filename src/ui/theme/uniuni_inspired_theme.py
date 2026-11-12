"""
@file: src/ui/theme/uniuni_inspired_theme.py
@brief: UniUni 1.0.2 风格规范化设计系统 Token 与全局 QPalette/QSS 样式引擎
@exports: UNIUNI_TOKENS, get_uniuni_stylesheet, apply_uniuni_theme
"""
from typing import Dict, Any
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

UNIUNI_TOKENS: Dict[str, str] = {
    "window_base": "#0b0c0f",
    "canvas": "#060708",
    "panel": "#101114",
    "card": "#15161a",
    "control": "#191a20",
    "control_hover": "#20222a",
    "text_primary": "#e4e6ea",
    "text_secondary": "#9ba0aa",
    "text_muted": "#6a6f78",
    "accent": "#2e7bf7",
    "accent_hover": "#4a8df9",
    "accent_pressed": "#2268db",
    "success": "#2bb673",
    "warning": "#f0a228",
    "danger": "#ee4d5a",
    "border": "rgba(236, 239, 243, 0.1)",
    "border_solid": "#23252b",
}


def get_uniuni_stylesheet() -> str:
    return f"""
    QMainWindow, QWidget#centralWidget {{
        background-color: {UNIUNI_TOKENS['window_base']};
        color: {UNIUNI_TOKENS['text_primary']};
        font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
        font-size: 12px;
    }}
    QFrame.panel-container, QFrame#leftDockContainer, QFrame#rightDockContainer, QFrame#timelineCanvasContainer {{
        background-color: {UNIUNI_TOKENS['panel']};
        border: 1px solid {UNIUNI_TOKENS['border_solid']};
        border-radius: 8px;
    }}
    QSplitter::handle {{
        background-color: {UNIUNI_TOKENS['window_base']};
    }}
    QSplitter::handle:hover {{
        background-color: {UNIUNI_TOKENS['accent']};
    }}
    QPushButton {{
        background-color: {UNIUNI_TOKENS['control']};
        color: {UNIUNI_TOKENS['text_primary']};
        border: 1px solid {UNIUNI_TOKENS['border_solid']};
        border-radius: 6px;
        padding: 4px 12px;
        min-height: 28px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: {UNIUNI_TOKENS['control_hover']};
        border-color: {UNIUNI_TOKENS['accent']};
    }}
    QPushButton:pressed {{
        background-color: {UNIUNI_TOKENS['accent_pressed']};
        color: #ffffff;
    }}
    QPushButton.btn-primary {{
        background-color: {UNIUNI_TOKENS['accent']};
        color: #ffffff;
        border: 1px solid {UNIUNI_TOKENS['accent_hover']};
    }}
    QPushButton.btn-primary:hover {{
        background-color: {UNIUNI_TOKENS['accent_hover']};
    }}
    QPushButton:disabled {{
        background-color: {UNIUNI_TOKENS['panel']};
        color: {UNIUNI_TOKENS['text_muted']};
        border-color: {UNIUNI_TOKENS['border_solid']};
    }}
    QComboBox, QLineEdit {{
        background-color: {UNIUNI_TOKENS['control']};
        color: {UNIUNI_TOKENS['text_primary']};
        border: 1px solid {UNIUNI_TOKENS['border_solid']};
        border-radius: 4px;
        padding: 2px 8px;
        min-height: 28px;
    }}
    QComboBox:hover, QLineEdit:hover, QLineEdit:focus {{
        border-color: {UNIUNI_TOKENS['accent']};
    }}
    QTabBar::tab {{
        background: transparent;
        color: {UNIUNI_TOKENS['text_secondary']};
        padding: 6px 14px;
        font-weight: 600;
    }}
    QTabBar::tab:selected {{
        color: {UNIUNI_TOKENS['accent']};
        border-bottom: 2px solid {UNIUNI_TOKENS['accent']};
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: #2b303c;
        border-radius: 3px;
        min-height: 20px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {UNIUNI_TOKENS['accent']};
    }}
    """


def apply_uniuni_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    font = QFont("Microsoft YaHei", 9)
    app.setFont(font)
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(UNIUNI_TOKENS["window_base"]))
    palette.setColor(QPalette.WindowText, QColor(UNIUNI_TOKENS["text_primary"]))
    palette.setColor(QPalette.Base, QColor(UNIUNI_TOKENS["panel"]))
    palette.setColor(QPalette.AlternateBase, QColor(UNIUNI_TOKENS["card"]))
    palette.setColor(QPalette.ToolTipBase, QColor(UNIUNI_TOKENS["card"]))
    palette.setColor(QPalette.ToolTipText, QColor(UNIUNI_TOKENS["text_primary"]))
    palette.setColor(QPalette.Text, QColor(UNIUNI_TOKENS["text_primary"]))
    palette.setColor(QPalette.Button, QColor(UNIUNI_TOKENS["control"]))
    palette.setColor(QPalette.ButtonText, QColor(UNIUNI_TOKENS["text_primary"]))
    palette.setColor(QPalette.BrightText, QColor(UNIUNI_TOKENS["danger"]))
    palette.setColor(QPalette.Highlight, QColor(UNIUNI_TOKENS["accent"]))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)
    app.setStyleSheet(get_uniuni_stylesheet())
