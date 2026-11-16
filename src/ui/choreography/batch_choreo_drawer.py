# @file: src/ui/choreography/batch_choreo_drawer.py
# @brief: Push drawer for batch-inserting actions or staggered trajectories across all robot tracks.
# @exports: BatchChoreoDrawer

from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QLabel, QWidget

from src.core.event_bus import StudioEvent
from src.domain.timeline_entities import TimelineBlockEntity
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.tokens import C_TEXT_2
from src.ui.design_system.u_buttons import UButton
from src.ui.design_system.u_dialog import UDrawer
from src.ui.design_system.u_inputs import UInputNumber, USelect


class BatchChoreoDrawer(UDrawer):
    """Push drawer applying an action/dance uniformly across selected tracks at once."""

    def __init__(self, state: StudioStateService, parent: QWidget | None = None) -> None:
        super().__init__(title="批量集群动作排布", width=310, parent=parent)
        self.state = state
        self.hide()

        desc = QLabel("为当前所有激活机器人轨道批量添加同步舞蹈或错峰动作：", self)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {C_TEXT_2}; font-size: 11px;")
        self.body_layout.addWidget(desc)

        form = QFormLayout()
        form.setSpacing(8)
        actions = state.action_repo.list_actions()
        self.act_sel = USelect([(f"[{a.no}] {a.name}", a.id) for a in actions], self)
        self.t0_spin = UInputNumber(0.0, 0.0, 999.0, 0.5, 1, "s", self)
        self.stagger_spin = UInputNumber(0.0, 0.0, 20.0, 0.2, 1, "s/台", self)
        form.addRow("选择动作", self.act_sel)
        form.addRow("起始时刻", self.t0_spin)
        form.addRow("依次延迟", self.stagger_spin)
        self.body_layout.addLayout(form)

        apply_btn = UButton("批量写入时间轴", variant="primary", size="sm", icon_name="check", parent=self)
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
            return
        t0 = self.t0_spin.value()
        dt = self.stagger_spin.value()
        written = 0
        for idx, tr in enumerate(self.state.tracks):
            if tr.locked:
                continue
            blk = TimelineBlockEntity(
                task_id=self.state.task.id or 1,
                track_id=tr.id or 1,
                block_type="action",
                ref_id=act.id or 0,
                code_no=act.lrmp_code or str(act.no),
                title=act.name,
                start_time=round(t0 + idx * dt, 2),
                duration=act.duration,
            )
            self.state.commit_block_change(None, blk, f"批量插入 {act.name}")
            written += 1
        self.state.notify(f"已批量为 {written} 条未锁定轨道添加 {act.name}", "ok")
        self.hide()
