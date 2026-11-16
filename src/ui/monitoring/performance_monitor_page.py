# @file: src/ui/monitoring/performance_monitor_page.py
# @brief: UniUni Page 4 Live Show Monitor implementing strict LRMP PREP -> BARRIER -> PLAY -> STOP / EMERGENCY workflow.
# @exports: PerformanceMonitorPage

from __future__ import annotations

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
    """Live LRMP V1.0-R3 show execution desk synchronized with 3D swarm playback."""

    def __init__(self, state: StudioStateService, playback: PlaybackCoordinator, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.playback = playback

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # Top transport & LRMP sequence bar
        bar = UPanel(title="演出控制台 (LRMP V1.0-R3 协议引擎)", parent=self)
        bar.setFixedHeight(92)
        bl = QHBoxLayout()
        bl.setSpacing(8)
        self.phase_badge = UBadge("阶段: 待命 (FREE)", tone="neutral", parent=bar.body_widget)
        prep_b = UButton("1. PREP 准备", variant="default", size="sm", parent=bar.body_widget)
        prep_b.clicked.connect(self._cmd_prep)
        bar_b = UButton("2. BARRIER 同步等待", variant="default", size="sm", parent=bar.body_widget)
        bar_b.clicked.connect(self._cmd_barrier)
        play_b = UButton("3. PLAY(T0) 开始演出", variant="primary", size="sm", icon_name="play", parent=bar.body_widget)
        play_b.clicked.connect(self._cmd_play)
        stop_b = UButton("STOP 停止", variant="default", size="sm", parent=bar.body_widget)
        stop_b.clicked.connect(self._cmd_stop)
        emg_b = UButton("EMERGENCY 紧急制动", variant="danger", size="sm", parent=bar.body_widget)
        emg_b.clicked.connect(self._cmd_emergency)

        for w in (self.phase_badge, prep_b, bar_b, play_b, stop_b, emg_b):
            bl.addWidget(w)
        bl.addStretch(1)
        bar.body_layout.addLayout(bl)
        root.addWidget(bar)

        # Main split: 3D Live Preview + Telemetry/Command Log
        mid = QHBoxLayout()
        mid.setSpacing(6)
        vp_panel = UPanel(title="3D 集群演出现场同步", parent=self)
        self.viewport = StageViewport3D(state, vp_panel.body_widget)
        vp_panel.body_layout.addWidget(self.viewport, 1)
        mid.addWidget(vp_panel, 2)

        right = UPanel(title="设备权威态与 LRMP 下发帧日志", parent=self)
        right.setFixedWidth(380)
        self.table = UTable(["目标", "IP", "控制权", "当前状态"], right.body_widget)
        self.log_box = QPlainTextEdit(right.body_widget)
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet(f"font-family: {FONT_MONO}; font-size: 11px;")
        right.body_layout.addWidget(self.table, 1)
        right.body_layout.addWidget(QLabel("LRMP 协议帧审计:", right.body_widget))
        right.body_layout.addWidget(self.log_box, 1)
        mid.addWidget(right)
        root.addLayout(mid, 1)

        state.bus.subscribe(StudioEvent.TRACKS_UPDATED, lambda _p: self._refresh_table())
        state.bus.subscribe(StudioEvent.TIMELINE_UPDATED, lambda _p: self._refresh_table())
        state.bus.subscribe(StudioEvent.ROBOT_TELEMETRY_UPDATED, lambda _p: self._refresh_table())
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
                self.state.arbiter.apply_command(tr.target_id, cmd)
                lines.append(f"[TX] {raw.decode('utf-8').strip()}")
            else:
                lines.append(f"[DENY] {tr.target_id}|{cmd}: {chk.reason}")
        self.log_box.appendPlainText("\n".join(lines))
        self._refresh_table()

    def _cmd_prep(self) -> None:
        if not self.state.tracks:
            self.state.notify("暂无真实机器人轨道，请先添加机器人", "warn")
            return
        plan = TimelineLrmpCompiler.compile_plan(self.state.tracks, self.state.blocks)
        for tr in self.state.tracks:
            self.state.arbiter.apply_command(tr.target_id, "PREP")
        for f in plan.prep_frames:
            self.state._send_raw_lrmp((f + "\n").encode("utf-8"))
        self.log_box.appendPlainText("\n".join(f"[TX] {f}" for f in plan.prep_frames))
        self.phase_badge.setText("阶段: CHOREO 就绪 (PREP)")
        self.phase_badge.set_tone("accent")
        self._refresh_table()

    def _cmd_barrier(self) -> None:
        self._emit_to_targets("BARRIER", "1001", "5000")
        if self.state.tracks:
            self.phase_badge.setText("阶段: BARRIER 同步锁齐")
            self.phase_badge.set_tone("accent")

    def _cmd_play(self) -> None:
        if not self.state.tracks:
            self.state.notify("暂无真实机器人轨道，请先添加机器人", "warn")
            return
        plan = TimelineLrmpCompiler.compile_plan(self.state.tracks, self.state.blocks)
        for tr in self.state.tracks:
            chk = self.state.arbiter.can_execute(tr.target_id, "PLAY")
            if not chk.allowed:
                self.log_box.appendPlainText(f"[DENY] {chk.reason}")
                return
        for f in plan.play_frames:
            self.state._send_raw_lrmp((f + "\n").encode("utf-8"))
        self.log_box.appendPlainText("\n".join(f"[TX] {f}" for f in plan.play_frames))
        self.playback.replay()
        self.phase_badge.setText("阶段: PLAY 执行中")
        self.phase_badge.set_tone("ok")
        self._refresh_table()

    def _cmd_stop(self) -> None:
        self.playback.pause()
        self._emit_to_targets("STOP")
        self._emit_to_targets("RELEASE")
        self.phase_badge.setText("阶段: STOP 已释放")
        self.phase_badge.set_tone("neutral")

    def _cmd_emergency(self) -> None:
        self.playback.pause()
        self._emit_to_targets("EMERGENCY")
        self.phase_badge.setText("阶段: EMERGENCY 已紧急急停!")
        self.phase_badge.set_tone("danger")

    def _refresh_table(self) -> None:
        has_serial = self.state.serial_manager is not None and bool(getattr(self.state.serial_manager, "is_connected", False))
        link_txt = "串口在线" if has_serial else "离线仿真信道"
        self.table.setRowCount(len(self.state.tracks))
        for r, tr in enumerate(self.state.tracks):
            auth = self.state.arbiter.get_state(tr.target_id).value
            self.table.setItem(r, 0, QTableWidgetItem(f"{tr.name} ({tr.target_id})"))
            self.table.setItem(r, 1, QTableWidgetItem(tr.robot_ip))
            self.table.setItem(r, 2, QTableWidgetItem(auth))
            self.table.setItem(r, 3, QTableWidgetItem(link_txt))
