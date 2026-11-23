# @file: src/ui/monitoring/performance_monitor_page.py
# @brief: UniUni Page 4 Live Show Monitor executing task-chain PREP/PLAY/STOP-to-origin/EMERGENCY via Wi-Fi HTTP.
# @exports: PerformanceMonitorPage

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QTableWidgetItem, QVBoxLayout, QWidget

from src.core.event_bus import StudioEvent
from src.protocol.lrmp_codec import LrmpCodec
from src.protocol.timeline_lrmp_compiler import TimelineLrmpCompiler
from src.services.playback_coordinator import PlaybackCoordinator
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.tokens import FONT_MONO
from src.ui.design_system.u_buttons import UBadge, UButton
from src.ui.design_system.u_panels import UPanel, UTable
from src.viewport3d.stage_viewport_3d import StageViewport3D


class PerformanceMonitorPage(QWidget):
    """Live Wi-Fi HTTP show execution desk synchronized with lower-computer callbacks and 3D preview."""

    _callbackSignal = Signal(object)

    def __init__(self, state: StudioStateService, playback: PlaybackCoordinator, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.playback = playback
        self._active_run_id: str = "9001"

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        bar = UPanel(title="演出控制台 (Wi-Fi HTTP 任务链调度 & 真实回调监测)", parent=self)
        bar.setFixedHeight(92)
        bl = QHBoxLayout()
        bl.setSpacing(8)
        self.phase_badge = UBadge("阶段: 待命 (FREE)", tone="neutral", parent=bar.body_widget)
        prep_b = UButton("1. PREP 上传并准备", variant="default", size="sm", parent=bar.body_widget)
        prep_b.clicked.connect(self._cmd_prep)
        bar_b = UButton("2. BARRIER 同步等待", variant="default", size="sm", parent=bar.body_widget)
        bar_b.clicked.connect(self._cmd_barrier)
        play_b = UButton("3. PLAY 启动任务链", variant="primary", size="sm", icon_name="play", parent=bar.body_widget)
        play_b.clicked.connect(self._cmd_play)
        stop_b = UButton("STOP 停止回原点", variant="default", size="sm", icon_name="stop", parent=bar.body_widget)
        stop_b.clicked.connect(self._cmd_stop)
        emg_b = UButton("EMERGENCY 紧急制动", variant="danger", size="sm", parent=bar.body_widget)
        emg_b.clicked.connect(self._cmd_emergency)

        for w in (self.phase_badge, prep_b, bar_b, play_b, stop_b, emg_b):
            bl.addWidget(w)
        bl.addStretch(1)
        bar.body_layout.addLayout(bl)
        root.addWidget(bar)

        mid = QHBoxLayout()
        mid.setSpacing(6)
        vp_panel = UPanel(title="3D 集群演出现场同步", parent=self)
        self.viewport = StageViewport3D(state, vp_panel.body_widget)
        vp_panel.body_layout.addWidget(self.viewport, 1)
        mid.addWidget(vp_panel, 2)

        right = UPanel(title="设备状态与 Wi-Fi HTTP 回调日志", parent=self)
        right.setFixedWidth(400)
        self.table = UTable(["目标", "无线 IP", "控制权", "当前执行/回调"], right.body_widget)
        self.log_box = QPlainTextEdit(right.body_widget)
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet(f"font-family: {FONT_MONO}; font-size: 11px;")
        right.body_layout.addWidget(self.table, 1)
        right.body_layout.addWidget(QLabel("Wi-Fi HTTP 请求与下位机回调:", right.body_widget))
        right.body_layout.addWidget(self.log_box, 1)
        mid.addWidget(right)
        root.addLayout(mid, 1)

        self._callbackSignal.connect(self._on_http_callback, Qt.ConnectionType.QueuedConnection)
        state.bus.subscribe(StudioEvent.TRACKS_UPDATED, lambda _p: self._refresh_table())
        state.bus.subscribe(StudioEvent.TIMELINE_UPDATED, lambda _p: self._refresh_table())
        state.bus.subscribe(StudioEvent.ROBOT_TELEMETRY_UPDATED, lambda evt: self._callbackSignal.emit(evt))
        self._refresh_table()

    def _on_http_callback(self, evt: object) -> None:
        if isinstance(evt, dict):
            tgt = evt.get("target_id", "")
            p = evt.get("payload", {})
            ev_name = p.get("event", "")
            title = p.get("title", "")
            self.log_box.appendPlainText(f"[HTTP-CB {tgt}] {ev_name} {title}".strip())
        self._refresh_table()

    def _emit_to_targets(self, cmd: str, *params: str) -> None:
        if not self.state.tracks:
            self.log_box.appendPlainText(f"[SKIP] 无真实机器人轨道，未发送 {cmd}")
            return
        lines = []
        for tr in self.state.tracks:
            chk = self.state.arbiter.can_execute(tr.target_id, cmd)
            if chk.allowed:
                raw = LrmpCodec.encode(tr.target_id, cmd, *params)
                self.state._send_raw_lrmp(raw)
                res = self.state.dispatch_command_http(tr.target_id, cmd, list(params))
                self.state.arbiter.apply_command(tr.target_id, cmd)
                lines.append(f"[HTTP-TX {tr.target_id}@{tr.robot_ip}] {cmd} -> {res.get('message', '')}")
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
        for f in plan.prep_frames:
            self.state._send_raw_lrmp((f + "\n").encode("utf-8"))
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
        for f in plan.play_frames:
            self.state._send_raw_lrmp((f + "\n").encode("utf-8"))
        res_list = self.state.start_task_chains_http(run_id=run_id)
        ok_cnt = sum(1 for r in res_list if r.get("ok"))
        for r in res_list:
            self.log_box.appendPlainText(f"[HTTP-PLAY {r['target_id']}@{r['robot_ip']}] {r['message']}")
        self.playback.replay()
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
        cb_map = self.state.callback_listener.latest_by_target
        sm = self.state.serial_manager
        has_serial = bool(sm.is_connected() if callable(getattr(sm, "is_connected", None)) else getattr(sm, "is_connected", False)) if sm is not None else False
        self.table.setRowCount(len(self.state.tracks))
        for r, tr in enumerate(self.state.tracks):
            auth = self.state.arbiter.get_state(tr.target_id).value
            cb = cb_map.get(tr.target_id.upper(), {})
            status_txt = cb.get("current_node_title") or cb.get("last_event") or ("串口在线" if has_serial else "Wi-Fi HTTP 就绪")
            self.table.setItem(r, 0, QTableWidgetItem(f"{tr.name} ({tr.target_id})"))
            self.table.setItem(r, 1, QTableWidgetItem(tr.robot_ip))
            self.table.setItem(r, 2, QTableWidgetItem(auth))
            self.table.setItem(r, 3, QTableWidgetItem(str(status_txt)))
