# @file: src/ui/modals/range_export_import_dialog.py
# @brief: Time-range JSON slice exporter and importer for merging choreography sections.
# @exports: RangeExportImportDialog

from __future__ import annotations

import json
from PySide6.QtWidgets import QFileDialog, QFormLayout, QHBoxLayout, QWidget

from src.core.event_bus import StudioEvent
from src.persistence.uniuni_slice_merger import merge_slice_into_current_task
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.u_buttons import UButton
from src.ui.design_system.u_dialog import UDialog
from src.ui.design_system.u_inputs import UInputNumber


class RangeExportImportDialog(UDialog):
    """Exports or imports a specific [t_start, t_end] window of multi-track choreography."""

    def __init__(self, state: StudioStateService, parent: QWidget | None = None) -> None:
        super().__init__("时间区间 JSON 导出与合入", width=440, height=240, confirm_text="关闭", cancel_text="", parent=parent)
        self.state = state
        form = QFormLayout()
        form.setSpacing(10)
        self.t0 = UInputNumber(0.0, 0.0, 999.0, 0.5, 1, "s", self)
        self.t1 = UInputNumber(state.total_duration(), 0.5, 999.0, 0.5, 1, "s", self)
        form.addRow("起始时间", self.t0)
        form.addRow("结束时间", self.t1)
        self.body_layout.addLayout(form)

        row = QHBoxLayout()
        exp_b = UButton("导出区间 JSON", variant="primary", size="sm", icon_name="save", parent=self)
        exp_b.clicked.connect(self._export_slice)
        imp_b = UButton("导入并合入工程", variant="default", size="sm", icon_name="upload", parent=self)
        imp_b.clicked.connect(self._import_slice)
        row.addWidget(exp_b)
        row.addWidget(imp_b)
        self.body_layout.addLayout(row)

    def _export_slice(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, "导出时间区间 JSON", "slice_export.json", "JSON (*.json)")
        if not p:
            return
        data = self.state.json_codec.export_task_to_dict(t_start=self.t0.value(), t_end=self.t1.value())
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        self.state.notify(f"已导出区间 [{self.t0.value():.1f}s - {self.t1.value():.1f}s]", "ok")

    def _import_slice(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "导入区间 JSON", "", "JSON (*.json)")
        if not p:
            return
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        added = merge_slice_into_current_task(self.state, data, offset_s=self.t0.value())
        self.state.reload_all()
        self.state.bus.publish(StudioEvent.TIMELINE_UPDATED, None)
        self.state.bus.publish(StudioEvent.TRACKS_UPDATED, None)
        self.state.notify(f"已合入 {added} 个任务链节点", "ok")
        self.accept()
