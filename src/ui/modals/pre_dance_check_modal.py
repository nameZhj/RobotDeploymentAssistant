# @file: src/ui/modals/pre_dance_check_modal.py
# @brief: Dual-mode Pre-performance Audit Checklist and Cluster HTTP Choreography Uploader dialog.
# @exports: PreDanceCheckModal

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QTableWidgetItem, QWidget

from src.core.settings import get_settings, save_settings
from src.protocol.timeline_lrmp_compiler import TimelineLrmpCompiler
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.u_buttons import UBadge, UButton
from src.ui.design_system.u_dialog import UDialog
from src.ui.design_system.u_inputs import UInputNumber
from src.ui.design_system.u_panels import UTable


class PreDanceCheckModal(UDialog):
    """Validates swarm safety margins & LRMP script (mode='check') or uploads cluster JSON via HTTP (mode='deploy')."""

    def __init__(self, state: StudioStateService, parent: QWidget | None = None, mode: str = "check") -> None:
        is_deploy = mode == "deploy"
        title = "HTTP 集群轨迹/编排下发（含虚拟接口）" if is_deploy else "演出前安全检查与 LRMP 审计"
        super().__init__(title, width=690, height=460, confirm_text="关闭", cancel_text="", parent=parent)
        self.state = state

        checks = self._run_checks()
        passed_all = all(ok for _, ok, _ in checks)

        top = QHBoxLayout()
        top.addWidget(QLabel("审计结论:", self))
        top.addWidget(UBadge("通过 · 允许下发" if passed_all else "存在异常/缺轨道", tone="ok" if passed_all else "danger", parent=self))
        top.addStretch(1)

        cfg = get_settings().virtual_interfaces
        self.port_spin = UInputNumber(float(cfg.http_default_port), 80, 65535, 1, 0, "端口", self)
        self.port_spin.setFixedWidth(120)
        self.virt_chk = QCheckBox("虚拟接口降级", self)
        self.virt_chk.setChecked(cfg.http_upload_virtual_fallback)
        top.addWidget(self.port_spin)
        top.addWidget(self.virt_chk)

        self.push_btn = UButton("下发全队方案 (HTTP)", variant="primary", size="sm", icon_name="upload", parent=self)
        self.push_btn.clicked.connect(self._push_cluster)
        top.addWidget(self.push_btn)
        self.body_layout.addLayout(top)

        self.table = UTable(["检查项 / 目标设备", "状态", "详情 / 回执"], stretch_col=2, parent=self)
        self._fill_checks(checks)
        self.body_layout.addWidget(self.table, 1)

    def _fill_checks(self, checks) -> None:
        self.table.setRowCount(len(checks))
        for r, (name, ok, detail) in enumerate(checks):
            self.table.setItem(r, 0, QTableWidgetItem(name))
            self.table.setItem(r, 1, QTableWidgetItem("通过" if ok else "异常"))
            self.table.setItem(r, 2, QTableWidgetItem(detail))

    def _run_checks(self):
        if not self.state.tracks:
            return [("机器人轨道检查", False, "当前尚未添加任何真实机器人轨道，请先添加轨道后再检查或下发。")]
        coll_dicts = [
            {"start": c.start_time, "end": c.end_time, "robots": f"{c.track_a}<->{c.track_b}"}
            for c in self.state.collisions
        ]
        report = TimelineLrmpCompiler.validate_before_launch(
            self.state.tracks, self.state.blocks, collision_intervals=coll_dicts
        )
        plan = TimelineLrmpCompiler.compile_plan(self.state.tracks, self.state.blocks)
        n_coll = len(self.state.collisions)
        rows = [
            ("集群空间安全距离", n_coll == 0, f"检测到 {n_coll} 处碰撞风险区间" if n_coll else "全时段安全无碰撞"),
            ("轨道合法性与重叠检查", report.passed, "; ".join(report.issues) if report.issues else "全部轨道及时间块校验通过"),
            ("LRMP V1.0-R3 指令编译", True, f"已生成 {len(plan.commands)} 条演出帧 ({len(plan.prep_frames)} 台PREP)"),
        ]
        if report.warnings:
            rows.append(("编排提示", True, "; ".join(report.warnings)))
        return rows

    def _push_cluster(self) -> None:
        if not self.state.tracks:
            self.state.notify("暂无真实机器人轨道，无法下发 HTTP 方案", "warn")
            return
        root_cfg = get_settings()
        root_cfg.virtual_interfaces.http_default_port = int(self.port_spin.value())
        root_cfg.virtual_interfaces.http_upload_virtual_fallback = self.virt_chk.isChecked()
        save_settings(root_cfg)
        pkg = self.state.json_codec.export_task_to_dict()
        items = [{"robotIp": t.robot_ip, "targetId": t.target_id, "payload": pkg} for t in self.state.tracks]
        receipts = self.state.http_client.upload_cluster_payloads(items, prefer_virtual=self.virt_chk.isChecked())
        self.table.setRowCount(len(receipts))
        for r, rec in enumerate(receipts):
            self.table.setItem(r, 0, QTableWidgetItem(f"{rec.target_id} ({rec.endpoint})"))
            self.table.setItem(r, 1, QTableWidgetItem(f"成功 [{rec.mode}]" if rec.success else f"失败 [{rec.mode}]"))
            self.table.setItem(r, 2, QTableWidgetItem(rec.message))
        ok_cnt = sum(1 for r in receipts if r.success)
        self.state.notify(f"HTTP 下发完成：{ok_cnt}/{len(receipts)} 台成功", "ok" if ok_cnt == len(receipts) else "warn")
