# @file: src/ui/choreography/editor_opbar.py
# @brief: Compact 2-column vertical operation toolbar for TaskEditor keeping minimum height <= 155px for 70:30 split.
# @exports: EditorOpbar

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QWidget

from src.ui.design_system.tokens import C_CARD, LINE
from src.ui.design_system.u_buttons import UIconButton


class EditorOpbar(QFrame):
    """Compact 2-column strip of vector tools driving Task Chain editing, stop-to-origin, and zoom."""

    toolClicked = Signal(str)

    _TOOLS = (
        ("cursor", "选择 / 拖拽排序模式", "select"),
        ("stop", "停止并回到原点", "stop_origin"),
        ("cut", "在游标处拆分节点", "split"),
        ("copy", "向后追加复制节点", "duplicate"),
        ("sliders", "忽略 / 恢复选中节点", "ignore"),
        ("delete", "删除选中节点 (Del)", "delete"),
        ("undo", "撤销 (Ctrl+Z)", "undo"),
        ("redo", "重做 (Ctrl+Y)", "redo"),
        ("layers", "批量任务链编排抽屉", "batch"),
        ("check", "节点顺序吸附开关", "snap"),
        ("zoom_in", "放大任务链视图", "zoom_in"),
        ("zoom_out", "缩小任务链视图", "zoom_out"),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(54)
        self.setStyleSheet(f"EditorOpbar {{ background: {C_CARD}; border-right: 1px solid {LINE}; }}")
        grid = QGridLayout(self)
        grid.setContentsMargins(4, 6, 4, 6)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)
        grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.snap_btn: UIconButton | None = None
        for idx, (icon, tip, action) in enumerate(self._TOOLS):
            checkable = action == "snap"
            btn = UIconButton(icon, tooltip=tip, size=20, checkable=checkable, parent=self)
            if checkable:
                btn.setChecked(True)
                self.snap_btn = btn
            btn.clicked.connect(lambda _chk=False, act=action: self.toolClicked.emit(act))
            grid.addWidget(btn, idx // 2, idx % 2)
