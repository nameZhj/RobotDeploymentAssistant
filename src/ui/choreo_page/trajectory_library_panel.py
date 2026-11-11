import logging
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger("TrajectoryLibraryPanel")


class TrajectoryLibraryPanel(QFrame):
    """
    Trajectory library panel managing motion paths grouped by robot track.
    Features header tools (+, bind, import, export), track accordion grouping,
    and draggable trajectory records.
    """

    trajectorySelected = Signal(dict)
    trajectoryAddRequested = Signal()
    trajectoryBindRequested = Signal(str)
    trajectoryImportRequested = Signal()
    trajectoryExportRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._groups: Dict[str, List[Dict[str, Any]]] = {}
        self._init_ui()
        self._seed_default_trajectories()

    def _init_ui(self) -> None:
        self.setObjectName("trajectoryLibraryPanel")
        self.setStyleSheet("""
            QFrame#trajectoryLibraryPanel {
                background-color: #171A21;
                border: 1px solid #232733;
                border-radius: 6px;
            }
            QLabel.title { color: #38BDF8; font-weight: 700; font-size: 12px; }
            QPushButton.tool-btn {
                background: #1C2230; color: #F1F5F9; border: 1px solid #2B3448;
                border-radius: 3px; font-weight: 700; font-size: 11px; padding: 3px 6px;
            }
            QPushButton.tool-btn:hover { background: #263147; border-color: #1E6FFF; color: #60A5FA; }
            QTreeWidget {
                background-color: #111318; border: 1px solid #2B3448;
                border-radius: 4px; color: #E2E8F0; font-size: 11px;
            }
            QTreeWidget::item:hover { background: #1C2230; }
            QTreeWidget::item:selected { background: #1E6FFF; color: #FFFFFF; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. Top Action Toolbar: Title + [+], [绑定], [导入], [导出]
        top_bar = QHBoxLayout()
        lbl_title = QLabel("📐 轨迹库", self)
        lbl_title.setProperty("class", "title")
        top_bar.addWidget(lbl_title)
        top_bar.addStretch(1)

        self.btn_add = QPushButton("+", self)
        self.btn_add.setToolTip("新增轨迹分组/路径")
        self.btn_add.setProperty("class", "tool-btn")
        self.btn_add.clicked.connect(self.trajectoryAddRequested.emit)
        top_bar.addWidget(self.btn_add)

        self.btn_bind = QPushButton("🔗 绑定", self)
        self.btn_bind.setToolTip("绑定分组到机器人轨道")
        self.btn_bind.setProperty("class", "tool-btn")
        self.btn_bind.clicked.connect(lambda: self.trajectoryBindRequested.emit(self.get_selected_group()))
        top_bar.addWidget(self.btn_bind)

        self.btn_import = QPushButton("📂 导入", self)
        self.btn_import.setProperty("class", "tool-btn")
        self.btn_import.clicked.connect(self.trajectoryImportRequested.emit)
        top_bar.addWidget(self.btn_import)

        self.btn_export = QPushButton("💾 导出", self)
        self.btn_export.setProperty("class", "tool-btn")
        self.btn_export.clicked.connect(self.trajectoryExportRequested.emit)
        top_bar.addWidget(self.btn_export)
        layout.addLayout(top_bar)

        # 2. Tree/Accordion Grouping by Robot Track
        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["编号 / 组名", "名称", "时间 (s)"])
        self.tree.header().resizeSection(0, 110)
        self.tree.header().resizeSection(1, 110)
        self.tree.setDragEnabled(True)
        self.tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.tree, 1)

    def _seed_default_trajectories(self) -> None:
        """Seed initial groups (Robot_1 🔗 轨道1, Robot_2 🔗 轨道2)."""
        self._groups = {
            "Robot_1 🔗 轨道 1": [
                {"id": "100001", "name": "轨迹-traj_circle_01", "duration": 2.04},
                {"id": "100002", "name": "轨迹-traj_forward_02", "duration": 3.50},
            ],
            "Robot_2 🔗 轨道 2": [
                {"id": "100003", "name": "轨迹-traj_s_curve", "duration": 4.12},
            ],
            "Robot_3 🔗 轨道 3": [],
        }
        self.refresh_groups()

    def refresh_groups(self) -> None:
        self.tree.clear()
        for group_name, traj_list in self._groups.items():
            grp_item = QTreeWidgetItem(self.tree, [group_name, "", ""])
            grp_item.setExpanded(True)

            if not traj_list:
                placeholder = QTreeWidgetItem(grp_item, ["当前分组暂无轨迹", "", ""])
                placeholder.setDisabled(True)
                placeholder.setForeground(0, Qt.darkGray)
            else:
                for traj in traj_list:
                    t_item = QTreeWidgetItem(
                        grp_item,
                        [traj["id"], traj["name"], f"{traj['duration']:.2f}s"]
                    )
                    t_item.setData(0, Qt.UserRole, traj)

    def get_selected_group(self) -> str:
        curr = self.tree.currentItem()
        if not curr:
            return ""
        if curr.parent():
            return curr.parent().text(0)
        return curr.text(0)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        traj_data = item.data(0, Qt.UserRole)
        if traj_data:
            self.trajectorySelected.emit(traj_data)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.LeftButton:
            item = self.tree.currentItem()
            if item and item.data(0, Qt.UserRole):
                drag = QDrag(self)
                mime = QMimeData()
                traj = item.data(0, Qt.UserRole)
                mime.setText(f"TRAJECTORY:{traj['id']}:{traj['name']}")
                drag.setMimeData(mime)
                drag.exec_(Qt.CopyAction)
        super().mouseMoveEvent(event)

