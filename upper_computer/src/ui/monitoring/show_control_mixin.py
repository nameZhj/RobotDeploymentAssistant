# @file: src/ui/monitoring/show_control_mixin.py
# @brief: Background-task show control (fleet health, PREP/BARRIER/PLAY/STOP/EMERGENCY) mixed into PerformanceMonitorPage.
# @exports: ShowControlMixin

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from src.protocol.robot_http_client import RobotHttpResponse
from src.protocol.timeline_lrmp_compiler import TimelineLrmpCompiler
from src.ui.common.async_task import TaskHandle, run_in_background


class ShowControlMixin:
    """Wi-Fi HTTP show-control actions executed as background tasks.

    The host (PerformanceMonitorPage) must provide ``state``, ``playback``, ``log_box``,
    ``phase_badge``, ``ping_b``, ``prep_b``, ``bar_b``, ``play_b``, ``emg_b``,
    ``_refresh_table()`` and ``_sync_live_3d_poses()``.
    """

    # ------------------------------------------------------------------ fleet health
    def refresh_fleet_health(self) -> Optional[TaskHandle]:
        """Probe /api/v1/health on every configured track in the background (parallel, 1.2s timeout each)."""
        if not self.state.tracks:
            self.log_box.appendPlainText("[HEALTH] 暂无机器人轨道，无需体检")
            return None
        return run_in_background(
            self.state.fleet_health,
            on_done=self._on_fleet_health,
            busy_widgets=[self.ping_b],
            busy_text="正在后台体检全队 Wi-Fi HTTP / ROS 状态...",
            notifier=self.state.notify,
        )

    def _on_fleet_health(self, results: Dict[str, RobotHttpResponse]) -> None:
        ok_cnt = 0
        for tr in self.state.tracks:
            tid = tr.target_id.upper()
            resp = results.get(tid)
            if resp is None:
                self._health_cache[tid] = "未设IP"
            elif resp.ok:
                ok_cnt += 1
                ros_tag = "ROS在线" if resp.data.get("ros_master_reachable") else "ROS离线"
                udp_info = resp.data.get("motion_udp") if isinstance(resp.data.get("motion_udp"), dict) else {}
                udp_tag = "·UDP可达" if udp_info.get("reachable") is True else ("·UDP超时" if resp.data.get("motion_udp_enabled") else "")
                mode_tag = f"·{resp.data.get('motion_state') or '-'}"
                faults = [f for f in (resp.data.get("active_faults") or []) if isinstance(f, dict)]
                fault_tag = f"·锁:{resp.data.get('lock_reason') or 'FAULT'}" if resp.data.get("safety_locked") else (f"·告警:{faults[0].get('code','')}" if faults else "")
                self._health_cache[tid] = f"HTTP·{ros_tag}{udp_tag}{mode_tag}{fault_tag}"
            else:
                self._health_cache[tid] = "离线"
        self.log_box.appendPlainText(f"[HEALTH] 机群在线体检完成: {ok_cnt}/{len(self.state.tracks)} 台可达")
        self._refresh_table()

    # ------------------------------------------------------------------ generic target commands
    def _emit_to_targets(self, cmd: str, *params: str) -> Optional[TaskHandle]:
        if not self.state.tracks:
            self.log_box.appendPlainText(f"[SKIP] 无真实机器人轨道，未发送 {cmd}")
            return None
        pending: List[Tuple[str, str, List[str]]] = []
        deny_lines: List[str] = []
        for tr in self.state.tracks:
            chk = self.state.arbiter.can_execute(tr.target_id, cmd)
            if chk.allowed:
                pending.append((tr.target_id, cmd, list(params)))
            else:
                deny_lines.append(f"[DENY] {tr.target_id}|{cmd}: {chk.reason}")
        if not pending:
            self.log_box.appendPlainText("\n".join(deny_lines))
            return None
        return run_in_background(
            lambda: self.state.dispatch_targets_http(pending),
            on_done=lambda res: self._on_targets_result(cmd, deny_lines, res),
            busy_widgets=[self.emg_b],
            busy_text=f"正在后台向 {len(pending)} 台机器人下发 {cmd} 指令...",
            notifier=self.state.notify,
        )

    def _on_targets_result(self, cmd: str, deny_lines: List[str], results: List[Dict[str, Any]]) -> None:
        lines = list(deny_lines)
        for r in results:
            tid = str(r.get("target_id", ""))
            self.state.arbiter.apply_command(tid, cmd)
            mode = (r.get("data") or {}).get("execution_mode", "")
            tag = " [RESERVED_SLOT]" if mode == "RESERVED_SLOT" else ""
            lines.append(f"[HTTP-TX {tid}@{r.get('robot_ip')}] {cmd}{tag} -> {r.get('message', '')}")
        self.log_box.appendPlainText("\n".join(lines))
        self._refresh_table()

    # ------------------------------------------------------------------ show control
    def _cmd_prep(self) -> Optional[TaskHandle]:
        if not self.state.tracks:
            self.state.notify("暂无真实机器人轨道，请先添加机器人", "warn")
            return None
        plan = TimelineLrmpCompiler.compile_plan(self.state.tracks, self.state.blocks)
        self._active_run_id = plan.run_id
        for tr in self.state.tracks:
            self.state.arbiter.apply_command(tr.target_id, "PREP")
        self.phase_badge.setText("阶段: PREP 后台下发了任务链...")
        self.phase_badge.set_tone("accent")
        return run_in_background(
            lambda: self.state.compile_and_upload_chains_http(plan_id=plan.plan_id, run_id=plan.run_id, prep=True),
            on_done=self._on_prep_done,
            busy_widgets=[self.prep_b, self.bar_b, self.play_b],
            busy_text=f"正在后台编译并向 {len(self.state.tracks)} 台机器人下发任务链 (PREP)...",
            notifier=self.state.notify,
        )

    def _on_prep_done(self, res_list: List[Dict[str, Any]]) -> None:
        for r in res_list:
            self.log_box.appendPlainText(f"[HTTP-PREP {r['target_id']}@{r['robot_ip']}] {r['message']}")
            if not (r.get("upload_ok") and r.get("prep_ok")) and int(r.get("status_code", 0) or 0) >= 400:
                tid = str(r.get("target_id", ""))
                if tid:
                    self.state.arbiter.apply_command(tid, "STOP")
        ok_cnt = sum(1 for r in res_list if r.get("upload_ok") and r.get("prep_ok"))
        self.phase_badge.setText(f"阶段: CHOREO 就绪 (PREP {ok_cnt}/{len(res_list)})")
        self.phase_badge.set_tone("ok" if res_list and ok_cnt == len(res_list) else ("accent" if ok_cnt > 0 else "warn"))
        self._refresh_table()

    def _cmd_barrier(self) -> Optional[TaskHandle]:
        if not self.state.tracks:
            return None
        run_id = self._active_run_id
        self.phase_badge.setText("阶段: BARRIER 后台放行中...")
        return run_in_background(
            lambda: self.state.barrier_task_chains_http(run_id, barrier_id="1"),
            on_done=self._on_barrier_done,
            busy_widgets=[self.bar_b],
            busy_text="正在后台向全队放行 BARRIER 同步点...",
            notifier=self.state.notify,
        )

    def _on_barrier_done(self, results: List[Dict[str, Any]]) -> None:
        for r in results:
            self.log_box.appendPlainText(f"[HTTP-BARRIER {r['target_id']}@{r['robot_ip']}] {r['message']}")
        ok_cnt = sum(1 for r in results if r.get("ok"))
        total = max(len(results), len(self.state.tracks))
        self.phase_badge.setText(f"阶段: BARRIER 同步 ({ok_cnt}/{total})")
        self.phase_badge.set_tone("ok" if ok_cnt > 0 else "warn")

    def _cmd_play(self) -> Optional[TaskHandle]:
        if not self.state.tracks:
            self.state.notify("暂无真实机器人轨道，请先添加机器人", "warn")
            return None
        plan = TimelineLrmpCompiler.compile_plan(self.state.tracks, self.state.blocks)
        run_id = self._active_run_id or plan.run_id
        for tr in self.state.tracks:
            chk = self.state.arbiter.can_execute(tr.target_id, "PLAY")
            if not chk.allowed:
                self.log_box.appendPlainText(f"[DENY] {chk.reason}")
                return None
        self._has_action_nodes = any(b.block_type == "action" and not b.is_ignored for b in self.state.blocks)
        self.phase_badge.setText("阶段: PLAY 后台启动中...")
        return run_in_background(
            lambda: self.state.start_task_chains_http(run_id=run_id),
            on_done=self._on_play_done,
            busy_widgets=[self.play_b, self.prep_b, self.bar_b],
            busy_text="正在后台启动机群任务链 (PLAY)...",
            notifier=self.state.notify,
        )

    def _on_play_done(self, res_list: List[Dict[str, Any]]) -> None:
        for r in res_list:
            self.log_box.appendPlainText(f"[HTTP-PLAY {r['target_id']}@{r['robot_ip']}] {r['message']}")
        if getattr(self, "_has_action_nodes", False):
            self.log_box.appendPlainText("[NOTE] 任务链含舞蹈动作节点：下位机经本机 UDP 运控桥执行并等待 DANCE_DONE 回包")
        self.playback.pause()
        self._sync_live_3d_poses()
        ok_cnt = sum(1 for r in res_list if r.get("ok"))
        self.phase_badge.setText(f"阶段: PLAY 执行中 ({ok_cnt}/{len(res_list)})")
        self.phase_badge.set_tone("ok" if ok_cnt > 0 else "warn")
        self._refresh_table()

    def _cmd_stop(self) -> None:
        self.playback.stop_and_return_origin()
        for tr in self.state.tracks:
            self.state.arbiter.apply_command(tr.target_id, "STOP")
        self.log_box.appendPlainText("[HTTP-STOP] 已停止本地播放，停止并回原点指令正在后台下发")
        self.phase_badge.setText("阶段: STOP 回原点中")
        self.phase_badge.set_tone("neutral")
        self._refresh_table()

    def _cmd_emergency(self) -> Optional[TaskHandle]:
        self.playback.pause()
        self.phase_badge.setText("阶段: EMERGENCY 急停指令后台下发中!")
        self.phase_badge.set_tone("danger")
        return self._emit_to_targets("EMERGENCY")
