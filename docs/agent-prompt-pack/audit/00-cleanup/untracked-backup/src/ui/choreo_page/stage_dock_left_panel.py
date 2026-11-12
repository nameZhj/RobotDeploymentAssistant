"""
@file: src/ui/choreo_page/stage_dock_left_panel.py
@brief: 舞台左侧信息坞：场景详情、机器人站位列表及初始位姿只读监视
@exports: StageDockLeftPanel
"""
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)


class StageDockLeftPanel(QWidget):
    """提供舞台场景元数据、多机器人站位列表以及初始位姿的只读展示坞"""

    robotSelected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._robots: List[Dict[str, Any]] = []
        self._selected_id: Optional[str] = None
        self._init_ui()

    def _init_ui(self) -> None:
        self.setStyleSheet("""
            QGroupBox {
                color: #94A3B8;
                font-weight: 700;
                font-size: 11px;
                border: 1px solid #1E293B;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 12px;
                background-color: #0F172A;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QLabel {
                color: #CBD5E1;
                font-size: 11px;
            }
            QLabel.val-label {
                color: #38BDF8;
                font-weight: 600;
            }
            QListWidget {
                background-color: #111827;
                border: 1px solid #1F2937;
                border-radius: 4px;
                color: #E2E8F0;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-bottom: 1px solid #1E293B;
            }
            QListWidget::item:selected {
                background-color: #1E3A8A;
                color: #60A5FA;
                font-weight: 700;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # 1. Area A: 场景信息 (Scene Info)
        grp_scene = QGroupBox("📍 场景信息 (SCENE INFO)", self)
        vbox_scene = QVBoxLayout(grp_scene)
        vbox_scene.setSpacing(4)
        self.lbl_scene_name = self._make_row(vbox_scene, "场景名称:", "默认演播舞台")
        self.lbl_map_file = self._make_row(vbox_scene, "地图文件:", "未载入")
        self.lbl_dimensions = self._make_row(vbox_scene, "场景尺寸:", "20.0m × 20.0m")
        self.lbl_resolution = self._make_row(vbox_scene, "栅格精度:", "0.05m")
        self.lbl_origin = self._make_row(vbox_scene, "舞台原点:", "(0.0, 0.0)")
        self.lbl_status = self._make_row(vbox_scene, "地图状态:", "未载入 (等待导入PCD)")
        layout.addWidget(grp_scene)

        # 2. Area B: 机器人站位列表 (Robot Spawns)
        grp_robots = QGroupBox("🤖 机器人站位 (ROBOT SPAWNS)", self)
        vbox_robots = QVBoxLayout(grp_robots)
        vbox_robots.setSpacing(4)
        self.robot_list = QListWidget(grp_robots)
        self.robot_list.currentItemChanged.connect(self._on_item_changed)
        vbox_robots.addWidget(self.robot_list)
        layout.addWidget(grp_robots, 1)

        # 3. Area C: 初始位姿展示 (Initial Pose Display)
        grp_pose = QGroupBox("📐 初始位姿 (INITIAL POSE)", self)
        vbox_pose = QVBoxLayout(grp_pose)
        vbox_pose.setSpacing(4)
        self.lbl_pose_robot = self._make_row(vbox_pose, "目标对象:", "未选中")
        self.lbl_pose_x = self._make_row(vbox_pose, "站位 X:", "0.00 m")
        self.lbl_pose_y = self._make_row(vbox_pose, "站位 Y:", "0.00 m")
        self.lbl_pose_yaw = self._make_row(vbox_pose, "朝向 Yaw:", "0.00°")
        lbl_lock = QLabel("🔒 初始位姿：只读监视", grp_pose)
        lbl_lock.setStyleSheet("color: #F59E0B; font-size: 10px; font-weight: 600; padding-top: 4px;")
        vbox_pose.addWidget(lbl_lock)
        layout.addWidget(grp_pose)

    def _make_row(self, layout: QVBoxLayout, title: str, default_val: str) -> QLabel:
        row = QWidget(self)
        h = QHBoxLayout(row)
        h.setContentsMargins(2, 1, 2, 1)
        lbl_t = QLabel(title, row)
        lbl_v = QLabel(default_val, row)
        lbl_v.setProperty("class", "val-label")
        lbl_v.setAlignment(Qt.AlignRight)
        h.addWidget(lbl_t)
        h.addStretch(1)
        h.addWidget(lbl_v)
        layout.addWidget(row)
        return lbl_v

    def update_scene_info(self, info: Dict[str, Any]) -> None:
        if not info:
            return
        if "name" in info:
            self.lbl_scene_name.setText(str(info["name"]))
        if "map_file" in info:
            self.lbl_map_file.setText(str(info["map_file"]))
        if "dimensions" in info:
            self.lbl_dimensions.setText(str(info["dimensions"]))
        if "resolution" in info:
            self.lbl_resolution.setText(f"{info['resolution']}m")
        if "origin" in info:
            self.lbl_origin.setText(str(info["origin"]))
        if "status" in info:
            self.lbl_status.setText(str(info["status"]))

    def set_robots(self, robots: List[Dict[str, Any]]) -> None:
        self._robots = list(robots)
        self.robot_list.clear()
        for r in self._robots:
            rid = str(r.get("id", ""))
            name = str(r.get("name", f"Robot_{rid}"))
            model = str(r.get("model", "G1"))
            x, y = r.get("pos", (0.0, 0.0))
            yaw = float(r.get("yaw_deg", 0.0))
            item = QListWidgetItem(f"[{rid}] {name} ({model}) - ({x:.1f}, {y:.1f})")
            item.setData(Qt.UserRole, rid)
            self.robot_list.addItem(item)
        if self._robots:
            self.robot_list.setCurrentRow(0)

    def select_robot(self, robot_id: str) -> None:
        for idx in range(self.robot_list.count()):
            item = self.robot_list.item(idx)
            if item and item.data(Qt.UserRole) == str(robot_id):
                self.robot_list.setCurrentRow(idx)
                break

    def _on_item_changed(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if not current:
            return
        rid = current.data(Qt.UserRole)
        self._selected_id = rid
        self._update_pose_display(rid)
        self.robotSelected.emit(str(rid))

    def _update_pose_display(self, robot_id: str) -> None:
        for r in self._robots:
            if str(r.get("id")) == str(robot_id):
                name = r.get("name", f"Robot_{robot_id}")
                x, y = r.get("pos", (0.0, 0.0))
                yaw = float(r.get("yaw_deg", 0.0))
                self.lbl_pose_robot.setText(f"{name} ({robot_id})")
                self.lbl_pose_x.setText(f"{x:.2f} m")
                self.lbl_pose_y.setText(f"{y:.2f} m")
                self.lbl_pose_yaw.setText(f"{yaw:.1f}°")
                return
