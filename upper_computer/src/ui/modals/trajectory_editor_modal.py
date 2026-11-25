# @file: src/ui/modals/trajectory_editor_modal.py
# @brief: Clean ROS-aligned waypoint editor dialog supporting 2D map drawing, real task-chain HTTP upload, and deletion.
# @exports: TrajectoryEditorModal

from __future__ import annotations

import copy
import json
from typing import List, Optional
from PySide6.QtWidgets import (
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
from src.ui.common.async_task import TaskHandle, run_in_background
from src.ui.design_system.tokens import C_CARD, C_TEXT_2, FONT_MONO, LINE
from src.ui.design_system.u_buttons import UBadge, UButton, USegmented
from src.ui.design_system.u_dialog import UDialog
from src.ui.design_system.u_inputs import UInputNumber, USelect
from src.ui.modals.trajectory_draw_canvas import TrajectoryDrawCanvas


class TrajectoryEditorModal(UDialog):
    """Waypoint & navigation-goal editor aligned with real ROS /move_base_simple/goal execution."""

    def __init__(
        self,
        state: StudioStateService,
        traj: Optional[TrajectoryEntity] = None,
        initial_points: Optional[List[ControlPoint2D]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(
            title="编辑航点路线" if traj else "新建航点路线",
            width=960,
            height=620,
            confirm_text="确认保存",
            cancel_text="取消",
            parent=parent,
            help_text="下位机按关键航点顺序执行 /move_base_simple/goal，到达终点后自动触发下一步动作。",
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
                name="导航到点1",
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
        right_card.setFixedWidth(306)
        right_card.setStyleSheet(f"background: {C_CARD}; border: 1px solid {LINE}; border-radius: 6px;")
        rl = QVBoxLayout(right_card)
        rl.setContentsMargins(12, 10, 12, 10)
        rl.setSpacing(8)

        form = QFormLayout()
        form.setSpacing(8)
        self.name_edit = QLineEdit(self.traj.name, right_card)
        self.no_edit = QLineEdit(str(self.traj.no), right_card)
        self.no_edit.setStyleSheet(f"font-family: {FONT_MONO};")
        self.group_sel = USelect([(g.name, g.id) for g in groups] or [("默认分组", 1)], right_card)
        self.group_sel.set_current_data(self.traj.group_id)
        last_yaw = self.traj.control_points[-1].yaw if self.traj.control_points else self.traj.end_yaw
        self.end_yaw_spin = UInputNumber(last_yaw, -6.28, 6.28, 0.1, 2, unit="rad", parent=right_card)
        self.dur_spin = UInputNumber(self.traj.duration, 0.5, 300.0, 0.5, 1, unit="s", parent=right_card)
        self.dur_spin.setToolTip("仅用于上位机预演条比例参考；真机按 ROS 实际到达目标点切换")

        form.addRow("路线名称", self.name_edit)
        form.addRow("路线编号", self.no_edit)
        form.addRow("归属分组", self.group_sel)
        form.addRow("终点朝向", self.end_yaw_spin)
        form.addRow("预演参考时长", self.dur_spin)
        rl.addLayout(form)

        self.metrics_lbl = QLabel("航点数: 0 | 总航程: 0.00m", right_card)
        self.metrics_lbl.setStyleSheet(f"color: {C_TEXT_2}; font-size: 11px; font-family: {FONT_MONO};")
        rl.addWidget(self.metrics_lbl)

        btn_row1 = QHBoxLayout()
        self.csv_btn = UButton("查看 ROS 航点 JSON", variant="default", size="xs", icon_name="file", parent=right_card)
        self.csv_btn.clicked.connect(self._show_waypoints_dialog)
        btn_row1.addWidget(self.csv_btn)
        rl.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        self.http_btn = UButton("HTTP 下发任务链测试", variant="primary", size="xs", icon_name="upload", parent=right_card)
        self.http_btn.clicked.connect(self._upload_http)
        self.del_btn = UButton("删除", variant="danger", size="xs", icon_name="trash", parent=right_card)
        self.del_btn.setVisible(self._is_existing)
        self.del_btn.clicked.connect(self._on_delete)
        btn_row2.addWidget(self.http_btn)
        btn_row2.addWidget(self.del_btn)
        rl.addLayout(btn_row2)

        self.http_badge = UBadge("待下发", tone="neutral", parent=right_card)
        rl.addWidget(self.http_badge)
        rl.addStretch(1)
        row.addWidget(right_card)

        self.body_layout.addLayout(row, 1)
        self.dur_spin.valueChanged.connect(lambda _v: self._sync_fields_and_preview())
        if self.confirm_btn:
            self.confirm_btn.clicked.disconnect()
            self.confirm_btn.clicked.connect(self._on_save)
        self._recalc_metrics()

    def _on_tool_changed(self, txt: str) -> None:
        self.canvas.set_tool({"点击落点": "click", "自由手绘": "brush", "拖拽调整": "move"}.get(txt, "click"))

    def _sync_fields_and_preview(self) -> None:
        self.traj.name = self.name_edit.text().strip() or "未命名航线"
        try:
            self.traj.no = int(self.no_edit.text().strip())
        except ValueError:
            pass
        self.traj.group_id = int(self.group_sel.current_data() or 1)
        self.traj.duration = max(0.5, self.dur_spin.value())
        self.traj.end_yaw = self.end_yaw_spin.value()
        if self.traj.control_points:
            self.traj.control_points[-1].yaw = self.traj.end_yaw
        self.canvas.refresh_preview()
        self._recalc_metrics()

    def _recalc_metrics(self) -> None:
        _, m = sample_trajectory_50fps(self.traj)
        n_wp = len(self.traj.control_points)
        end_txt = f"({self.traj.control_points[-1].x:.2f}, {self.traj.control_points[-1].y:.2f})" if n_wp else "(-)"
        self.metrics_lbl.setText(f"航点数:{n_wp} | 航程:{m.arc_length:.2f}m | 终点:{end_txt}")

    def _build_chain_payload(self, target_id: str, robot_ip: str) -> dict:
        pts = self.traj.control_points or [ControlPoint2D(0.0, 0.0, 0.0)]
        last = pts[-1]
        wps = [{"x": round(float(p.x), 4), "y": round(float(p.y), 4), "yaw": round(float(p.yaw), 4)} for p in pts]
        return {
            "scene_id": self.state.scene.id or 1,
            "plan_id": str(self.traj.no),
            "target_id": target_id,
            "robot_ip": robot_ip,
            "origin_pose": {"x": float(pts[0].x), "y": float(pts[0].y), "yaw": float(pts[0].yaw)},
            "chain_summary": self.traj.name,
            "chain_nodes": [{
                "node_type": "trajectory",
                "title": self.traj.name,
                "target_x": round(float(last.x), 4),
                "target_y": round(float(last.y), 4),
                "target_yaw": round(float(last.yaw), 4),
                "wait_for_arrival": True,
                "waypoints": wps,
            }],
        }

    def _show_waypoints_dialog(self) -> None:
        self._sync_fields_and_preview()
        dlg = UDialog("下位机 ROS 任务链航点载荷预览", width=520, height=360, confirm_text="关闭", cancel_text="", parent=self)
        ip = self.state.tracks[0].robot_ip if self.state.tracks else ""
        tgt = self.state.tracks[0].target_id if self.state.tracks else "A"
        txt = QPlainTextEdit(json.dumps(self._build_chain_payload(tgt, ip), ensure_ascii=False, indent=2), dlg)
        txt.setReadOnly(True)
        txt.setStyleSheet(f"font-family: {FONT_MONO}; font-size: 11px;")
        dlg.body_layout.addWidget(txt, 1)
        dlg.exec()

    def _upload_http(self) -> Optional[TaskHandle]:
        """Upload the waypoint chain to the robot in the background; badge updates when done."""
        self._sync_fields_and_preview()
        if not self.traj.control_points:
            self.http_badge.setText("请先在画布添加至少 1 个航点")
            self.http_badge.set_tone("warn")
            return None
        ip = next((t.robot_ip.strip() for t in self.state.tracks if t.robot_ip), "")
        tgt = next((t.target_id for t in self.state.tracks if t.robot_ip), "A")
        if not ip:
            self.http_badge.setText("未配置机器人 Wi-Fi IP")
            self.http_badge.set_tone("warn")
            return None
        payload = self._build_chain_payload(tgt, ip)
        self.http_badge.setText("[HTTP] 任务链后台下发中...")
        self.http_badge.set_tone("accent")
        return run_in_background(
            lambda: self.state.http_rpc.upload_task_chain(ip, tgt, payload),
            on_done=self._on_upload_done,
            busy_text="正在后台下发轨迹任务链 (Wi-Fi HTTP)...",
            notifier=self.state.notify,
        )

    def _on_upload_done(self, res) -> None:
        self.http_badge.setText(f"[HTTP] {'已下发' if res.ok else res.message[:22]}")
        self.http_badge.set_tone("ok" if res.ok else "warn")

    def _on_delete(self) -> None:
        if self.traj.id is None:
            return
        if QMessageBox.question(self, "确认删除", f"删除航线 [{self.traj.name}] 将同步清除任务链关联节点，是否继续？") == QMessageBox.StandardButton.Yes:
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
        self.state.notify(f"已保存航线 #{self.saved_traj.no} {self.saved_traj.name}", "ok")
        self.accept()
