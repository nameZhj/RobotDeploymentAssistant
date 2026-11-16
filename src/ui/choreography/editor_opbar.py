# @file: src/ui/choreography/editor_opbar.py
# @brief: 40px vertical operation toolbar with UniUni v3 timeline editing & zoom icon buttons.
# @exports: EditorOpbar

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from src.ui.design_system.tokens import C_CARD, LINE, W_OPBAR
from src.ui.design_system.u_buttons import UIconButton


class EditorOpbar(QFrame):
    """Vertical 40px strip of vector tools driving TaskEditor operations and timeline zoom."""

    toolClicked = Signal(str)

    _TOOLS = (
        ("cursor", "选择 / 移动模式", "select"),
        ("cut", "在播放头处分割块", "split"),
        ("copy", "向后复制选中块", "duplicate"),
        ("sliders", "忽略 / 恢复选中块", "ignore"),
        ("delete", "删除选中块 (Del)", "delete"),
        ("---", "", ""),
        ("undo", "撤销 (Ctrl+Z)", "undo"),
        ("redo", "重做 (Ctrl+Y)", "redo"),
        ("layers", "批量编排抽屉", "batch"),
        ("---", "", ""),
        ("zoom_in", "放大时间轴", "zoom_in"),
        ("zoom_out", "缩小时间轴", "zoom_out"),
        ("check", "时间吸附开关 (0.1s)", "snap"),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(W_OPBAR)
        self.setStyleSheet(f"EditorOpbar {{ background: {C_CARD}; border-right: 1px solid {LINE}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 8, 6, 8)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.snap_btn: UIconButton | None = None
        for icon, tip, action in self._TOOLS:
            if icon == "---":
                sep = QFrame(self)
                sep.setFixedSize(20, 1)
                sep.setStyleSheet(f"background: {LINE};")
                lay.addWidget(sep)
                continue
            checkable = action == "snap"
            btn = UIconButton(icon, tooltip=tip, size=26, checkable=checkable, parent=self)
            if checkable:
                btn.setChecked(True)
                self.snap_btn = btn
            btn.clicked.connect(lambda _chk=False, act=action: self.toolClicked.emit(act))
            lay.addWidget(btn)
        lay.addStretch(1)
