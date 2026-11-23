# @file: src/ui/modals/trajectory_editor_modal.py
# @brief: UniUni TaskTrajectory dialog supporting 2D spline drawing, timing, orientation, CSV preview, delete, and HTTP upload.
# @exports: TrajectoryEditorModal

from __future__ import annotations

import copy
from typing import List, Optional
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.core.event_bus import StudioEvent
from src.domain.trajectory_entities import ControlPoint2D, TrajectoryEntity
from src.math.trajectory_sampler import sample_trajectory_50fps
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.tokens import C_CARD, C_TEXT_2, C_WARN, FONT_MONO, LINE
from src.ui.design_system.u_buttons import UBadge, UButton, USegmented
from src.ui.design_system.u_dialog import UDialog
from src.ui.design_system.u_inputs import UInputNumber, USelect
from src.ui.modals.trajectory_draw_canvas import TrajectoryDrawCanvas


class TrajectoryEditorModal(UDialog):
    """Modal CAD workspace matching UniUni AddTrajectoryItem / TaskTrajectory settings."""

    def __init__(
        self,
        state: StudioStateService,
        traj: Optional[TrajectoryEntity] = None,
        initial_points: Optional[List[ControlPoint2D]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(
            title="编辑轨迹" if traj else "任务轨迹参数与绘制保存",
            width=980,
            height=650,
            confirm_text="确认保存",
            cancel_text="取消",
            parent=parent,
        )
        self.state = state
        groups = state.list_groups()
        default_gid = groups[0].id if groups else 1
        default_no = state.traj_repo.next_trajectory_no(groups[0].bound_track_no or 1 if groups else 1)
        self._is_existing = traj is not None and traj.id is not None
        if traj is not None:
            self.traj = copy.deepcopy(traj)
        else:
            self.traj = TrajectoryEntity(
                group_id=default_gid or 1,
                no=default_no,
                name="新舞台轨迹",
                duration=6.0,
                control_points=copy.deepcopy(initial_points) if initial_points else [],
            )
        self.saved_traj: Optional[TrajectoryEntity] = None

        row = QHBoxLayout()
        row.setSpacing(10)

        left_col = QVBoxLayout()
        left_col.setSpacing(6)
        tools = QHBoxLayout()
        self.tool_seg = USegmented(["点击落点", "自由手绘", "拖拽调整"], default="点击落点", parent=self)
        self.tool_seg.currentChanged.connect(self._on_tool_changed)
        tools.addWidget(self.tool_seg)
        undo_btn = UButton("撤销一点", variant="default", size="xs", icon_name="undo", parent=self)
        undo_btn.clicked.connect(lambda: self.canvas.undo_point())
        clr_btn = UButton("清空", variant="danger", size="xs", icon_name="trash", parent=self)
        clr_btn.clicked.connect(lambda: self.canvas.clear_points())
        tools.addStretch(1)
        tools.addWidget(undo_btn)
        tools.addWidget(clr_btn)
        left_col.addLayout(tools)

        self.canvas = TrajectoryDrawCanvas(state, self.traj, self)
        self.canvas.pointsChanged.connect(self._recalc_metrics)
        left_col.addWidget(self.canvas, 1)
        row.addLayout(left_col, 1)

        right_card = QWidget(self)
        right_card.setFixedWidth(310)
        right_card.setStyleSheet(f"background: {C_CARD}; border: 1px solid {LINE}; border-radius: 6px;")
        rl = QVBoxLayout(right_card)
        rl.setContentsMargins(12, 10, 12, 10)
        rl.setSpacing(7)

        form = QFormLayout()
        form.setSpacing(7)
        self.name_edit = QLineEdit(self.traj.name, right_card)
        self.no_edit = QLineEdit(str(self.traj.no), right_card)
        self.no_edit.setStyleSheet(f"font-family: {FONT_MONO};")
        self.group_sel = USelect([(g.name, g.id) for g in groups] or [("默认分组", 1)], right_card)
        self.group_sel.set_current_data(self.traj.group_id)
        self.interp_sel = USelect([("uniform (S曲线匀加减速)", "uniform"), ("linear (直线段)", "linear")], right_card)
        self.interp_sel.set_current_data(self.traj.interpolation_mode)
        self.run_sel = USelect([("走跑 (默认 504)", 504), ("稳健步行 (501)", 501), ("快速巡航 (508)", 508)], right_card)
        self.run_sel.set_current_data(self.traj.run_mode)

        self.dur_spin = UInputNumber(self.traj.duration, 0.5, 300.0, 0.5, 2, unit="s", parent=right_card)
        self.acc_spin = UInputNumber(self.traj.max_acc, 0.2, 5.0, 0.1, 2, unit="m/s²", parent=right_card)
        self.hold_chk = QCheckBox("保持固定朝向 (holdDirection)", right_card)
        self.hold_chk.setChecked(self.traj.hold_direction)
        self.hold_yaw_spin = UInputNumber(self.traj.hold_yaw, -6.28, 6.28, 0.1, 2, unit="rad", parent=right_card)
        self.end_turn_chk = QCheckBox("末端独立转身 (endTurn)", right_card)
        self.end_turn_chk.setChecked(self.traj.end_turn)
        self.end_yaw_spin = UInputNumber(self.traj.end_yaw, -6.28, 6.28, 0.1, 2, unit="rad", parent=right_card)

        form.addRow("轨迹名称", self.name_edit)
        form.addRow("轨迹编号", self.no_edit)
        form.addRow("归属分组", self.group_sel)
        form.addRow("插值算法", self.interp_sel)
        form.addRow("运行模式", self.run_sel)
        form.addRow("执行时长", self.dur_spin)
        form.addRow("最大加速度", self.acc_spin)
        rl.addLayout(form)
        rl.addWidget(self.hold_chk)
        rl.addWidget(self.hold_yaw_spin)
        rl.addWidget(self.end_turn_chk)
        rl.addWidget(self.end_yaw_spin)

        self.metrics_lbl = QLabel("航程: 0.00m | T_min: 0.00s", right_card)
        self.metrics_lbl.setStyleSheet(f"color: {C_TEXT_2}; font-size: 11px; font-family: {FONT_MONO};")
        rl.addWidget(self.metrics_lbl)

        btn_row1 = QHBoxLayout()
        self.fit_tmin_btn = UButton("对齐最短时长", variant="default", size="xs", parent=right_card)
        self.fit_tmin_btn.clicked.connect(self._apply_tmin)
        self.csv_btn = UButton("查看轨迹数据", variant="default", size="xs", icon_name="file", parent=right_card)
        self.csv_btn.clicked.connect(self._show_csv_dialog)
        btn_row1.addWidget(self.fit_tmin_btn)
        btn_row1.addWidget(self.csv_btn)
        rl.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        self.http_btn = UButton("HTTP 上传", variant="default", size="xs", icon_name="upload", parent=right_card)
        self.http_btn.clicked.connect(self._upload_http)
        self.del_btn = UButton("删除轨迹", variant="danger", size="xs", icon_name="trash", parent=right_card)
        self.del_btn.setVisible(self._is_existing)
        self.del_btn.clicked.connect(self._on_delete)
        btn_row2.addWidget(self.http_btn)
        btn_row2.addWidget(self.del_btn)
        rl.addLayout(btn_row2)

        self.http_badge = UBadge("本地已准备", tone="neutral", parent=right_card)
        rl.addWidget(self.http_badge)
        rl.addStretch(1)
        row.addWidget(right_card)

        self.body_layout.addLayout(row, 1)
        self.dur_spin.valueChanged.connect(lambda _v: self._sync_fields_and_preview())
        self.acc_spin.valueChanged.connect(lambda _v: self._sync_fields_and_preview())
        self.interp_sel.currentIndexChanged.connect(lambda _i: self._sync_fields_and_preview())
        if self.confirm_btn:
            self.confirm_btn.clicked.disconnect()
            self.confirm_btn.clicked.connect(self._on_save)
        self._recalc_metrics()

    def _on_tool_changed(self, txt: str) -> None:
        self.canvas.set_tool({"点击落点": "click", "自由手绘": "brush", "拖拽调整": "move"}.get(txt, "click"))

    def _sync_fields_and_preview(self) -> None:
        self.traj.name = self.name_edit.text().strip() or "未命名轨迹"
        try:
            self.traj.no = int(self.no_edit.text().strip())
        except ValueError:
            pass
        self.traj.group_id = int(self.group_sel.current_data() or 1)
        self.traj.interpolation_mode = str(self.interp_sel.current_data() or "uniform")
        self.traj.run_mode = int(self.run_sel.current_data() or 504)
        self.traj.duration = max(0.5, self.dur_spin.value())
        self.traj.max_acc = max(0.2, self.acc_spin.value())
        self.traj.hold_direction = self.hold_chk.isChecked()
        self.traj.hold_yaw = self.hold_yaw_spin.value()
        self.traj.end_turn = self.end_turn_chk.isChecked()
        self.traj.end_yaw = self.end_yaw_spin.value()
        self.canvas.refresh_preview()
        self._recalc_metrics()

    def _recalc_metrics(self) -> None:
        arr, m = sample_trajectory_50fps(self.traj)
        warn = " (! 过快)" if self.traj.duration < m.min_execution_time else ""
        self.metrics_lbl.setText(f"航程:{m.arc_length:.2f}m | T_min:{m.min_execution_time:.2f}s | {len(arr)}帧{warn}")
        self.metrics_lbl.setStyleSheet(f"color: {C_WARN if warn else C_TEXT_2}; font-size: 11px; font-family: {FONT_MONO};")

    def _apply_tmin(self) -> None:
        _, m = sample_trajectory_50fps(self.traj)
        self.dur_spin.setValue(max(1.0, round(m.min_execution_time * 1.15, 1)))
        self._sync_fields_and_preview()

    def _show_csv_dialog(self) -> None:
        self._sync_fields_and_preview()
        sample_trajectory_50fps(self.traj)
        dlg = UDialog("50FPS 轨迹采样点数据 (t, x, y, yaw)", width=520, height=380, confirm_text="关闭", cancel_text="", parent=self)
        txt = QPlainTextEdit(self.traj.point_data_csv or "暂无控制点采样数据", dlg)
        txt.setReadOnly(True)
        txt.setStyleSheet(f"font-family: {FONT_MONO}; font-size: 11px;")
        dlg.body_layout.addWidget(txt, 1)
        dlg.exec()

    def _upload_http(self) -> None:
        self._sync_fields_and_preview()
        sample_trajectory_50fps(self.traj)
        payload = {
            "no": self.traj.no, "name": self.traj.name, "duration": self.traj.duration,
            "runMode": self.traj.run_mode, "pointDataCsv": self.traj.point_data_csv,
            "points": [{"x": p.x, "y": p.y, "yaw": p.yaw} for p in self.traj.control_points],
        }
        ip = self.state.tracks[0].robot_ip if self.state.tracks else "192.168.123.164"
        tgt = self.state.tracks[0].target_id if self.state.tracks else "A"
        res = self.state.http_client.upload_payload(ip, tgt, payload)
        self.http_badge.setText(f"[{res.mode}] {res.message[:24]}")
        self.http_badge.set_tone("ok" if res.success else "warn")

    def _on_delete(self) -> None:
        if self.traj.id is None:
            return
        if QMessageBox.question(self, "确认删除", f"删除轨迹 [{self.traj.name}] 将同步清除任务链关联节点，是否继续？") == QMessageBox.StandardButton.Yes:
            self.state.traj_repo.delete_trajectory(self.traj.id)
            self.state.reload_all()
            self.state.bus.publish(StudioEvent.TRAJECTORY_LIB_UPDATED, self.traj.id)
            self.state.bus.publish(StudioEvent.TIMELINE_UPDATED, None)
            self.reject()

    def _on_save(self) -> None:
        self._sync_fields_and_preview()
        sample_trajectory_50fps(self.traj)
        self.saved_traj = self.state.traj_repo.upsert_trajectory(self.traj)
        self.state.reload_all()
        self.state.bus.publish(StudioEvent.TRAJECTORY_LIB_UPDATED, self.saved_traj.id)
        self.state.notify(f"已保存轨迹 #{self.saved_traj.no} {self.saved_traj.name}", "ok")
        self.accept()
