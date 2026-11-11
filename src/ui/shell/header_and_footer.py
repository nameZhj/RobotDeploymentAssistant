"""
@file: src/ui/shell/header_and_footer.py
@brief: 1:1 复刻原程序的全局顶部导航栏与底部诊断状态栏组件
@exports: StudioHeaderBar, StudioFooterBar
"""
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QWidget
)


class StudioHeaderBar(QFrame):
    """顶部主导航栏，提供主视图切换、场景选择与全局辅助菜单"""

    page_changed = Signal(int)
    scene_changed = Signal(str)
    device_connect_clicked = Signal()
    settings_clicked = Signal()
    menu_action_triggered = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(50)
        self.setObjectName("studioHeaderBar")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(12)

        lbl_logo = QLabel("🤖 <b>ChoreoNexus</b>", self)
        lbl_logo.setStyleSheet("font-size: 15px; color: #38bdf8;")
        layout.addWidget(lbl_logo)
        layout.addSpacing(10)

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)
        tab_names = ["舞蹈编排", "表演监测", "导航地图"]
        for idx, name in enumerate(tab_names):
            btn = QPushButton(name, self)
            btn.setCheckable(True)
            if idx == 0:
                btn.setChecked(True)
            self.btn_group.addButton(btn, idx)
            layout.addWidget(btn)
        self.btn_group.idClicked.connect(self.page_changed.emit)

        layout.addStretch()

        self.combo_scene = QComboBox(self)
        self.combo_scene.addItems(["123", "现场舞台", "实验室展厅"])
        self.combo_scene.currentTextChanged.connect(self.scene_changed.emit)
        layout.addWidget(self.combo_scene)

        btn_view = QPushButton("视图 ▾", self)
        menu_view = QMenu(btn_view)
        for act in ["动作测试", "雷达监控", "轨迹规划", "运行日志", "UniStore"]:
            menu_view.addAction(act, lambda a=act: self.menu_action_triggered.emit(a))
        btn_view.setMenu(menu_view)
        layout.addWidget(btn_view)

        btn_help = QPushButton("帮助 ▾", self)
        menu_help = QMenu(btn_help)
        for act in ["现场实施指南", "LRMP 协议文档", "系统关于"]:
            menu_help.addAction(act, lambda a=act: self.menu_action_triggered.emit(a))
        btn_help.setMenu(menu_help)
        layout.addWidget(btn_help)

        btn_dev = QPushButton("设备连接", self)
        btn_dev.clicked.connect(self.device_connect_clicked.emit)
        layout.addWidget(btn_dev)

        btn_user = QPushButton("👤 admin", self)
        layout.addWidget(btn_user)

        btn_cfg = QPushButton("⚙️", self)
        btn_cfg.setFixedWidth(36)
        btn_cfg.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(btn_cfg)


class StudioFooterBar(QFrame):
    """底栏状态与前置检查器，承载场景、初始化点配置、音乐与网络在线诊断"""

    init_point_clicked = Signal()
    music_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setObjectName("studioFooterBar")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(10)

        lbl_user = QLabel("👤 admin", self)
        layout.addWidget(lbl_user)

        lbl_pro = QLabel("PRO", self)
        lbl_pro.setStyleSheet("background: #d97706; color: #000; font-weight: 800; font-size: 9px; padding: 1px 4px; border-radius: 2px;")
        layout.addWidget(lbl_pro)

        layout.addWidget(QLabel("系统 1.0.2", self))
        self.lbl_scene = QLabel("场景 123", self)
        layout.addWidget(self.lbl_scene)

        self.btn_init = QPushButton("初始化点 配置 1 +", self)
        self.btn_init.setStyleSheet("background: transparent; border: none; color: #38bdf8; padding: 0 4px;")
        self.btn_init.clicked.connect(self.init_point_clicked.emit)
        layout.addWidget(self.btn_init)

        self.btn_music = QPushButton("音乐 未配置音乐", self)
        self.btn_music.setStyleSheet("background: transparent; border: none; color: #cbd5e1; padding: 0 4px;")
        self.btn_music.clicked.connect(self.music_clicked.emit)
        layout.addWidget(self.btn_music)

        layout.addStretch()

        lbl_net = QLabel("<span style='color: #22c55e;'>●</span> 联网", self)
        layout.addWidget(lbl_net)

        layout.addWidget(QLabel("IP 172.18.0.1", self))
        self.lbl_robots = QLabel("机器人 在线 2", self)
        self.lbl_robots.setStyleSheet("color: #38bdf8; font-weight: 600;")
        layout.addWidget(self.lbl_robots)

    def set_music_title(self, title: str) -> None:
        text = f"音乐 {title}" if title else "音乐 未配置音乐"
        color = "#22c55e" if title and title != "未配置音乐" else "#cbd5e1"
        self.btn_music.setText(text)
        self.btn_music.setStyleSheet(f"background: transparent; border: none; color: {color}; padding: 0 4px;")

    def set_init_cfg(self, cfg_name: str) -> None:
        self.btn_init.setText(f"初始化点 {cfg_name} +")

    def set_scene_name(self, name: str) -> None:
        self.lbl_scene.setText(f"场景 {name}")

