# @file: src/ui/modals/task_json_viewer_modal.py
# @brief: Live JSON inspector and clipboard/file exporter for stage task & trajectory structures.
# @exports: TaskJsonViewerModal

from __future__ import annotations

import json
from PySide6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QPlainTextEdit, QWidget

from src.services.studio_state_service import StudioStateService
from src.ui.design_system.tokens import FONT_MONO
from src.ui.design_system.u_buttons import UButton
from src.ui.design_system.u_dialog import UDialog


class TaskJsonViewerModal(UDialog):
    """Displays full stage JSON serialization of the current task and supports file export."""

    def __init__(self, state: StudioStateService, parent: QWidget | None = None) -> None:
        super().__init__("工程 JSON 数据视图", width=720, height=520, confirm_text="关闭", cancel_text="", parent=parent)
        self.state = state
        payload = state.json_codec.export_task_to_dict()
        self._text = json.dumps(payload, ensure_ascii=False, indent=2)

        top = QHBoxLayout()
        cp_b = UButton("复制 JSON", variant="default", size="sm", icon_name="copy", parent=self)
        cp_b.clicked.connect(self._copy)
        sv_b = UButton("导出 .json 文件", variant="primary", size="sm", icon_name="save", parent=self)
        sv_b.clicked.connect(self._export)
        top.addWidget(cp_b)
        top.addWidget(sv_b)
        top.addStretch(1)
        self.body_layout.addLayout(top)

        self.editor = QPlainTextEdit(self._text, self)
        self.editor.setReadOnly(True)
        self.editor.setStyleSheet(f"font-family: {FONT_MONO}; font-size: 11px;")
        self.body_layout.addWidget(self.editor, 1)

    def _copy(self) -> None:
        QApplication.clipboard().setText(self._text)
        self.state.notify("JSON 已复制到剪贴板", "ok")

    def _export(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, "导出 JSON", "choreo_task.json", "JSON (*.json)")
        if p:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(self._text)
            self.state.notify(f"已保存 JSON 至 {p}", "ok")
