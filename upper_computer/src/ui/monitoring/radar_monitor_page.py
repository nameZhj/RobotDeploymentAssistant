# @file: src/ui/monitoring/radar_monitor_page.py
# @brief: UniUni Page 5 Live Radar & Safety Perimeter Telemetry monitoring view synced with playhead and tracks.
# @exports: RadarMonitorPage

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QTableWidgetItem, QWidget

from src.core.event_bus import StudioEvent
from src.core.settings import get_settings
from src.services.studio_state_service import StudioStateService
from src.ui.choreography.stage_canvas_2d import StageCanvas2D
from src.ui.design_system.u_buttons import UButton
from src.ui.design_system.u_panels import UPanel, UTable


class RadarMonitorPage(QWidget):
    """2D top-down lidar/safety monitor and live fleet telemetry inspector."""

    _telemetrySignal = Signal()

    def __init__(self, state: StudioStateService, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        left = UPanel(title="二维雷达安全区与实时分布", parent=self)
        self.canvas = StageCanvas2D(state, left.body_widget)
        left.body_layout.addWidget(self.canvas, 1)
        lay.addWidget(left, 2)

        right = UPanel(title="单机心跳与位姿遥测 (Wi-Fi HTTP)", parent=self)
        right.setFixedWidth(455)
        self.table = UTable(["目标", "位姿 (X,Y,Yaw)", "安全净空 / 定位", "通讯 IP"], stretch_col=2, parent=right.body_widget)
        ref_b = UButton("刷新状态快照", variant="default", size="sm", icon_name="refresh", parent=right.body_widget)
        ref_b.clicked.connect(self.refresh)
        right.body_layout.addWidget(self.table, 1)
        right.body_layout.addWidget(ref_b)
        lay.addWidget(right)

        self._telemetrySignal.connect(self.refresh, Qt.ConnectionType.QueuedConnection)
        for ev in (StudioEvent.PLAYHEAD_MOVED, StudioEvent.TRACKS_UPDATED, StudioEvent.COLLISION_UPDATED):
            state.bus.subscribe(ev, lambda _p: self.refresh())
        state.bus.subscribe(StudioEvent.ROBOT_TELEMETRY_UPDATED, lambda _p: self._telemetrySignal.emit())
        self.refresh()

    def refresh(self) -> None:
        t = self.state.playhead_s
        d_safe = get_settings().stage_defaults.safety_distance_m
        cb_map = self.state.callback_listener.latest_by_target
        coll_set = {c.track_a for c in self.state.collisions if c.start_time <= t <= c.end_time} | {
            c.track_b for c in self.state.collisions if c.start_time <= t <= c.end_time
        }
        self.table.setRowCount(len(self.state.tracks))
        for r, tr in enumerate(self.state.tracks):
            live = cb_map.get(tr.target_id.upper(), {})
            live_pose = live.get("pose") if isinstance(live.get("pose"), dict) else None
            if live_pose is not None:
                x, y, yaw = float(live_pose.get("x", 0.0)), float(live_pose.get("y", 0.0)), float(live_pose.get("yaw", 0.0))
                src_tag = " [实机]"
            else:
                x, y, yaw = self.state.evaluate_robot_pose(tr, t)
                src_tag = ""
            in_err = tr.name in coll_set
            self.table.setItem(r, 0, QTableWidgetItem(f"{tr.name} [{tr.target_id}]"))
            self.table.setItem(r, 1, QTableWidgetItem(f"{x:.2f}, {y:.2f}, {yaw:.2f}{src_tag}"))
            self.table.setItem(r, 2, QTableWidgetItem(f"告警 (<{d_safe:.2f}m)" if in_err else f"安全 ≥{d_safe:.2f}m"))
            self.table.setItem(r, 3, QTableWidgetItem(tr.robot_ip))
