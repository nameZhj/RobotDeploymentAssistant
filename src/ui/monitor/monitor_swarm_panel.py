"""
@file: src/ui/monitor/monitor_swarm_panel.py
@brief: 表演监测右侧集群控制面板（急停滑块、模式选择、同步控制与五大标签页）
@exports: SlideEmergencyBrake, MonitorSwarmPanel
"""
from typing import Any, Dict, Optional, Set
from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QPushButton, QTabWidget, QVBoxLayout, QWidget
)
from src.application.services.swarm_monitor_service import SwarmMonitorService


class SlideEmergencyBrake(QFrame):
    """右滑触发急停的安全滑块控件"""
    emergency_triggered = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(34)
        self.setFixedWidth(140)
        self.setStyleSheet("QFrame { background-color: #3a1515; border: 1px solid #c0392b; border-radius: 17px; }")
        self.handle_x = 3.0
        self.dragging = False

    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QColor("#e74c3c"))
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, ">> 右滑急停 >>")
        p.setBrush(QColor("#c0392b"))
        p.setPen(QColor("#ffffff"))
        p.drawEllipse(int(self.handle_x), 3, 28, 28)
        p.drawText(QRect(int(self.handle_x), 3, 28, 28), Qt.AlignmentFlag.AlignCenter, "●")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and event.position().x() <= self.handle_x + 32:
            self.dragging = True

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self.dragging:
            return
        self.handle_x = max(3.0, min(float(event.position().x() - 14), float(self.width() - 31)))
        self.update()
        if self.handle_x >= self.width() - 33:
            self.dragging = False
            self.handle_x = 3.0
            self.emergency_triggered.emit()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.dragging = False
        self.handle_x = 3.0
        self.update()


