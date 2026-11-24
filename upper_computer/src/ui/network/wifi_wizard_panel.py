# @file: src/ui/network/wifi_wizard_panel.py
# @brief: Step-by-step Unitree G1 LoRa wireless provisioning (scan -> connect -> IPv4) -> Wi-Fi HTTP sync panel.
# @exports: WifiWizardPanel

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTableWidgetItem,
)

from src.core.event_bus import StudioEvent
from src.services.g1_wifi_provisioner import G1WifiProvisioner
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.tokens import C_TEXT_2, FONT_MONO
from src.ui.design_system.u_buttons import UBadge, UButton
from src.ui.design_system.u_inputs import USelect
from src.ui.design_system.u_panels import UPanel, UTable


class WifiWizardPanel(UPanel):
    """G1 LoRa-only Wi-Fi provisioning wizard feeding wireless IPs to HTTP runtime."""

    def __init__(self, state: StudioStateService, provisioner: G1WifiProvisioner, parent=None) -> None:
        super().__init__(
            title="无线配网向导",
            header_widgets=[],
            parent=parent,
            help_text="通过 LoRa 串口（或备用有线 SSH）为机器人配置 Wi-Fi 与静态 IP；配网完成后业务通信全部走 Wi-Fi HTTP。",
        )
        self.state = state
        self.prov = provisioner
        self.body_layout.setSpacing(8)

        lora_row = QHBoxLayout()
        lora_row.setSpacing(6)
        self.lora_port_sel = USelect([], self.body_widget)
        ref_lora_b = UButton("刷新串口", variant="ghost", size="xs", icon_name="refresh", parent=self.body_widget)
        ref_lora_b.clicked.connect(self.refresh_lora_ports)
        bind_lora_b = UButton("1. 绑定纯 LoRa 配网口", variant="primary", size="xs", parent=self.body_widget)
        bind_lora_b.clicked.connect(self._on_bind_lora)
        probe_b = UButton("2. 探测网卡", variant="default", size="xs", parent=self.body_widget)
        probe_b.clicked.connect(self._on_probe)
        scan_b = UButton("3. 扫描 Wi-Fi", variant="default", size="xs", icon_name="refresh", parent=self.body_widget)
        scan_b.clicked.connect(self._on_scan)
        lora_lbl = QLabel("LoRa 串口:", self.body_widget)
        lora_lbl.setStyleSheet(f"color: {C_TEXT_2}; font-size: 11px;")
        lora_row.addWidget(lora_lbl)
        lora_row.addWidget(self.lora_port_sel, 1)
        lora_row.addWidget(ref_lora_b)
        lora_row.addWidget(bind_lora_b)
        lora_row.addWidget(probe_b)
        lora_row.addWidget(scan_b)
        self.body_layout.addLayout(lora_row)

        ssh_row = QHBoxLayout()
        ssh_row.setSpacing(6)
        self.host_edit = QLineEdit("192.168.123.164", self.body_widget)
        self.user_edit = QLineEdit("unitree", self.body_widget)
        self.pwd_edit = QLineEdit("vsislab509", self.body_widget)
        self.pwd_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ifname_edit = QLineEdit("wlan0", self.body_widget)
        self.ifname_edit.setFixedWidth(72)

        conn_b = UButton("可选: 有线 SSH 连接", variant="ghost", size="xs", parent=self.body_widget)
        conn_b.clicked.connect(self._on_ssh_connect)

        for lbl_t, w in (("可选有线SSH:", self.host_edit), ("用户:", self.user_edit), ("密码:", self.pwd_edit), ("网卡:", self.ifname_edit)):
            lbl = QLabel(lbl_t, self.body_widget)
            lbl.setStyleSheet(f"color: {C_TEXT_2}; font-size: 11px;")
            ssh_row.addWidget(lbl)
            ssh_row.addWidget(w)
        ssh_row.addWidget(conn_b)
        self.body_layout.addLayout(ssh_row)

        self.wifi_table = UTable(["状态", "SSID", "信号%", "加密方式", "BSSID"], self.body_widget)
        self.wifi_table.itemSelectionChanged.connect(self._on_pick_ssid)
        self.body_layout.addWidget(self.wifi_table, 1)

        bot = QHBoxLayout()
        bot.setSpacing(10)

        w_form = QFormLayout()
        self.ssid_edit = QLineEdit("", self.body_widget)
        self.wifi_pwd_edit = QLineEdit("", self.body_widget)
        self.wifi_pwd_edit.setEchoMode(QLineEdit.EchoMode.Password)
        join_b = UButton("4. 连接选中 Wi-Fi", variant="primary", size="sm", parent=self.body_widget)
        join_b.clicked.connect(self._on_connect_wifi)
        w_form.addRow("目标 SSID", self.ssid_edit)
        w_form.addRow("Wi-Fi 密码", self.wifi_pwd_edit)
        w_form.addRow("", join_b)
        bot.addLayout(w_form, 1)

        ip_form = QFormLayout()
        self.ip_method = USelect([("静态 IP (manual)", "manual"), ("自动 DHCP (auto)", "auto")], self.body_widget)
        self.ip_addr_edit = QLineEdit("192.168.50.101", self.body_widget)
        self.gw_edit = QLineEdit("192.168.50.1", self.body_widget)
        self.track_sel = USelect([], self.body_widget)
        apply_ip_b = UButton("5. 应用并同步轨道 IP", variant="default", size="sm", icon_name="check", parent=self.body_widget)
        apply_ip_b.clicked.connect(self._on_apply_ipv4)
        ip_form.addRow("配置方式", self.ip_method)
        ip_form.addRow("无线静态 IP", self.ip_addr_edit)
        ip_form.addRow("默认网关", self.gw_edit)
        ip_form.addRow("同步 HTTP 轨道", self.track_sel)
        ip_form.addRow("", apply_ip_b)
        bot.addLayout(ip_form, 1)
        self.body_layout.addLayout(bot)

        self.status_badge = UBadge("LoRa 待连接", tone="neutral", parent=self.body_widget)
        self.log_view = QPlainTextEdit(self.body_widget)
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(95)
        self.log_view.setStyleSheet(f"font-family: {FONT_MONO}; font-size: 11px;")
        self.body_layout.addWidget(self.status_badge)
        self.body_layout.addWidget(self.log_view)
        state.bus.subscribe(StudioEvent.TRACKS_UPDATED, lambda _p: self.refresh_tracks())
        self.refresh_lora_ports()
        self.refresh_tracks()

    def refresh_lora_ports(self) -> None:
        self.lora_port_sel.clear()
        ports = self.prov.list_lora_ports()
        if not ports:
            self.lora_port_sel.addItem("COM13 (默认 LoRa 串口)", "COM13")
            return
        for p in ports:
            self.lora_port_sel.addItem(f"{p.get('port')} ({p.get('description', 'LoRa')})", p.get("port"))

    def _on_bind_lora(self) -> None:
        port = str(self.lora_port_sel.current_data() or "COM13")
        res = self.prov.bind_lora_port(port)
        self.log_view.appendPlainText(f"[LoRa] {res.get('message')}")
        self.status_badge.setText(f"LoRa 已绑定: {port}")
        self.status_badge.set_tone("accent")

    def refresh_tracks(self) -> None:
        self.track_sel.clear()
        if not self.state.tracks:
            self.track_sel.addItem("请先添加真实机器人轨道", "")
            return
        for t in self.state.tracks:
            self.track_sel.addItem(f"{t.name} [{t.target_id}]", t.target_id)

    def _on_ssh_connect(self) -> None:
        self._on_bind_lora()
        res = self.prov.connect_wired_ssh(self.host_edit.text().strip(), self.user_edit.text().strip(), self.pwd_edit.text())
        self.status_badge.setText(res.get("message", ""))
        self.status_badge.set_tone("ok" if res.get("ok") else "danger")
        self.log_view.appendPlainText(f"[LoRa-Tunnel] {res.get('message')}")

    def _on_probe(self) -> None:
        res = self.prov.probe_network(self.ifname_edit.text().strip())
        self.log_view.appendPlainText(f"[PROBE] {res.get('message')}\n{res.get('probe_log', '')[:400]}")

    def _on_scan(self) -> None:
        res = self.prov.scan_wifi(self.ifname_edit.text().strip())
        self.log_view.appendPlainText(f"[SCAN] {res.get('message')}")
        nets = res.get("networks", [])
        self.wifi_table.setRowCount(len(nets))
        for r, net in enumerate(nets):
            self.wifi_table.setItem(r, 0, QTableWidgetItem("★ 已连" if net.get("in_use") else "-"))
            self.wifi_table.setItem(r, 1, QTableWidgetItem(str(net.get("ssid", ""))))
            self.wifi_table.setItem(r, 2, QTableWidgetItem(str(net.get("signal", 0))))
            self.wifi_table.setItem(r, 3, QTableWidgetItem(str(net.get("security", ""))))
            self.wifi_table.setItem(r, 4, QTableWidgetItem(str(net.get("bssid", ""))))

    def _on_pick_ssid(self) -> None:
        row = self.wifi_table.currentRow()
        if row >= 0 and self.wifi_table.item(row, 1):
            self.ssid_edit.setText(self.wifi_table.item(row, 1).text())

    def _on_connect_wifi(self) -> None:
        res = self.prov.connect_wifi(self.ssid_edit.text().strip(), self.wifi_pwd_edit.text(), self.ifname_edit.text().strip())
        self.log_view.appendPlainText(f"[WIFI] {res.get('message')}")
        ip = (res.get("state") or {}).get("ip_address", "")
        if ip:
            self.ip_addr_edit.setText(ip.split("/")[0])

    def _on_apply_ipv4(self) -> None:
        method = str(self.ip_method.current_data() or "manual")
        addr = self.ip_addr_edit.text().strip()
        res = self.prov.configure_ipv4(
            ifname=self.ifname_edit.text().strip(), method=method,
            address=addr, netmask="255.255.255.0", gateway=self.gw_edit.text().strip(),
        )
        self.log_view.appendPlainText(f"[IPv4] {res.get('message')}")
        if res.get("ok"):
            final_ip = (res.get("state") or {}).get("ip_address") or addr
            tgt = str(self.track_sel.current_data() or "")
            if tgt:
                self.prov.sync_track_wireless_ip(tgt, final_ip)
            else:
                self.state.notify("IPv4 已通过 LoRa 配网下发；尚无轨道可同步，请按需在编排页添加轨道", "info")
