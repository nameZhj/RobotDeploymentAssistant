# @file: src/ui/choreography/track_lib_row.py
# @brief: Trajectory Library row widget with visibility checkbox, multi-robot binding dialog, drag-drop, edit, and delete.
# @exports: TrajectoryRowWidget, BindRobotsDialog

from __future__ import annotations

import json
from typing import Dict, List, Optional
from PySide6.QtCore import QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.domain.track_entities import TrackEntity
from src.domain.trajectory_entities import TrajectoryEntity
from src.ui.design_system.tokens import (
    C_ACCENT_DIM,
    C_CARD,
    C_CONTROL,
    C_CONTROL_HOVER,
    C_TEXT_1,
    C_TEXT_2,
    FONT_MONO,
    LINE,
)
from src.ui.design_system.u_buttons import UBadge, UIconButton, UButton
from src.ui.design_system.u_dialog import UDialog


class BindRobotsDialog(UDialog):
    """Multi-select dialog binding a saved trajectory to one or more robot tracks."""

    def __init__(
        self,
        traj: TrajectoryEntity,
        tracks: List[TrackEntity],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(f"绑定机器人 · {traj.name}", width=380, height=340, confirm_text="确认绑定", parent=parent)
        hint = QLabel("勾选该轨迹绑定的一个或多个机器人轨道：", self)
        hint.setStyleSheet(f"color: {C_TEXT_2}; font-size: 11px;")
        self.body_layout.addWidget(hint)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        holder = QWidget(scroll)
        vl = QVBoxLayout(holder)
        vl.setContentsMargins(2, 2, 2, 2)
        vl.setSpacing(4)

        self._checks: Dict[int, QCheckBox] = {}
        bound = set(traj.bound_track_nos)
        if not tracks:
            vl.addWidget(QLabel("当前尚未添加任何机器人轨道", holder))
        for tr in tracks:
            cb = QCheckBox(f"轨道 {tr.track_no} · {tr.name} [{tr.target_id}]", holder)
            cb.setChecked(tr.track_no in bound)
            vl.addWidget(cb)
            self._checks[tr.track_no] = cb
        vl.addStretch(1)
        scroll.setWidget(holder)
        self.body_layout.addWidget(scroll, 1)

        self.sync_timeline_chk = QCheckBox("同时将此轨迹加入所选机器人的任务链", self)
        self.sync_timeline_chk.setChecked(True)
        self.body_layout.addWidget(self.sync_timeline_chk)

    def selected_track_nos(self) -> List[int]:
        """Return sorted selected robot track numbers."""
        return sorted(rno for rno, cb in self._checks.items() if cb.isChecked())


class TrajectoryRowWidget(QFrame):
    """Saved trajectory card featuring map visibility checkbox, multi-robot bind button, and Qt drag-to-timeline."""

    editRequested = Signal(int)
    deleteRequested = Signal(int)
    visibilityToggled = Signal(int, bool)
    bindRobotsRequested = Signal(int)

    def __init__(
        self,
        traj: TrajectoryEntity,
        target_map: Dict[int, str],
        mime_type: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.traj = traj
        self._mime_type = mime_type
        self._drag_start: Optional[QPoint] = None
        self.setFixedHeight(34)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setStyleSheet(
            f"TrajectoryRowWidget {{ background: {C_CARD}; border: 1px solid {LINE}; border-radius: 4px; }}"
            f"TrajectoryRowWidget:hover {{ background: {C_CONTROL_HOVER}; }}"
        )
        hl = QHBoxLayout(self)
        hl.setContentsMargins(6, 0, 4, 0)
        hl.setSpacing(4)

        self.vis_chk = QCheckBox(self)
        self.vis_chk.setChecked(traj.visible_on_map)
        self.vis_chk.setToolTip("显示 / 隐藏该轨迹在 2D/3D 地图上的预览")
        self.vis_chk.toggled.connect(lambda ch: self.visibilityToggled.emit(self.traj.id or 0, ch))
        hl.addWidget(self.vis_chk)

        no_lbl = QLabel(f"#{traj.no}", self)
        no_lbl.setStyleSheet(f"font-family: {FONT_MONO}; font-size: 11px; color: {C_TEXT_2}; border: none;")
        hl.addWidget(no_lbl)

        name_lbl = QLabel(traj.name, self)
        name_lbl.setStyleSheet(f"font-size: 12px; color: {C_TEXT_1}; border: none;")
        hl.addWidget(name_lbl, 1)

        labels = [target_map.get(n, f"#{n}") for n in traj.bound_track_nos]
        bind_txt = ",".join(labels[:2]) + ("+" if len(labels) > 2 else "") if labels else "绑定"
        self.bind_btn = UButton(bind_txt, variant="default", size="xs", tooltip="绑定给一个或多个机器人", parent=self)
        self.bind_btn.setFixedHeight(22)
        if labels:
            self.bind_btn.setStyleSheet(
                f"background: {C_ACCENT_DIM}; color: {C_TEXT_1}; border: 1px solid {LINE}; border-radius: 4px; padding: 0 5px; font-size: 10px;"
            )
        else:
            self.bind_btn.setStyleSheet(
                f"background: {C_CONTROL}; color: {C_TEXT_2}; border: 1px solid {LINE}; border-radius: 4px; padding: 0 5px; font-size: 10px;"
            )
        self.bind_btn.clicked.connect(lambda: self.bindRobotsRequested.emit(self.traj.id or 0))
        hl.addWidget(self.bind_btn)

        if traj.control_points:
            ep = traj.control_points[-1]
            badge_txt = f"({ep.x:.1f},{ep.y:.1f})"
        else:
            badge_txt = "导航点"
        hl.addWidget(UBadge(badge_txt, tone="neutral", parent=self))

        edit_b = UIconButton("edit", tooltip="编辑 2D 样条", size=20, color=C_TEXT_2, parent=self)
        edit_b.clicked.connect(lambda: self.editRequested.emit(self.traj.id or 0))
        hl.addWidget(edit_b)

        del_b = UIconButton("trash", tooltip="删除轨迹", size=20, color=C_TEXT_2, parent=self)
        del_b.clicked.connect(lambda: self.deleteRequested.emit(self.traj.id or 0))
        hl.addWidget(del_b)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_start = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
        if self._drag_start and (e.position().toPoint() - self._drag_start).manhattanLength() >= 6:
            drag = QDrag(self)
            mime = QMimeData()
            payload = {
                "block_type": "trajectory",
                "ref_id": self.traj.id or 0,
                "code_no": str(self.traj.no),
                "title": self.traj.name,
                "duration": float(self.traj.duration),
            }
            mime.setData(self._mime_type, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.CopyAction)
            self._drag_start = None

    def mouseDoubleClickEvent(self, _e) -> None:
        self.editRequested.emit(self.traj.id or 0)
