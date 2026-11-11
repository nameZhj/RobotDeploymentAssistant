import logging
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QWidget,
)
from src.core.config_loader import config_loader

logger = logging.getLogger("TopNavigationBar")


class TopNavigationBar(QFrame):
    """
    Studio top navigation bar featuring core module tabs, scene selection,
    view/help menus, and quick-access utility dialog buttons.
    """

    pageChanged = Signal(int)
    sceneChanged = Signal(str)
    menuActionTriggered = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._app_info = config_loader.get_app_info()
        self._init_ui()

    def _init_ui(self) -> None:
        self.setFixedHeight(50)
        self.setObjectName("topNavigationBar")
        self.setStyleSheet("""
            QFrame#topNavigationBar {
                background-color: #111318;
                border-bottom: 1px solid #232733;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(14)

        # 1. Left Brand Identifier
        brand_layout = QHBoxLayout()
        brand_layout.setSpacing(6)
        lbl_logo = QLabel("🤖", self)
        lbl_logo.setStyleSheet("font-size: 18px;")
        brand_layout.addWidget(lbl_logo)

        lbl_title = QLabel(self._app_info.get("app_title", "ChoreoNexus Studio"), self)
        lbl_title.setStyleSheet("font-size: 14px; font-weight: 800; color: #FFFFFF; letter-spacing: 0.5px;")
        brand_layout.addWidget(lbl_title)
        layout.addLayout(brand_layout)

        layout.addSpacing(16)

        # 2. Main Navigation Tabs: 舞蹈编排(0) / 表演监测(1) / 导航地图(2)
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)

        tabs = [("💃 舞蹈编排", 0), ("📡 表演监测", 1), ("🗺️ 导航地图", 2)]
        for label, idx in tabs:
            btn = QPushButton(label, self)
            btn.setCheckable(True)
            btn.setProperty("class", "nav-tab")
            if idx == 0:
                btn.setChecked(True)
            btn.clicked.connect(lambda _, i=idx: self._on_tab_clicked(i))
            self.tab_group.addButton(btn, idx)
            layout.addWidget(btn)

        self.tab_group.idClicked.connect(self._on_tab_clicked)

        layout.addStretch(1)

        # 3. Scene Dropdown Selector
        lbl_scene = QLabel("场景:", self)
        lbl_scene.setStyleSheet("color: #94A3B8; font-size: 11px;")
        layout.addWidget(lbl_scene)

        self.combo_scene = QComboBox(self)
        self.combo_scene.addItem("默认演播大厅 (Main Hall)", "scene_default")
        self.combo_scene.addItem("奥体主舞台 (Sports Arena)", "scene_arena")
        self.combo_scene.addItem("户外路演广场 (Square)", "scene_plaza")
        self.combo_scene.currentIndexChanged.connect(
            lambda: self.sceneChanged.emit(self.combo_scene.currentData())
        )
        layout.addWidget(self.combo_scene)

        # 4. View Dropdown Menu
        self.btn_view_menu = QPushButton("视图 ▾", self)
        self.btn_view_menu.setCursor(Qt.PointingHandCursor)
        self.view_menu = QMenu(self)
        view_items = [
            ("⚡ 动作测试", "ACTION_TEST"),
            ("📡 雷达监控", "LIDAR_MONITOR"),
            ("📐 轨迹规划", "TRAJ_PLANNER"),
            ("📜 运行日志", "RUN_LOGS"),
            ("🛒 动作商店 (Store)", "CHOREO_STORE"),
            ("🔄 重新加载界面", "RELOAD_VIEW"),
        ]
        for name, code in view_items:
            action = self.view_menu.addAction(name)
            action.triggered.connect(lambda _, c=code: self.menuActionTriggered.emit(c))
        self.btn_view_menu.setMenu(self.view_menu)
        self.btn_view_menu.clicked.connect(lambda: None)
        layout.addWidget(self.btn_view_menu)

        # 5. Help Dropdown Menu
        self.btn_help_menu = QPushButton("帮助 ▾", self)
        self.btn_help_menu.setCursor(Qt.PointingHandCursor)
        self.help_menu = QMenu(self)
        help_items = [
            ("📖 使用说明手册", "HELP_DOC"),
            ("❓ 常见问答 Q&A", "HELP_QA"),
            ("📝 版本更新日志", "CHANGELOG"),
            ("ℹ️ 关于本系统", "ABOUT"),
        ]
        for name, code in help_items:
            action = self.help_menu.addAction(name)
            action.triggered.connect(lambda _, c=code: self.menuActionTriggered.emit(c))
        self.btn_help_menu.setMenu(self.help_menu)
        self.btn_help_menu.clicked.connect(lambda: None)
        layout.addWidget(self.btn_help_menu)

        # 6. Utility Action Buttons: Device Overview, User Center, Settings
        self.btn_devices = QPushButton("💻 设备", self)
        self.btn_devices.clicked.connect(lambda: self.menuActionTriggered.emit("OPEN_DEVICE_OVERVIEW"))
        layout.addWidget(self.btn_devices)

        self.btn_user = QPushButton("👤 用户", self)
        self.btn_user.clicked.connect(lambda: self.menuActionTriggered.emit("OPEN_USER_CENTER"))
        layout.addWidget(self.btn_user)

        self.btn_settings = QPushButton("⚙️", self)
        self.btn_settings.setToolTip("系统设置 (System Settings)")
        self.btn_settings.clicked.connect(lambda: self.menuActionTriggered.emit("OPEN_SETTINGS"))
        layout.addWidget(self.btn_settings)

    def _on_tab_clicked(self, tab_id: int) -> None:
        logger.info(f"Main navigation tab switched to index: {tab_id}")
        self.pageChanged.emit(tab_id)
