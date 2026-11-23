# @file: src/ui/choreography/action_lib_panel.py
# @brief: Right-Bottom Action Library listing all 33 LRMP dances & custom CSV/NPZ motions with filter and CRUD.
# @exports: ActionLibPanel

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Optional
from PySide6.QtCore import QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.core.event_bus import StudioEvent
from src.core.paths import get_paths
from src.domain.action_entities import ActionEntity
from src.services.studio_state_service import StudioStateService
from src.ui.choreography.track_lib_panel import BLOCK_MIME_TYPE
from src.ui.design_system.tokens import C_CARD, C_CONTROL_HOVER, C_TEXT_1, C_TEXT_2, FONT_MONO, LINE
from src.ui.design_system.u_buttons import UBadge, UIconButton
from src.ui.design_system.u_dialog import UDialog
from src.ui.design_system.u_inputs import UInputNumber, USearchInput, USelect
from src.ui.design_system.u_panels import UEmpty, UPanel


class _DraggableActionRow(QFrame):
    """Single action item supporting drag onto timeline and custom action edit/delete."""

    editRequested = Signal(object)
    deleteRequested = Signal(int)

    def __init__(self, action: ActionEntity, parent=None) -> None:
        super().__init__(parent)
        self.action = action
        self._drag_start: Optional[QPoint] = None
        self.setFixedHeight(32)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setStyleSheet(
            f"_DraggableActionRow {{ background: {C_CARD}; border: 1px solid {LINE}; border-radius: 4px; }}"
            f"_DraggableActionRow:hover {{ background: {C_CONTROL_HOVER}; }}"
        )
        hl = QHBoxLayout(self)
        hl.setContentsMargins(6, 0, 4, 0)
        hl.setSpacing(5)

        no_lbl = QLabel(str(action.no), self)
        no_lbl.setStyleSheet(f"font-family: {FONT_MONO}; font-size: 11px; color: {C_TEXT_2}; border: none; background: transparent;")
        hl.addWidget(no_lbl)

        name_lbl = QLabel(action.name, self)
        name_lbl.setStyleSheet(f"font-size: 12px; color: {C_TEXT_1}; border: none; background: transparent;")
        hl.addWidget(name_lbl, 1)

        code = action.lrmp_code or action.category
        hl.addWidget(UBadge(code[:12], tone="accent" if action.lrmp_code else "neutral", parent=self))

        ed_b = UIconButton("edit", tooltip="编辑动作参数", size=20, color=C_TEXT_2, parent=self)
        ed_b.clicked.connect(lambda: self.editRequested.emit(self.action))
        dl_b = UIconButton("trash", tooltip="删除动作", size=20, color=C_TEXT_2, parent=self)
        dl_b.clicked.connect(lambda: self.deleteRequested.emit(self.action.id or 0))
        hl.addWidget(ed_b)
        hl.addWidget(dl_b)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_start = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
        if self._drag_start and (e.position().toPoint() - self._drag_start).manhattanLength() >= 6:
            drag = QDrag(self)
            mime = QMimeData()
            payload = {
                "block_type": "action",
                "ref_id": self.action.id or 0,
                "code_no": self.action.lrmp_code or str(self.action.no),
                "title": self.action.name,
                "duration": float(self.action.duration),
            }
            mime.setData(BLOCK_MIME_TYPE, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.CopyAction)
            self._drag_start = None


