# @file: src/ui/modals/fragment_save_dialog.py
# @brief: Full CRUD manager for saving, browsing, inserting onto timeline, and deleting choreography fragments.
# @exports: FragmentSaveDialog

from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QLineEdit, QTableWidgetItem, QWidget

from src.domain.timeline_entities import TimelineFragmentEntity
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.tokens import C_TEXT_2
from src.ui.design_system.u_buttons import UButton
from src.ui.design_system.u_dialog import UDialog
from src.ui.design_system.u_inputs import UInputNumber
from src.ui.design_system.u_panels import UTable


class FragmentSaveDialog(UDialog):
    """Captures active blocks into numbered slots and supports restoring or deleting saved snippets."""

    def __init__(self, state: StudioStateService, t_default: float = 0.0, parent: QWidget | None = None) -> None:
        super().__init__(
            "快捷片段管理",
            width=600,
            height=440,
            confirm_text="保存当前片段",
            cancel_text="关闭",
            parent=parent,
            help_text="可保存当前时间线片段，或在列表中选中片段载入至当前位置或删除。",
        )
        self.state = state
        self._t_default = max(0.0, float(t_default))

        form = QFormLayout()
        form.setSpacing(8)
        self.slot_spin = UInputNumber(1, 1, 99, 1, 0, "号槽", self)
        self.name_edit = QLineEdit("任务链片段", self)
        self.t0_spin = UInputNumber(self._t_default, 0.0, 999.0, 0.5, 1, "", self)
        self.t1_spin = UInputNumber(self._t_default + 10.0, 0.5, 999.0, 0.5, 1, "", self)

        form.addRow("目标槽位", self.slot_spin)
        form.addRow("片段名称", self.name_edit)
        form.addRow("起始游标", self.t0_spin)
        form.addRow("结束游标", self.t1_spin)
        self.body_layout.addLayout(form)

        hdr = QLabel("已保存片段库:", self)
        hdr.setStyleSheet(f"color: {C_TEXT_2}; font-size: 11px; margin-top: 6px;")
        self.body_layout.addWidget(hdr)

        self.table = UTable(["槽位", "名称", "类型", "节点数", "创建时间"], stretch_col=1, parent=self)
        self.body_layout.addWidget(self.table, 1)

        ops = QHBoxLayout()
        load_b = UButton("链入当前位置", variant="primary", size="sm", icon_name="play", parent=self)
        load_b.clicked.connect(self._on_load_selected)
        del_b = UButton("删除选中片段", variant="danger", size="sm", icon_name="trash", parent=self)
        del_b.clicked.connect(self._on_delete_selected)
        ops.addWidget(load_b)
        ops.addWidget(del_b)
        ops.addStretch(1)
        self.body_layout.addLayout(ops)

        self._frags: list[TimelineFragmentEntity] = []
        self._reload_table()
        if self.confirm_btn:
            self.confirm_btn.clicked.disconnect()
            self.confirm_btn.clicked.connect(self._on_save)

    def _reload_table(self) -> None:
        self._frags = self.state.map_repo.list_fragments(self.state.scene.id or 1)
        self.table.setRowCount(len(self._frags))
        for r, f in enumerate(self._frags):
            cnt = len(f.payload.get("trackState", []))
            self.table.setItem(r, 0, QTableWidgetItem(f"#{f.slot_no}"))
            self.table.setItem(r, 1, QTableWidgetItem(f.name))
            self.table.setItem(r, 2, QTableWidgetItem("任务链片段"))
            self.table.setItem(r, 3, QTableWidgetItem(f"{cnt} 节点"))
            self.table.setItem(r, 4, QTableWidgetItem(f.created_at))

    def _on_save(self) -> None:
        t0, t1 = min(self.t0_spin.value(), self.t1_spin.value()), max(self.t0_spin.value(), self.t1_spin.value())
        payload = self.state.json_codec.export_task_to_dict(t_start=t0, t_end=t1)
        slot = int(self.slot_spin.value())
        self.state.map_repo.save_fragment(
            TimelineFragmentEntity(
                scene_id=self.state.scene.id or 1,
                slot_no=slot,
                name=self.name_edit.text().strip() or f"片段 {slot}",
                duration=max(0.5, t1 - t0),
                payload=payload,
            )
        )
        self._reload_table()
        self.state.notify(f"已保存片段到 #{slot} 槽位", "ok")

    def _on_load_selected(self) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self._frags)):
            self.state.notify("请先选择要载入的片段", "warn")
            return
        frag = self._frags[row]
        if frag.id is None:
            return
        cnt = self.state.load_fragment_at(frag.id, self.state.playhead_s)
        self.state.notify(f"已向任务链插入 {cnt} 个编排节点 ({frag.name})", "ok" if cnt > 0 else "warn")
        self.accept()

    def _on_delete_selected(self) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self._frags)):
            return
        frag = self._frags[row]
        if frag.id is not None:
            self.state.map_repo.delete_fragment(frag.id)
            self._reload_table()
            self.state.notify(f"已删除片段 #{frag.slot_no} {frag.name}", "info")
