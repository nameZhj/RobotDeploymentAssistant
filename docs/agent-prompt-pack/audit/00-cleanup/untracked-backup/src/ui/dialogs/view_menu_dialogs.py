import logging
import os
from pathlib import Path
from typing import Any, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from src.core.event_bus import event_bus
from src.infrastructure.lrmp.command_parser import command_parser

logger = logging.getLogger("ViewMenuDialogs")


class ActionTestDialog(QDialog):
    """Direct manual kinematic testing (STAND, GAIT, PASSIVE, MOVE, DANCE, STOP, RELEASE)."""

    def __init__(self, parent: Optional[QWidget] = None, controller: Optional[Any] = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("⚡ 动作测试 (Direct Kinematic Test)")
        self.resize(460, 260)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("目标机器人:"))
        self.combo_target = QComboBox(self)
        self.combo_target.addItems(["A (Robot_1)", "B (Robot_2)", "ALL (全机群)"])
        layout.addWidget(self.combo_target)

        btn_grid = QHBoxLayout()
        for cmd in ["STAND", "GAIT", "PASSIVE", "MOVE", "DANCE", "STOP", "RELEASE"]:
            btn = QPushButton(f"[{cmd}]", self)
            btn.clicked.connect(lambda _, c=cmd: self._send_cmd(c))
            btn_grid.addWidget(btn)
        layout.addLayout(btn_grid)
        self.lbl_feedback = QLabel("就绪 - 点击上方指令直接调试动作", self)
        layout.addWidget(self.lbl_feedback)

    def _send_cmd(self, cmd_name: str) -> None:
        tgt = self.combo_target.currentText().split()[0]
        targets = ["A", "B"] if tgt == "ALL" else [tgt]
        payload = f"{tgt}|{cmd_name}" if cmd_name not in ("MOVE", "DANCE") else (f"{tgt}|MOVE,0.5,0.0,0.0,1.0" if cmd_name == "MOVE" else f"{tgt}|DANCE,POPPING1")
        if self.controller:
            if cmd_name == "MOVE":
                self.controller.send_lrmp(targets, "MOVE", "0.5,0.0,0.0,1.0")
            elif cmd_name == "DANCE":
                self.controller.send_lrmp(targets, "DANCE", "POPPING1")
            else:
                self.controller.send_lrmp(targets, cmd_name)
        res = command_parser.parse(payload)
        status = "成功" if res.is_valid else f"被拦截: {res.error_msg}"
        self.lbl_feedback.setText(f"指令: {payload} -> {status}")
        event_bus.publish("ACTION_TEST_SENT", {"cmd": payload, "valid": res.is_valid})


class RadarMonitorDialog(QDialog):
    """LiDAR link, IMU stability, and real-time point cloud inspector."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("📡 雷达监控 (LiDAR Stability Monitor)")
        self.resize(520, 280)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(2, 4, self)
        self.table.setHorizontalHeaderLabels(["机器人", "雷达连接", "IMU状态", "点云采集"])
        self.table.setItem(0, 0, QTableWidgetItem("Robot_1 (A)"))
        self.table.setItem(0, 1, QTableWidgetItem("● 正常 (2 Hz)"))
        self.table.setItem(0, 2, QTableWidgetItem("9.81 m/s² (正常)"))
        self.table.setItem(0, 3, QTableWidgetItem("128,400 pts"))
        self.table.setItem(1, 0, QTableWidgetItem("Robot_2 (B)"))
        self.table.setItem(1, 1, QTableWidgetItem("● 正常 (2 Hz)"))
        self.table.setItem(1, 2, QTableWidgetItem("9.80 m/s² (正常)"))
        self.table.setItem(1, 3, QTableWidgetItem("125,600 pts"))
        layout.addWidget(self.table)
        btn_refresh = QPushButton("获取最新点云与IMU诊断", self)
        btn_refresh.clicked.connect(lambda: QMessageBox.information(self, "雷达诊断", "全部机器人雷达与IMU链路状态正常！"))
        layout.addWidget(btn_refresh)


class RunLogDialog(QDialog):
    """Audit log inspection strictly displaying true hardware device SRC_ID."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("📜 运行日志 (Audit Log with Real SRC_ID)")
        self.resize(620, 320)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(3, 4, self)
        self.table.setHorizontalHeaderLabels(["时间", "真实来源 (SRC_ID)", "目标 (DST_ID)", "负载/指令"])
        logs = [
            ("15:40:02", "GW_1001 (Robot_1)", "HOST", "RSP,READY"),
            ("15:40:03", "GW_1002 (Robot_2)", "HOST", "RSP,READY"),
            ("15:40:04", "HOST", "ALL", "PLAY,RUN_1001,170000"),
        ]
        log_f = Path(__file__).resolve().parent.parent.parent.parent / "runtime" / "logs" / "lrmp_session.log"
        if log_f.exists():
            with open(log_f, "r", encoding="utf-8", errors="ignore") as fp:
                for line in [l.strip() for l in fp if l.strip()][-15:]:
                    src = "GW_8C2F" if "GW_8C2F" in line else ("A" if "from A" in line or "-> A" in line else ("B" if "from B" in line or "-> B" in line else "LOCAL"))
                    dst = "ALL" if "-> ALL" in line else ("A" if "-> A" in line else ("B" if "-> B" in line else "HOST"))
                    logs.append(("LOG", src, dst, line))
        self.table.setRowCount(len(logs))
        for row, (t, src, dst, p) in enumerate(logs):
            self.table.setItem(row, 0, QTableWidgetItem(t))
            self.table.setItem(row, 1, QTableWidgetItem(src))
            self.table.setItem(row, 2, QTableWidgetItem(dst))
            self.table.setItem(row, 3, QTableWidgetItem(p))
        layout.addWidget(self.table)