class ActionLibPanel(UPanel):
    """Right-bottom Action Library populated via Wi-Fi HTTP GET /api/v1/actions/list or local imports."""

    def __init__(self, state: StudioStateService, parent=None) -> None:
        super().__init__(title="动作库 (Wi-Fi HTTP 同步)", header_widgets=[], parent=parent)
        self.state = state
        self.body_layout.setContentsMargins(6, 6, 6, 6)
        self.body_layout.setSpacing(6)

        self.sync_btn = UIconButton("refresh", tooltip="通过无线 Wi-Fi HTTP 从下位机同步真实动作库", size=24, parent=self)
        self.sync_btn.clicked.connect(self._sync_from_http)
        self.header_bar.layout().addWidget(self.sync_btn)

        imp_b = UIconButton("plus", tooltip="导入本地 CSV / NPZ 动作文件", size=24, parent=self)
        imp_b.clicked.connect(self._import_motion_file)
        self.header_bar.layout().addWidget(imp_b)

        flt = QHBoxLayout()
        flt.setSpacing(6)
        self.search_box = USearchInput("搜索动作名称 / 别名...", self.body_widget)
        self.search_box.textChanged.connect(lambda _t: self.refresh())
        self.cat_sel = USelect(
            [("全部分组", "ALL"), ("G1 组", "G1"), ("G2 组", "G2"), ("G3 组", "G3"), ("本地导入", "CUSTOM")],
            self.body_widget,
        )
        self.cat_sel.setFixedWidth(96)
        self.cat_sel.currentIndexChanged.connect(lambda _i: self.refresh())
        flt.addWidget(self.search_box, 1)
        flt.addWidget(self.cat_sel)
        self.body_layout.addLayout(flt)

        self.scroll = QScrollArea(self.body_widget)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = QWidget(self.scroll)
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(4)
        self.scroll.setWidget(self.container)
        self.body_layout.addWidget(self.scroll, 1)

        state.bus.subscribe(StudioEvent.ACTION_LIB_UPDATED, lambda _p: self.refresh())
        self.refresh()

    def refresh(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        kw = self.search_box.text().strip()
        cat = str(self.cat_sel.current_data() or "ALL")
        actions = self.state.action_repo.list_actions(keyword=kw, robot_model="ALL")
        if cat != "ALL":
            actions = [a for a in actions if a.category == cat]

        if not actions:
            self.list_layout.addWidget(
                UEmpty("暂无动作", "请配置机器人 Wi-Fi IP 后点击右上角同步按钮获取真实动作 (HTTP)", self.container)
            )
        for act in actions:
            row = _DraggableActionRow(act, self.container)
            row.editRequested.connect(self._edit_action)
            row.deleteRequested.connect(self._delete_action)
            self.list_layout.addWidget(row)
        self.list_layout.addStretch(1)

    def _sync_from_http(self) -> None:
        self.state.sync_actions_from_http()

    def _sync_from_serial(self) -> None:
        self.state.sync_actions_from_serial()

    def _edit_action(self, act: ActionEntity) -> None:
        dlg = UDialog(f"编辑动作 [{act.no}]", width=380, height=230, confirm_text="保存", parent=self)
        form = QFormLayout()
        n_ed = QLineEdit(act.name, dlg)
        c_ed = QLineEdit(act.lrmp_code, dlg)
        d_sp = UInputNumber(act.duration, 0.5, 300.0, 0.5, 1, "s", dlg)
        form.addRow("动作名称", n_ed)
        form.addRow("LRMP 代码", c_ed)
        form.addRow("持续时长", d_sp)
        dlg.body_layout.addLayout(form)
        if dlg.exec():
            act.name = n_ed.text().strip() or act.name
            act.lrmp_code = c_ed.text().strip().upper() or act.lrmp_code
            act.duration = d_sp.value()
            self.state.action_repo.upsert_action(act)
            self.state.bus.publish(StudioEvent.ACTION_LIB_UPDATED, act.id)
            self.state.notify(f"已更新动作 {act.name}", "ok")

    def _delete_action(self, action_id: int) -> None:
        if action_id <= 0:
            return
        self.state.action_repo.delete_action(action_id)
        self.state.bus.publish(StudioEvent.ACTION_LIB_UPDATED, None)
        self.state.notify("已删除自定义动作", "info")

    def _import_motion_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "导入本地动作文件", "", "Motion Files (*.csv *.npz)")
        if not path:
            return
        src = Path(path)
        dst = get_paths().motions_dir / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        existing = self.state.action_repo.list_actions()
        next_no = max((a.no for a in existing), default=2000) + 1
        rel = dst.relative_to(get_paths().root_dir).as_posix()
        act = ActionEntity(
            no=next_no,
            name=src.stem,
            category="CUSTOM",
            lrmp_code=f"CUSTOM_{src.stem.upper()[:10]}",
            robot_model="G1",
            duration=15.0,
            motion_file_path=rel,
            is_builtin=False,
        )
        self.state.action_repo.upsert_action(act)
        self.state.bus.publish(StudioEvent.ACTION_LIB_UPDATED, act.id)
        self.state.notify(f"已导入本地动作 {act.name}", "ok")
