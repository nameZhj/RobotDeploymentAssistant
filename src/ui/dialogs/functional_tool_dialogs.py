"""
实用工具弹窗集合 (Functional Tool Dialogs)
提供动作测试控制台、运行日志审计器、初始化点配置对话框与音乐选择交互
"""
import os
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget
)

from src.application.services.lrmp_swarm_service import LRMPSwarmService


class ActionTestDialog(QDialog):
    """LRMP V1.0-R3 动作与直接运动控制台"""

    def __init__(self, lrmp_service: Optional[LRMPSwarmService] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("动作测试 (LRMP Direct Control)")
        self.setFixedSize(520, 420)
        self.setStyleSheet("background: #0f172a; color: #f8fafc;")
        self.svc = lrmp_service or LRMPSwarmService()
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 1. 目标选择
        row_tgt = QHBoxLayout()
        row_tgt.addWidget(QLabel("测试目标:"))
        self.chk_a = QCheckBox("Robot A (ID:1)")
        self.chk_b = QCheckBox("Robot B (ID:2)")
        self.chk_a.setChecked(True)
        row_tgt.addWidget(self.chk_a)
        row_tgt.addWidget(self.chk_b)
        row_tgt.addStretch()
        layout.addLayout(row_tgt)

        # 2. 基础模式
        row_mode = QHBoxLayout()
        for cmd in ("STAND", "GAIT", "PASSIVE", "RELEASE", "STOP"):
            btn = QPushButton(cmd)
            col = "#dc2626" if cmd == "STOP" else ("#0284c7" if cmd == "STAND" else "#334155")
            btn.setStyleSheet(f"background: {col}; color: white; padding: 5px; border-radius: 4px; font-weight: bold;")
            btn.clicked.connect(lambda chk, c=cmd: self._send_cmd(c))
            row_mode.addWidget(btn)
        layout.addLayout(row_mode)

        # 3. 方向按键九宫格
        grid_frame = QFrame()
        grid_frame.setStyleSheet("background: #1e293b; border-radius: 6px; padding: 6px;")
        grid = QGridLayout(grid_frame)
        dirs = [
            ("左转 ↺", "MOVE,0.0,0.0,0.5,1.0", 0, 0), ("前进 ↑", "MOVE,0.5,0.0,0.0,1.0", 0, 1), ("右转 ↻", "MOVE,0.0,0.0,-0.5,1.0", 0, 2),
            ("左移 ←", "MOVE,0.0,0.5,0.0,1.0", 1, 0), ("停止 ■", "STOP", 1, 1), ("右移 →", "MOVE,0.0,-0.5,0.0,1.0", 1, 2),
            ("后退 ↓", "MOVE,-0.5,0.0,0.0,1.0", 2, 1)
        ]
        for name, cmd, r, c in dirs:
            b = QPushButton(name)
            b.setStyleSheet("background: #334155; color: white; padding: 6px; border-radius: 4px;")
            b.clicked.connect(lambda chk, cm=cmd: self._send_cmd(cm))
            grid.addWidget(b, r, c)
        layout.addWidget(grid_frame)

        # 4. 预置舞蹈下发
        row_dance = QHBoxLayout()
        row_dance.addWidget(QLabel("单次舞蹈:"))
        for dname in ("POPPING1", "芭蕾", "KUNGFU"):
            btn = QPushButton(dname)
            btn.setStyleSheet("background: #4f46e5; color: white; padding: 4px 8px; border-radius: 4px;")
            btn.clicked.connect(lambda chk, dn=dname: self._send_cmd(f"DANCE,{dn}"))
            row_dance.addWidget(btn)
        row_dance.addStretch()
        layout.addLayout(row_dance)

        # 5. 反馈输出日志
        self.txt_feedback = QTextEdit()
        self.txt_feedback.setReadOnly(True)
        self.txt_feedback.setStyleSheet("background: #020617; border: 1px solid #1e293b; color: #38bdf8; font-family: Consolas; font-size: 11px;")
        layout.addWidget(self.txt_feedback)

    def _get_selected_targets(self) -> List[str]:
        tgts = []
        if self.chk_a.isChecked():
            tgts.append("A")
        if self.chk_b.isChecked():
            tgts.append("B")
        return tgts

    def _send_cmd(self, cmd: str) -> None:
        tgts = self._get_selected_targets()
        if not tgts:
            self.txt_feedback.append("[WARN] 未勾选任何目标机器人！")
            return
        for t in tgts:
            res = self.svc.send_frame(t, cmd)
            for src, pay in res:
                self.txt_feedback.append(f">> [{src}] {pay}")


class RunLogDialog(QDialog):
    """运行日志查看器 (支持按设备 SRC_ID 实时过滤)"""

    def __init__(self, log_path: str = os.path.join("runtime", "logs", "lrmp_session.log"), parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("运行日志审计 (Run Logs)")
        self.setFixedSize(620, 450)
        self.setStyleSheet("background: #0f172a; color: #f8fafc;")
        self.log_path = log_path
        self._init_ui()
        self.refresh_logs()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("设备来源 SRC_ID 过滤:"))
        self.combo_src = QComboBox()
        self.combo_src.addItems(["全部来源", "A", "B", "GW_8C2F", "SYS", "LOCAL"])
        self.combo_src.currentIndexChanged.connect(self.refresh_logs)
        top.addWidget(self.combo_src)
        top.addStretch()

        btn_refresh = QPushButton("刷新")
        btn_refresh.setStyleSheet("background: #0284c7; color: white; padding: 4px 10px; border-radius: 4px;")
        btn_refresh.clicked.connect(self.refresh_logs)
        top.addWidget(btn_refresh)
        layout.addLayout(top)

        self.txt_logs = QTextEdit()
        self.txt_logs.setReadOnly(True)
        self.txt_logs.setStyleSheet("background: #020617; border: 1px solid #1e293b; color: #94a3b8; font-family: Consolas; font-size: 11px;")
        layout.addWidget(self.txt_logs)

    def refresh_logs(self) -> None:
        self.txt_logs.clear()
        if not os.path.exists(self.log_path):
            self.txt_logs.setText("暂无日志记录 (runtime/logs/lrmp_session.log 不存在)")
            return
        filt = self.combo_src.currentText()
        with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        matched = []
        for line in lines:
            if filt == "全部来源" or f"SRC_ID: {filt}" in line or f"from {filt}" in line:
                matched.append(line.strip())
        self.txt_logs.setText("\n".join(matched[-200:]))


class InitPointEditDialog(QDialog):
    """机器人初始化点坐标编辑弹窗"""

    def __init__(self, current_points: Optional[List[Dict[str, float]]] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("初始化点配置")
        self.setFixedSize(320, 220)
        self.setStyleSheet("background: #0f172a; color: #f8fafc;")
        self.pts = current_points or [{"id": "1", "x": -2.0, "y": 0.0}, {"id": "2", "x": 2.0, "y": 0.0}]
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.sp_a_x = QDoubleSpinBox()
        self.sp_a_x.setRange(-20.0, 20.0)
        self.sp_a_x.setValue(self.pts[0].get("x", -2.0))
        self.sp_a_y = QDoubleSpinBox()
        self.sp_a_y.setRange(-20.0, 20.0)
        self.sp_a_y.setValue(self.pts[0].get("y", 0.0))

        self.sp_b_x = QDoubleSpinBox()
        self.sp_b_x.setRange(-20.0, 20.0)
        self.sp_b_x.setValue(self.pts[1].get("x", 2.0) if len(self.pts) > 1 else 2.0)
        self.sp_b_y = QDoubleSpinBox()
        self.sp_b_y.setRange(-20.0, 20.0)
        self.sp_b_y.setValue(self.pts[1].get("y", 0.0) if len(self.pts) > 1 else 0.0)

        form.addRow("Robot 1 X (m):", self.sp_a_x)
        form.addRow("Robot 1 Y (m):", self.sp_a_y)
        form.addRow("Robot 2 X (m):", self.sp_b_x)
        form.addRow("Robot 2 Y (m):", self.sp_b_y)
        layout.addLayout(form)

        btn_ok = QPushButton("保存配置")
        btn_ok.setStyleSheet("background: #0284c7; color: white; padding: 6px; border-radius: 4px; font-weight: bold;")
        btn_ok.clicked.connect(self.accept)
        layout.addWidget(btn_ok)

    def get_points(self) -> List[Dict[str, float]]:
        return [
            {"id": "1", "x": self.sp_a_x.value(), "y": self.sp_a_y.value()},
            {"id": "2", "x": self.sp_b_x.value(), "y": self.sp_b_y.value()},
        ]


class MusicSelectDialog(QDialog):
    """背景音乐音频选择弹窗"""

    def __init__(self, current_bgm: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("场景音乐伴奏配置")
        self.setFixedSize(380, 160)
        self.setStyleSheet("background: #0f172a; color: #f8fafc;")
        self.selected_path = current_bgm
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.lbl_path = QLabel(f"当前音乐: {os.path.basename(self.selected_path) if self.selected_path else '未配置'}")
        layout.addWidget(self.lbl_path)

        btn_browse = QPushButton("选择本地音频 (.mp3/.wav)...")
        btn_browse.setStyleSheet("background: #334155; color: white; padding: 6px; border-radius: 4px;")
        btn_browse.clicked.connect(self._browse_file)
        layout.addWidget(btn_browse)

        btn_ok = QPushButton("确认应用")
        btn_ok.setStyleSheet("background: #0284c7; color: white; padding: 6px; border-radius: 4px; font-weight: bold;")
        btn_ok.clicked.connect(self.accept)
        layout.addWidget(btn_ok)

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择背景伴奏音乐", "", "Audio Files (*.mp3 *.wav)")
        if path:
            self.selected_path = path
            self.lbl_path.setText(f"当前音乐: {os.path.basename(path)}")

