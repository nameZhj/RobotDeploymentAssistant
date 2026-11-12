"""
@file: src/ui/choreo_page/right_dock_panel.py
@brief: 舞台编导右侧停靠区：选中对象属性、HTTP/建图状态与 HTTP 轨迹上传预留接口面板
@exports: RightDockPanel
"""
import logging
from typing import Any, Dict, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)
from src.core.robot_gateway import robot_trajectory_http_gateway
from src.ui.dialogs.http_preview_dialog import HttpPreviewDialog

logger = logging.getLogger("RightDockPanel")


class RightDockPanel(QWidget):
    """编导右侧控制坞：承载选中实体属性编辑、通信状态与 HTTP 轨迹上传预留"""

    emergencyTriggered = Signal()
    basicMotionRequested = Signal(str, str)  # target, cmd
    saveTrajectoryRequested = Signal()
    loadTrajectoryRequested = Signal()
    httpUploadTriggered = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._target_id = "A"
        self._active_trajectory_data: Dict[str, Any] = {}
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # 1. 选中对象属性面板
        self.box_props = QGroupBox("🎯 选中对象属性 (Inspector)")
        self.box_props.setStyleSheet("""
            QGroupBox { color: #38bdf8; font-weight: bold; border: 1px solid #334155; border-radius: 6px; margin-top: 4px; padding-top: 8px; }
            QLabel { color: #cbd5e1; font-size: 11px; }
            QLineEdit { background: #1e293b; color: #f8fafc; border: 1px solid #475569; border-radius: 4px; padding: 2px 4px; font-size: 11px; }
        """)
        flay = QFormLayout(self.box_props)
        flay.setSpacing(4)
        self.txt_type = QLineEdit("机器人 (Robot)"); self.txt_type.setReadOnly(True)
        flay.addRow("对象类型:", self.txt_type)
        self.txt_id = QLineEdit("A"); self.txt_id.setReadOnly(True)
        flay.addRow("目标标识 (ID):", self.txt_id)
        self.txt_pos = QLineEdit("X: 0.00m, Y: 0.00m, Yaw: 0.0°"); self.txt_pos.setReadOnly(True)
        flay.addRow("位姿参数:", self.txt_pos)
        self.txt_extra = QLineEdit("就绪"); self.txt_extra.setReadOnly(True)
        flay.addRow("动态属性:", self.txt_extra)
        main_layout.addWidget(self.box_props)

        # 2. HTTP 轨迹上传与 JSON 保存区
        box_upload = QGroupBox("🚀 HTTP 轨迹上传 (预留接口)")
        box_upload.setStyleSheet("""
            QGroupBox { color: #38bdf8; font-weight: bold; border: 1px solid #334155; border-radius: 6px; margin-top: 4px; padding-top: 8px; }
            QLabel { font-size: 10px; color: #cbd5e1; }
            QLineEdit, QSpinBox { background: #1e293b; color: #f8fafc; border: 1px solid #475569; border-radius: 4px; padding: 2px 4px; font-size: 10px; }
        """)
        uplay = QVBoxLayout(box_upload)
        uplay.setSpacing(4)
        ep_row = QHBoxLayout()
        ep_row.addWidget(QLabel("IP:"))
        self.txt_ip = QLineEdit("192.168.123.164")
        ep_row.addWidget(self.txt_ip)
        ep_row.addWidget(QLabel("Port:"))
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1, 65535); self.spin_port.setValue(8090)
        ep_row.addWidget(self.spin_port)
        uplay.addLayout(ep_row)

        self.btn_upload_http = QPushButton("🌐 通过 HTTP 上传到机器人 (预留)")
        self.btn_upload_http.setStyleSheet("background: #0284c7; color: white; font-weight: bold; padding: 5px; font-size: 11px;")
        self.btn_upload_http.clicked.connect(self._on_http_upload_clicked)
        uplay.addWidget(self.btn_upload_http)

        json_row = QHBoxLayout()
        btn_save_json = QPushButton("💾 保存轨迹 JSON")
        btn_save_json.setStyleSheet("background: #10b981; color: white; font-size: 10px; padding: 4px;")
        btn_save_json.clicked.connect(self.saveTrajectoryRequested.emit)
        json_row.addWidget(btn_save_json)
        btn_load_json = QPushButton("📂 重现轨迹 JSON")
        btn_load_json.setStyleSheet("background: #6366f1; color: white; font-size: 10px; padding: 4px;")
        btn_load_json.clicked.connect(self.loadTrajectoryRequested.emit)
        json_row.addWidget(btn_load_json)
        uplay.addLayout(json_row)
        main_layout.addWidget(box_upload)

        # 3. HTTP 与通信状态面板
        self.box_status = QGroupBox("🌐 通信与建图接口状态")
        self.box_status.setStyleSheet("QGroupBox { color: #38bdf8; font-weight: bold; border: 1px solid #334155; border-radius: 6px; margin-top: 4px; padding-top: 8px; } QLabel { font-size: 10px; }")
        slay = QVBoxLayout(self.box_status); slay.setSpacing(4)
        self.lbl_http = QLabel("● HTTP 服务: 运行中 (127.0.0.1:8088)")
        self.lbl_http.setStyleSheet("color: #22c55e; font-weight: 600;"); slay.addWidget(self.lbl_http)
        self.lbl_map = QLabel("● PCD 建图接口: 就绪 (支持标准本地导入)")
        self.lbl_map.setStyleSheet("color: #38bdf8; font-weight: 600;"); slay.addWidget(self.lbl_map)
        self.lbl_lora = QLabel("● LoRa 串口: 9600 8N1 (单向广播通道就绪)")
        self.lbl_lora.setStyleSheet("color: #a855f7; font-weight: 600;"); slay.addWidget(self.lbl_lora)
        main_layout.addWidget(self.box_status)

        # 4. 基础运控快捷指令区
        box_quick = QGroupBox("🎮 基础指令发射")
        box_quick.setStyleSheet("QGroupBox { color: #38bdf8; font-weight: bold; border: 1px solid #334155; border-radius: 6px; margin-top: 4px; padding-top: 8px; } QPushButton { background: #1e293b; color: #f8fafc; border: 1px solid #475569; border-radius: 4px; padding: 4px 6px; font-size: 10px; font-weight: 600; } QPushButton:hover { background: #334155; color: #38bdf8; }")
        qlay = QVBoxLayout(box_quick); qlay.setSpacing(4)
        btn_row1 = QHBoxLayout()
        for name, cmd in [("站立 (STAND)", "STAND"), ("步态 (GAIT)", "GAIT")]:
            btn = QPushButton(name); btn.clicked.connect(lambda _, c=cmd: self.basicMotionRequested.emit(self._target_id, c))
            btn_row1.addWidget(btn)
        qlay.addLayout(btn_row1)
        btn_row2 = QHBoxLayout()
        for name, cmd in [("软停 (STOP)", "STOP"), ("被动 (PASSIVE)", "PASSIVE")]:
            btn = QPushButton(name); btn.clicked.connect(lambda _, c=cmd: self.basicMotionRequested.emit(self._target_id, c))
            btn_row2.addWidget(btn)
        qlay.addLayout(btn_row2)
        main_layout.addWidget(box_quick)
        main_layout.addStretch(1)

    def set_selected_robot(self, robot_id: str, x: float = 0.0, y: float = 0.0, yaw: float = 0.0) -> None:
        self._target_id = robot_id
        self.txt_type.setText("机甲 (Robot)"); self.txt_id.setText(robot_id)
        self.txt_pos.setText(f"X: {x:.2f}m, Y: {y:.2f}m, Yaw: {yaw:.1f}°")
        self.txt_extra.setText("就绪")

    def set_selected_trajectory(self, traj_data: Dict[str, Any]) -> None:
        self._active_trajectory_data = dict(traj_data)
        self.txt_type.setText("轨迹 (Trajectory)")
        self.txt_id.setText(traj_data.get("name") or traj_data.get("trajectory_id", "TRAJ"))
        dur = traj_data.get("duration", 3.0)
        max_v = traj_data.get("max_velocity", 1.2)
        self.txt_pos.setText(f"最大线速: {max_v} m/s")
        self.txt_extra.setText(f"预估时长: {dur:.2f}s")

    def _on_http_upload_clicked(self) -> None:
        if not self._active_trajectory_data:
            QMessageBox.information(
                self,
                "上传提示",
                "尚未选择或绘制轨迹。请先在 2D 画布中绘制轨迹并保存，或在左侧素材库中选择一条轨迹！",
            )
            return
        ip = self.txt_ip.text().strip()
        port = self.spin_port.value()
        res = robot_trajectory_http_gateway.upload_trajectory(ip, port, self._active_trajectory_data)
        self.httpUploadTriggered.emit(res)
        dlg = HttpPreviewDialog(self, preview_data=res)
        dlg.exec()
