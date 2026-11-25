# @file: src/ui/modals/pre_dance_check_modal.py
# @brief: Pure Wi-Fi HTTP Pre-performance Audit Checklist with background online ROS health probe and Cluster Task-Chain Uploader.
# @exports: PreDanceCheckModal

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple
from PySide6.QtWidgets import QHBoxLayout, QLabel, QTableWidgetItem, QWidget

from src.core.settings import get_settings, save_settings
from src.protocol.robot_http_client import RobotHttpResponse
from src.protocol.timeline_lrmp_compiler import TimelineLrmpCompiler
from src.services.studio_state_service import StudioStateService
from src.ui.common.async_task import TaskHandle, run_in_background
from src.ui.design_system.u_buttons import UBadge, UButton
from src.ui.design_system.u_dialog import UDialog
from src.ui.design_system.u_inputs import UInputNumber
from src.ui.design_system.u_panels import UTable


class PreDanceCheckModal(UDialog):
    """Validates swarm safety, probes live HTTP/ROS health, and uploads sequential task chains via Wi-Fi HTTP."""

    def __init__(self, state: StudioStateService, parent: QWidget | None = None, mode: str = "check") -> None:
        is_deploy = mode == "deploy"
        title = "下发全队任务链" if is_deploy else "演出前预检"
        super().__init__(
            title,
            width=720,
            height=470,
            confirm_text="关闭",
            cancel_text="",
            parent=parent,
            help_text="校验轨道 Wi-Fi IP、碰撞净空与任务链节点完整性；支持在线检测 HTTP/ROS 状态并一键下发。",
        )
        self.state = state

        checks = self._run_checks()
        passed_all = all(ok for _, ok, _ in checks)

        top = QHBoxLayout()
        top.addWidget(QLabel("审计结论:", self))
        self.badge = UBadge("通过 · 允许下发" if passed_all else "存在异常/缺轨道", tone="ok" if passed_all else "danger", parent=self)
        top.addWidget(self.badge)
        top.addStretch(1)

        cfg = get_settings().virtual_interfaces
        self.port_spin = UInputNumber(float(cfg.http_default_port), 80, 65535, 1, 0, "端口", self)
        self.port_spin.setFixedWidth(120)
        top.addWidget(self.port_spin)

        self.probe_btn = UButton("检测在线 (HTTP/ROS)", variant="default", size="sm", icon_name="refresh", parent=self)
        self.probe_btn.clicked.connect(self.run_online_health_check)
        top.addWidget(self.probe_btn)

        self.push_btn = UButton("下发全队任务链 (HTTP)", variant="primary", size="sm", icon_name="upload", parent=self)
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
        missing_ip = [tr.target_id for tr in self.state.tracks if not (tr.robot_ip or "").strip()]
        coll_dicts = [
            {"start": c.start_time, "end": c.end_time, "robots": f"{c.track_a}<->{c.track_b}"}
            for c in self.state.collisions
        ]
        report = TimelineLrmpCompiler.validate_before_launch(
            self.state.tracks, self.state.blocks, collision_intervals=coll_dicts
        )
        active_nodes = [b for b in self.state.blocks if not b.is_ignored]
        action_cnt = sum(1 for b in active_nodes if b.block_type == "action")
        n_coll = len(self.state.collisions)
        rows = [
            ("Wi-Fi IP 配置完整性", not missing_ip, "全部轨道已配置无线 IP" if not missing_ip else f"缺少 IP: {', '.join(missing_ip)}"),
            ("集群空间安全距离", n_coll == 0, f"检测到 {n_coll} 处碰撞风险区间" if n_coll else "全时段安全无碰撞"),
            ("任务链节点合法性", report.passed, "; ".join(report.issues) if report.issues else f"共 {len(active_nodes)} 个任务链节点校验通过"),
        ]
        if action_cnt > 0:
            rows.append(("动作槽位提示", True, f"含 {action_cnt} 个舞蹈动作节点（下位机经本机 UDP 运控桥下发）"))
        if report.warnings:
            rows.append(("编排提示", True, "; ".join(report.warnings)))
        return rows

    def run_online_health_check(self) -> Optional[TaskHandle]:
        """Probe /api/v1/health (and UDP /probe if unverified) on all tracks in the background."""
        if not self.state.tracks:
            self.state.notify("暂无真实机器人轨道可检测", "warn")
            return None
        self._persist_port()
        def _probe_bg() -> Dict[str, RobotHttpResponse]:
            results = self.state.fleet_health()
            pending = [
                tr for tr in self.state.tracks
                if (r := results.get(tr.target_id.upper())) and r.ok
                and r.data.get("motion_udp_enabled")
                and not (isinstance(r.data.get("motion_udp"), dict) and r.data["motion_udp"].get("reachable") is True)
            ]
            if pending:
                def _probe_one(tr):
                    tid = tr.target_id.upper()
                    pr = self.state.http_rpc.probe_motion(tr.robot_ip, target_id=tid)
                    return tid, (self.state.http_rpc.health(tr.robot_ip) if pr.ok else None)
                with ThreadPoolExecutor(max_workers=min(8, len(pending))) as pool:
                    for tid, fresh in pool.map(_probe_one, pending):
                        if fresh is not None:
                            results[tid] = fresh
            return results
        return run_in_background(
            _probe_bg,
            on_done=self._on_health_done,
            busy_widgets=[self.probe_btn],
            busy_text="正在后台检测全队 HTTP / ROS / 运控 UDP 状态...",
            notifier=self.state.notify,
        )

    def _on_health_done(self, results: Dict[str, RobotHttpResponse]) -> int:
        rows: List[Tuple[str, bool, str]] = list(self._run_checks())
        ok_cnt = 0
        for tr in self.state.tracks:
            resp = results.get(tr.target_id.upper()) if tr.robot_ip else None
            if resp and resp.ok:
                ok_cnt += 1
                ros_ok = bool(resp.data.get("ros_master_reachable", False))
                nav_ok = bool(resp.data.get("navctl_available", False))
                udp_en = bool(resp.data.get("motion_udp_enabled", False))
                udp_info = resp.data.get("motion_udp") if isinstance(resp.data.get("motion_udp"), dict) else {}
                udp_reach = udp_info.get("reachable")
                udp_txt = "可达" if udp_reach is True else ("超时/未连接" if udp_en else "未启用")
                locked = bool(resp.data.get("safety_locked", False))
                faults = [f for f in (resp.data.get("active_faults") or []) if isinstance(f, dict)]
                fault_txt = ", ".join(f"{f.get('level','')}:{f.get('code','')}" for f in faults) or "无"
                mode_txt = f"{resp.data.get('motion_state') or '-'}/{resp.data.get('nav_input') or '-'}"
                row_ok = ros_ok and (not locked) and (not udp_en or udp_reach is True)
                rows.append((
                    f"在线检测 {tr.target_id} ({tr.robot_ip})",
                    row_ok,
                    f"HTTP在线 | ROS:{'可达' if ros_ok else '不可达'} | navctl:{'可用' if nav_ok else '不可用'} | 运控UDP:{udp_txt} | 姿态:{mode_txt} | 故障:{fault_txt}",
                ))
            else:
                rows.append((f"在线检测 {tr.target_id} ({tr.robot_ip or '未设IP'})", False, resp.message if resp else "未配置 IP"))
        self._fill_checks(rows)
        all_ok = all(ok for _, ok, _ in rows)
        if all_ok:
            self.badge.setText("通过 · 全队在线")
            self.badge.set_tone("ok")
        elif ok_cnt == len(self.state.tracks):
            self.badge.setText("在线异常 · 禁下发")
            self.badge.set_tone("danger")
        else:
            self.badge.setText(f"在线 {ok_cnt}/{len(self.state.tracks)}")
            self.badge.set_tone("warn")
        self.state.notify(f"设备在线预检完成: {ok_cnt}/{len(self.state.tracks)} 台 HTTP 可达", "ok" if ok_cnt == len(self.state.tracks) else "warn")
        return ok_cnt

    def _persist_port(self) -> None:
        root_cfg = get_settings()
        root_cfg.virtual_interfaces.http_default_port = int(self.port_spin.value())
        root_cfg.virtual_interfaces.http_upload_virtual_fallback = False
        save_settings(root_cfg)

    def _push_cluster(self) -> Optional[TaskHandle]:
        if not self.state.tracks:
            self.state.notify("暂无真实机器人轨道，无法下发 HTTP 任务链", "warn")
            return None
        self._persist_port()
        return run_in_background(
            lambda: self.state.compile_and_upload_chains_http(prep=False),
            on_done=self._on_push_done,
            busy_widgets=[self.push_btn],
            busy_text=f"正在后台向 {len(self.state.tracks)} 台机器人下发任务链 (Wi-Fi HTTP)...",
            notifier=self.state.notify,
        )

    def _on_push_done(self, results: List[Dict[str, Any]]) -> None:
        self.table.setRowCount(len(results))
        for r, rec in enumerate(results):
            self.table.setItem(r, 0, QTableWidgetItem(f"{rec['target_id']} ({rec['robot_ip']})"))
            self.table.setItem(r, 1, QTableWidgetItem("成功 [Wi-Fi HTTP]" if rec["upload_ok"] else "失败 [Wi-Fi HTTP]"))
            self.table.setItem(r, 2, QTableWidgetItem(str(rec["message"])))
        ok_cnt = sum(1 for r in results if r["upload_ok"])
        self.state.notify(f"Wi-Fi HTTP 任务链下发完成：{ok_cnt}/{len(results)} 台成功", "ok" if ok_cnt == len(results) else "warn")
