# @file: src/ui/design_system/u_panels.py
# @brief: Structural containers UPanel, UCollapsibleGroup (.group-card), UTable, and UEmpty for UniUni v3 panels.
# @exports: UPanel, UCollapsibleGroup, UTable, UEmpty

from __future__ import annotations

from typing import Optional, Sequence
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from src.ui.design_system.tokens import (
    C_ACCENT_DIM,
    C_CARD,
    C_CONTROL,
    C_PANEL,
    C_TEXT_1,
    C_TEXT_2,
    C_TEXT_3,
    H_BTN_XS,
    LINE,
    R_CARD,
)
from src.ui.design_system.u_buttons import UBadge, UHelpIcon, UIconButton


class UPanel(QFrame):
    """Standard #101114 bordered panel with optional compact 34px header toolbar."""

    def __init__(
        self,
        title: str = "",
        header_widgets: Sequence[QWidget] = (),
        parent: Optional[QWidget] = None,
        help_text: str = "",
    ) -> None:
        super().__init__(parent)
        self._help_icon: Optional[UHelpIcon] = None
        self.setProperty("uniPanel", True)
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        self.header_bar: Optional[QWidget] = None
        if title or header_widgets or help_text:
            self.header_bar = QFrame(self)
            self.header_bar.setFixedHeight(34)
            self.header_bar.setStyleSheet(
                f"background: {C_CARD}; border: none; border-bottom: 1px solid {LINE}; "
                f"border-top-left-radius: {R_CARD}px; border-top-right-radius: {R_CARD}px;"
            )
            hl = QHBoxLayout(self.header_bar)
            hl.setContentsMargins(10, 0, 8, 0)
            hl.setSpacing(4)
            self.title_label = QLabel(title, self.header_bar)
            self.title_label.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {C_TEXT_1};")
            hl.addWidget(self.title_label)
            hl.addStretch(1)
            for w in header_widgets:
                hl.addWidget(w)
            self.root_layout.addWidget(self.header_bar)
            if help_text:
                self.set_help_text(help_text)

        self.body_widget = QWidget(self)
        self.body_widget.setObjectName("uPanelBody")
        self.body_widget.setStyleSheet(f"#uPanelBody {{ background: {C_PANEL}; border: none; }}")
        self.body_layout = QVBoxLayout(self.body_widget)
        self.body_layout.setContentsMargins(8, 8, 8, 8)
        self.body_layout.setSpacing(6)
        self.root_layout.addWidget(self.body_widget, 1)

    def set_help_text(self, help_text: str, title: str = "操作提示") -> None:
        """Attach or update a top-right circular '?' help button on the panel header."""
        if self.header_bar is None:
            return
        hl = self.header_bar.layout()
        text = help_text.strip()
        if not text:
            if self._help_icon is not None:
                self._help_icon.hide()
            return
        if self._help_icon is None:
            self._help_icon = UHelpIcon(text, title=title, parent=self.header_bar)
        else:
            self._help_icon.set_help_text(text, title=title)
            self._help_icon.show()
            hl.removeWidget(self._help_icon)
        hl.addWidget(self._help_icon)


