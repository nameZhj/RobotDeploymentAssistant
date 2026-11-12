import logging
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger("ActionLibraryPanel")


class ActionLibraryPanel(QFrame):
    """
    Action motion library panel displaying search filters, robot model selection,
    action items table, and a collapsible vertical Action Edit drawer.
    """

    actionSelected = Signal(dict)
    actionEditToggled = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._actions: List[Dict[str, Any]] = []
        self._init_ui()
        self._seed_default_actions()

    def _init_ui(self) -> None:
        self.setObjectName("actionLibraryPanel")
        self.setStyleSheet("""
            QFrame#actionLibraryPanel {
                background-color: #171A21;
                border: 1px solid #232733;
                border-radius: 6px;
            }
            QLabel.title { color: #38BDF8; font-weight: 700; font-size: 12px; }
            QLineEdit, QComboBox {
                background-color: #111318; border: 1px solid #2B3448;
                border-radius: 4px; color: #F1F5F9; padding: 4px 6px; font-size: 11px;
            }
            QTableWidget {
                background-color: #111318; border: 1px solid #2B3448;
                border-radius: 4px; color: #E2E8F0; gridline-color: #1F2430; font-size: 11px;
            }
            QTableWidget::item:selected { background-color: #1E6FFF; color: #FFFFFF; }
            QPushButton.edit-tab-btn {
                background-color: #1C2230; color: #38BDF8; border: 1px solid #2B3448;
                border-radius: 4px; font-weight: 700; font-size: 11px; padding: 6px 2px;
            }
            QPushButton.edit-tab-btn:hover { background-color: #263147; border-color: #1E6FFF; }
        """)

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.setSpacing(4)

        # Left Main Content Area
        main_content = QVBoxLayout()
        main_content.setSpacing(6)

        # 1. Header & Filters: Title, Search Box, Model Filter
        header_bar = QHBoxLayout()
        lbl_title = QLabel("💃 动作库", self)
        lbl_title.setProperty("class", "title")
        header_bar.addWidget(lbl_title)

        self.input_search = QLineEdit(self)
        self.input_search.setPlaceholderText("🔍 编号 / 名称搜索...")
        self.input_search.textChanged.connect(self._filter_actions)
        header_bar.addWidget(self.input_search, 1)

        self.combo_model = QComboBox(self)
        self.combo_model.addItems(["全部型号", "G1", "H2"])
        self.combo_model.currentIndexChanged.connect(self._filter_actions)
        header_bar.addWidget(self.combo_model)
        main_content.addLayout(header_bar)

        # 2. Action Table: 编号, 名称, 时间
        self.table = QTableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["编号", "名称", "时间 (s)"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemClicked.connect(self._on_table_item_clicked)
        main_content.addWidget(self.table, 1)

        root_layout.addLayout(main_content, 1)

        # 3. Right Vertical Strip: 动作编辑 (Action Edit collapsible trigger)
        strip_layout = QVBoxLayout()
        strip_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_edit_drawer = QPushButton("动\n作\n编\n辑", self)
        self.btn_edit_drawer.setProperty("class", "edit-tab-btn")
        self.btn_edit_drawer.setCheckable(True)
        self.btn_edit_drawer.toggled.connect(self._on_edit_toggled)
        strip_layout.addWidget(self.btn_edit_drawer)
        strip_layout.addStretch(1)
        root_layout.addLayout(strip_layout)

    def _seed_default_actions(self) -> None:
        self._actions = [
            {"id": "200001", "name": "POPPING1 (机械震感)", "model": "G1", "duration": 8.50},
            {"id": "200002", "name": "经典芭蕾 (旋转起舞)", "model": "H2", "duration": 12.00},
            {"id": "200003", "name": "中华武术套路 (马步冲拳)", "model": "G1", "duration": 15.00},
            {"id": "200004", "name": "太空步滑行 (Moonwalk)", "model": "G1", "duration": 10.20},
            {"id": "200005", "name": "迎宾鞠躬致意 (Bow)", "model": "H2", "duration": 5.00},
        ]
        self._render_table(self._actions)

    def _render_table(self, action_list: List[Dict[str, Any]]) -> None:
        self.table.setRowCount(len(action_list))
        for row, act in enumerate(action_list):
            item_id = QTableWidgetItem(act["id"])
            item_name = QTableWidgetItem(act["name"])
            item_dur = QTableWidgetItem(f"{act['duration']:.2f}s")

            item_id.setData(Qt.UserRole, act)
            self.table.setItem(row, 0, item_id)
            self.table.setItem(row, 1, item_name)
            self.table.setItem(row, 2, item_dur)

    def _filter_actions(self) -> None:
        kw = self.input_search.text().strip().lower()
        selected_model = self.combo_model.currentText()

        filtered = []
        for act in self._actions:
            model_match = selected_model == "全部型号" or act.get("model") == selected_model
            kw_match = not kw or (kw in act["id"].lower() or kw in act["name"].lower())
            if model_match and kw_match:
                filtered.append(act)
        self._render_table(filtered)

    def _on_table_item_clicked(self, item: QTableWidgetItem) -> None:
        row = item.row()
        id_item = self.table.item(row, 0)
        if id_item:
            act_data = id_item.data(Qt.UserRole)
            if act_data:
                self.actionSelected.emit(act_data)

    def _on_edit_toggled(self, checked: bool) -> None:
        self.actionEditToggled.emit(checked)
        logger.info(f"Action edit vertical drawer toggled: {checked}")

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.LeftButton:
            row = self.table.currentRow()
            if row >= 0:
                id_item = self.table.item(row, 0)
                if id_item:
                    act = id_item.data(Qt.UserRole)
                    if act:
                        drag = QDrag(self)
                        mime = QMimeData()
                        mime.setText(f"ACTION:{act['id']}:{act['name']}")
                        drag.setMimeData(mime)
                        drag.exec_(Qt.CopyAction)
        super().mouseMoveEvent(event)

