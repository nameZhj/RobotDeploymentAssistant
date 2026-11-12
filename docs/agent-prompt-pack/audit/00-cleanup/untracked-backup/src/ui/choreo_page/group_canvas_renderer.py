"""
@file: src/ui/choreo_page/group_canvas_renderer.py
@brief: 2D 舞台群组轨迹多机渲染、端点标牌、边界违规与两两线段间距不足高亮渲染器
@exports: GroupCanvasRenderer
"""
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen

from src.domain.trajectory.group_trajectory_compiler import GroupMemberTrajectory
from src.domain.trajectory.group_trajectory_safety import (
    BoundaryViolation,
    GroupTrajectorySafetyReport,
    PairwiseClearance,
)


class GroupCanvasRenderer:
    """提供 2D 舞台多机器人群组轨迹折线、专属色板、起点/终点标牌及安全冲突高亮渲染。"""

    ROBOT_PALETTE: Tuple[str, ...] = (
        "#38BDF8",  # 天蓝
        "#F43F5E",  # 玫红
        "#10B981",  # 翠绿
        "#A855F7",  # 紫罗兰
        "#F59E0B",  # 琥珀黄
        "#06B6D4",  # 青蓝
        "#EC4899",  # 粉红
        "#84CC16",  # 嫩绿
    )

    @classmethod
    def get_robot_color(cls, robot_id: str, index: int = 0) -> QColor:
        """根据 robot_id 和索引确定对比明显的机器人专属颜色。"""
        if robot_id in ("A", "Robot_1"):
            return QColor("#38BDF8")
        if robot_id in ("B", "Robot_2"):
            return QColor("#F43F5E")
        if robot_id in ("C", "Robot_3"):
            return QColor("#10B981")
        color_hex = cls.ROBOT_PALETTE[index % len(cls.ROBOT_PALETTE)]
        return QColor(color_hex)

    @classmethod
    def resolve_safety_status(
        cls, safety_report: Optional[GroupTrajectorySafetyReport]
    ) -> Optional[Tuple[str, str]]:
        """将安全筛查报告转换为界面状态胶囊文本与告警级别。"""
        if safety_report is None:
            return None
        if safety_report.is_safe:
            return ("静态几何检查通过", "info")
        if safety_report.boundary_violations:
            return ("存在舞台边界违规", "error")
        if any(c.min_distance_m <= 1e-6 for c in safety_report.pairwise_clearances if not c.is_clear):
            return ("存在路径交叉风险", "error")
        return ("存在最小间距不足", "error")

    @classmethod
    def draw_group_preview(
        cls,
        p: QPainter,
        trajectories: Sequence[GroupMemberTrajectory],
        safety_report: Optional[GroupTrajectorySafetyReport],
        cx: float,
        cy: float,
        scale: float,
    ) -> None:
        """主绘制入口：依次绘制轨迹折线、端点、违规高亮线段与告警标签。"""
        if not trajectories:
            return

        p.save()
        traj_by_id: Dict[str, GroupMemberTrajectory] = {}
        for idx, traj in enumerate(trajectories):
            traj_by_id[traj.robot_id] = traj
            color = cls.get_robot_color(traj.robot_id, idx)
            cls._draw_member_path(p, traj, color, cx, cy, scale)

        if safety_report and safety_report.pairwise_clearances:
            cls._draw_clearance_conflicts(p, traj_by_id, safety_report.pairwise_clearances, cx, cy, scale)

        if safety_report and safety_report.boundary_violations:
            cls._draw_boundary_violations(p, safety_report.boundary_violations, cx, cy, scale)

        p.restore()

    @classmethod
    def _draw_member_path(
        cls,
        p: QPainter,
        traj: GroupMemberTrajectory,
        color: QColor,
        cx: float,
        cy: float,
        scale: float,
    ) -> None:
        """绘制单台机器人的采样点折线、行进方向箭头、轻量采样点与起终点图钉。"""
        pts = traj.sampled_points
        if not pts:
            return

        p.setPen(QPen(color, 2.5, Qt.SolidLine))
        for i in range(1, len(pts)):
            p0 = QPointF(cx + pts[i - 1].x_m * scale, cy - pts[i - 1].y_m * scale)
            p1 = QPointF(cx + pts[i].x_m * scale, cy - pts[i].y_m * scale)
            p.drawLine(p0, p1)

        # 1. 绘制轻量化轨迹采样点点阵（降采样避免视觉拥挤）
        dot_step = max(1, len(pts) // 15)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(color.lighter(130)))
        for i in range(0, len(pts), dot_step):
            p.drawEllipse(QPointF(cx + pts[i].x_m * scale, cy - pts[i].y_m * scale), 2.0, 2.0)

        # 2. 绘制行进方向指示箭头
        if len(pts) >= 2:
            step = max(1, len(pts) // 5)
            p.setPen(QPen(color.lighter(140), 2))
            for i in range(step, len(pts), step):
                p0 = QPointF(cx + pts[i - 1].x_m * scale, cy - pts[i - 1].y_m * scale)
                p1 = QPointF(cx + pts[i].x_m * scale, cy - pts[i].y_m * scale)
                dx, dy = p1.x() - p0.x(), p1.y() - p0.y()
                if dx * dx + dy * dy > 1.0:
                    ang = math.atan2(dy, dx)
                    mx, my = (p0.x() + p1.x()) / 2.0, (p0.y() + p1.y()) / 2.0
                    p.drawLine(QPointF(mx, my), QPointF(mx - 7 * math.cos(ang - 0.45), my - 7 * math.sin(ang - 0.45)))
                    p.drawLine(QPointF(mx, my), QPointF(mx - 7 * math.cos(ang + 0.45), my - 7 * math.sin(ang + 0.45)))

        # 3. 绘制起点（绿色光晕图钉）与终点（方形专属图钉）
        start_pt = QPointF(cx + pts[0].x_m * scale, cy - pts[0].y_m * scale)
        p.setPen(QPen(QColor("#10B981"), 2))
        p.setBrush(QBrush(QColor("#065F46")))
        p.drawEllipse(start_pt, 6, 6)
        p.setFont(QFont("Segoe UI", 8, QFont.Bold))
        p.setPen(QColor("#A7F3D0"))
        p.drawText(int(start_pt.x()) + 8, int(start_pt.y()) - 4, f"{traj.robot_id} 起点")

        end_pt = QPointF(cx + pts[-1].x_m * scale, cy - pts[-1].y_m * scale)
        p.setPen(QPen(color.lighter(130), 2))
        p.setBrush(QBrush(color.darker(140)))
        p.drawRect(QRectF(end_pt.x() - 5, end_pt.y() - 5, 10, 10))
        p.setPen(color.lighter(150))
        p.drawText(int(end_pt.x()) + 8, int(end_pt.y()) + 12, f"{traj.robot_id} 终点")

    @classmethod
    def _draw_clearance_conflicts(
        cls,
        p: QPainter,
        traj_by_id: Dict[str, GroupMemberTrajectory],
        pairwise_clearances: Sequence[PairwiseClearance],
        cx: float,
        cy: float,
        scale: float,
    ) -> None:
        """高亮发生间距不足的具体线段，并标注两机中心线最短间距。"""
        p.setFont(QFont("Segoe UI", 8, QFont.Bold))
        for c in pairwise_clearances:
            if c.is_clear:
                continue

            traj_a = traj_by_id.get(c.robot_id_a)
            traj_b = traj_by_id.get(c.robot_id_b)
            if not traj_a or not traj_b:
                continue

            p_a0, p_a1 = cls._get_segment_screen_points(traj_a, c.segment_index_a, cx, cy, scale)
            p_b0, p_b1 = cls._get_segment_screen_points(traj_b, c.segment_index_b, cx, cy, scale)

            if p_a0 and p_a1:
                p.setPen(QPen(QColor(239, 68, 68, 120), 8, Qt.SolidLine))
                p.drawLine(p_a0, p_a1)
                p.setPen(QPen(QColor("#EF4444"), 3, Qt.SolidLine))
                p.drawLine(p_a0, p_a1)

            if p_b0 and p_b1:
                p.setPen(QPen(QColor(239, 68, 68, 120), 8, Qt.SolidLine))
                p.drawLine(p_b0, p_b1)
                p.setPen(QPen(QColor("#EF4444"), 3, Qt.SolidLine))
                p.drawLine(p_b0, p_b1)

            if p_a0 and p_b0:
                mid_x = (p_a0.x() + p_b0.x()) / 2.0
                mid_y = (p_a0.y() + p_b0.y()) / 2.0
                label = f"⚠ {c.robot_id_a}-{c.robot_id_b}: {c.min_distance_m:.2f}m < {c.required_clearance_m:.2f}m"
                cls._draw_tag_badge(p, mid_x, mid_y, label, bg_color=QColor(220, 38, 38, 220))

    @classmethod
    def _draw_boundary_violations(
        cls,
        p: QPainter,
        violations: Sequence[BoundaryViolation],
        cx: float,
        cy: float,
        scale: float,
    ) -> None:
        """在超出舞台边界的点位绘制警告图钉与说明。"""
        p.setFont(QFont("Segoe UI", 8, QFont.Bold))
        for v in violations:
            px = cx + v.x_m * scale
            py = cy - v.y_m * scale
            p.setPen(QPen(QColor("#FCA5A5"), 2))
            p.setBrush(QBrush(QColor(220, 38, 38, 220)))
            p.drawEllipse(QPointF(px, py), 7, 7)
            label = f"⚠ {v.robot_id} 越界 ({v.boundary})"
            cls._draw_tag_badge(p, px, py - 14, label, bg_color=QColor(185, 28, 28, 220))

    @staticmethod
    def _get_segment_screen_points(
        traj: GroupMemberTrajectory,
        seg_idx: int,
        cx: float,
        cy: float,
        scale: float,
    ) -> Tuple[Optional[QPointF], Optional[QPointF]]:
        pts = traj.sampled_points
        if 0 <= seg_idx < len(pts) - 1:
            p0 = QPointF(cx + pts[seg_idx].x_m * scale, cy - pts[seg_idx].y_m * scale)
            p1 = QPointF(cx + pts[seg_idx + 1].x_m * scale, cy - pts[seg_idx + 1].y_m * scale)
            return p0, p1
        return None, None

    @staticmethod
    def _draw_tag_badge(
        p: QPainter, x: float, y: float, text: str, bg_color: QColor
    ) -> None:
        metrics = p.fontMetrics()
        w = metrics.horizontalAdvance(text) + 12
        h = 20
        rect = QRectF(x - w / 2.0, y - h / 2.0, w, h)
        p.setPen(QPen(QColor("#FCA5A5"), 1))
        p.setBrush(QBrush(bg_color))
        p.drawRoundedRect(rect, 4, 4)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(rect, Qt.AlignCenter, text)
