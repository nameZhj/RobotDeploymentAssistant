# @file: src/ui/monitoring/performance_monitor_page.py
# @brief: Live Show Monitor page UI with real ROS pose 3D sync, clearance table, and background show control mixin.
# @exports: PerformanceMonitorPage

from __future__ import annotations

import math
import time
from typing import Dict, Tuple
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QTableWidgetItem, QVBoxLayout, QWidget

from src.core.event_bus import StudioEvent
from src.core.settings import get_settings
from src.services.playback_coordinator import PlaybackCoordinator
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.tokens import FONT_MONO
from src.ui.design_system.u_buttons import UBadge, UButton
from src.ui.design_system.u_panels import UPanel, UTable
from src.ui.monitoring.show_control_mixin import ShowControlMixin
from src.viewport3d.stage_viewport_3d import StageViewport3D


class PerformanceMonitorPage(QWidget, ShowControlMixin):
    """Pure Wi-Fi HTTP live show execution desk synced with real lower-computer ROS poses & callbacks.

    Every blocking HTTP call (health probe, PREP/BARRIER/PLAY/EMERGENCY) runs on a background
    thread via ``run_in_background``; the GUI thread only renders results, so clicking a show
    button never freezes the window even when robots are unreachable.
    """

    _callbackSignal = Signal(object)

    def __init__(self, state: StudioStateService, playback: PlaybackCoordinator, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.playback = playback
        self._active_run_id: str = "9001"
        self._health_cache: Dict[str, str] = {}
        self._live_dance_state: Dict[str, Tuple[str, float]] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        bar = UPanel(
            title="演出控制台",
            parent=self,
            help_text="标准调度流程：1. PREP 下发任务链；2. BARRIER 同步就绪；3. PLAY 开始演出；异常时点击 EMERGENCY 急停。所有指令后台下发，不阻塞界面。",
        )
        bar.setFixedHeight(92)
        bl = QHBoxLayout()
        bl.setSpacing(8)
        self.phase_badge = UBadge("阶段: 待命 (FREE)", tone="neutral", parent=bar.body_widget)
        self.prep_b = UButton("1. PREP 准备", variant="default", size="sm", parent=bar.body_widget)
        self.prep_b.clicked.connect(self._cmd_prep)
        self.bar_b = UButton("2. BARRIER 放行", variant="default", size="sm", parent=bar.body_widget)
        self.bar_b.clicked.connect(self._cmd_barrier)
        self.play_b = UButton("3. PLAY 启动", variant="primary", size="sm", icon_name="play", parent=bar.body_widget)
        self.play_b.clicked.connect(self._cmd_play)
        self.stop_b = UButton("STOP 停止", variant="default", size="sm", icon_name="stop", parent=bar.body_widget)
        self.stop_b.clicked.connect(self._cmd_stop)
        self.emg_b = UButton("EMERGENCY 急停", variant="danger", size="sm", parent=bar.body_widget)
        self.emg_b.clicked.connect(self._cmd_emergency)
        self.ping_b = UButton("刷新在线", variant="ghost", size="sm", icon_name="refresh", parent=bar.body_widget)
        self.ping_b.clicked.connect(self.refresh_fleet_health)

        for w in (self.phase_badge, self.prep_b, self.bar_b, self.play_b, self.stop_b, self.emg_b, self.ping_b):
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

    # ------------------------------------------------------------------ live callbacks
    def _on_http_callback(self, evt: object) -> None:
        if isinstance(evt, dict):
            tgt = str(evt.get("target_id", "")).upper()
            p = evt.get("payload", {}) if isinstance(evt.get("payload"), dict) else {}
            ev_name = str(p.get("event", ""))
            title = str(p.get("title", "") or p.get("alias", "") or p.get("code", "") or p.get("status", ""))
            rem = p.get("remaining_distance_m")
            rem_s = f" 距目标 {rem:.2f}m" if isinstance(rem, (int, float)) else ""
            err_s = f" ERR:{p.get('error') or p.get('reason')}" if (p.get("error") or p.get("reason")) else ""
            self.log_box.appendPlainText(f"[HTTP-CB {tgt}] {ev_name} {title}{rem_s}{err_s}".strip())
            rs_cb = p.get("robot_state") if isinstance(p.get("robot_state"), dict) else {}
            if ev_name == "DANCE_STARTED" or (ev_name in ("TASK_STARTED", "STEP_STARTED") and (p.get("alias") or p.get("task_type") == "dance")):
                alias = str(p.get("alias") or rs_cb.get("active_dance") or p.get("title") or "")
                if alias:
                    self._live_dance_state[tgt] = (alias, time.monotonic())
            elif ev_name in ("DANCE_DONE", "DANCE_COMPLETED", "DANCE_ABORTED", "CHAIN_COMPLETED", "CHAIN_ABORTED", "TASK_ERROR"):
                self._live_dance_state.pop(tgt, None)
            if ev_name == "ROBOT_FAULT" and p.get("level") in ("ERROR", "FATAL"):
                self._live_dance_state.pop(tgt, None)
                self.state.arbiter.apply_command(tgt, "EMERGENCY")
                self.phase_badge.setText(f"阶段: 安全熔断 ({p.get('code', 'FAULT')})")
                self.phase_badge.set_tone("danger")
            elif ev_name == "ROBOT_STATE_CHANGED" and p.get("state") in ("ESTOP", "FAULT", "MANUAL_OVERRIDE"):
                self._live_dance_state.pop(tgt, None)
                self.state.arbiter.apply_command(tgt, "EMERGENCY")
                self.phase_badge.setText(f"阶段: 安全锁 ({p.get('state')})")
                self.phase_badge.set_tone("danger")
            elif ev_name == "ROBOT_STATE_CHANGED" and p.get("state") in ("PASSIVE", "STAND", "FREE"):
                self._live_dance_state.pop(tgt, None)
            elif ev_name == "ROBOT_FAULT_CLEARED" and not p.get("safety_locked"):
                cb_map = self.state.callback_listener.latest_by_target
                if not any(isinstance(r, dict) and r.get("safety_locked") for r in cb_map.values()):
                    self.phase_badge.setText("阶段: 故障已清除 (FREE)")
                    self.phase_badge.set_tone("ok")
            elif ev_name == "TASK_ERROR":
                self.state.arbiter.apply_command(tgt, "STOP")
                self.phase_badge.setText(f"阶段: 任务异常 ({p.get('title', 'ERR')})")
                self.phase_badge.set_tone("warn")
            elif ev_name == "CHAIN_COMPLETED":
                self.state.arbiter.apply_command(tgt, "STOP")
                still_choreo = any(self.state.arbiter.get_state(tr.target_id).value == "CHOREO" for tr in self.state.tracks)
                self.phase_badge.setText("阶段: 演出完成 (FREE)" if not still_choreo else f"阶段: {tgt} 完成 · 其余运行中")
                self.phase_badge.set_tone("ok" if not still_choreo else "accent")
            elif ev_name == "CHAIN_ABORTED":
                cmd = "EMERGENCY" if "EMERGENCY" in str(p.get("reason", "")).upper() else "STOP"
                self.state.arbiter.apply_command(tgt, cmd)
                still_choreo = any(self.state.arbiter.get_state(tr.target_id).value == "CHOREO" for tr in self.state.tracks)
                self.phase_badge.setText("阶段: 任务已中止 (FREE)" if not still_choreo else f"阶段: {tgt} 已中止")
                self.phase_badge.set_tone("danger" if cmd == "EMERGENCY" else "warn")
        self._sync_live_3d_poses()
        self._refresh_table()

    def _sync_live_3d_poses(self) -> None:
        cb_map = self.state.callback_listener.latest_by_target
        live_poses: Dict[str, Tuple[float, float, float]] = {}
        live_states: Dict[str, Dict[str, object]] = {}
        for tgt, rec in cb_map.items():
            if not isinstance(rec, dict):
                continue
            tid = tgt.upper()
            p = rec.get("pose")
            if isinstance(p, dict) and "x" in p and "y" in p:
                pose_t = (float(p["x"]), float(p["y"]), float(p.get("yaw", 0.0)))
                live_poses[tid] = pose_t
                ms = str(rec.get("motion_state") or "").upper()
                cb_dance = str(rec.get("active_dance") or "").strip()
                last_ev = str(rec.get("last_event") or "")
                terminal_dance = last_ev in ("DANCE_DONE", "DANCE_COMPLETED", "DANCE_ABORTED", "CHAIN_COMPLETED", "CHAIN_ABORTED")
                if cb_dance and not terminal_dance and ms not in ("ESTOP", "FAULT", "PASSIVE"):
                    if tid not in self._live_dance_state or self._live_dance_state[tid][0] != cb_dance:
                        self._live_dance_state[tid] = (cb_dance, time.monotonic())
                    dance_alias, dance_t0 = self._live_dance_state[tid]
                elif tid in self._live_dance_state and not terminal_dance and ms not in ("ESTOP", "FAULT", "PASSIVE"):
                    dance_alias, dance_t0 = self._live_dance_state[tid]
                else:
                    dance_alias, dance_t0 = "", 0.0
                live_states[tid] = {
                    "pose": pose_t,
                    "motion_state": ms,
                    "active_dance": dance_alias,
                    "dance_start_s": dance_t0,
                    "fault": bool(rec.get("safety_locked")) or ms in ("ESTOP", "FAULT"),
                }
        self.viewport.set_live_robot_states(live_states)

    # ------------------------------------------------------------------ table
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
            mode_s = f"{cb.get('motion_state') or ''}" + (f"({cb['nav_input']})" if cb.get("nav_input") else "")
            faults = [f.get("code", "") for f in (cb.get("active_faults") or []) if isinstance(f, dict)]
            fault_s = f" [故障:{','.join(faults)}]" if faults else ""
            status_txt = cb.get("current_node_title") or cb.get("last_event") or self._health_cache.get(tid) or "Wi-Fi HTTP 就绪"
            self.table.setItem(r, 0, QTableWidgetItem(f"{tr.name}[{tr.target_id}] {tr.robot_ip}"))
            self.table.setItem(r, 1, QTableWidgetItem(f"{x:.2f}, {y:.2f}, {yaw:.2f}" + (" [实机]" if is_live else " [原点]")))
            self.table.setItem(r, 2, QTableWidgetItem(clear_txt))
            self.table.setItem(r, 3, QTableWidgetItem(f"{auth}" + (f"·{mode_s}" if mode_s else "") + f"{fault_s} · {status_txt}"))
