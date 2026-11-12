"""
@file: src/ui/dialogs/http_preview_dialog.py
@brief: HTTP 虚拟接口轨迹报文预览对话框，展示标准请求头、URL 与格式化 JSON
@exports: HttpPreviewDialog
"""
import json
from typing import Any, Dict, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)


class HttpPreviewDialog(QDialog):
    """展示即将发送给机器人 HTTP 接口的标准报文载荷"""

    def __init__(self, parent: Optional[QWidget] = None, preview_data: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(parent)
        self.data = preview_data or {}
        self._init_ui()

    def _init_ui(self) -> None:
        self.setWindowTitle("🌐 HTTP 轨迹上传报文预览 (预留虚拟接口)")
        self.resize(720, 560)
        self.setStyleSheet("background-color: #0f172a; color: #f8fafc;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 头部说明
        lbl_tip = QLabel("📌 此报文为对齐机器人 HTTP 运控端生成的标准 JSON 载荷（未连接真机时处于仿真预留模式）：")
        lbl_tip.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 11px;")
        layout.addWidget(lbl_tip)

        # URL 与 Method
        ep = self.data.get("endpoint", "http://192.168.123.164:8090/api/v1/trajectory/upload")
        method = self.data.get("method", "POST")
        lbl_url = QLabel(f"<b>请求方式:</b> <span style='color: #22c55e;'>{method}</span> &nbsp;&nbsp; <b>目标 URL:</b> <span style='color: #f59e0b;'>{ep}</span>")
        lbl_url.setStyleSheet("font-size: 11px; background: #1e293b; padding: 6px; border-radius: 4px;")
        layout.addWidget(lbl_url)

        # JSON 载荷
        layout.addWidget(QLabel("HTTP Payload (JSON 报文内容):"))
        self.txt_payload = QTextEdit(self)
        self.txt_payload.setReadOnly(True)
        self.txt_payload.setStyleSheet("""
            QTextEdit {
                background-color: #030712;
                color: #a5f3fc;
                border: 1px solid #1f2937;
                border-radius: 4px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
            }
        """)

        payload = self.data.get("payload", {})
        formatted_json = json.dumps(payload, indent=2, ensure_ascii=False)
        self.txt_payload.setPlainText(formatted_json)
        layout.addWidget(self.txt_payload, 1)

        # 底部操作按钮
        btn_bar = QHBoxLayout()
        btn_copy = QPushButton("📋 复制完整报文")
        btn_copy.setStyleSheet("background: #0284c7; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        btn_copy.clicked.connect(self._copy_to_clipboard)
        btn_bar.addWidget(btn_copy)

        btn_bar.addStretch(1)

        btn_close = QPushButton("关闭")
        btn_close.setStyleSheet("background: #475569; color: white; padding: 6px 16px; border-radius: 4px;")
        btn_close.clicked.connect(self.accept)
        btn_bar.addWidget(btn_close)
        layout.addLayout(btn_bar)

    def _copy_to_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(self.txt_payload.toPlainText())
        QMessageBox.information(self, "复制成功", "JSON 报文已成功复制到剪贴板！")