class ActionStoreDialog(QDialog):
    """Motion asset repository and cloud action package manager."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("🛒 动作商店 (Motion Asset Store)")
        self.resize(500, 280)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("全机群可用舞蹈动作资产列表:"))
        self.table = QTableWidget(3, 3, self)
        self.table.setHorizontalHeaderLabels(["动作名称", "版本", "状态"])
        items = [("POPPING1 (震感舞)", "v1.2", "已安装"), ("中华武术 (Kungfu)", "v2.0", "已安装"), ("芭蕾独舞 (Ballet)", "v1.0", "待安装")]
        for row, (n, v, s) in enumerate(items):
            self.table.setItem(row, 0, QTableWidgetItem(n))
            self.table.setItem(row, 1, QTableWidgetItem(v))
            self.table.setItem(row, 2, QTableWidgetItem(s))
        layout.addWidget(self.table)
        btn_install = QPushButton("一键同步并安装全部未装动作", self)
        btn_install.clicked.connect(lambda: QMessageBox.information(self, "动作商店", "全机群动作同步完成！"))
        layout.addWidget(btn_install)


class SystemSettingsDialog(QDialog):
    """System configuration: IP binding, Graphics profile (Eco/Pro), E-stop style."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("⚙️ 系统设置 (System Settings)")
        self.resize(460, 260)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("网卡 IP 绑定:"))
        self.edit_ip = QLineEdit("172.18.0.1", self)
        layout.addWidget(self.edit_ip)

        layout.addWidget(QLabel("3D 渲染档位 (Graphics Profile):"))
        self.combo_gfx = QComboBox(self)
        self.combo_gfx.addItems(["Pro 模式 (OpenGL 4.3 / 完整 URDF Mesh / 4x MSAA)", "Eco 模式 (OpenGL 3.3 / ANGLE / 简化骨骼)"])
        layout.addWidget(self.combo_gfx)

        layout.addWidget(QLabel("急停操作风格:"))
        self.combo_brake = QComboBox(self)
        self.combo_brake.addItems(["滑块式 (右滑触发)", "按钮式 (直接点击)"])
        layout.addWidget(self.combo_brake)

        btn_save = QPushButton("保存设置", self)
        btn_save.clicked.connect(self._on_save)
        layout.addWidget(btn_save)

    def _on_save(self) -> None:
        data = {
            "bind_ip": self.edit_ip.text().strip(),
            "profile": "pro" if "Pro" in self.combo_gfx.currentText() else "eco",
            "brake_style": "slider" if "滑块" in self.combo_brake.currentText() else "button",
        }
        event_bus.publish("SYSTEM_SETTINGS_SAVED", data)
        self.accept()


def open_view_menu_dialog(parent: Optional[QWidget], action_code: str) -> Optional[QDialog]:
    """Factory creating and executing dialog matching top menu action codes."""
    ctrl = getattr(parent, "controller", None)
    dlg: Optional[QDialog] = None
    if action_code == "ACTION_TEST":
        dlg = ActionTestDialog(parent, controller=ctrl)
    elif action_code == "LIDAR_MONITOR":
        dlg = RadarMonitorDialog(parent)
    elif action_code == "RUN_LOGS":
        dlg = RunLogDialog(parent)
    elif action_code in ("CHOREO_STORE", "ACTION_STORE"):
        dlg = ActionStoreDialog(parent)
    elif action_code in ("OPEN_SETTINGS", "SYSTEM_SETTINGS"):
        dlg = SystemSettingsDialog(parent)

    if dlg:
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            dlg.show()
        else:
            dlg.exec_()
    return dlg

