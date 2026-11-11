"""
@file: src/ui/monitor/monitor_stage_panel.py
@brief: 表演监测左侧实时地图视口（无AI按钮）与同步只读双层时间轴
@exports: MonitorStagePanel
"""
import math
from typing import Any, Dict, List, Optional, Tuple
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from src.infrastructure.map.pcd_io_engine import PcdMapLoader
from src.infrastructure.storage.studio_repository import StudioRepository


class MonitorStagePanel(QWidget):
    """表演监测 2D 实时点云地图视口与进度同步只读时间轴"""

    def __init__(self, parent: Optional[QWidget] = None,
                 repo: Optional[StudioRepository] = None) -> None:
        super().__init__(parent)
        self.repo = repo or StudioRepository()
        self.show_target_traj = True
        self.show_actual_traj = True
        self.show_init_points = True
        self.playhead_s = 0.0
        self.scale = 28.0
        self.pan_x = 360.0
        self.pan_y = 220.0

        self.pcd_pts = PcdMapLoader.load_or_create_default()
        self.init_pts = self.repo.get_init_point_configs("123", cfg_id=1)
        self.clips = self.repo.get_track_clips("123", "默认任务1")
        self.robot_poses: Dict[str, Tuple[float, float, float]] = {
            "A": (-1.2, 0.2, 0.0), "B": (-3.2, -1.2, 0.0)
        }
        self.target_trajs = [[(-1.2, 0.2), (0.5, 1.2), (1.8, 0.4)]]
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. 2D 视口容器
        self.map_view = QFrame(self)
        self.map_view.paintEvent = self._paint_map
        mv_lay = QVBoxLayout(self.map_view)
        mv_lay.setContentsMargins(8, 8, 8, 8)

        # 顶部悬浮栏 (严格移除 AI 轨迹与 AI 预设计)
        top_bar = QHBoxLayout()
        btn_back = QPushButton("<", self)
        btn_back.setFixedWidth(28)
        top_bar.addWidget(btn_back)

        self.btn_t_traj = QPushButton("显示目标轨迹", self)
        self.btn_t_traj.setCheckable(True)
        self.btn_t_traj.setChecked(True)
        self.btn_t_traj.clicked.connect(lambda c: setattr(self, "show_target_traj", c) or self.map_view.update())
        top_bar.addWidget(self.btn_t_traj)

        self.btn_a_traj = QPushButton("显示轨迹", self)
        self.btn_a_traj.setCheckable(True)
        self.btn_a_traj.setChecked(True)
        self.btn_a_traj.clicked.connect(lambda c: setattr(self, "show_actual_traj", c) or self.map_view.update())
        top_bar.addWidget(self.btn_a_traj)

        self.btn_init = QPushButton("显示初始化点", self)
        self.btn_init.setCheckable(True)
        self.btn_init.setChecked(True)
        self.btn_init.clicked.connect(lambda c: setattr(self, "show_init_points", c) or self.map_view.update())
        top_bar.addWidget(self.btn_init)
        top_bar.addStretch()
        mv_lay.addLayout(top_bar)
        mv_lay.addStretch()
        layout.addWidget(self.map_view, 1)

        # 2. 底部同步只读时间轴
        self.tl_view = QFrame(self)
        self.tl_view.setFixedHeight(110)
        self.tl_view.paintEvent = self._paint_timeline
        layout.addWidget(self.tl_view)

    def sync_playhead(self, t: float) -> None:
        self.playhead_s = max(0.0, float(t))
        self.tl_view.update()
        self.map_view.update()

    def update_robot_poses(self, poses: Dict[str, Tuple[float, float, float]]) -> None:
        self.robot_poses.update(poses)
        self.map_view.update()

    def _paint_map(self, _) -> None:
        p = QPainter(self.map_view)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.map_view.rect(), QColor("#0c0e12"))

        # 网格与点云
        p.setPen(QPen(QColor("#1e2533"), 1))
        for gx in range(-15, 6, 2):
            sx = int(self.pan_x + gx * self.scale)
            p.drawLine(sx, 0, sx, self.map_view.height())
        for gy in range(-6, 7, 2):
            sy = int(self.pan_y - gy * self.scale)
            p.drawLine(0, sy, self.map_view.width(), sy)

        p.setPen(QColor("#38bdf8"))
        for i in range(0, len(self.pcd_pts), 10):
            sx = int(self.pan_x + self.pcd_pts[i, 0] * self.scale)
            sy = int(self.pan_y - self.pcd_pts[i, 1] * self.scale)
            p.drawPoint(sx, sy)

        # 目标轨迹 (绿色虚线)
        if self.show_target_traj:
            p.setPen(QPen(QColor("#10b981"), 2, Qt.DashLine))
            for traj in self.target_trajs:
                for k in range(len(traj) - 1):
                    x1, y1 = self.pan_x + traj[k][0] * self.scale, self.pan_y - traj[k][1] * self.scale
                    x2, y2 = self.pan_x + traj[k + 1][0] * self.scale, self.pan_y - traj[k + 1][1] * self.scale
                    p.drawLine(int(x1), int(y1), int(x2), int(y2))

        # 初始化点 (红圈)
        if self.show_init_points:
            p.setBrush(QBrush(QColor("#ef4444")))
            for pt in self.init_pts:
                ix = int(self.pan_x + pt["init_x"] * self.scale)
                iy = int(self.pan_y - pt["init_y"] * self.scale)
                p.drawEllipse(ix - 5, iy - 5, 10, 10)
                p.setPen(QColor("#ffffff"))
                p.drawText(ix + 8, iy + 4, pt.get("robot_alias", ""))

        # 实时机器人卡位 (蓝圈带朝向)
        if self.show_actual_traj:
            for alias, (rx, ry, ryaw) in self.robot_poses.items():
                cx = int(self.pan_x + rx * self.scale)
                cy = int(self.pan_y - ry * self.scale)
                p.setBrush(QBrush(QColor("#2563eb")))
                p.setPen(QPen(QColor("#60a5fa"), 2))
                p.drawEllipse(cx - 7, cy - 7, 14, 14)
                # 朝向箭头
                hx = int(cx + 12 * math.cos(ryaw))
                hy = int(cy - 12 * math.sin(ryaw))
                p.drawLine(cx, cy, hx, hy)
                p.setPen(QColor("#ffffff"))
                p.drawText(cx - 3, cy - 9, alias)

    def _paint_timeline(self, _) -> None:
        p = QPainter(self.tl_view)
        p.fillRect(self.tl_view.rect(), QColor("#11141c"))
        px_s = 10.0
        h = self.tl_view.height()

        p.setPen(QColor("#283042"))
        for sec in range(0, 120, 10):
            x = int(sec * px_s)
            p.drawLine(x, 0, x, h)
            p.drawText(x + 2, 12, f"{sec}s")

        for c in self.clips:
            bx = int(c["start_s"] * px_s)
            bw = max(8, int(c["duration_s"] * px_s))
            by = 24 if c["sub_layer"] == "ACTION" else 50
            col = QColor("#2563eb") if c["sub_layer"] == "ACTION" else QColor("#059669")
            p.fillRect(QRectF(bx, by, bw, 20), col)
            p.setPen(QColor("#ffffff"))
            p.drawText(bx + 4, by + 14, c.get("title", ""))

        # 同步游标
        cur_x = int(self.playhead_s * px_s)
        p.setPen(QPen(QColor("#ef4444"), 2))
        p.drawLine(cur_x, 0, cur_x, h)

