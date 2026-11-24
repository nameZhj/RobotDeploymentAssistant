# @file: src/ui/network/system_network_page.py
# @brief: Page 5 Network Provisioning & System Settings workspace with pure Wi-Fi HTTP health check & persistent params.
# @exports: SystemNetworkPage

from __future__ import annotations

from typing import Dict
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QInputDialog, QTableWidgetItem, QWidget

from src.core.event_bus import StudioEvent
from src.core.settings import get_settings, save_settings
from src.protocol.robot_http_client import RobotHttpClient
from src.services.g1_wifi_provisioner import G1WifiProvisioner
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.u_buttons import UButton
from src.ui.design_system.u_inputs import UInputNumber
from src.ui.design_system.u_panels import UPanel, UTable
from src.ui.network.wifi_wizard_panel import WifiWizardPanel


class SystemNetworkPage(QWidget):
    """System & Network page housing LoRa Wi-Fi setup, real track IP routing, HTTP/ROS health check, and safety params."""

    def __init__(self, state: StudioStateService, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.provisioner = G1WifiProvisioner(state)
        self._health_status: Dict[str, str] = {}

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        self.wizard = WifiWizardPanel(state, self.provisioner, self)
        lay.addWidget(self.wizard, 2)

        right = UPanel(
            title="集群路由与参数",
            header_widgets=[],
            parent=self,
            help_text="管理各机器人轨道 Wi-Fi IP 与在线状态，调整碰撞安全阈值和默认 HTTP 端口。",
        )
        right.setFixedWidth(420)
        self.ip_table = UTable(["轨道", "目标", "Wi-Fi IP", "在线状态"], stretch_col=3, parent=right.body_widget)
        right.body_layout.addWidget(self.ip_table, 1)

        ip_btn_row = QHBoxLayout()
        edit_ip_b = UButton("修改 IP", variant="default", size="xs", icon_name="edit", parent=right.body_widget)
        edit_ip_b.clicked.connect(self._edit_selected_ip)
        check_b = UButton("全队在线体检", variant="primary", size="xs", icon_name="refresh", parent=right.body_widget)
        check_b.clicked.connect(self.check_fleet_online)
        clr_b = UButton("清空轨道", variant="danger", size="xs", parent=right.body_widget)
        clr_b.clicked.connect(self.state.clear_all_tracks)
        for b in (edit_ip_b, check_b, clr_b):
            ip_btn_row.addWidget(b)
        right.body_layout.addLayout(ip_btn_row)

        cfg = get_settings()
        form = QFormLayout()
        self.safety_spin = UInputNumber(cfg.stage_defaults.safety_distance_m, 0.25, 3.0, 0.05, 2, "m", right.body_widget)
        self.port_spin = UInputNumber(float(cfg.virtual_interfaces.http_default_port), 80, 65535, 1, 0, "", right.body_widget)
        self.safety_spin.valueChanged.connect(lambda _v: self._persist_settings())
        self.port_spin.valueChanged.connect(lambda _v: self._persist_settings())
        form.addRow("碰撞安全阈值", self.safety_spin)
        form.addRow("HTTP 默认端口", self.port_spin)
        right.body_layout.addLayout(form)
        lay.addWidget(right)

        state.bus.subscribe(StudioEvent.TRACKS_UPDATED, lambda _p: self.refresh_ips())
        self.refresh_ips()

    def _persist_settings(self) -> None:
        self.state.apply_settings_update(self.safety_spin.value(), False)
        cfg = get_settings()
        cfg.virtual_interfaces.http_default_port = int(self.port_spin.value())
        save_settings(cfg)
        self.state.notify(
            f"系统参数已保存 (安全阈值 {self.safety_spin.value():.2f}m | HTTP 端口 {int(self.port_spin.value())})",
            "ok",
        )

    def check_fleet_online(self) -> int:
        """Probe GET /api/v1/health on every configured track over Wi-Fi HTTP."""
        if not self.state.tracks:
            self.state.notify("暂无真实机器人轨道可检测", "warn")
            return 0
        client = RobotHttpClient(timeout_s=1.2)
        ok_cnt = 0
        for tr in self.state.tracks:
            tid = tr.target_id.upper()
            if not tr.robot_ip:
                self._health_status[tid] = "未配置 IP"
                continue
            resp = client.health(tr.robot_ip, port=int(self.port_spin.value()))
            if resp.ok:
                ok_cnt += 1
                ros_s = "ROS在线" if resp.data.get("ros_master_reachable") else "ROS离线"
                nav_s = "navctl就绪" if resp.data.get("navctl_available") else "无navctl"
                self._health_status[tid] = f"在线 · {ros_s} · {nav_s}"
            else:
                self._health_status[tid] = "离线 / 不可达"
        self.refresh_ips()
        self.state.notify(f"机群体检完成：{ok_cnt}/{len(self.state.tracks)} 台 Wi-Fi HTTP 在线", "ok" if ok_cnt == len(self.state.tracks) else "warn")
        return ok_cnt

    def _edit_selected_ip(self) -> None:
        row = self.ip_table.currentRow()
        if not (0 <= row < len(self.state.tracks)):
            self.state.notify("请先在路由表中选择一台机器人", "warn")
            return
        tr = self.state.tracks[row]
        new_ip, ok = QInputDialog.getText(self, "修改通讯 IP", f"{tr.name} [{tr.target_id}] IP:", text=tr.robot_ip)
        if ok and new_ip.strip():
            tr.robot_ip = new_ip.strip()
            self.state.scene_repo.upsert_track(tr)
            self.state.reload_all()
            self.state.bus.publish(StudioEvent.TRACKS_UPDATED, tr.id)
            self.state.notify(f"已更新 {tr.name} IP 为 {tr.robot_ip}", "ok")

    def refresh_ips(self) -> None:
        self.ip_table.setRowCount(len(self.state.tracks))
        for r, tr in enumerate(self.state.tracks):
            tid = tr.target_id.upper()
            self.ip_table.setItem(r, 0, QTableWidgetItem(tr.name))
            self.ip_table.setItem(r, 1, QTableWidgetItem(tr.target_id))
            self.ip_table.setItem(r, 2, QTableWidgetItem(tr.robot_ip))
            self.ip_table.setItem(r, 3, QTableWidgetItem(self._health_status.get(tid, "未检测")))
