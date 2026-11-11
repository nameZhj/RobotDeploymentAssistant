import logging
import random
from typing import Dict, List, Optional
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from src.application.services.fleet_onboarding_svc import fleet_onboarding_svc
from src.core.event_bus import event_bus
from src.ui.right_dock.manual_override_drawer import ManualOverrideDrawer
from src.ui.right_dock.robot_vital_card import RobotVitalCard

logger = logging.getLogger("FleetTelemetryDock")


class FleetTelemetryDock(QWidget):
    """
    Fleet telemetry dock managing device list, broadcast discovery with backoff,
    unbound gateway pairing, multi-selection, and vital cards.
    """

    selectedRobotsChanged = Signal(list)
    discoveryTriggered = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._cards: Dict[str, RobotVitalCard] = {}
        self._selected_aliases: List[str] = []
        self._backoff_timer = QTimer(self)
        self._backoff_timer.timeout.connect(self._on_backoff_tick)
        self._backoff_remaining_ms = 0

        self._init_ui()
        self._populate_initial_fleet()
        self._subscribe_events()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        top_bar = QHBoxLayout()
        self.btn_discover = QPushButton("📡 发现 ALL|DISCOVER", self)
        self.btn_discover.setStyleSheet("""
            QPushButton { background: #0284c7; color: #fff; font-weight: 700; border-radius: 4px; padding: 5px 8px; font-size: 11px; }
            QPushButton:hover { background: #0369a1; }
        """)
        self.btn_discover.clicked.connect(self._start_discovery_with_backoff)
        top_bar.addWidget(self.btn_discover)

        self.btn_pair_gw = QPushButton("🔗 配对网关", self)
        self.btn_pair_gw.setStyleSheet("""
            QPushButton { background: #475569; color: #f1f5f9; border-radius: 4px; padding: 5px 8px; font-size: 11px; }
            QPushButton:hover { background: #64748b; }
        """)
        self.btn_pair_gw.clicked.connect(self._auto_pair_unbound_gateways)
        top_bar.addWidget(self.btn_pair_gw)
        layout.addLayout(top_bar)

        ctrl_bar = QHBoxLayout()
        self.chk_all = QCheckBox("全选集群机甲", self)
        self.chk_all.setChecked(True)
        self.chk_all.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self.chk_all.toggled.connect(self._toggle_select_all)
        ctrl_bar.addWidget(self.chk_all)

        self.lbl_count = QLabel("在线: 0 台", self)
        self.lbl_count.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 600;")
        ctrl_bar.addStretch(1)
        ctrl_bar.addWidget(self.lbl_count)
        layout.addLayout(ctrl_bar)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.card_container = QWidget()
        self.card_layout = QVBoxLayout(self.card_container)
        self.card_layout.setContentsMargins(2, 2, 2, 2)
        self.card_layout.setSpacing(6)
        self.card_layout.addStretch(1)
        self.scroll.setWidget(self.card_container)
        layout.addWidget(self.scroll, 1)

        self.drawer = ManualOverrideDrawer(self)
        layout.addWidget(self.drawer)

    def _populate_initial_fleet(self) -> None:
        for alias in ["A", "B"]:
            self.add_or_update_robot(alias, {"is_online": True, "battery": 95, "temperature": 36.8, "pose": (0.0, 0.0, 0.0)})
        self._update_selected_list()

    def add_or_update_robot(self, alias: str, data: Dict) -> None:
        clean_alias = alias.strip().upper()
        if clean_alias not in self._cards:
            card = RobotVitalCard(clean_alias, self.card_container)
            card.selectionChanged.connect(self._on_card_selection_changed)
            card.cardClicked.connect(self._on_card_clicked)
            self._cards[clean_alias] = card
            self.card_layout.insertWidget(self.card_layout.count() - 1, card)

        self._cards[clean_alias].update_telemetry(data)
        self.lbl_count.setText(f"在线: {len(self._cards)} 台")

    def _start_discovery_with_backoff(self) -> None:
        self.discoveryTriggered.emit()
        fleet_onboarding_svc.trigger_discovery()
        self._backoff_remaining_ms = random.randint(300, 600)
        self.btn_discover.setEnabled(False)
        self.btn_discover.setText(f"⏳ 退避等待 ({self._backoff_remaining_ms}ms)")
        self._backoff_timer.start(50)

    def _on_backoff_tick(self) -> None:
        self._backoff_remaining_ms -= 50
        if self._backoff_remaining_ms > 0:
            self.btn_discover.setText(f"⏳ 监听信道 ({self._backoff_remaining_ms}ms)")
        else:
            self._backoff_timer.stop()
            self.btn_discover.setEnabled(True)
            self.btn_discover.setText("📡 发现 ALL|DISCOVER")

    def _auto_pair_unbound_gateways(self) -> None:
        nodes = fleet_onboarding_svc.list_nodes()
        unbound = [n for n in nodes if n["node_id"].startswith("GW_")]
        unbound_id = unbound[0]["node_id"] if unbound else "GW_8C2F"
        target_alias = "C"
        fleet_onboarding_svc.bind_alias(unbound_id, target_alias)
        self.add_or_update_robot(target_alias, {"is_online": True, "battery": 100})
        self._update_selected_list()

    def _on_card_selection_changed(self, alias: str, checked: bool) -> None:
        self._update_selected_list()

    def _on_card_clicked(self, alias: str) -> None:
        self.drawer.set_target(alias)

    def _toggle_select_all(self, checked: bool) -> None:
        for card in self._cards.values():
            card.chk_select.setChecked(checked)
        self._update_selected_list()

    def _update_selected_list(self) -> None:
        self._selected_aliases = [
            alias for alias, card in self._cards.items() if card.chk_select.isChecked()
        ]
        self.selectedRobotsChanged.emit(self._selected_aliases)

    def _subscribe_events(self) -> None:
        event_bus.subscribe("ROBOT_TELEMETRY_UPDATED", self._on_telemetry_event)

    def _on_telemetry_event(self, data: Dict) -> None:
        if isinstance(data, dict) and "target" in data:
            self.add_or_update_robot(data["target"], data)