class MonitorSwarmPanel(QWidget):
    """集群演播控制台：双机状态监测、批处理命令与多维同步"""
    def __init__(self, swarm_service: Optional[SwarmMonitorService] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.service = swarm_service or SwarmMonitorService()
        self.selected_robots: Set[str] = set(self.service.robot_bindings.keys())
        self.card_checkboxes: Dict[str, QCheckBox] = {}
        self._init_ui()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        root.addLayout(self._create_row1())
        root.addLayout(self._create_row2())
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_overview_tab(), "☷ 总览")
        self.tabs.addTab(self._build_batch_tab(), "批量操作")
        self.tabs.addTab(self._build_id_assign_tab(), "分配ID")
        self.tabs.addTab(self._build_map_check_tab(), "地图检查")
        self.tabs.addTab(self._build_music_check_tab(), "音乐检查")
        root.addWidget(self.tabs)
        self.lbl_status = QLabel("就绪 | 当前状态: IDLE")
        root.addWidget(self.lbl_status)

    def _create_row1(self) -> QHBoxLayout:
        r1 = QHBoxLayout()
        self.btn_play = QPushButton("▷ 音乐伴奏")
        self.btn_play.setStyleSheet("background-color: #1976d2; color: white; font-weight: bold; min-height: 28px;")
        self.btn_play.clicked.connect(self._on_play_clicked)
        r1.addWidget(self.btn_play)
        self.brake_slider = SlideEmergencyBrake(self)
        self.brake_slider.emergency_triggered.connect(self._on_emergency_brake)
        r1.addWidget(self.brake_slider)
        for mode in ["音乐伴奏", "舞蹈调试", "循环执行"]:
            btn = QPushButton(mode)
            btn.setCheckable(True)
            btn.setChecked(mode == "音乐伴奏")
            r1.addWidget(btn)
        return r1

    def _create_row2(self) -> QHBoxLayout:
        r2 = QHBoxLayout()
        self.chk_all = QCheckBox("全选")
        self.chk_all.setChecked(True)
        self.chk_all.stateChanged.connect(self._on_toggle_select_all)
        r2.addWidget(self.chk_all)
        self.btn_init = QPushButton("初始化")
        self.btn_init.setStyleSheet("background-color: #d35400; color: white; font-weight: bold;")
        self.btn_init.clicked.connect(self._on_init_clicked)
        r2.addWidget(self.btn_init)
        for name, callback in [("同步任务", lambda: self._on_sync("任务", self.service.sync_task)),
                               ("同步轨迹", lambda: self._on_sync("轨迹", lambda: self.service.sync_task("TRAJ"))),
                               ("同步地图", lambda: self._on_sync("地图", self.service.run_map_check))]:
            btn = QPushButton(name)
            btn.clicked.connect(callback)
            r2.addWidget(btn)
        return r2

    def _build_overview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.cards_layout = QGridLayout()
        self._refresh_overview_cards()
        layout.addLayout(self.cards_layout)
        layout.addStretch()
        return widget

    def _refresh_overview_cards(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.card_checkboxes.clear()
        for idx, (alias, data) in enumerate(self.service.robot_bindings.items()):
            card = QGroupBox(f"机体 {alias} ({data['gw_id']})")
            vbox = QVBoxLayout(card)
            chk = QCheckBox(f"选择 轨道: {data['track_id']}")
            chk.setChecked(alias in self.selected_robots)
            chk.stateChanged.connect(lambda s, a=alias: self._on_card_checked(a, s))
            self.card_checkboxes[alias] = chk
            vbox.addWidget(chk)
            auth = self.service.arbiter.get_state(alias)
            vbox.addWidget(QLabel(f"控制权: {auth} | 在线: 正常\n电量: 86%  温度: 32℃\n坐标: x={data['pos'][0]:.2f}, y={data['pos'][1]:.2f}"))
            self.cards_layout.addWidget(card, idx // 2, idx % 2)

    def _build_batch_tab(self) -> QWidget:
        widget = QWidget()
        grid = QGridLayout(widget)
        for idx, (t, c) in enumerate([("起立", "STAND"), ("踏步", "GAIT"), ("阻尼", "PASSIVE"), ("急停释放", "RELEASE")]):
            btn = QPushButton(t)
            btn.setStyleSheet("min-height: 32px;")
            btn.clicked.connect(lambda _, cmd=c: self._on_batch_cmd(cmd))
            grid.addWidget(btn, idx // 2, idx % 2)
        return widget

    def _build_id_assign_tab(self) -> QWidget:
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        self.combo_gw = QComboBox()
        self.combo_gw.addItems(["GW_8C2F", "GW_9B1D"])
        self.combo_alias = QComboBox()
        self.combo_alias.addItems(["A", "B", "C"])
        vbox.addWidget(self.combo_gw)
        vbox.addWidget(self.combo_alias)
        btn_bind = QPushButton("执行绑定")
        btn_bind.clicked.connect(self._on_bind_clicked)
        vbox.addWidget(btn_bind)
        vbox.addStretch()
        return widget

    def _build_map_check_tab(self) -> QWidget:
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        self.lbl_map_res = QLabel("未校验")
        vbox.addWidget(self.lbl_map_res)
        btn_check = QPushButton("立即校验地图 MD5")
        btn_check.clicked.connect(lambda: self.lbl_map_res.setText(f"通过: {self.service.run_map_check()}"))
        vbox.addWidget(btn_check)
        vbox.addStretch()
        return widget

    def _build_music_check_tab(self) -> QWidget:
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        self.lbl_music_res = QLabel("未校验")
        vbox.addWidget(self.lbl_music_res)
        btn_check = QPushButton("校验音频文件与指纹")
        btn_check.clicked.connect(lambda: self.lbl_music_res.setText("音频存在且指纹一致" if self.service.run_music_check("默认音乐") else "不存在"))
        vbox.addWidget(btn_check)
        vbox.addStretch()
        return widget

    def _on_card_checked(self, alias: str, state: int) -> None:
        if state == Qt.CheckState.Checked.value:
            self.selected_robots.add(alias)
        else:
            self.selected_robots.discard(alias)

    def _on_toggle_select_all(self, state: int) -> None:
        is_chk = state == Qt.CheckState.Checked.value
        for chk in self.card_checkboxes.values():
            chk.setChecked(is_chk)
        self.selected_robots = set(self.service.robot_bindings.keys()) if is_chk else set()

    def _on_play_clicked(self) -> None:
        ok = self.service.start_performance()
        self.lbl_status.setText(f"开演状态: {'成功 (PLAYING)' if ok else '失败 (未就绪或被拒)'}")

    def _on_emergency_brake(self) -> None:
        self.service.emergency_brake_all()
        self.lbl_status.setText("!! 紧急急停已执行: 所有机器人已刹车 !!")
        self._refresh_overview_cards()

    def _on_init_clicked(self) -> None:
        ok = self.service.initialize_robots_to_start()
        self.lbl_status.setText(f"初始化定位: {'全部就绪 (READY)' if ok else '失败'}")
        self._refresh_overview_cards()

    def _on_sync(self, name: str, fn: Any) -> None:
        fn()
        self.lbl_status.setText(f"已下发{name}同步指令")

    def _on_batch_cmd(self, cmd: str) -> None:
        for r in self.selected_robots:
            self.service.send_motion_command(r, cmd)
        self.lbl_status.setText(f"批量下发 {cmd} 到: {list(self.selected_robots)}")
        self._refresh_overview_cards()

    def _on_bind_clicked(self) -> None:
        gw = self.combo_gw.currentText()
        alias = self.combo_alias.currentText()
        self.service.bind_device_alias(gw, alias, track_id=1)
        self._refresh_overview_cards()
        self.lbl_status.setText(f"已绑定 {gw} -> {alias}")
