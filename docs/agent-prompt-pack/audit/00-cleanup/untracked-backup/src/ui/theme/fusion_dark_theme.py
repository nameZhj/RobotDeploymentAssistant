"""
@file: src/ui/theme/fusion_dark_theme.py
@brief: 高对比度 Fusion 暗色主题引擎与全局 QPalette/QSS 样式注入器
@exports: apply_fusion_dark_theme
"""
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

DARK_STYLESHEET = """
QWidget {
    background-color: #0c0e12;
    color: #f8fafc;
    font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    font-size: 12px;
}
QDialog, QMessageBox, QMenu {
    background-color: #11141c;
    color: #f8fafc;
    border: 1px solid #283042;
}
QMenu::item {
    padding: 6px 20px;
    background-color: transparent;
}
QMenu::item:selected {
    background-color: #2563eb;
    color: #ffffff;
}
QPushButton {
    background-color: #1e2533;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 0px 12px;
    min-height: 30px;
    text-align: center;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #2b3548;
    border-color: #38bdf8;
}
QPushButton:pressed {
    background-color: #171d28;
}
QPushButton:checked {
    background-color: #2563eb;
    color: #ffffff;
    border-color: #60a5fa;
}
QPushButton:disabled {
    background-color: #151821;
    color: #475569;
    border-color: #1e2430;
}
QComboBox {
    background-color: #161a24;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 2px 8px;
    min-height: 28px;
    color: #f8fafc;
}
QComboBox:hover {
    border-color: #38bdf8;
}
QComboBox QAbstractItemView {
    background-color: #11141c;
    border: 1px solid #334155;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
    color: #f8fafc;
}
QTableWidget, QTableView, QTreeWidget, QTreeView {
    background-color: #0e1118;
    alternate-background-color: #141822;
    gridline-color: #1e2533;
    border: 1px solid #283042;
    color: #f8fafc;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}
QHeaderView::section {
    background-color: #161b26;
    color: #cbd5e1;
    border: none;
    border-right: 1px solid #232b3b;
    border-bottom: 1px solid #232b3b;
    padding: 5px;
    font-weight: 600;
}
QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: #141822;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 4px 6px;
    color: #f8fafc;
    selection-background-color: #2563eb;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #38bdf8;
}
QScrollBar:vertical {
    background: #0e1118;
    width: 8px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #2a3447;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #3b4963;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background: #0e1118;
    height: 8px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: #2a3447;
    min-width: 20px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: #3b4963;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    height: 0px;
}
"""


def apply_fusion_dark_theme(app: QApplication) -> None:
    """为应用程序注入 Fusion 高对比度暗色主题与全局组件样式表"""
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#0c0e12"))
    palette.setColor(QPalette.WindowText, QColor("#f8fafc"))
    palette.setColor(QPalette.Base, QColor("#161a24"))
    palette.setColor(QPalette.AlternateBase, QColor("#1e2533"))
    palette.setColor(QPalette.ToolTipBase, QColor("#161a24"))
    palette.setColor(QPalette.ToolTipText, QColor("#f8fafc"))
    palette.setColor(QPalette.Text, QColor("#f8fafc"))
    palette.setColor(QPalette.Button, QColor("#1e2533"))
    palette.setColor(QPalette.ButtonText, QColor("#f8fafc"))
    palette.setColor(QPalette.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.Link, QColor("#38bdf8"))
    palette.setColor(QPalette.Highlight, QColor("#2563eb"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))

    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#475569"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#475569"))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#475569"))

    app.setPalette(palette)
    app.setStyleSheet(DARK_STYLESHEET)

