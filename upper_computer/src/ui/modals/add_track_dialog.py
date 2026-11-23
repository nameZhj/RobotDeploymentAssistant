# @file: src/ui/modals/add_track_dialog.py
# @brief: Modal dialog for adding or editing a real robot timeline track with LRMP uniqueness validation.
# @exports: AddTrackDialog

from __future__ import annotations

import copy
from typing import Optional
from PySide6.QtWidgets import QFormLayout, QLabel, QLineEdit, QWidget

from src.domain.track_entities import TrackEntity, default_target_alias, pick_track_color
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.tokens import C_DANGER
from src.ui.design_system.u_dialog import UDialog
from src.ui.design_system.u_inputs import UInputNumber, USelect


class AddTrackDialog(UDialog):
    """Modal dialog creating or editing a real robot TrackEntity."""

    def __init__(
        self,
        state: StudioStateService,
        parent: Optional[QWidget] = None,
        track: Optional[TrackEntity] = None,
    ) -> None:
        is_edit = track is not None
        super().__init__(
            "编辑机器人轨道" if is_edit else "添加机器人轨道",
            width=430,
            height=380,
            confirm_text="保存修改" if is_edit else "创建轨道",
            parent=parent,
        )
        self.state = state
        self._editing = copy.deepcopy(track) if track else None
        next_no = track.track_no if track else max((t.track_no for t in state.tracks), default=0) + 1
        alias = track.target_id if track else default_target_alias(next_no)

        form = QFormLayout()
        form.setSpacing(8)
        self.name_edit = QLineEdit(track.name if track else f"G1-{next_no:02d}", self)
        self.target_edit = QLineEdit(alias, self)
        self.ip_edit = QLineEdit(track.robot_ip if track else f"192.168.123.{100 + next_no}", self)
        self.model_sel = USelect([("G1-29DOF", "G1-29DOF"), ("G1-Edu", "G1-Edu")], self)
        if track:
            self.model_sel.set_current_data(track.robot_model)
        self.init_x = UInputNumber(track.init_x if track else (next_no - 1) * 1.2 - 1.8, -30.0, 30.0, 0.2, 2, "m", self)
        self.init_y = UInputNumber(track.init_y if track else 0.0, -30.0, 30.0, 0.2, 2, "m", self)
        self.init_yaw = UInputNumber(track.init_yaw if track else 1.5708, -6.28, 6.28, 0.1, 3, "rad", self)

        form.addRow("轨道名称", self.name_edit)
        form.addRow("LRMP 目标符", self.target_edit)
        form.addRow("机器人 IP", self.ip_edit)
        form.addRow("机型", self.model_sel)
        form.addRow("初始 X", self.init_x)
        form.addRow("初始 Y", self.init_y)
        form.addRow("初始朝向", self.init_yaw)
        self.body_layout.addLayout(form)

        self.err_lbl = QLabel("", self)
        self.err_lbl.setWordWrap(True)
        self.err_lbl.setStyleSheet(f"color: {C_DANGER}; font-size: 11px;")
        self.body_layout.addWidget(self.err_lbl)

        if self.confirm_btn:
            self.confirm_btn.clicked.disconnect()
            self.confirm_btn.clicked.connect(self._on_submit)

    def _on_submit(self) -> None:
        if self._editing is not None:
            tr = self._editing
        else:
            next_no = max((t.track_no for t in self.state.tracks), default=0) + 1
            tr = TrackEntity(
                task_id=self.state.task.id or 1,
                track_no=next_no,
                robot_id=f"g1_{next_no:02d}",
                color_hex=pick_track_color(next_no),
            )
        tr.name = self.name_edit.text().strip() or f"G1-{tr.track_no:02d}"
        tr.target_id = self.target_edit.text().strip().upper() or default_target_alias(tr.track_no)
        tr.robot_ip = self.ip_edit.text().strip() or "192.168.123.101"
        tr.robot_model = str(self.model_sel.current_data() or "G1-29DOF")
        tr.init_x = self.init_x.value()
        tr.init_y = self.init_y.value()
        tr.init_yaw = self.init_yaw.value()

        try:
            saved = self.state.upsert_track_validated(tr)
        except ValueError as exc:
            self.err_lbl.setText(str(exc))
            self.state.notify(str(exc), "err")
            return
        verb = "更新" if self._editing else "添加"
        self.state.notify(f"已{verb}轨道 {saved.name} [{saved.target_id}]", "ok")
        self.accept()
