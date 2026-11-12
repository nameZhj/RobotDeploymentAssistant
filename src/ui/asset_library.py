"""
@file: src/ui/asset_library.py
@brief: 支持 QDrag 拖拽编排的素材库面板（舞蹈、动作、轨迹与阵型素材）
@exports: DraggableAssetListWidget, AssetLibraryPanel
"""
import json
import logging
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)
from src.core.asset_registry import asset_registry

logger = logging.getLogger("AssetLibrary")
CHOREO_MIME_TYPE = "application/x-robo-choreo-asset"


class DraggableAssetListWidget(QListWidget):
    """支持拖拽的素材列表控件，封装标准 QMimeData"""

    sig_item_dragged = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.setStyleSheet("""
            QListWidget { background: #111827; border: 1px solid #1f2937; border-radius: 4px; color: #e2e8f0; font-size: 11px; }
            QListWidget::item { padding: 5px; border-bottom: 1px solid #1e293b; }
            QListWidget::item:hover { background: #1e293b; }
            QListWidget::item:selected { background: #0284c7; color: white; }
        """)

    def startDrag(self, supportedActions: Qt.DropActions) -> None:
        item = self.currentItem()
        if not item:
            return
        data: Dict[str, Any] = item.data(Qt.UserRole)
        if not data:
            return

        mime_data = QMimeData()
        json_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        mime_data.setData(CHOREO_MIME_TYPE, json_bytes)
        mime_data.setData("application/x-choreo-asset", json_bytes)
        mime_data.setText(json.dumps(data, ensure_ascii=False))

        drag = QDrag(self)
        drag.setMimeData(mime_data)

        # 拖拽半透明气泡缩略图
        pix = QPixmap(140, 28)
        pix.fill(QColor(data.get("color", "#38bdf8")))
        p = QPainter(pix)
        p.setPen(QColor("#ffffff"))
        p.drawText(pix.rect(), Qt.AlignCenter, f"{data.get('name', '素材')[:10]}")
        p.end()
        drag.setPixmap(pix)
        drag.setHotSpot(QPoint(70, 14))

        self.sig_item_dragged.emit(data)
        drag.exec(Qt.CopyAction)


class AssetLibraryPanel(QWidget):
    """舞台编导素材库：四Tab分类展示真实动作、33支舞蹈、轨迹与阵型模板"""

    sig_asset_selected = Signal(dict)
    trajectorySelected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._init_ui()
        self.reload_all()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 搜索与刷新行
        header_lay = QHBoxLayout()
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍 搜索素材名称或别名...")
        self.txt_search.setStyleSheet("background: #111827; border: 1px solid #334155; border-radius: 4px; color: #f8fafc; padding: 4px;")
        self.txt_search.textChanged.connect(self._filter_assets)
        header_lay.addWidget(self.txt_search, 1)

        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setToolTip("刷新素材库")
        self.btn_refresh.setFixedWidth(28)
        self.btn_refresh.setStyleSheet("background: #1e293b; color: #38bdf8; font-weight: bold;")
        self.btn_refresh.clicked.connect(self.reload_all)
        header_lay.addWidget(self.btn_refresh)
        layout.addLayout(header_lay)

        # 四 Tab 分类
        self.tabs = QTabWidget(self)
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #1e293b; background: #0f172a; border-radius: 4px; }
            QTabBar::tab { background: #1e293b; color: #94a3b8; padding: 5px 8px; font-size: 11px; }
            QTabBar::tab:selected { background: #0284c7; color: white; font-weight: bold; }
        """)

        self.list_dance = DraggableAssetListWidget(self)
        self.list_dance.itemClicked.connect(self._on_item_clicked)
        self.tabs.addTab(self.list_dance, "💃 舞蹈")

        self.list_action = DraggableAssetListWidget(self)
        self.list_action.itemClicked.connect(self._on_item_clicked)
        self.tabs.addTab(self.list_action, "🤸 动作")

        self.list_trajectory = DraggableAssetListWidget(self)
        self.list_trajectory.itemClicked.connect(self._on_item_clicked)
        self.tabs.addTab(self.list_trajectory, "📈 轨迹")

        self.list_formation = DraggableAssetListWidget(self)
        self.list_formation.itemClicked.connect(self._on_item_clicked)
        self.tabs.addTab(self.list_formation, "👥 阵型")

        layout.addWidget(self.tabs, 1)

        lbl_tip = QLabel("💡 提示：按住任意素材直接拖拽至底部时间轴轨道")
        lbl_tip.setStyleSheet("color: #64748b; font-size: 10px;")
        layout.addWidget(lbl_tip)

    def reload_all(self) -> None:
        asset_registry.reload()
        self._populate_list(self.list_dance, asset_registry.get_dances())
        self._populate_list(self.list_action, asset_registry.get_actions())
        self._populate_list(self.list_trajectory, asset_registry.get_trajectories())
        self._populate_list(self.list_formation, asset_registry.get_formations())

    def _populate_list(self, list_widget: QListWidget, items: List[Dict[str, Any]]) -> None:
        list_widget.clear()
        for it in items:
            cat = it.get("category", "")
            dur = it.get("duration", 0.0)
            if cat == "dance":
                text = f"💃 {it.get('name')} [{it.get('alias')}] ({dur:.1f}s)\n   按键: {it.get('keys', '')}"
            elif cat == "action":
                text = f"🤸 {it.get('name')} ({dur:.1f}s)\n   指令: {it.get('cmd', '')}"
            elif cat == "trajectory":
                ttype = "群体" if it.get("target_type") == "swarm" else "单机"
                text = f"📈 {it.get('name')} [{ttype}] ({dur:.1f}s)\n   ID: {it.get('alias')}"
            else:
                text = f"👥 {it.get('name')} [{it.get('type')}]\n   成员数: {it.get('member_count', 0)}"

            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, it)
            list_widget.addItem(item)

    def _filter_assets(self, query: str) -> None:
        q = query.lower().strip()
        for list_w in (self.list_dance, self.list_action, self.list_trajectory, self.list_formation):
            for i in range(list_w.count()):
                it = list_w.item(i)
                data = it.data(Qt.UserRole) or {}
                name = str(data.get("name", "")).lower()
                alias = str(data.get("alias", "")).lower()
                cmd = str(data.get("cmd", "")).lower()
                matched = (not q) or (q in name) or (q in alias) or (q in cmd)
                it.setHidden(not matched)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        if item and item.data(Qt.UserRole):
            data = item.data(Qt.UserRole)
            self.sig_asset_selected.emit(data)
            if data.get("category") == "trajectory":
                self.trajectorySelected.emit(str(data.get("alias", "")))

    def refresh_trajectories(self) -> None:
        self.reload_all()
