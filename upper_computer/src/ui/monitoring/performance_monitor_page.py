# @file: src/ui/monitoring/performance_monitor_page.py
# @brief: Live Show Monitor executing Wi-Fi HTTP task chains with real ROS pose 3D sync, clearance check, and callbacks.
# @exports: PerformanceMonitorPage

from __future__ import annotations

import math
from typing import Dict, Tuple
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QTableWidgetItem, QVBoxLayout, QWidget

from src.core.event_bus import StudioEvent
from src.core.settings import get_settings
from src.protocol.timeline_lrmp_compiler import TimelineLrmpCompiler
from src.services.playback_coordinator import PlaybackCoordinator
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.tokens import FONT_MONO
from src.ui.design_system.u_buttons import UBadge, UButton
from src.ui.design_system.u_panels import UPanel, UTable
from src.viewport3d.stage_viewport_3d import StageViewport3D


class PerformanceMonitorPage(QWidget):
    """Pure Wi-Fi HTTP live show execution desk synced with real lower-computer ROS poses & callbacks."""

    _callbackSignal = Signal(object)

    def __init__(self, state: StudioStateService, playback: PlaybackCoordinator, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.playback = playback
        self._active_run_id: str = "9001"
        self._health_cache: Dict[str, str] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        bar = UPanel(
            title="演出控制台",
            parent=self,
            help_text="标准调度流程：1. PREP 下发任务链；2. BARRIER 同步就绪；3. PLAY 开始演出；异常时点击 EMERGENCY 急停。",
        )
        bar.setFixedHeight(92)
        bl = QHBoxLayout()
        bl.setSpacing(8)
        self.phase_badge = UBadge("阶段: 待命 (FREE)", tone="neutral", parent=bar.body_widget)
        prep_b = UButton("1. PREP 准备", variant="default", size="sm", parent=bar.body_widget)
        prep_b.clicked.connect(self._cmd_prep)
        bar_b = UButton("2. BARRIER 放行", variant="default", size="sm", parent=bar.body_widget)
        bar_b.clicked.connect(self._cmd_barrier)
        play_b = UButton("3. PLAY 启动", variant="primary", size="sm", icon_name="play", parent=bar.body_widget)
        play_b.clicked.connect(self._cmd_play)
        stop_b = UButton("STOP 停止", variant="default", size="sm", icon_name="stop", parent=bar.body_widget)
        stop_b.clicked.connect(self._cmd_stop)
        emg_b = UButton("EMERGENCY 急停", variant="danger", size="sm", parent=bar.body_widget)
        emg_b.clicked.connect(self._cmd_emergency)
        ping_b = UButton("刷新在线", variant="ghost", size="sm", icon_name="refresh", parent=bar.body_widget)
        ping_b.clicked.connect(self.refresh_fleet_health)

        for w in (self.phase_badge, prep_b, bar_b, play_b, stop_b, emg_b, ping_b):
            bl.addWidget(w)
        bl.addStretch(1)
        bar.body_layout.addLayout(bl)
        root.addWidget(bar)

        mid = QHBoxLayout()
        mid.setSpacing(6)
        vp_panel = UPanel(
            title="3D 演出现场",
            parent=self,
            help_text="优先显示机器人回传的实时 ROS 位姿，未连接时显示仿真预览。",
        )
        self.viewport = StageViewport3D(state, vp_panel.body_widget)
        vp_panel.body_layout.addWidget(self.viewport, 1)
        mid.addWidget(vp_panel, 2)

        right = UPanel(title="机群状态与日志", parent=self)
        right.setFixedWidth(480)
        self.table = UTable(["目标 / IP", "位姿 (X,Y,Yaw)", "安全净空 / 进度", "控制权 / 状态"], stretch_col=2, parent=right.body_widget)
        self.log_box = QPlainTextEdit(right.body_widget)
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet(f"font-family: {FONT_MONO}; font-size: 11px;")
        right.body_layout.addWidget(self.table, 1)
        right.body_layout.addWidget(QLabel("通信日志:", right.body_widget))
        right.body_layout.addWidget(self.log_box, 1)
        mid.addWidget(right)
        root.addLayout(mid, 1)

        self._callbackSignal.connect(self._on_http_callback, Qt.ConnectionType.QueuedConnection)
        state.bus.subscribe(StudioEvent.TRACKS_UPDATED, lambda _p: self._refresh_table())
        state.bus.subscribe(StudioEvent.TIMELINE_UPDATED, lambda _p: self._refresh_table())
        state.bus.subscribe(StudioEvent.COLLISION_UPDATED, lambda _p: self._refresh_table())
        state.bus.subscribe(StudioEvent.ROBOT_TELEMETRY_UPDATED, lambda evt: self._callbackSignal.emit(evt))
        self._refresh_table()

    def _on_http_callback(self, evt: object) -> None:
        if isinstance(evt, dict):
            tgt = evt.get("target_id", "")
            p = evt.get("payload", {}) if isinstance(evt.get("payload"), dict) else {}
            ev_name = p.get("event", "")
            title = p.get("title", "")
            rem = p.get("remaining_distance_m")
            rem_s = f" 距目标 {rem:.2f}m" if isinstance(rem, (int, float)) else ""
            err_s = f" ERR:{p.get('error')}" if p.get("error") else ""
            self.log_box.appendPlainText(f"[HTTP-CB {tgt}] {ev_name} {title}{rem_s}{err_s}".strip())
        self._sync_live_3d_poses()
        self._refresh_table()

    def _sync_live_3d_poses(self) -> None:
        cb_map = self.state.callback_listener.latest_by_target
        live_poses: Dict[str, Tuple[float, float, float]] = {}
        for tgt, rec in cb_map.items():
            p = rec.get("pose") if isinstance(rec, dict) else None
            if isinstance(p, dict) and "x" in p and "y" in p:
                live_poses[tgt.upper()] = (float(p["x"]), float(p["y"]), float(p.get("yaw", 0.0)))
        self.viewport.set_live_robot_poses(live_poses)

    def refresh_fleet_health(self) -> int:
        """Actively probe /api/v1/health on every configured track over Wi-Fi HTTP."""
        ok_cnt = 0
        for tr in self.state.tracks:
            if not tr.robot_ip:
                self._health_cache[tr.target_id.upper()] = "未设IP"
                continue
            resp = self.state.http_rpc.health(tr.robot_ip)
            if resp.ok:
                ok_cnt += 1
                ros_tag = "ROS在线" if resp.data.get("ros_master_reachable") else "ROS离线"
                self._health_cache[tr.target_id.upper()] = f"HTTP在线·{ros_tag}"
            else:
                self._health_cache[tr.target_id.upper()] = "离线"
        self.log_box.appendPlainText(f"[HEALTH] 机群在线体检完成: {ok_cnt}/{len(self.state.tracks)} 台可达")
        self._refresh_table()
        return ok_cnt

    def _emit_to_targets(self, cmd: str, *params: str) -> None:
        if not self.state.tracks:
            self.log_box.appendPlainText(f"[SKIP] 无真实机器人轨道，未发送 {cmd}")
            return
        lines = []
        for tr in self.state.tracks:
            chk = self.state.arbiter.can_execute(tr.target_id, cmd)
            if chk.allowed:
                res = self.state.dispatch_command_http(tr.target_id, cmd, list(params))
                self.state.arbiter.apply_command(tr.target_id, cmd)
                mode = (res.get("data") or {}).get("execution_mode", "")
                tag = " [RESERVED_SLOT]" if mode == "RESERVED_SLOT" else ""
                lines.append(f"[HTTP-TX {tr.target_id}@{tr.robot_ip}] {cmd}{tag} -> {res.get('message', '')}")
            else:
                lines.append(f"[DENY] {tr.target_id}|{cmd}: {chk.reason}")
        self.log_box.appendPlainText("\n".join(lines))
        self._refresh_table()

    def _cmd_prep(self) -> None:
        if not self.state.tracks:
            self.state.notify("暂无真实机器人轨道，请先添加机器人", "warn")
            return
        plan = TimelineLrmpCompiler.compile_plan(self.state.tracks, self.state.blocks)
        self._active_run_id = plan.run_id
        for tr in self.state.tracks:
            self.state.arbiter.apply_command(tr.target_id, "PREP")
        res_list = self.state.compile_and_upload_chains_http(plan_id=plan.plan_id, run_id=plan.run_id, prep=True)
        ok_cnt = sum(1 for r in res_list if r.get("upload_ok") and r.get("prep_ok"))
        for r in res_list:
            self.log_box.appendPlainText(f"[HTTP-PREP {r['target_id']}@{r['robot_ip']}] {r['message']}")
        self.phase_badge.setText(f"阶段: CHOREO 就绪 (PREP {ok_cnt}/{len(res_list)})")
        self.phase_badge.set_tone("accent" if ok_cnt > 0 else "warn")
        self._refresh_table()

    def _cmd_barrier(self) -> None:
        if not self.state.tracks:
            return
        ok_cnt = 0
        for tr in self.state.tracks:
            if tr.muted:
                continue
            resp = self.state.http_rpc.barrier_task_chain(tr.robot_ip, self._active_run_id, barrier_id="1")
            ok_cnt += int(resp.ok)
            self.log_box.appendPlainText(f"[HTTP-BARRIER {tr.target_id}@{tr.robot_ip}] {resp.message}")
        self.phase_badge.setText(f"阶段: BARRIER 同步 ({ok_cnt}/{len(self.state.tracks)})")
        self.phase_badge.set_tone("accent" if ok_cnt > 0 else "warn")

    def _cmd_play(self) -> None:
        if not self.state.tracks:
            self.state.notify("暂无真实机器人轨道，请先添加机器人", "warn")
            return
        plan = TimelineLrmpCompiler.compile_plan(self.state.tracks, self.state.blocks)
        run_id = self._active_run_id or plan.run_id
        for tr in self.state.tracks:
            chk = self.state.arbiter.can_execute(tr.target_id, "PLAY")
            if not chk.allowed:
                self.log_box.appendPlainText(f"[DENY] {chk.reason}")
                return
        has_action = any(b.block_type == "action" and not b.is_ignored for b in self.state.blocks)
        res_list = self.state.start_task_chains_http(run_id=run_id)
        ok_cnt = sum(1 for r in res_list if r.get("ok"))
        for r in res_list:
            self.log_box.appendPlainText(f"[HTTP-PLAY {r['target_id']}@{r['robot_ip']}] {r['message']}")
        if has_action:
            self.log_box.appendPlainText("[NOTE] 任务链含舞蹈动作节点：下位机当前为 RESERVED_SLOT（白名单校验，待 DDS 手柄挂载）")
        self.playback.pause()
        self._sync_live_3d_poses()
        self.phase_badge.setText(f"阶段: PLAY 执行中 ({ok_cnt}/{len(res_list)})")
        self.phase_badge.set_tone("ok" if ok_cnt > 0 else "warn")
        self._refresh_table()

    def _cmd_stop(self) -> None:
        self.playback.stop_and_return_origin()
        for tr in self.state.tracks:
            self.state.arbiter.apply_command(tr.target_id, "STOP")
        self.log_box.appendPlainText("[HTTP-STOP] 已发送任务链停止并回到初始原点指令")
        self.phase_badge.setText("阶段: STOP 已回原点")
        self.phase_badge.set_tone("neutral")
        self._refresh_table()

    def _cmd_emergency(self) -> None:
        self.playback.pause()
        self._emit_to_targets("EMERGENCY")
        self.phase_badge.setText("阶段: EMERGENCY 已紧急急停!")
        self.phase_badge.set_tone("danger")

    def _refresh_table(self) -> None:
        d_safe = get_settings().stage_defaults.safety_distance_m
        cb_map = self.state.callback_listener.latest_by_target
        poses_xy: Dict[str, Tuple[float, float, float, bool]] = {}
        for tr in self.state.tracks:
            live = cb_map.get(tr.target_id.upper(), {})
            lp = live.get("pose") if isinstance(live.get("pose"), dict) else None
            if lp is not None:
                poses_xy[tr.target_id.upper()] = (float(lp.get("x", 0.0)), float(lp.get("y", 0.0)), float(lp.get("yaw", 0.0)), True)
            else:
                poses_xy[tr.target_id.upper()] = (tr.init_x, tr.init_y, tr.init_yaw, False)

        self.table.setRowCount(len(self.state.tracks))
        for r, tr in enumerate(self.state.tracks):
            tid = tr.target_id.upper()
            x, y, yaw, is_live = poses_xy[tid]
            min_peer = min(
                (math.hypot(x - ox, y - oy) for ot, (ox, oy, _, _) in poses_xy.items() if ot != tid),
                default=99.0,
            )
            cb = cb_map.get(tid, {})
            rem = cb.get("remaining_distance_m")
            conf = cb.get("localization_confidence")
            clear_txt = f"告警 ({min_peer:.2f}m<{d_safe:.2f}m)" if min_peer < d_safe else f"安全 ≥{d_safe:.2f}m"
            if isinstance(rem, (int, float)):
                clear_txt += f" · 余{rem:.2f}m"
            if isinstance(conf, (int, float)):
                clear_txt += f" · 置信{conf:.2f}"
            auth = self.state.arbiter.get_state(tr.target_id).value
            status_txt = cb.get("current_node_title") or cb.get("last_event") or self._health_cache.get(tid) or "Wi-Fi HTTP 就绪"
            self.table.setItem(r, 0, QTableWidgetItem(f"{tr.name}[{tr.target_id}] {tr.robot_ip}"))
            self.table.setItem(r, 1, QTableWidgetItem(f"{x:.2f}, {y:.2f}, {yaw:.2f}" + (" [实机]" if is_live else " [原点]")))
            self.table.setItem(r, 2, QTableWidgetItem(clear_txt))
            self.table.setItem(r, 3, QTableWidgetItem(f"{auth} · {status_txt}"))
