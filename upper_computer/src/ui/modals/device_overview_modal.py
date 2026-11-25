# @file: src/ui/modals/device_overview_modal.py
# @brief: Interactive fleet device manager modal with real robot add, edit, delete, and LRMP authority reset.
# @exports: DeviceOverviewModal

from __future__ import annotations

from typing import Dict, Optional
from PySide6.QtWidgets import QHBoxLayout, QTableWidgetItem, QWidget

from src.core.event_bus import StudioEvent
from src.protocol.robot_http_client import RobotHttpResponse
from src.services.studio_state_service import StudioStateService
from src.ui.common.async_task import TaskHandle, run_in_background
from src.ui.design_system.u_buttons import UButton
from src.ui.design_system.u_dialog import UDialog
from src.ui.design_system.u_panels import UTable
from src.ui.modals.add_track_dialog import AddTrackDialog


class DeviceOverviewModal(UDialog):
    """Displays real-time track-to-robot mapping with full add, edit, delete, and LRMP reset controls."""

    def __init__(self, state: StudioStateService, parent: QWidget | None = None) -> None:
        super().__init__("集群设备总览与控制权管理", width=780, height=440, confirm_text="关闭", cancel_text="", parent=parent)
        self.state = state
        self._online_cache: Dict[str, str] = {}

        top = QHBoxLayout()
        top.setSpacing(6)
        add_b = UButton("+ 添加机器人", variant="primary", size="sm", icon_name="plus", parent=self)
        add_b.clicked.connect(self._on_add)
        edit_b = UButton("编辑选中", variant="default", size="sm", icon_name="edit", parent=self)
        edit_b.clicked.connect(self._on_edit)
        del_b = UButton("删除选中", variant="danger", size="sm", icon_name="trash", parent=self)
        del_b.clicked.connect(self._on_delete)
        ping_b = UButton("刷新在线状态", variant="default", size="sm", icon_name="refresh", parent=self)
        ping_b.clicked.connect(self.refresh_online_health)
        self.ping_b = ping_b
        rst_b = UButton("释放全队 LRMP (FREE)", variant="default", size="sm", parent=self)
        rst_b.clicked.connect(self._on_reset_lrmp)
        for b in (add_b, edit_b, del_b, ping_b, rst_b):
            top.addWidget(b)
        top.addStretch(1)
        self.body_layout.addLayout(top)

        self.table = UTable(["轨道", "目标符", "机器人 IP", "初始位姿 (X, Y)", "控制权", "在线 / ROS 状态"], stretch_col=5, parent=self)
        self.table.doubleClicked.connect(lambda _idx: self._on_edit())
        self.body_layout.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        self.table.setRowCount(len(self.state.tracks))
        for r, t in enumerate(self.state.tracks):
            mode = self.state.arbiter.get_state(t.target_id).value
            self.table.setItem(r, 0, QTableWidgetItem(t.name))
            self.table.setItem(r, 1, QTableWidgetItem(t.target_id))
            self.table.setItem(r, 2, QTableWidgetItem(t.robot_ip))
            self.table.setItem(r, 3, QTableWidgetItem(f"({t.init_x:.2f}, {t.init_y:.2f})"))
            self.table.setItem(r, 4, QTableWidgetItem(f"LRMP:{mode}"))
            self.table.setItem(r, 5, QTableWidgetItem(self._online_cache.get(t.target_id.upper(), "未检测")))

    def refresh_online_health(self) -> Optional[TaskHandle]:
        """Probe /api/v1/health on all tracks in the background (parallel) and refresh the table afterwards."""
        return run_in_background(
            self.state.fleet_health,
            on_done=self._on_health_done,
            busy_widgets=[self.ping_b],
            busy_text="正在后台检测全队 HTTP / ROS 在线状态...",
            notifier=self.state.notify,
        )

    def _on_health_done(self, results: Dict[str, RobotHttpResponse]) -> None:
        ok_cnt = 0
        for t in self.state.tracks:
            tid = t.target_id.upper()
            resp = results.get(tid)
            if resp is None:
                self._online_cache[tid] = "未设IP"
            elif resp.ok:
                ok_cnt += 1
                ros_s = "ROS在线" if resp.data.get("ros_master_reachable") else "ROS离线"
                self._online_cache[tid] = f"在线 · {ros_s}"
            else:
                self._online_cache[tid] = "离线"
        self.refresh()
        self.state.notify(f"设备在线检测完成: {ok_cnt}/{len(self.state.tracks)} 台可达", "ok" if ok_cnt == len(self.state.tracks) else "warn")

    def _selected_track(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.state.tracks):
            return self.state.tracks[row]
        return None

    def _on_add(self) -> None:
        if AddTrackDialog(self.state, self).exec():
            self.refresh()

    def _on_edit(self) -> None:
        tr = self._selected_track()
        if tr and AddTrackDialog(self.state, self, track=tr).exec():
            self.refresh()

    def _on_delete(self) -> None:
        tr = self._selected_track()
        if tr and tr.id is not None:
            name = self.state.delete_track_with_undo(tr.id)
            if name:
                self.state.notify(f"已删除机器人 {name} (支持 Ctrl+Z 撤销)", "info")
                self.refresh()

    def _on_reset_lrmp(self) -> Optional[TaskHandle]:
        """Release LRMP authority on every track in the background; arbiter + UI update when done."""
        commands = [(t.target_id, "RELEASE", []) for t in self.state.tracks]
        if not commands:
            self.state.notify("当前没有机器人轨道可释放", "info")
            return None
        return run_in_background(
            lambda: self.state.dispatch_targets_http(commands),
            on_done=self._on_reset_done,
            busy_text=f"正在后台向 {len(commands)} 台机器人释放 LRMP 控制权...",
            notifier=self.state.notify,
        )

    def _on_reset_done(self, results) -> None:
        ok_cnt = 0
        for r in results:
            if r.get("ok"):
                ok_cnt += 1
            self.state.arbiter.apply_command(str(r.get("target_id", "")), "RELEASE")
        self.state.bus.publish(StudioEvent.ROBOT_TELEMETRY_UPDATED, None)
        self.state.notify(f"已释放全部轨道控制权至 FREE (Wi-Fi HTTP 响应 {ok_cnt}/{len(results)})", "ok")
        self.refresh()
