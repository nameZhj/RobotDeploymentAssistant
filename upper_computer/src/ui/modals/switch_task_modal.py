# @file: src/ui/modals/switch_task_modal.py
# @brief: Task selector modal supporting task creation, switching, and deletion.
# @exports: SwitchTaskModal

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QInputDialog, QListWidget, QListWidgetItem, QWidget

from src.core.event_bus import StudioEvent
from src.domain.scene_entities import TaskEntity
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.u_buttons import UButton
from src.ui.design_system.u_dialog import UDialog


class SwitchTaskModal(UDialog):
    """Manage choreography tasks inside the active scene cleanly (0 demo tracks)."""

    def __init__(self, state: StudioStateService, parent: QWidget | None = None) -> None:
        super().__init__("任务管理与切换", width=460, height=340, confirm_text="切换至选中任务", parent=parent)
        self.state = state
        self.list_w = QListWidget(self)
        self.body_layout.addWidget(self.list_w, 1)

        btns = QHBoxLayout()
        new_b = UButton("新建空白任务", variant="default", size="sm", icon_name="plus", parent=self)
        new_b.clicked.connect(self._create_task)
        ren_b = UButton("重命名", variant="default", size="sm", icon_name="edit", parent=self)
        ren_b.clicked.connect(self._rename_task)
        del_b = UButton("删除选中", variant="danger", size="sm", icon_name="trash", parent=self)
        del_b.clicked.connect(self._delete_task)
        btns.addWidget(new_b)
        btns.addWidget(ren_b)
        btns.addWidget(del_b)
        btns.addStretch(1)
        self.body_layout.addLayout(btns)

        self._reload_list()
        if self.confirm_btn:
            self.confirm_btn.clicked.disconnect()
            self.confirm_btn.clicked.connect(self._switch_selected)

    def _reload_list(self) -> None:
        self.list_w.clear()
        for t in self.state.scene_repo.list_tasks(self.state.scene.id or 1):
            suffix = " (当前)" if t.id == self.state.task.id else ""
            item = QListWidgetItem(f"{t.name}{suffix} — 任务链工程")
            item.setData(256, t.id)
            self.list_w.addItem(item)
            if t.id == self.state.task.id:
                self.list_w.setCurrentItem(item)

    def _create_task(self) -> None:
        name, ok = QInputDialog.getText(self, "新建空白编排任务", "任务名称:")
        if not ok or not name.strip():
            return
        task = self.state.scene_repo.create_task(
            TaskEntity(scene_id=self.state.scene.id or 1, name=name.strip(), total_duration=30.0)
        )
        self.state.reload_all()
        self.state.bus.publish(StudioEvent.TASK_SWITCHED, task.id)
        self._reload_list()

    def _rename_task(self) -> None:
        cur = self.list_w.currentItem()
        if not cur:
            return
        tid = int(cur.data(256))
        new_name, ok = QInputDialog.getText(self, "重命名任务", "新任务名称:")
        if ok and new_name.strip():
            self.state.scene_repo.rename_task(tid, new_name.strip())
            self.state.reload_all()
            self.state.bus.publish(StudioEvent.TASK_SWITCHED, tid)
            self._reload_list()

    def _delete_task(self) -> None:
        cur = self.list_w.currentItem()
        if not cur or self.list_w.count() <= 1:
            self.state.notify("至少保留一个编排任务", "warn")
            return
        tid = int(cur.data(256))
        self.state.scene_repo.delete_task(tid)
        self.state.reload_all()
        self.state.bus.publish(StudioEvent.TASK_SWITCHED, self.state.task.id)
        self._reload_list()

    def _switch_selected(self) -> None:
        cur = self.list_w.currentItem()
        if cur:
            tid = int(cur.data(256))
            self.state.scene_repo.switch_active_task(self.state.scene.id or 1, tid)
            self.state.reload_all()
            self.state.bus.publish(StudioEvent.TASK_SWITCHED, tid)
        self.accept()
