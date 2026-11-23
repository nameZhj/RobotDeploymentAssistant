# @file: src/ui/network/system_network_page.py
# @brief: UniUni Page 6 Network Provisioning & System Settings workspace with persistent settings and stage reset.
# @exports: SystemNetworkPage

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QFormLayout, QHBoxLayout, QInputDialog, QTableWidgetItem, QWidget

from src.core.event_bus import StudioEvent
from src.core.settings import get_settings
from src.services.g1_wifi_provisioner import G1WifiProvisioner
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.u_buttons import UButton
from src.ui.design_system.u_inputs import UInputNumber
from src.ui.design_system.u_panels import UPanel, UTable
from src.ui.network.wifi_wizard_panel import WifiWizardPanel


class SystemNetworkPage(QWidget):
    """Page 6 housing G1 Wi-Fi setup, track wireless IP CRUD, and persistent system parameters."""

    def __init__(self, state: StudioStateService, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.provisioner = G1WifiProvisioner(state)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        self.wizard = WifiWizardPanel(state, self.provisioner, self)
        lay.addWidget(self.wizard, 2)

        right = UPanel(title="机群 IP 路由表与系统参数", header_widgets=[], parent=self)
        right.setFixedWidth(365)
        self.ip_table = UTable(["轨道", "LRMP 目标", "当前通讯 IP", "型号"], stretch_col=2, parent=right.body_widget)
        right.body_layout.addWidget(self.ip_table, 1)

        ip_btn_row = QHBoxLayout()
        edit_ip_b = UButton("修改选中 IP", variant="default", size="xs", icon_name="edit", parent=right.body_widget)
        edit_ip_b.clicked.connect(self._edit_selected_ip)
        demo_b = UButton("载入 4 机示例", variant="ghost", size="xs", parent=right.body_widget)
        demo_b.clicked.connect(self.state.load_demo_swarm_preset)
        clr_b = UButton("清空轨道", variant="danger", size="xs", parent=right.body_widget)
        clr_b.clicked.connect(self.state.clear_all_tracks)
        for b in (edit_ip_b, demo_b, clr_b):
            ip_btn_row.addWidget(b)
        right.body_layout.addLayout(ip_btn_row)

        cfg = get_settings()
        form = QFormLayout()
        self.safety_spin = UInputNumber(cfg.stage_defaults.safety_distance_m, 0.25, 3.0, 0.05, 2, "m", right.body_widget)
        self.virt_http_chk = QCheckBox("启用 HTTP 虚拟轨迹接口降级 (无实机测试)", right.body_widget)
        self.virt_http_chk.setChecked(cfg.virtual_interfaces.http_upload_virtual_fallback)
        self.safety_spin.valueChanged.connect(lambda _v: self._persist_settings())
        self.virt_http_chk.toggled.connect(lambda _c: self._persist_settings())
        form.addRow("碰撞安全阈值", self.safety_spin)
        right.body_layout.addLayout(form)
        right.body_layout.addWidget(self.virt_http_chk)
        lay.addWidget(right)

        state.bus.subscribe(StudioEvent.TRACKS_UPDATED, lambda _p: self.refresh_ips())
        self.refresh_ips()

    def _persist_settings(self) -> None:
        self.state.apply_settings_update(self.safety_spin.value(), self.virt_http_chk.isChecked())
        self.state.notify(
            f"系统参数已保存 (安全阈值 {self.safety_spin.value():.2f}m | HTTP虚拟降级={'开' if self.virt_http_chk.isChecked() else '关'})",
            "ok",
        )

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
            self.ip_table.setItem(r, 0, QTableWidgetItem(tr.name))
            self.ip_table.setItem(r, 1, QTableWidgetItem(tr.target_id))
            self.ip_table.setItem(r, 2, QTableWidgetItem(tr.robot_ip))
            self.ip_table.setItem(r, 3, QTableWidgetItem(tr.robot_model))
