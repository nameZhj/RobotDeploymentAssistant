# @file: src/ui/choreography/batch_choreo_drawer.py
# @brief: Push drawer for batch-appending actions into all active robot task chains.
# @exports: BatchChoreoDrawer

from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QLabel, QWidget

from src.core.event_bus import StudioEvent
from src.domain.timeline_entities import TimelineBlockEntity
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.tokens import C_TEXT_2
from src.ui.design_system.u_buttons import UButton
from src.ui.design_system.u_dialog import UDrawer
from src.ui.design_system.u_inputs import USelect


class BatchChoreoDrawer(UDrawer):
    """Push drawer appending an action/dance uniformly onto all unlocked robot task chains."""

    def __init__(self, state: StudioStateService, parent: QWidget | None = None) -> None:
        super().__init__(title="批量任务链动作编排", width=310, parent=parent)
        self.state = state
        self.hide()

        desc = QLabel("为当前所有激活机器人轨道的任务链批量追加动作节点（前序节点完成后自动触发）：", self)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {C_TEXT_2}; font-size: 11px;")
        self.body_layout.addWidget(desc)

        form = QFormLayout()
        form.setSpacing(8)
        actions = state.action_repo.list_actions()
        self.act_sel = USelect([(f"[{a.no}] {a.name}", a.id) for a in actions], self)
        self.mode_sel = USelect([("追加至任务链末尾", "append"), ("插入至任务链首部", "prepend")], self)
        form.addRow("选择动作", self.act_sel)
        form.addRow("链入方式", self.mode_sel)
        self.body_layout.addLayout(form)

        apply_btn = UButton("批量加入任务链", variant="primary", size="sm", icon_name="check", parent=self)
        apply_btn.clicked.connect(self._apply_batch)
        self.body_layout.addWidget(apply_btn)
        self.body_layout.addStretch(1)
        state.bus.subscribe(StudioEvent.ACTION_LIB_UPDATED, lambda _p: self._reload_actions())

    def _reload_actions(self) -> None:
        actions = self.state.action_repo.list_actions()
        self.act_sel.clear()
        for a in actions:
            self.act_sel.addItem(f"[{a.no}] {a.name}", a.id)

    def _apply_batch(self) -> None:
        if not self.state.tracks:
            self.state.notify("当前没有真实机器人轨道，请先添加轨道", "warn")
            return
        aid = int(self.act_sel.current_data() or 0)
        act = self.state.action_repo.get_action(aid)
        if not act:
            self.state.notify("动作库为空，请先通过 Wi-Fi HTTP 同步真实动作", "warn")
            return
        mode = str(self.mode_sel.current_data() or "append")
        written = 0
        for tr in self.state.tracks:
            if tr.locked or tr.id is None:
                continue
            if mode == "prepend":
                shift = max(0.5, float(act.duration))
                for existing in list(self.state.blocks):
                    if existing.track_id == tr.id and not existing.is_ignored:
                        existing.start_time = round(existing.start_time + shift, 2)
                        self.state.scene_repo.upsert_block(existing)
                slot_t = 0.0
            else:
                slot_t = self.state.next_track_end_time(tr.id)
            blk = TimelineBlockEntity(
                task_id=self.state.task.id or 1,
                track_id=tr.id,
                block_type="action",
                ref_id=act.id or 0,
                code_no=act.lrmp_code or str(act.no),
                title=act.name,
                start_time=slot_t,
                duration=act.duration,
            )
            verb = "首部插入" if mode == "prepend" else "末尾追加"
            self.state.commit_block_change(None, blk, f"批量{verb} {act.name}")
            written += 1
        self.state.notify(f"已批量为 {written} 条轨道的任务链{'首部插入' if mode == 'prepend' else '追加'} {act.name}", "ok")
        self.hide()
