"""
@file: src/ui/choreo_page/stage_canvas_2d.py
@brief: 2D 舞台平面交互画布，提供样条拟合、控制点拖拽、群组预览与多机交互
@exports: StageCanvas2D
"""
import copy, logging, math, time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QWheelEvent
from PySide6.QtWidgets import QWidget
from src.domain.trajectory.spline_builder import SplineTrajectoryBuilder
from src.domain.trajectory.trajectory_draft_validator import TrajectoryDraftValidator
from src.ui.choreo_page.group_canvas_renderer import GroupCanvasRenderer
from src.ui.choreo_page.map_canvas_renderer import MapCanvasRenderer

logger = logging.getLogger("StageCanvas2D")


class StageCanvas2D(QWidget):
    """2D 舞台平面交互视口，支持向心样条拟合、控制点拖拽编辑、持久化与多机选择"""

    trajectoryFinished = Signal(dict); trajectoryCancelled = Signal(); trajectorySelected = Signal(str)
    trajectoryDeleted = Signal(str); trajectorySaved = Signal(dict); validationFailed = Signal(str)
    pointAdded = Signal(float, float); robotSelected = Signal(str); mapLoaded = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None, controller: Optional[Any] = None, store: Optional[Any] = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.store = store or getattr(controller, "store", None)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._scale, self._offset_x, self._offset_y = 20.0, 0.0, 0.0
        self._is_panning, self._pan_start = False, QPointF()

        self._draw_mode = "DRAW_TRAJECTORY"
        self._active_waypoints: List[Tuple[float, float]] = []
        self._live_spline_points: List[Tuple[float, float]] = []
        self._hover_stage_pos: Optional[Tuple[float, float]] = None
        self._completed_trajectories: List[Dict[str, Any]] = []
        self._selected_trajectory_id: Optional[str] = None
        self._backup_trajectory: Optional[Dict[str, Any]] = None
        self._dragging_point_idx: Optional[int] = None
        self._selected_robot_id: Optional[str] = None
        self._robot_spawns: List[Dict[str, Any]] = []
        self._current_poses: Dict[Any, Any] = {}
        self._status_message: Optional[Tuple[str, str, float]] = None
        self._grid_image: Optional[QImage] = None
        self._grid_info: Optional[Dict[str, Any]] = None

        self._group_preview_trajectories: List[Any] = []
        self._group_safety_report: Optional[Any] = None
        self._update_cursor_for_mode()
        if self.controller and hasattr(self.controller, "playhead_updated"):
            self.controller.playhead_updated.connect(self._on_playhead_updated)

    def _update_cursor_for_mode(self) -> None:
        self.setCursor(Qt.CrossCursor if "DRAW" in self._draw_mode else (Qt.PointingHandCursor if "SELECT" in self._draw_mode else Qt.ArrowCursor))

    def screen_to_stage(self, pos: Union[QPointF, Tuple[float, float], Any]) -> Tuple[float, float]:
        px = float(pos.x()) if hasattr(pos, "x") else float(pos[0])
        py = float(pos.y()) if hasattr(pos, "y") else float(pos[1])
        cx, cy = self.width() / 2.0 + self._offset_x, self.height() / 2.0 + self._offset_y
        return round((px - cx) / self._scale, 3), round(-(py - cy) / self._scale, 3)

    def stage_to_screen(self, x: float, y: float) -> QPointF:
        return QPointF(self.width() / 2.0 + self._offset_x + x * self._scale, self.height() / 2.0 + self._offset_y - y * self._scale)

    def world_to_screen(self, x: float, y: float) -> QPointF: return self.stage_to_screen(x, y)
    def screen_to_world(self, px: float, py: float) -> Tuple[float, float]: return self.screen_to_stage((px, py))

    def set_draw_mode(self, mode: str) -> None:
        self._draw_mode, self._hover_stage_pos = mode.upper(), None
        self._update_cursor_for_mode(); self.update()

    def set_active_formation(self, form_data: Optional[Dict[str, Any]]) -> None:
        self._active_formation = form_data; self.update()
    def reset_view(self) -> None:
        self._offset_x, self._offset_y, self._scale = 0.0, 0.0, 20.0; self.update()
    def set_robots(self, robots: Sequence[Dict[str, Any]]) -> None:
        self._robot_spawns = [dict(r) for r in robots]
        valid_ids = [str(r.get("id")) for r in self._robot_spawns]
        if self._selected_robot_id not in valid_ids:
            self._selected_robot_id = valid_ids[0] if valid_ids else None
        self.update()
    def select_robot(self, robot_id: str) -> None:
        self._selected_robot_id = str(robot_id); self.robotSelected.emit(str(robot_id)); self.update()

    def get_robot_pose(self, robot_id: Optional[str] = None) -> Optional[Tuple[float, float, float]]:
        return TrajectoryDraftValidator.resolve_robot_pose(str(robot_id or self._selected_robot_id or ""), self._current_poses, self._completed_trajectories, self._robot_spawns)

    def validate_trajectory_draft(self, waypoints: List[Tuple[float, float]], robot_id: Optional[str]) -> Tuple[bool, str]:
        return TrajectoryDraftValidator.validate(waypoints, robot_id, self.get_robot_pose(robot_id))

    def select_trajectory(self, traj_id: Optional[str]) -> bool:
        if not traj_id:
            self._selected_trajectory_id, self._backup_trajectory = None, None
            self.update(); return False
        item = next((t for t in self._completed_trajectories if str(t.get("id")) == str(traj_id)), None)
        if not item: return False
        self._selected_trajectory_id, self._backup_trajectory = str(traj_id), copy.deepcopy(item)
        self._status_message = (f"已选中轨迹 '{item['name']}' 进入编辑模式", "info", time.time())
        self.trajectorySelected.emit(str(traj_id)); self.update(); return True

    def cancel_edit(self) -> bool:
        if not (self._selected_trajectory_id and self._backup_trajectory): return False
        idx = next((i for i, t in enumerate(self._completed_trajectories) if str(t.get("id")) == self._selected_trajectory_id), None)
        if idx is not None: self._completed_trajectories[idx] = self._backup_trajectory
        self._selected_trajectory_id, self._backup_trajectory, self._dragging_point_idx = None, None, None
        self._status_message = ("已取消编辑并还原轨迹状态", "info", time.time()); self.update(); return True

    def insert_waypoint_to_trajectory(self, traj_id: str, index: int, pos: Tuple[float, float]) -> bool:
        ok = TrajectoryDraftValidator.insert_and_refresh(self._completed_trajectories, traj_id, index, pos)
        if ok: self.update()
        return ok

    def delete_waypoint_from_trajectory(self, traj_id: str, index: int) -> bool:
        ok, err = TrajectoryDraftValidator.delete_and_refresh(self._completed_trajectories, traj_id, index)
        if not ok: self._status_message = (err, "error", time.time()); self.validationFailed.emit(err)
        self.update(); return ok

    def finish_trajectory(self) -> bool:
        valid, err_msg = self.validate_trajectory_draft(self._active_waypoints, self._selected_robot_id)
        if not valid:
            self._status_message = (err_msg, "error", time.time()); self.validationFailed.emit(err_msg)
            logger.warning(f"轨迹绘制校验失败: {err_msg}"); self.update(); return False
        seq = len(self._completed_trajectories) + 1
        _, traj_data = TrajectoryDraftValidator.build_trajectory_asset(self._active_waypoints, str(self._selected_robot_id), seq)
        self._completed_trajectories.append(traj_data); self.trajectoryFinished.emit(traj_data)
        self._status_message = (f"轨迹已生成并绑定机器人 {self._selected_robot_id}", "info", time.time())
        self.clear_active_trajectory(silent=True); return True

    def save_current_trajectory(self, traj_id: Optional[str] = None, allow_overwrite_referenced: bool = False) -> bool:
        ok, msg, item = TrajectoryDraftValidator.save_current(
            self.store, self._completed_trajectories, traj_id or self._selected_trajectory_id, self._selected_robot_id, allow_overwrite_referenced
        )
        self._status_message = (msg, "info" if ok else "error", time.time())
        if ok and item:
            self._backup_trajectory = copy.deepcopy(item); self.trajectorySaved.emit(item)
        elif not ok: self.validationFailed.emit(msg)
        self.update(); return ok

    def delete_trajectory(self, traj_id: str) -> bool:
        ok, msg = TrajectoryDraftValidator.delete_trajectory(self.store, self._completed_trajectories, traj_id)
        self._status_message = (msg, "info" if ok else "error", time.time())
        if ok:
            if self._selected_trajectory_id == str(traj_id): self._selected_trajectory_id, self._backup_trajectory = None, None
            self.trajectoryDeleted.emit(str(traj_id))
        self.update(); return ok

    def load_trajectories_from_store(self, robot_group: Optional[str] = None) -> int:
        self._completed_trajectories = TrajectoryDraftValidator.load_trajectories_from_store(self.store, robot_group, self._selected_robot_id or "A")
        self.update(); return len(self._completed_trajectories)

    def cancel_trajectory(self) -> None: self.clear_active_trajectory(silent=False)

    def clear_active_trajectory(self, silent: bool = False) -> None:
        self._active_waypoints.clear(); self._live_spline_points.clear(); self._hover_stage_pos = None
        if not silent:
            self._status_message = ("已取消当前轨迹绘制", "info", time.time()); self.trajectoryCancelled.emit()
        self.update()

    def clear_all(self) -> None:
        self.clear_active_trajectory(); self._completed_trajectories.clear()
        self._selected_trajectory_id, self._backup_trajectory = None, None; self.update()

    def set_group_preview(self, member_trajectories: Optional[Sequence[Any]], safety_report: Optional[Any] = None) -> None:
        self._group_preview_trajectories = list(member_trajectories or ())
        self._group_safety_report = safety_report
        status = GroupCanvasRenderer.resolve_safety_status(safety_report)
        if status:
            self._status_message = (status[0], status[1], time.time())
        self.update()

    def clear_group_preview(self) -> None:
        self._group_preview_trajectories.clear(); self._group_safety_report = None; self.update()

    def undo_waypoint(self) -> None:
        if self._active_waypoints:
            self._active_waypoints.pop(); self._recompute_spline(); self.update()

    def _recompute_spline(self) -> None:
        if len(self._active_waypoints) < 2:
            self._live_spline_points = list(self._active_waypoints); return
        curve, _, _ = SplineTrajectoryBuilder.fit_spline_curve(self._active_waypoints, alpha=0.5)
        self._live_spline_points = [(float(pt[0]), float(pt[1])) for pt in curve]

    def set_grid_data(self, grid_image: Optional[QImage], grid_info: Optional[Dict[str, Any]], meta: Optional[Dict[str, Any]] = None) -> None:
        self._grid_image, self._grid_info = grid_image, grid_info
        if meta: self.mapLoaded.emit(meta)
        self.update()

    def load_map(self, file_path: Optional[str] = None) -> None:
        try:
            img, info, meta = MapCanvasRenderer.load_pcd_grid_image(file_path)
            self.set_grid_data(img, info, meta)
        except Exception as e:
            logger.error(f"Failed to load PCD map: {e}")

    def _on_playhead_updated(self, t: float, poses: dict) -> None:
        self._current_poses = poses; self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("#111318"))
        cx, cy = w / 2.0 + self._offset_x, h / 2.0 + self._offset_y
        MapCanvasRenderer.draw_grid_and_axes(p, w, h, cx, cy, self._scale)
        MapCanvasRenderer.draw_occupancy_grid(p, self._grid_image, self._grid_info, cx, cy, self._scale)
        if self._robot_spawns:
            MapCanvasRenderer.draw_robot_spawns(p, self._robot_spawns, self._selected_robot_id, cx, cy, self._scale, self._current_poses)
        elif not self._completed_trajectories and not self._active_waypoints:
            p.save(); p.setPen(QColor("#475569"))
            f = p.font(); f.setPointSize(11); f.setBold(True); p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter, "舞台就绪 · 无机器人站位 (等待载入工程或添加机器人)")
            p.restore()
        for item in self._completed_trajectories:
            is_sel = (self._selected_trajectory_id == str(item.get("id")))
            drag_pt = self._dragging_point_idx if is_sel else None
            MapCanvasRenderer.draw_spline_trajectory(p, item.get("waypoints", []), item.get("spline_points"), False, cx, cy, self._scale, is_selected=is_sel, drag_idx=drag_pt)
        if self._group_preview_trajectories:
            GroupCanvasRenderer.draw_group_preview(p, self._group_preview_trajectories, self._group_safety_report, cx, cy, self._scale)
        if self._active_waypoints:
            MapCanvasRenderer.draw_spline_trajectory(p, self._active_waypoints, self._live_spline_points, True, cx, cy, self._scale, self._hover_stage_pos)
        if self._status_message and (time.time() - self._status_message[2] < 4.0):
            MapCanvasRenderer.draw_status_toast(p, w, self._status_message[0], self._status_message[1])

    def mousePressEvent(self, event) -> None:
        ev_pos = event.position() if hasattr(event, "position") else event.pos()
        if event.button() == Qt.MiddleButton or (event.button() == Qt.LeftButton and event.modifiers() & Qt.AltModifier):
            self._is_panning, self._pan_start = True, ev_pos; return
        if event.button() == Qt.LeftButton:
            wx, wy = self.screen_to_stage(ev_pos)
            if "SELECT" in self._draw_mode:
                self._handle_robot_selection(wx, wy); return
            if not self._active_waypoints and self._handle_control_point_interaction(wx, wy): return
            if "DRAW" in self._draw_mode:
                if not self._active_waypoints:
                    r_pose = self.get_robot_pose(self._selected_robot_id)
                    if r_pose and math.hypot(wx - r_pose[0], wy - r_pose[1]) <= 0.8: wx, wy = round(r_pose[0], 3), round(r_pose[1], 3)
                self._active_waypoints.append((wx, wy))
                self._recompute_spline(); self.pointAdded.emit(wx, wy)
                self._status_message = (f"已添加控制点 P{len(self._active_waypoints)}: ({wx:.2f}, {wy:.2f})", "info", time.time())
                self.update()
        elif event.button() == Qt.RightButton and "DRAW" in self._draw_mode and self._active_waypoints:
            self.finish_trajectory()
        super().mousePressEvent(event)

    def _handle_control_point_interaction(self, wx: float, wy: float) -> bool:
        targets = [t for t in self._completed_trajectories if str(t.get("id")) == self._selected_trajectory_id] if self._selected_trajectory_id else self._completed_trajectories
        for t in targets:
            hit = TrajectoryDraftValidator.find_closest_waypoint(t.get("waypoints", []), (wx, wy), max_dist_m=0.5)
            if hit is not None:
                self.select_trajectory(t.get("id")); self._dragging_point_idx = hit; self.update(); return True
        return False

    def _handle_robot_selection(self, wx: float, wy: float) -> None:
        for r in self._robot_spawns:
            if math.hypot(wx - r.get("pos", (0.0, 0.0))[0], wy - r.get("pos", (0.0, 0.0))[1]) <= 0.6:
                self.select_robot(str(r["id"])); return

    def mouseMoveEvent(self, event) -> None:
        ev_pos = event.position() if hasattr(event, "position") else event.pos()
        if self._is_panning:
            delta = ev_pos - self._pan_start
            self._offset_x += delta.x(); self._offset_y += delta.y()
            self._pan_start = ev_pos; self.update(); return
        wx, wy = self.screen_to_stage(ev_pos)
        if self._dragging_point_idx is not None and self._selected_trajectory_id:
            item = next((t for t in self._completed_trajectories if str(t.get("id")) == self._selected_trajectory_id), None)
            if item:
                item["waypoints"] = TrajectoryDraftValidator.update_waypoint(item["waypoints"], self._dragging_point_idx, (wx, wy))
                TrajectoryDraftValidator.refresh_trajectory_preview(item)
                self.update(); return
        if "DRAW" in self._draw_mode and self._active_waypoints:
            self._hover_stage_pos = (wx, wy); self.update()
        elif self._hover_stage_pos is not None:
            self._hover_stage_pos = None; self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self._hover_stage_pos is not None: self._hover_stage_pos = None; self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() in (Qt.LeftButton, Qt.MiddleButton): self._is_panning, self._dragging_point_idx = False, None
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 0.85
        self._scale = max(5.0, min(120.0, self._scale * factor)); self.update()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Z and event.modifiers() & Qt.ControlModifier: self.undo_waypoint()
        elif event.key() == Qt.Key_Escape:
            if not self.cancel_edit(): self.cancel_trajectory()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._active_waypoints: self.finish_trajectory()
            elif self._selected_trajectory_id: self.save_current_trajectory()
        super().keyPressEvent(event)