class UCollapsibleGroup(QFrame):
    """Collapsible .group-card for Trajectory Library with track binding, rename, and delete controls."""

    bindTrackClicked = Signal(int)
    renameClicked = Signal(int)
    deleteClicked = Signal(int)

    def __init__(
        self,
        group_id: int,
        name: str,
        robot_count: int,
        item_count: int,
        bound_track_no: Optional[int] = None,
        expanded: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.group_id = group_id
        self._expanded = expanded
        self.setStyleSheet(
            f"UCollapsibleGroup {{ background: {C_CARD}; border: 1px solid {LINE}; border-radius: 6px; }}"
        )
        main_l = QVBoxLayout(self)
        main_l.setContentsMargins(0, 0, 0, 0)
        main_l.setSpacing(0)

        head = QFrame(self)
        head.setFixedHeight(32)
        head.setStyleSheet(f"background: {C_CARD}; border: none; border-radius: 6px;")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(6, 0, 6, 0)
        hl.setSpacing(4)

        self.toggle_btn = UIconButton(
            "chevron_down" if expanded else "chevron_right",
            tooltip="展开 / 折叠分组",
            size=H_BTN_XS,
            color=C_TEXT_2,
        )
        self.toggle_btn.clicked.connect(self.toggle)
        hl.addWidget(self.toggle_btn)

        self.name_label = QLabel(name, head)
        self.name_label.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {C_TEXT_1};")
        hl.addWidget(self.name_label, 1)

        hl.addWidget(UBadge(f"{robot_count}机", tone="neutral", parent=head))
        hl.addWidget(UBadge(f"{item_count}条", tone="accent", parent=head))

        track_txt = f"轨道 {bound_track_no}" if bound_track_no else "绑定轨道"
        self.bind_btn = QPushButton(track_txt, head)
        self.bind_btn.setFixedHeight(22)
        self.bind_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bind_btn.setToolTip("将此分组轨迹快速分配/绑定到机器人轨道")
        self.bind_btn.setStyleSheet(
            f"QPushButton {{ background: {C_CONTROL}; color: {C_TEXT_2}; border: 1px solid {LINE}; "
            f"border-radius: 4px; padding: 0 6px; font-size: 11px; }} "
            f"QPushButton:hover {{ background: {C_ACCENT_DIM}; color: {C_TEXT_1}; }}"
        )
        self.bind_btn.clicked.connect(lambda: self.bindTrackClicked.emit(self.group_id))
        hl.addWidget(self.bind_btn)

        self.del_btn = UIconButton("trash", tooltip="删除分组", size=H_BTN_XS, color=C_TEXT_3)
        self.del_btn.clicked.connect(lambda: self.deleteClicked.emit(self.group_id))
        self.ren_btn = UIconButton("edit", tooltip="重命名分组", size=H_BTN_XS, color=C_TEXT_3)
        self.ren_btn.clicked.connect(lambda: self.renameClicked.emit(self.group_id))
        hl.addWidget(self.ren_btn)
        hl.addWidget(self.del_btn)
        main_l.addWidget(head)

        self.content_holder = QWidget(self)
        self.content_layout = QVBoxLayout(self.content_holder)
        self.content_layout.setContentsMargins(4, 2, 4, 6)
        self.content_layout.setSpacing(4)
        self.content_holder.setVisible(expanded)
        main_l.addWidget(self.content_holder)

    def toggle(self) -> None:
        self._expanded = not self._expanded
        self.content_holder.setVisible(self._expanded)
        from src.ui.design_system.svg_icons import render_svg_icon
        self.toggle_btn.setIcon(
            render_svg_icon("chevron_down" if self._expanded else "chevron_right", color=C_TEXT_2, size=12)
        )


class UTable(QTableWidget):
    """Dense UniUni table supporting full-row selection and clean drag-payload creation."""

    def __init__(
        self,
        headers: Sequence[str],
        stretch_col: int | QWidget = 0,
        parent: Optional[QWidget] = None,
    ) -> None:
        if isinstance(stretch_col, QWidget):
            parent = stretch_col
            stretch_col = max(0, len(headers) - 1)
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(list(headers))
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(26)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        hdr = self.horizontalHeader()
        hdr.setHighlightSections(False)
        for col in range(len(headers)):
            mode = (
                QHeaderView.ResizeMode.Stretch
                if col == stretch_col
                else QHeaderView.ResizeMode.ResizeToContents
            )
            hdr.setSectionResizeMode(col, mode)


class UEmpty(QLabel):
    """Subtle centered empty-state hint label."""

    def __init__(self, text: str = "暂无数据", subtitle: str | QWidget = "", parent: Optional[QWidget] = None) -> None:
        if isinstance(subtitle, QWidget):
            parent = subtitle
            subtitle = ""
        full = f"{text}\n{subtitle}" if subtitle else text
        super().__init__(full, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"color: {C_TEXT_3}; font-size: 12px; padding: 18px;")
