import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from src.application.services.direct_motion_svc import direct_motion_svc

logger = logging.getLogger("DanceLibraryDock")


class ActionCard(QFrame):
    """Draggable action card displaying metadata and preview authorization."""

    previewRequested = Signal(str)

    def __init__(self, action_meta: Dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.meta = action_meta
        self.action_id = action_meta.get("id", "")
        self.is_licensed = bool(action_meta.get("licensed", False))
        self._drag_start_pos = None

        self._init_ui()

    def _init_ui(self) -> None:
        self.setStyleSheet("""
            QFrame { background-color: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 4px; }
            QFrame:hover { border-color: #0ea5e9; }
            QLabel { color: #f1f5f9; font-size: 11px; }
            QLabel.title { font-weight: 700; color: #38bdf8; font-size: 12px; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        header = QHBoxLayout()
        lbl_name = QLabel(self.meta.get("name", self.action_id), self)
        lbl_name.setProperty("class", "title")
        header.addWidget(lbl_name, 1)

        badge_text = "✅ 授权" if self.is_licensed else "🔒 未授权"
        lbl_badge = QLabel(badge_text, self)
        lbl_badge.setStyleSheet("color: #10b981; font-weight: 700;" if self.is_licensed else "color: #ef4444; font-weight: 700;")
        header.addWidget(lbl_badge)
        layout.addLayout(header)

        footer = QHBoxLayout()
        dur = float(self.meta.get("duration_s", 0.0))
        lbl_dur = QLabel(f"⏱️ {dur:.1f}s", self)
        lbl_dur.setStyleSheet("color: #94a3b8;")
        footer.addWidget(lbl_dur)

        footer.addStretch(1)
        self.btn_preview = QPushButton("试跳", self)
        self.btn_preview.setEnabled(self.is_licensed)
        self.btn_preview.setStyleSheet("""
            QPushButton { background: #0284c7; color: #fff; font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 3px; }
            QPushButton:disabled { background: #475569; color: #94a3b8; }
        """)
        self.btn_preview.clicked.connect(self._on_preview_clicked)
        footer.addWidget(self.btn_preview)
        layout.addLayout(footer)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.LeftButton and self._drag_start_pos:
            dist = (event.pos() - self._drag_start_pos).manhattanLength()
            if dist >= 8:
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(self.action_id)
                drag.setMimeData(mime)
                drag.exec_(Qt.CopyAction)
        super().mouseMoveEvent(event)

    def _on_preview_clicked(self) -> None:
        if not self.is_licensed:
            logger.warning(f"Action {self.action_id} not licensed! DANCE execution rejected.")
            return
        direct_motion_svc.execute_dance("A", self.action_id)
        self.previewRequested.emit(self.action_id)


class DanceLibraryDock(QWidget):
    """Dance motion library dock categorizing authorized choreography clips by robot model."""

    actionSelected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._models_data: Dict[str, Any] = {}
        self._load_registry()
        self._init_ui()

    def _load_registry(self) -> None:
        candidates = [
            Path("configs/action_registry.yaml").resolve(),
            Path(__file__).resolve().parent.parent.parent.parent / "configs" / "action_registry.yaml",
        ]
        for p in candidates:
            if p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        raw = yaml.safe_load(f) or {}
                        self._models_data = raw.get("robot_models", {})
                        if self._models_data:
                            return
                except Exception:
                    pass

        self._models_data = {
            "G1": {
                "display_name": "G1 人形机器人",
                "actions": [
                    {"id": "G1_dance", "name": "G1 经典迎宾舞", "duration_s": 15.0, "licensed": True},
                    {"id": "KUNGFU", "name": "中华武术套路", "duration_s": 18.0, "licensed": True},
                ],
            }
        }

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        filter_bar = QHBoxLayout()
        lbl_model = QLabel("机型:", self)
        lbl_model.setStyleSheet("color: #94a3b8; font-size: 11px;")
        filter_bar.addWidget(lbl_model)

        self.model_combo = QComboBox(self)
        self.model_combo.setStyleSheet("background: #1e293b; color: #38bdf8; font-weight: 600; padding: 4px;")
        for m_id, m_data in self._models_data.items():
            self.model_combo.addItem(f"🤖 {m_data.get('display_name', m_id)}", m_id)
        self.model_combo.currentIndexChanged.connect(self._refresh_cards)
        filter_bar.addWidget(self.model_combo, 1)
        layout.addLayout(filter_bar)

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

        self._refresh_cards()

    def _refresh_cards(self) -> None:
        while self.card_layout.count() > 1:
            item = self.card_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        curr_model = self.model_combo.currentData() or "G1"
        actions = self._models_data.get(curr_model, {}).get("actions", [])
        for act in actions:
            card = ActionCard(act, self.card_container)
            card.previewRequested.connect(lambda a_id: self.actionSelected.emit(a_id))
            self.card_layout.insertWidget(self.card_layout.count() - 1, card)
