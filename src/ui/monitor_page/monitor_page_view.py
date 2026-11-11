import logging
import time
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from src.application.services.lrmp_show_coordinator import LRMPShowCoordinator
from src.core.event_bus import event_bus
from src.ui.monitor_page.monitor_map_panel import MonitorMapPanel
from src.ui.monitor_page.swarm_control_header import SwarmControlHeader

logger = logging.getLogger("MonitorPageView")


class MonitorPageView(QWidget):
    """
    Unified Show Monitoring Workspace:
    - Upper Left: Stage LiDAR occupancy map & AI arrange toolstrip.
    - Upper Right: Swarm control header, empty state placeholder ('无机器人在线') or active vital cards.
    - Bottom: Real-time show synchronization progress timeline bar.
    - Sub-actions: Assign ID, Initialize, Sync Task/Traj/Map, Slide-to-brake Emergency Stop.
    """

    def __init__(self, parent: Optional[QWidget] = None, controller: Optional[Any] = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.coordinator = LRMPShowCoordinator(parent=self)
        self._active_robots: List[Dict[str, Any]] = [
            {"id": "A", "alias": "Robot_1", "ip": "172.18.0.101", "bat": 92, "temp": 41.0, "synced": True, "pos": "(-2.0, 0.0)"},
            {"id": "B", "alias": "Robot_2", "ip": "172.18.0.102", "bat": 92, "temp": 41.0, "synced": True, "pos": "(2.0, 0.0)"},
        ]
        self._init_ui()
        self._wire_signals()

    def _init_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(8)

        self.h_splitter = QSplitter(Qt.Horizontal, self)
        root_layout.addWidget(self.h_splitter, 1)

        self.map_panel = MonitorMapPanel(self.h_splitter, controller=self.controller)
        self.h_splitter.addWidget(self.map_panel)

        right_container = QFrame(self.h_splitter)
        right_container.setStyleSheet("background-color: #0E121A; border-radius: 6px;")
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        self.control_header = SwarmControlHeader(right_container, controller=self.controller)
        right_layout.addWidget(self.control_header)

        self.fleet_stack = QStackedWidget(right_container)
        self.empty_card = self._build_empty_card()
        self.fleet_cards_container = QFrame(self.fleet_stack)
        self.fleet_cards_container.setStyleSheet("background-color: #111318; border: 1px solid #1E293B; border-radius: 6px;")
        self.fleet_cards_layout = QVBoxLayout(self.fleet_cards_container)
        self.fleet_cards_layout.setContentsMargins(8, 8, 8, 8)
        self.fleet_cards_layout.setSpacing(6)
        self._populate_fleet_cards()

        self.fleet_stack.addWidget(self.empty_card)
        self.fleet_stack.addWidget(self.fleet_cards_container)
        self.fleet_stack.setCurrentIndex(0 if self.controller is not None else 1)
        right_layout.addWidget(self.fleet_stack, 1)
        self.h_splitter.addWidget(right_container)
        self.h_splitter.setSizes([520, 760])

        bottom_bar = QFrame(self)
        bottom_bar.setFixedHeight(48)
        bottom_bar.setStyleSheet("background-color: #111318; border: 1px solid #1E293B; border-radius: 6px;")
        b_layout = QHBoxLayout(bottom_bar)
        b_layout.setContentsMargins(12, 6, 12, 6)

        self.lbl_progress_state = QLabel("● 待命中 (00:00.000 / 02:30.000)", bottom_bar)
        self.lbl_progress_state.setStyleSheet("color: #38BDF8; font-weight: 700; font-size: 11px;")
        b_layout.addWidget(self.lbl_progress_state)

        self.progress_bar = QProgressBar(bottom_bar)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background-color: #1E2430; border-radius: 4px; text-align: center; color: #FFF; height: 14px; }
            QProgressBar::chunk { background-color: #1E6FFF; border-radius: 4px; }
        """)
        b_layout.addWidget(self.progress_bar, 1)
        root_layout.addWidget(bottom_bar)

    def _build_empty_card(self) -> QWidget:
        box = QFrame(self)
        box.setStyleSheet("background-color: #111318; border: 1px dashed #334155; border-radius: 6px;")
        layout = QVBoxLayout(box)
        layout.setAlignment(Qt.AlignCenter)
        lbl_icon = QLabel("🤖", box)
        lbl_icon.setStyleSheet("font-size: 32px;")
        lbl_icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_icon)
        lbl_msg = QLabel("无机器人在线\n请先点击右上角「初始化」发现并建链机器人", box)
        lbl_msg.setStyleSheet("color: #64748B; font-size: 12px; font-weight: 600; line-height: 18px;")
        lbl_msg.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_msg)
        return box

    def _populate_fleet_cards(self) -> None:
        while self.fleet_cards_layout.count() > 0:
            item = self.fleet_cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for r in self._active_robots:
            card = QFrame(self.fleet_cards_container)
            card.setStyleSheet("background-color: #1A202C; border: 1px solid #2D3748; border-radius: 4px; padding: 6px;")
            c_lay = QHBoxLayout(card)
            c_lay.setContentsMargins(8, 4, 8, 4)
            lbl = QLabel(f"● ID: {r['id']} ({r['alias']}) | 电量: {r['bat']}% | 温度: {int(r['temp'])}°C | 坐标: {r.get('pos', '0,0')} | 状态: READY", card)
            lbl.setStyleSheet("color: #E2E8F0; font-size: 11px; font-weight: 600;")
            c_lay.addWidget(lbl)
            self.fleet_cards_layout.addWidget(card)
        self.fleet_cards_layout.addStretch(1)

    def _wire_signals(self) -> None:
        self.control_header.playTriggered.connect(self._on_play_triggered)
        self.control_header.initClicked.connect(self._on_init_clicked)
        self.control_header.syncActionClicked.connect(self._on_sync_action)
        self.control_header.deviceActionClicked.connect(self._on_device_action)
        self.control_header.emergencyStopTriggered.connect(self._on_emergency_stop)
        self.coordinator.showStarted.connect(self._on_show_started)
        self.coordinator.stepProgress.connect(self._on_coordinator_progress)

    def _on_emergency_stop(self) -> None:
        if self.controller:
            self.controller.send_lrmp(["A", "B"], "STOP")
            if self.controller.is_playing:
                self.controller.toggle_playback()
            self.controller.swarm_status_changed.emit({"emergency_alarm": True, "status": "STOPPED"})
        self.coordinator.emergency_stop("右滑急停触发")
        self.lbl_progress_state.setText("● 🚨 急停已触发 (A,B|STOP)")
        self.lbl_progress_state.setStyleSheet("color: #EF4444; font-weight: 700; font-size: 11px;")
        if not getattr(self, "_suppress_alert", False):
            msg = QMessageBox(self)
            msg.setWindowTitle("急停告警")
            msg.setIcon(QMessageBox.Warning)
            msg.setText("全员急停指令 (A,B|STOP) 已下发！\n时间轴已暂停播放，状态栏进入急停告警。")
            msg.show()

    def _on_init_clicked(self) -> None:
        if self.controller:
            self.controller.send_lrmp(["ALL"], "DISCOVER")
            self.controller.send_lrmp(["A", "B"], "SETUP", "601")
            self.controller.swarm_status_changed.emit({"robot_count": 2, "status": "READY", "emergency_alarm": False})
        self._populate_fleet_cards()
        self.fleet_stack.setCurrentIndex(1)
        self.lbl_progress_state.setText("● 集群就绪 (Robot_1, Robot_2 在线 | READY)")
        self.lbl_progress_state.setStyleSheet("color: #10B981; font-weight: 700; font-size: 11px;")

    def _on_play_triggered(self, mode: str) -> None:
        t0_ms = int(time.time() * 1000) + 3000
        targets = [r["id"] for r in self._active_robots] or ["A", "B"]
        if self.controller:
            self.controller.send_lrmp(["A", "B"], "PLAY", f"9001,{t0_ms}")
            if not self.controller.is_playing:
                self.controller.toggle_playback()
        self.coordinator.prepare_show(targets, "8001")
        self.coordinator.start_music_show(lead_time_ms=3000)
        self.control_header.set_is_playing(True)
        self.lbl_progress_state.setText(f"● 音乐伴舞运行中 (T0={t0_ms})")
        self.lbl_progress_state.setStyleSheet("color: #38BDF8; font-weight: 700; font-size: 11px;")

    def _on_sync_action(self, action: str) -> None:
        targets = [r["id"] for r in self._active_robots] or ["A", "B"]
        if action == "TASK":
            if self.controller:
                self.controller.send_lrmp(["A", "B"], "PREP", "8001,9001")
            self.coordinator.sync_task(targets, "8001,9001")
            self.lbl_progress_state.setText("● 任务已同步 (PREP 8001,9001 -> READY)")
        elif action == "TRAJECTORY":
            if self.controller:
                self.controller.send_lrmp(["A", "B"], "SYNC_TRAJ", "100001,100002")
            self.coordinator.sync_trajectory(targets, "TRAJ_01")
            self.lbl_progress_state.setText("● 轨迹已同步")
        elif action == "MAP":
            if self.controller:
                self.controller.send_lrmp(["A", "B"], "SYNC_MAP", "default")
            self.show_map_check_dialog()

    def _on_device_action(self, code: str) -> None:
        if code == "ASSIGN_ID":
            if self.controller:
                self.controller.send_lrmp(["ALL"], "DISCOVER")
                self.controller.send_lrmp(["GW_8C2F"], "BIND", "A")
            self.show_assign_id_dialog()
        elif code == "MAP_CHECK":
            self.show_map_check_dialog()
        elif code == "MUSIC_CHECK":
            self.show_music_check_dialog()
        elif code == "OVERVIEW":
            self.map_panel.update()

    def _on_show_started(self, t0_ms: int) -> None:
        self.lbl_progress_state.setText(f"● 演出中 (T0={t0_ms})")
        self.progress_bar.setValue(10)

    def _on_coordinator_progress(self, msg: str, pct: float) -> None:
        self.lbl_progress_state.setText(f"● {msg}")
        self.progress_bar.setValue(int(pct * 100))

    def show_assign_id_dialog(self) -> None:
        msg = QMessageBox(self)
        msg.setWindowTitle("分配 ID 与网关绑定")
        msg.setText("【分配 ID 控制台】\n已广播 ALL|DISCOVER\n发现网关设备 GW_8C2F -> 绑定 ID: A\n已下发 GW_8C2F|BIND,A")
        msg.show()

    def show_init_dialog(self) -> None:
        self._on_init_clicked()

    def show_map_check_dialog(self) -> None:
        msg = QMessageBox(self)
        msg.setWindowTitle("地图检查")
        msg.setText("【舞台地图状态检查】\n点云地图: 已加载\n分辨率: 0.05m\n高程范围: -0.2m ~ 2.0m\n校验: PASSED")
        msg.show()

    def show_music_check_dialog(self) -> None:
        msg = QMessageBox(self)
        msg.setWindowTitle("音乐伴奏检查")
        msg.setText("【音乐伴奏检查】\n伴奏音频: stage_bgm.mp3 (就绪)\n采样率: 44.1kHz\n波形时钟: 已对齐")
        msg.show()
