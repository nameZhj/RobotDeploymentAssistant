"""
@file: src/ui/choreo_page/group_trajectory_workspace.py
@brief: 2D 舞台群组轨迹独立工作区：多机成员列表、2D 群组预览视口与静态安全筛查面板
@exports: GroupTrajectoryWorkspace
"""
import time
from typing import Any, Dict, List, Optional, Sequence
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from src.application.stage_director.group_trajectory_controller import (
    GroupTrajectoryController,
)
from src.domain.trajectory.group_trajectory import GroupTrajectory
from src.domain.trajectory.group_trajectory_compiler import GroupMemberTrajectory
from src.domain.trajectory.group_trajectory_safety import GroupTrajectorySafetyReport
from src.ui.choreo_page.group_member_edit_panel import GroupMemberEditPanel
from src.ui.choreo_page.stage_canvas_2d import StageCanvas2D


class GroupTrajectoryWorkspace(QWidget):
    """群组轨迹专用工作区窗口，提供成员列表、2D 群组预览视口与静态安全检测结果面板。"""

    backRequested = Signal()
    groupSaved = Signal(object)
    groupDeleted = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None, controller: Optional[Any] = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.group_controller = GroupTrajectoryController()
        self._current_group: Optional[GroupTrajectory] = None
        self._member_trajectories: List[GroupMemberTrajectory] = []
        self._safety_report: Optional[GroupTrajectorySafetyReport] = None
        self._init_ui()
        self._connect_panel_signals()
        self._load_initial_references()

    def _init_ui(self) -> None:
        self.setStyleSheet("""
            QWidget { background-color: #0b0f19; color: #e2e8f0; font-family: 'Segoe UI', sans-serif; }
            QFrame.panel-box { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 6px; }
            QGroupBox {
                color: #94a3b8; font-weight: 700; font-size: 11px;
                border: 1px solid #1e293b; border-radius: 6px; margin-top: 10px;
                padding-top: 12px; background-color: #0f172a;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QPushButton.top-back-btn {
                background-color: #1e293b; color: #38bdf8; border: 1px solid #0284c7;
                border-radius: 4px; padding: 6px 14px; font-size: 12px; font-weight: 700;
            }
            QPushButton.top-back-btn:hover { background-color: #0284c7; color: #ffffff; }
            QLabel.empty-state-hint { color: #64748b; font-size: 11px; line-height: 18px; }
        """)
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)
        root_layout.addWidget(self._build_top_bar())

        self.splitter = QSplitter(Qt.Horizontal, self)
        root_layout.addWidget(self.splitter, 1)

        self.edit_panel = GroupMemberEditPanel(self.splitter)
        self.splitter.addWidget(self.edit_panel)
        self.splitter.addWidget(self._build_center_panel())
        self.splitter.addWidget(self._build_right_panel())
        self.splitter.setSizes([320, 820, 300])

        # 兼容旧测试属性别名
        self.list_members = self.edit_panel.list_members
        self.lbl_selected_robot = QLabel("当前选中: （尚未选择机器人）", self)
        self.lbl_empty_members = QLabel("【空状态】尚未添加机器人成员", self)

    def _build_top_bar(self) -> QFrame:
        top_bar = QFrame(self)
        top_bar.setProperty("class", "panel-box")
        layout = QHBoxLayout(top_bar)
        layout.setContentsMargins(12, 6, 12, 6)
        self.btn_back = QPushButton("⬅ 返回单机器人编排", top_bar)
        self.btn_back.setProperty("class", "top-back-btn")
        self.btn_back.clicked.connect(self.backRequested.emit)
        layout.addWidget(self.btn_back)
        self.lbl_title = QLabel("👥 群组轨迹工作区 (GROUP TRAJECTORY)", top_bar)
        self.lbl_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #38bdf8; margin-left: 12px;")
        layout.addWidget(self.lbl_title)
        layout.addStretch(1)
        self.lbl_mode_tag = QLabel("静态空间预览模式", top_bar)
        self.lbl_mode_tag.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        layout.addWidget(self.lbl_mode_tag)
        return top_bar

    def _build_center_panel(self) -> QFrame:
        self.center_container = QFrame(self.splitter)
        self.center_container.setProperty("class", "panel-box")
        layout = QVBoxLayout(self.center_container)
        layout.setContentsMargins(0, 0, 0, 0)
        self.canvas_2d = StageCanvas2D(self.center_container, controller=self.controller)
        layout.addWidget(self.canvas_2d)
        return self.center_container

    def _build_right_panel(self) -> QFrame:
        self.right_container = QFrame(self.splitter)
        self.right_container.setProperty("class", "panel-box")
        self.right_container.setMinimumWidth(280)
        layout = QVBoxLayout(self.right_container)
        layout.setContentsMargins(8, 8, 8, 8)
        grp = QGroupBox("🛡️ 静态安全检测 (SAFETY REPORT)", self.right_container)
        grp_layout = QVBoxLayout(grp)
        grp_layout.setSpacing(6)
        self.lbl_safety_status = QLabel("检测状态: 尚未检测", grp)
        self.lbl_overall_result = QLabel("综合判定: —", grp)
        self.lbl_boundary_status = QLabel("舞台边界状态: 尚未检测", grp)
        self.lbl_clearance_status = QLabel("两两最小空间距离: 尚未检测", grp)
        self.lbl_violations_count = QLabel("违规风险计数: 0", grp)
        for w in (self.lbl_safety_status, self.lbl_overall_result, self.lbl_boundary_status, self.lbl_clearance_status, self.lbl_violations_count):
            grp_layout.addWidget(w)
        self.lbl_empty_safety = QLabel(
            "【空状态】\n尚未执行静态安全检测。\n生成多机器人全局轨迹后将自动在此呈现边界违规与最小间距。", grp
        )
        self.lbl_empty_safety.setProperty("class", "empty-state-hint")
        self.lbl_empty_safety.setAlignment(Qt.AlignCenter)
        grp_layout.addWidget(self.lbl_empty_safety, 1)
        self.lbl_disclaimer = QLabel("注: 0.6m为静态几何中心线工程阈值，非真机实体包络碰撞验证", grp)
        self.lbl_disclaimer.setStyleSheet("color: #64748b; font-size: 10px;")
        self.lbl_disclaimer.setWordWrap(True)
        grp_layout.addWidget(self.lbl_disclaimer)
        layout.addWidget(grp)
        return self.right_container

    def _connect_panel_signals(self) -> None:
        p = self.edit_panel
        p.referenceSelected.connect(self._on_reference_selected)
        p.formationApplied.connect(self._on_formation_applied)
        p.memberAdded.connect(self._on_member_added)
        p.memberRemoved.connect(self._on_member_removed)
        p.memberOffsetChanged.connect(self._on_member_offset_changed)
        p.previewRequested.connect(self.generate_group_preview)
        p.saveRequested.connect(self._on_save_group_clicked)
        p.loadRequested.connect(self._on_load_group_clicked)
        p.deleteRequested.connect(self._on_delete_group_clicked)

    def _load_initial_references(self) -> None:
        refs = self.group_controller.load_available_references()
        self.edit_panel.set_available_references(refs)

    def _on_reference_selected(self, tid: str) -> None:
        asset = self.group_controller.select_reference_trajectory(tid)
        self.edit_panel.set_selected_reference(asset)

    def _show_toast(self, text: str, level: str = "info") -> None:
        self.canvas_2d._status_message = (text, level, time.time())
        self.canvas_2d.update()

    def _on_formation_applied(self, f_type: str, r: int, c: int, s: float) -> None:
        try:
            if f_type == "LINE":
                self.group_controller.apply_line_formation(spacing_m=s)
            elif f_type == "COLUMN":
                self.group_controller.apply_column_formation(spacing_m=s)
            elif f_type == "CIRCLE":
                self.group_controller.apply_circle_formation(radius_m=s)
            else:
                self.group_controller.apply_grid_formation(rows=r, cols=c, spacing_m=s)
            self.edit_panel.set_members(self.group_controller.get_members())
        except Exception as e:
            self._show_toast(f"阵型生成失败: {e}", "error")

    def _on_member_added(self, rid: str) -> None:
        try:
            self.group_controller.add_member(rid)
            self.edit_panel.set_members(self.group_controller.get_members())
        except Exception as e:
            self._show_toast(f"添加失败: {e}", "error")

    def _on_member_removed(self, rid: str) -> None:
        self.group_controller.remove_member(rid)
        self.edit_panel.set_members(self.group_controller.get_members())

    def _on_member_offset_changed(self, rid: str, x: float, y: float, yaw: float) -> None:
        try:
            self.group_controller.update_member_offset(rid, x, y, yaw)
        except Exception:
            pass

    def generate_group_preview(self) -> None:
        """收集配置并生成群组轨迹与安全检测预览。"""
        try:
            group, trajs, report = self.group_controller.compile_and_validate()
            self.set_group_data(group, trajs, report)
            self._show_toast("群组轨迹预览生成成功", "info")
        except Exception as e:
            self._show_toast(f"生成失败: {e}", "error")

    def _on_save_group_clicked(self) -> None:
        try:
            group = self.group_controller.save_current_group()
            self._show_toast(f"群组配置 '{group.name}' 保存成功", "info")
            self.groupSaved.emit(group)
        except Exception as e:
            self._show_toast(f"保存失败: {e}", "error")

    def _on_load_group_clicked(self) -> None:
        groups = self.group_controller.list_saved_groups()
        if not groups:
            self._show_toast("当前无已保存的群组配置", "info")
            return
        target_id = groups[0]["group_trajectory_id"]
        try:
            group = self.group_controller.load_group(target_id)
            self.edit_panel.set_members(self.group_controller.get_members())
            self.generate_group_preview()
            self._show_toast(f"群组配置 '{group.name}' 加载成功", "info")
        except Exception as e:
            self._show_toast(f"加载失败: {e}", "error")

    def _on_delete_group_clicked(self) -> None:
        groups = self.group_controller.list_saved_groups()
        if not groups: return
        target_id = groups[0]["group_trajectory_id"]
        if self.group_controller.delete_group(target_id):
            self._show_toast(f"已删除群组配置 '{target_id}'", "info")
            self.groupDeleted.emit(target_id)

    def set_group_data(
        self,
        group: Optional[GroupTrajectory] = None,
        trajectories: Optional[Sequence[GroupMemberTrajectory]] = None,
        safety_report: Optional[GroupTrajectorySafetyReport] = None,
    ) -> None:
        """注入群组模型、轨迹预览与安全报告并同步刷新视口与右侧面板。"""
        self._current_group = group
        self._member_trajectories = list(trajectories or ())
        self._safety_report = safety_report
        if group and group.members:
            self.edit_panel.set_members(list(group.members))
            self.lbl_empty_members.hide()
            self.lbl_selected_robot.setText(f"群组: {group.name} ({len(group.members)} 机)")
        else:
            self.lbl_empty_members.show()
            self.lbl_selected_robot.setText("当前选中: （尚未选择机器人）")
        self.canvas_2d.set_group_preview(self._member_trajectories, self._safety_report)
        self._refresh_safety_view()

    def _refresh_safety_view(self) -> None:
        if not self._safety_report:
            self.lbl_empty_safety.show()
            self.lbl_safety_status.setText("检测状态: 尚未检测")
            self.lbl_overall_result.setText("综合判定: —")
            self.lbl_boundary_status.setText("舞台边界状态: 尚未检测")
            self.lbl_clearance_status.setText("两两最小空间距离: 尚未检测")
            self.lbl_violations_count.setText("违规风险计数: 0")
            return

        rep = self._safety_report
        self.lbl_empty_safety.hide()
        self.lbl_safety_status.setText("检测状态: 已完成静态安全检测")
        self.lbl_overall_result.setText(f"综合判定: {'✅ 静态空间安全通过' if rep.is_safe else '❌ 存在几何风险'}")
        b_count = len(rep.boundary_violations)
        if b_count > 0:
            b_ids = sorted(set(v.robot_id for v in rep.boundary_violations))
            self.lbl_boundary_status.setText(f"舞台边界状态: ❌ 存在越界 ({b_count} 处, 涉及: {', '.join(b_ids)})")
        else:
            self.lbl_boundary_status.setText("舞台边界状态: ✅ 正常 (无越界)")

        min_d = min((c.min_distance_m for c in rep.pairwise_clearances), default=None)
        req_d = min((c.required_clearance_m for c in rep.pairwise_clearances), default=0.6)
        bad_c = [f"{c.robot_id_a}-{c.robot_id_b}" for c in rep.pairwise_clearances if not c.is_clear]
        if bad_c:
            self.lbl_clearance_status.setText(f"两两最小空间距离: {min_d:.2f}m (要求>={req_d:.2f}m, 冲突: {', '.join(bad_c)})")
        elif min_d is not None:
            self.lbl_clearance_status.setText(f"两两最小空间距离: {min_d:.2f}m (✅ 间距充足)")
        else:
            self.lbl_clearance_status.setText("两两最小空间距离: 尚未检测")
        self.lbl_violations_count.setText(f"违规风险计数: {rep.violation_count}")

    def clear_workspace(self) -> None:
        """清空群组工作区状态，完全恢复纯净空状态。"""
        self.group_controller.clear_members()
        self.edit_panel.set_members([])
        self.set_group_data(None, None, None)
