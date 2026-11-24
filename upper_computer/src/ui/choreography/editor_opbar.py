# @file: src/ui/choreography/editor_opbar.py
# @brief: Clean single-column task-chain editing toolbar with 4 large ergonomic action buttons (<=160px height).
# @exports: EditorOpbar

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from src.ui.design_system.tokens import C_CARD, C_DANGER, C_TEXT_1, LINE
from src.ui.design_system.u_buttons import UIconButton


class EditorOpbar(QFrame):
    """Streamlined single-column vertical toolbar keeping only essential Task Chain actions at generous 30x30px size."""

    toolClicked = Signal(str)

    _TOOLS = (
        ("undo", "撤销上一步 (Ctrl+Z)", "undo", "default", C_TEXT_1),
        ("redo", "重做 (Ctrl+Y)", "redo", "default", C_TEXT_1),
        ("layers", "批量任务链动作编排", "batch", "default", C_TEXT_1),
        ("delete", "删除选中任务节点 (Del)", "delete", "danger", C_DANGER),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(48)
        self.setStyleSheet(f"EditorOpbar {{ background: {C_CARD}; border-right: 1px solid {LINE}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(9, 10, 9, 10)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.snap_btn: UIconButton | None = None
        for icon, tip, action, variant, color in self._TOOLS:
            btn = UIconButton(icon, tooltip=tip, size=30, color=color, variant=variant, parent=self)
            btn.clicked.connect(lambda _chk=False, act=action: self.toolClicked.emit(act))
            lay.addWidget(btn)
        lay.addStretch(1)
