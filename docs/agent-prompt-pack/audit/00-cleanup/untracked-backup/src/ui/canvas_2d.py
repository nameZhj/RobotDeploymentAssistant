"""
@file: src/ui/canvas_2d.py
@brief: 2D 交互式地图与轨迹画布，支持物理坐标变换、PCD散点底图、单机与群体轨迹交互编辑与重现
@exports: InteractiveCanvas2D, Canvas2D
"""
import copy
import json
import logging
import math
import os
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QWheelEvent
from PySide6.QtWidgets import QWidget
from src.core.formation_calc import FormationCalculator
from src.core.models import TrajectoryModel
from src.core.storage_manager import storage_manager
from src.domain.trajectory.trajectory_interpolator import TrajectoryInterpolator
from src.ui.canvas_2d_renderer import Canvas2DRenderer

logger = logging.getLogger("Canvas2D")


class InteractiveCanvas2D(QWidget):
    """2D 舞台交互画布：实现米级物理坐标变换、PCD点云投影、单机/群体轨迹绘制与编辑"""

    trajectoryChanged = Signal(dict)
    pointSelected = Signal(int, float, float, float)
    robotSelected = Signal(str)
    formationChanged = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._scale: float = 30.0  # 像素/米
        self._offset_x, self._offset_y = 0.0, 0.0
        self._is_panning = False
        self._last_mouse_pos = QPointF()

        self._pcd_points: Optional[np.ndarray] = None
        self._map_meta: Dict[str, Any] = {}
        self._active_formation: Optional[Dict[str, Any]] = None
        self._drag_form_center, self._drag_form_yaw = False, False

        self.mode = "DRAW"  # "DRAW" 或 "EDIT"
        self.target_type = "single"  # "single" 或 "swarm"
        self.target_id = "A"
        self.interpolation_mode = "catmull_rom"
        self.max_velocity = 0.8

        self.trajectory_id = f"traj_{int(time.time())}"
        self.trajectory_name = "新建轨迹"
        self.control_points: List[Dict[str, Any]] = []
        self.sampled_points: List[Dict[str, Any]] = []
        self._selected_pt_idx = -1
        self._dragging_point, self._dragging_yaw = False, False

        self.robots: Dict[str, Dict[str, Any]] = {
            "A": {"id": "A", "x": -2.0, "y": 0.0, "yaw": 0.0, "color": "#38bdf8"},
            "B": {"id": "B", "x": 2.0, "y": 0.0, "yaw": 3.14, "color": "#34d399"},
        }
        self.groups: Dict[str, List[str]] = {"group_1": ["A", "B"]}

    # --- 坐标变换体系 ---
    def world_to_screen(self, x: float, y: float) -> QPointF:
        cx, cy = self.width() / 2.0 + self._offset_x, self.height() / 2.0 + self._offset_y
        return QPointF(cx + x * self._scale, cy - y * self._scale)

    def screen_to_world(self, px: float, py: float) -> Tuple[float, float]:
        cx, cy = self.width() / 2.0 + self._offset_x, self.height() / 2.0 + self._offset_y
        return float((px - cx) / self._scale), float((cy - py) / self._scale)

    def set_pcd_points(self, points: Optional[np.ndarray], meta: Optional[Dict[str, Any]] = None) -> None:
        self._pcd_points, self._map_meta = points, meta or {}
        self.update()

    def set_active_formation(self, formation: Optional[Dict[str, Any]]) -> None:
        self._active_formation = formation
        self.update()

    def clear_map(self) -> None:
        self._pcd_points, self._map_meta = None, {}
        self.update()

    def _check_formation_press(self, wx: float, wy: float) -> bool:
        if not self._active_formation:
            return False
        c = self._active_formation.get("center", {})
        cx, cy, cyaw = float(c.get("x", 0.0)), float(c.get("y", 0.0)), float(c.get("yaw", 0.0))
        if math.hypot(wx - (cx + 0.8 * math.cos(cyaw)), wy - (cy + 0.8 * math.sin(cyaw))) < 0.35:
            self._drag_form_yaw = True
            return True
        if math.hypot(wx - cx, wy - cy) < 0.45:
            self._drag_form_center = True
            return True
        return False

    def _sync_formation_drag(self, wx: float, wy: float) -> None:
        if not self._active_formation:
            return
        c = self._active_formation.setdefault("center", {})
        if self._drag_form_center:
            c["x"], c["y"] = round(wx, 3), round(wy, 3)
        elif self._drag_form_yaw:
            c["yaw"] = round(math.atan2(wy - float(c.get("y", 0.0)), wx - float(c.get("x", 0.0))), 3)
        mems = self._active_formation.get("members", [])
        w_mems = FormationCalculator.calculate_world_poses(mems, float(c.get("x", 0.0)), float(c.get("y", 0.0)), float(c.get("yaw", 0.0)))
        safe, warns = FormationCalculator.check_safety_distances(w_mems)
        self._active_formation["members"] = w_mems
        self._active_formation["is_safe"] = safe
        self._active_formation["warnings"] = warns
        self.formationChanged.emit(self._active_formation)
        self.update()

    # --- 鼠标与键盘交互事件 ---
    def wheelEvent(self, event: QWheelEvent) -> None:
        cursor = event.position()
        wx, wy = self.screen_to_world(cursor.x(), cursor.y())
        factor = 1.15 if event.angleDelta().y() > 0 else (1.0 / 1.15)
        new_scale = max(6.0, min(300.0, self._scale * factor))
        if new_scale != self._scale:
            self._scale = new_scale
            self._offset_x = cursor.x() - (self.width() / 2.0 + wx * self._scale)
            self._offset_y = cursor.y() - (self.height() / 2.0 - wy * self._scale)
            self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._is_panning = True
            self._last_mouse_pos = event.position()
            return
        if event.button() == Qt.LeftButton:
            wx, wy = self.screen_to_world(event.position().x(), event.position().y())
            if self._check_formation_press(wx, wy):
                self.update()
                return
            if self.mode == "DRAW":
                self._add_control_point(wx, wy)
            elif self.mode == "EDIT":
                self._handle_edit_press(wx, wy)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_panning:
            delta = event.position() - self._last_mouse_pos
            self._offset_x += delta.x()
            self._offset_y += delta.y()
            self._last_mouse_pos = event.position()
            self.update()
            return
        wx, wy = self.screen_to_world(event.position().x(), event.position().y())
        if self._drag_form_center or self._drag_form_yaw:
            self._sync_formation_drag(wx, wy)
            return
        if self.mode == "EDIT" and self._selected_pt_idx >= 0:
            pt = self.control_points[self._selected_pt_idx]
            if self._dragging_point:
                pt["x"], pt["y"] = round(wx, 3), round(wy, 3)
                self._recalculate_times_and_samples()
                self.update()
            elif self._dragging_yaw:
                pt["yaw"] = round(math.atan2(wy - pt["y"], wx - pt["x"]), 3)
                self._recalculate_times_and_samples()
                self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._is_panning = False
        if event.button() == Qt.LeftButton:
            self._dragging_point, self._dragging_yaw = False, False
            self._drag_form_center, self._drag_form_yaw = False, False

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self.mode == "EDIT" and len(self.control_points) >= 2:
            wx, wy = self.screen_to_world(event.position().x(), event.position().y())
            insert_idx = self._find_nearest_segment(wx, wy)
            if insert_idx >= 0:
                p_prev, p_next = self.control_points[insert_idx], self.control_points[insert_idx + 1]
                yaw = math.atan2(p_next["y"] - p_prev["y"], p_next["x"] - p_prev["x"])
                self.control_points.insert(insert_idx + 1, {"seq": insert_idx + 1, "x": round(wx, 3), "y": round(wy, 3), "yaw": round(yaw, 3), "t": 0.0})
                self._reindex_and_update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.mode == "EDIT" and self._selected_pt_idx >= 0:
            self.control_points.pop(self._selected_pt_idx)
            self._selected_pt_idx = -1
            self._reindex_and_update()

    # --- 轨迹计算与增删改 ---
    def _add_control_point(self, x: float, y: float) -> None:
        seq = len(self.control_points)
        yaw = 0.0
        if seq > 0:
            prev = self.control_points[-1]
            yaw = math.atan2(y - prev["y"], x - prev["x"])
            prev["yaw"] = round(yaw, 3)
        self.control_points.append({"seq": seq, "x": round(x, 3), "y": round(y, 3), "yaw": round(yaw, 3), "t": 0.0})
        self._recalculate_times_and_samples()

    def _handle_edit_press(self, wx: float, wy: float) -> None:
        for i, p in enumerate(self.control_points):
            hx = p["x"] + 0.45 * math.cos(p["yaw"])
            hy = p["y"] + 0.45 * math.sin(p["yaw"])
            if math.hypot(wx - hx, wy - hy) <= (14.0 / self._scale):
                self._selected_pt_idx = i
                self._dragging_yaw = True
                return
        for i, p in enumerate(self.control_points):
            if math.hypot(wx - p["x"], wy - p["y"]) <= (12.0 / self._scale):
                self._selected_pt_idx = i
                self._dragging_point = True
                self.pointSelected.emit(i, p["x"], p["y"], p["yaw"])
                return
        self._selected_pt_idx = -1

    def _find_nearest_segment(self, wx: float, wy: float) -> int:
        best_idx, best_dist = -1, 0.4
        for i in range(len(self.control_points) - 1):
            p1, p2 = self.control_points[i], self.control_points[i + 1]
            dist = self._point_to_line_dist(wx, wy, p1["x"], p1["y"], p2["x"], p2["y"])
            if dist < best_dist:
                best_dist, best_idx = dist, i
        return best_idx

    @staticmethod
    def _point_to_line_dist(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
        l2 = (x2 - x1) ** 2 + (y2 - y1) ** 2
        if l2 == 0:
            return math.hypot(px - x1, py - y1)
        t = max(0.0, min(1.0, ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / l2))
        return math.hypot(px - (x1 + t * (x2 - x1)), py - (y1 + t * (y2 - y1)))

    def _reindex_and_update(self) -> None:
        for idx, pt in enumerate(self.control_points):
            pt["seq"] = idx
        self._recalculate_times_and_samples()
        self.update()

    def _recalculate_times_and_samples(self) -> None:
        cum_t = 0.0
        v = max(0.1, min(1.5, self.max_velocity))
        for i in range(len(self.control_points)):
            if i > 0:
                p_prev, p_curr = self.control_points[i - 1], self.control_points[i]
                d = math.hypot(p_curr["x"] - p_prev["x"], p_curr["y"] - p_prev["y"])
                cum_t += d / v
            self.control_points[i]["t"] = round(cum_t, 3)

        self.sampled_points = TrajectoryInterpolator.sample_trajectory(
            self.control_points, mode=self.interpolation_mode, max_velocity=self.max_velocity,
        )
        self.trajectoryChanged.emit(self.to_dict())

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#090d16"))
        Canvas2DRenderer.draw_grid_and_axes(p, self.width(), self.height(), self.world_to_screen(0, 0), self._scale, self.world_to_screen)
        Canvas2DRenderer.draw_pcd_scatter(p, self._pcd_points, self.world_to_screen)
        Canvas2DRenderer.draw_robots(p, self.robots, self._scale, self.world_to_screen)
        Canvas2DRenderer.draw_formation(p, self._active_formation, self._scale, self.world_to_screen)
        Canvas2DRenderer.draw_trajectory(p, self.control_points, self.sampled_points, self._selected_pt_idx, self.target_type, self.world_to_screen)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": "1.0", "trajectory_id": self.trajectory_id, "name": self.trajectory_name,
            "scene_id": "scene_001", "map_id": self._map_meta.get("map_id", "sample_stage"),
            "target_type": self.target_type, "target_id": self.target_id,
            "formation_id": "form_001" if self.target_type == "swarm" else "",
            "interpolation": self.interpolation_mode, "max_velocity": self.max_velocity,
            "control_points": copy.deepcopy(self.control_points), "sampled_points": copy.deepcopy(self.sampled_points),
        }

    def save_trajectory_json(self, target_path: Optional[str] = None) -> str:
        data = self.to_dict()
        model = TrajectoryModel.from_dict(data)
        saved_id = storage_manager.save_trajectory(model)
        if target_path:
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        return saved_id

    def load_trajectory_data(self, d: Dict[str, Any]) -> None:
        self.trajectory_id = d.get("trajectory_id", f"traj_{int(time.time())}")
        self.trajectory_name, self.target_type = d.get("name", "已加载轨迹"), d.get("target_type", "single")
        self.target_id, self.interpolation_mode = d.get("target_id", "A"), d.get("interpolation", "catmull_rom")
        self.max_velocity = float(d.get("max_velocity", 0.8))
        self.control_points = copy.deepcopy(d.get("control_points", []))
        self.sampled_points = copy.deepcopy(d.get("sampled_points", []))
        self._selected_pt_idx = -1
        if not self.sampled_points and self.control_points:
            self._recalculate_times_and_samples()
        self.update()


Canvas2D = InteractiveCanvas2D
