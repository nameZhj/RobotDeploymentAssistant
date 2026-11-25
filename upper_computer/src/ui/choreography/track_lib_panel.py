# @file: src/ui/choreography/track_lib_panel.py
# @brief: Right-Column Trajectory Library with collapsible groups, track binding, drag-to-timeline, and JSON I/O.
# @exports: TrackLibPanel, BLOCK_MIME_TYPE

from __future__ import annotations

import json
from typing import Dict, List
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QInputDialog,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.core.event_bus import StudioEvent
from src.domain.trajectory_entities import TrajectoryEntity, TrajectoryGroupEntity
from src.services.studio_state_service import StudioStateService
from src.ui.choreography.track_lib_row import BindRobotsDialog, TrajectoryRowWidget
from src.ui.design_system.u_buttons import UIconButton
from src.ui.design_system.u_panels import UCollapsibleGroup, UEmpty, UPanel

BLOCK_MIME_TYPE = "application/x-studio-block"


class TrackLibPanel(UPanel):
    """Right-top Trajectory Library panel (groups, track binding, 2D draw modal, JSON export)."""

    def __init__(self, state: StudioStateService, parent=None) -> None:
        super().__init__(title="轨迹库", header_widgets=[], parent=parent)
        self.state = state
        self.body_layout.setContentsMargins(6, 6, 6, 6)

        add_b = UIconButton("plus", tooltip="新建 2D 轨迹", size=24, parent=self)
        add_b.clicked.connect(self.open_new_trajectory)
        grp_b = UIconButton("folder", tooltip="新建轨迹分组", size=24, parent=self)
        grp_b.clicked.connect(self._create_group)
        imp_b = UIconButton("upload", tooltip="导入 JSON 工程", size=24, parent=self)
        imp_b.clicked.connect(self._import_json)
        exp_b = UIconButton("save", tooltip="导出 JSON 工程", size=24, parent=self)
        exp_b.clicked.connect(self._export_json)

        hdr = self.header_bar.layout()
        for b in (add_b, grp_b, imp_b, exp_b):
            hdr.addWidget(b)

        self.scroll = QScrollArea(self.body_widget)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = QWidget(self.scroll)
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(6)
        self.scroll.setWidget(self.container)
        self.body_layout.addWidget(self.scroll, 1)

        state.bus.subscribe(StudioEvent.TRAJECTORY_LIB_UPDATED, lambda _p: self.refresh())
        state.bus.subscribe(StudioEvent.SCENE_CHANGED, lambda _p: self.refresh())
        state.bus.subscribe(StudioEvent.TASK_SWITCHED, lambda _p: self.refresh())
        self.refresh()

    def refresh(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        groups = self.state.list_groups()
        all_trajs = list(self.state.trajectories.values())
        by_group: Dict[int, List[TrajectoryEntity]] = {}
        for t in all_trajs:
            by_group.setdefault(t.group_id, []).append(t)

        if not groups:
            self.list_layout.addWidget(UEmpty("暂无轨迹分组", "点击右上角 + 新建轨迹", self.container))
        for grp in groups:
            gid = grp.id or 1
            items = sorted(by_group.get(gid, []), key=lambda x: x.no)
            card = UCollapsibleGroup(
                group_id=gid,
                name=grp.name,
                robot_count=grp.robot_count,
                item_count=len(items),
                bound_track_no=grp.bound_track_no,
                expanded=True,
                parent=self.container,
            )
            card.bindTrackClicked.connect(self._cycle_bind_track)
            card.renameClicked.connect(self._rename_group)
            card.deleteClicked.connect(self._delete_group)
            target_map = {t.track_no: t.target_id or f"M{t.track_no}" for t in self.state.tracks}
            for tr in items:
                row = TrajectoryRowWidget(tr, target_map, BLOCK_MIME_TYPE, card)
                row.editRequested.connect(self.open_edit_trajectory)
                row.deleteRequested.connect(self._delete_trajectory)
                row.visibilityToggled.connect(self._toggle_traj_visibility)
                row.bindRobotsRequested.connect(self._open_bind_robots)
                card.content_layout.addWidget(row)
            self.list_layout.addWidget(card)
        self.list_layout.addStretch(1)

    def _toggle_traj_visibility(self, traj_id: int, visible: bool) -> None:
        self.state.set_trajectory_visibility(traj_id, visible)

    def _open_bind_robots(self, traj_id: int) -> None:
        traj = self.state.trajectories.get(traj_id)
        if traj is None:
            return
        dlg = BindRobotsDialog(traj, self.state.tracks, self)
        if dlg.exec():
            nos = dlg.selected_track_nos()
            added = self.state.bind_trajectory_tracks(traj_id, nos, sync_to_timeline=dlg.sync_timeline_chk.isChecked())
            self.state.notify(f"已将 [{traj.name}] 绑定给 {len(nos)} 台机器人（同步写入 {added} 块）", "ok")

    def open_new_trajectory(self) -> None:
        from src.ui.modals.trajectory_editor_modal import TrajectoryEditorModal
        dlg = TrajectoryEditorModal(self.state, None, parent=self)
        dlg.exec()

    def open_edit_trajectory(self, traj_id: int) -> None:
        traj = self.state.trajectories.get(traj_id)
        if traj:
            from src.ui.modals.trajectory_editor_modal import TrajectoryEditorModal
            dlg = TrajectoryEditorModal(self.state, traj, parent=self)
            dlg.exec()

    def _delete_trajectory(self, traj_id: int) -> None:
        refs = self.state.traj_repo.count_block_references([traj_id])
        if refs > 0:
            ans = QMessageBox.question(
                self, "删除确认", f"该轨迹已被任务链引用 ({refs} 处)，删除后对应节点也将清理，是否继续？"
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
        self.state.traj_repo.delete_trajectory(traj_id)
        self.state.reload_all()
        self.state.bus.publish(StudioEvent.TRAJECTORY_LIB_UPDATED, traj_id)
        self.state.bus.publish(StudioEvent.TIMELINE_UPDATED, None)

    def _create_group(self) -> None:
        name, ok = QInputDialog.getText(self, "新建轨迹分组", "分组名称:")
        if ok and name.strip():
            self.state.traj_repo.upsert_group(
                TrajectoryGroupEntity(scene_id=self.state.scene.id or 1, name=name.strip(), robot_count=1)
            )
            self.state.bus.publish(StudioEvent.TRAJECTORY_LIB_UPDATED, None)

    def _rename_group(self, group_id: int) -> None:
        grp = next((g for g in self.state.list_groups() if g.id == group_id), None)
        if grp is None:
            return
        name, ok = QInputDialog.getText(self, "重命名轨迹分组", "新分组名称:", text=grp.name)
        if ok and name.strip() and name.strip() != grp.name:
            self.state.traj_repo.rename_group(group_id, name.strip())
            self.state.bus.publish(StudioEvent.TRAJECTORY_LIB_UPDATED, None)
            self.state.notify(f"分组已重命名为 [{name.strip()}]", "ok")

    def _cycle_bind_track(self, group_id: int) -> None:
        groups = self.state.list_groups()
        grp = next((g for g in groups if g.id == group_id), None)
        if grp is None or not self.state.tracks:
            return
        cur = grp.bound_track_no or 0
        next_no = (cur % len(self.state.tracks)) + 1
        grp.bound_track_no = next_no
        self.state.traj_repo.upsert_group(grp)
        self.refresh()
        self.state.notify(f"分组 [{grp.name}] 已绑定到轨道 {next_no}", "info")

    def _delete_group(self, group_id: int) -> None:
        if len(self.state.list_groups()) <= 1:
            self.state.notify("至少保留一个轨迹分组", "warn")
            return
        ids = [t.id for t in self.state.trajectories.values() if t.group_id == group_id and t.id is not None]
        refs = self.state.traj_repo.count_block_references(ids)
        if refs > 0 and QMessageBox.question(
            self, "删除分组确认", f"分组内有 {refs} 处任务链引用节点，删除后将连带清除，继续？"
        ) != QMessageBox.StandardButton.Yes:
            return
        self.state.traj_repo.delete_group(group_id)
        self.state.reload_all()
        self.state.bus.publish(StudioEvent.TRAJECTORY_LIB_UPDATED, None)
        self.state.bus.publish(StudioEvent.TIMELINE_UPDATED, None)
        self.refresh()

    def _import_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "导入工程 JSON", "", "JSON (*.json)")
        if not path:
            return
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.state.json_codec.import_task_from_dict(data)
        self.state.reload_all()
        self.state.bus.publish(StudioEvent.SCENE_CHANGED, None)
        self.state.notify("已从 JSON 导入轨迹与任务链", "ok")

    def _export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出工程 JSON", "choreo_export.json", "JSON (*.json)")
        if not path:
            return
        payload = self.state.json_codec.export_task_to_dict()
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        self.state.notify(f"已导出工程到 {path}", "ok")
