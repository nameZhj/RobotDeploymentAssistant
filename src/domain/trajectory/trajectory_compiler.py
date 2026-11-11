"""
@file: src/domain/trajectory/trajectory_compiler.py
@brief: 轨迹点云数据编译、向心样条/折线平滑插值与舞台草图笔管理器
@exports: TrajectoryCompiler, StageSketchManager, SketchStrokeManager, reverse_trajectory_points, trajectory_compiler
"""
import json
import math
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from src.domain.trajectory.spline_builder import SplineTrajectoryBuilder
from src.domain.trajectory.trajectory_asset import TrajectoryAsset, TrajectoryPoint


class StageSketchManager:
    """舞台自由手绘草图笔画管理器，提供笔画堆栈、单步撤销与清空"""

    def __init__(self) -> None:
        self.strokes: List[List[Tuple[float, float]]] = []
        self._curr: List[Tuple[float, float]] = []

    def begin_stroke(self) -> None:
        self._curr = []

    def add_point(self, x: float, y: float) -> None:
        self._curr.append((round(float(x), 4), round(float(y), 4)))

    def end_stroke(self) -> None:
        if len(self._curr) >= 2:
            self.strokes.append(self._curr)
        self._curr = []

    def add_stroke(self, stroke_pts: List[Tuple[float, float]]) -> None:
        if len(stroke_pts) >= 2:
            self.strokes.append([(round(float(x), 4), round(float(y), 4)) for x, y in stroke_pts])

    def undo_stroke(self) -> Optional[List[Tuple[float, float]]]:
        return self.strokes.pop() if self.strokes else None

    def clear_sketches(self) -> None:
        self.strokes.clear()
        self._curr = []

    def get_all_strokes(self) -> List[List[Tuple[float, float]]]:
        return [list(s) for s in self.strokes]


class TrajectoryCompiler:
    """轨迹解析、向心 Catmull-Rom/线性折线平滑插值与反转轨迹生成器"""

    @staticmethod
    def parse_trajectory_data(data_str: str) -> List[Tuple[float, float, float, float]]:
        if not data_str or not data_str.strip():
            return []
        pts: List[Tuple[float, float, float, float]] = []
        clean_str = data_str.strip()
        if clean_str.startswith("["):
            try:
                raw_json = json.loads(clean_str)
                if isinstance(raw_json, list):
                    for item in raw_json:
                        if isinstance(item, (list, tuple)) and len(item) >= 4:
                            pts.append((float(item[0]), float(item[1]), float(item[2]), float(item[3])))
                        elif isinstance(item, dict):
                            t = float(item.get("t", item.get("t_s", item.get("t_seconds", 0.0))))
                            x = float(item.get("x", item.get("x_m", 0.0)))
                            y = float(item.get("y", item.get("y_m", 0.0)))
                            yaw = float(item.get("yaw", item.get("yaw_deg", 0.0)))
                            pts.append((t, x, y, yaw))
                    if pts:
                        return pts
            except Exception:
                pass
        for line in clean_str.splitlines():
            tokens = [t.strip() for t in line.split(",") if t.strip()]
            if len(tokens) >= 4:
                pts.append((float(tokens[0]), float(tokens[1]), float(tokens[2]), float(tokens[3])))
        return pts

    @classmethod
    def compile_asset(
        cls,
        asset: TrajectoryAsset,
        duration_ms: int
    ) -> Tuple[List[Tuple[float, float, float, float]], float]:
        """
        将纯空间 TrajectoryAsset 依据 Clip 给定的 duration_ms 转换为旧编译器 4 元组序列。
        输出格式: (List[(t_seconds, x_m, y_m, yaw_deg)], duration_seconds)
        """
        if not isinstance(asset, TrajectoryAsset):
            raise TypeError(f"asset 必须为 TrajectoryAsset 类型，得到: {type(asset).__name__}")
        if not isinstance(duration_ms, int) or isinstance(duration_ms, bool):
            raise TypeError(f"duration_ms 必须为整型毫秒，得到: {type(duration_ms).__name__}")
        if duration_ms <= 0:
            raise ValueError(f"duration_ms 必须大于 0，实际为: {duration_ms}")
        if asset.length_m <= 0.0:
            raise ValueError(f"轨迹长度 length_m 必须大于 0，实际为: {asset.length_m}")
        if not asset.sampled_points:
            raise ValueError("TrajectoryAsset 的 sampled_points 不能为空")

        total_dur_s = round(duration_ms / 1000.0, 6)
        total_len, n = asset.length_m, len(asset.sampled_points)
        result: List[Tuple[float, float, float, float]] = []

        for i, pt in enumerate(asset.sampled_points):
            t_s = 0.0 if i == 0 else (total_dur_s if i == n - 1 else round(min(1.0, max(0.0, pt.s_m / total_len)) * total_dur_s, 6))
            if result and t_s < result[-1][0]:
                t_s = result[-1][0]
            result.append((max(0.0, t_s), float(pt.x_m), float(pt.y_m), float(pt.yaw_deg)))

        return result, total_dur_s

    @classmethod
    def to_trajectory_asset(
        cls,
        trajectory: Union[str, List[Tuple[float, float, float, float]]],
        trajectory_id: str = "legacy_traj",
        name: str = "历史兼容轨迹",
        coordinate_frame: str = "stage_world",
    ) -> TrajectoryAsset:
        """
        从历史轨迹元组/字符串构造纯空间 TrajectoryAsset。
        【信息损失说明】: 原始历史时间戳 t_seconds 将被丢弃（时间轴由未来 TrajectoryClip 提供），
        s_m 严格由空间欧氏距离累积生成，不得将 t_seconds 误当成 s_m。
        """
        pts = cls.parse_trajectory_data(trajectory) if isinstance(trajectory, str) else list(trajectory)
        if not pts:
            raise ValueError("旧轨迹数据不能为空")

        s_acc = 0.0
        s_list = [0.0]
        for i in range(1, len(pts)):
            s_acc += math.hypot(pts[i][1] - pts[i - 1][1], pts[i][2] - pts[i - 1][2])
            s_list.append(s_acc)

        sampled = [
            TrajectoryPoint(x_m=float(p[1]), y_m=float(p[2]), yaw_deg=float(p[3]), s_m=round(s_list[i], 6))
            for i, p in enumerate(pts)
        ]
        ctrl_pts = [(p[1], p[2]) for p in pts]
        if len(ctrl_pts) > 20:
            step = max(1, len(ctrl_pts) // 10)
            sparse_ctrl = [ctrl_pts[i] for i in range(0, len(ctrl_pts), step)]
            if sparse_ctrl[-1] != ctrl_pts[-1]:
                sparse_ctrl.append(ctrl_pts[-1])
            ctrl_pts = sparse_ctrl

        total_len = s_list[-1]
        return TrajectoryAsset(
            trajectory_id=trajectory_id,
            name=name,
            coordinate_frame=coordinate_frame,
            control_points=ctrl_pts,
            sampled_points=sampled,
            length_m=round(total_len, 6),
            recommended_speed_mps=0.5,
            spline_type="catmull_rom",
        )

    @staticmethod
    def serialize_trajectory_data(points: List[Tuple[float, float, float, float]]) -> str:
        lines = [f"{p[0]:.2f},{p[1]:.4f},{p[2]:.4f},{p[3]:.2f}" for p in points]
        return "\n".join(lines)

    @classmethod
    def compile_waypoints(
        cls,
        waypoints: List[Tuple[float, float]],
        mode: str = "uniform",
        max_acc: float = 1.5,
        v_max: float = 1.2,
        hold_direction: bool = False,
        hold_direction_yaw: float = 0.0,
        end_turn: bool = False,
        end_turn_yaw: float = 0.0
    ) -> Tuple[List[Tuple[float, float, float, float]], float]:
        if len(waypoints) < 2:
            single = waypoints[0] if waypoints else (0.0, 0.0)
            y = hold_direction_yaw if hold_direction else 0.0
            return [(0.0, single[0], single[1], y)], 0.0

        if mode.lower() == "uniform":
            curve, _, total_len = SplineTrajectoryBuilder.fit_spline_curve(waypoints)
        else:
            pts = np.array(waypoints, dtype=np.float32)
            dists = np.linalg.norm(np.diff(pts, axis=0), axis=1)
            total_len = float(np.sum(dists))
            steps = max(20, int(math.ceil(total_len / 0.02)))
            curve = np.linspace(pts[0], pts[-1], steps).astype(np.float32)

        duration = round(SplineTrajectoryBuilder.compute_trapezoidal_duration(total_len, v_max, max_acc), 2)
        n = len(curve)
        t_steps = np.linspace(0.0, duration, n)
        result: List[Tuple[float, float, float, float]] = []

        for i in range(n):
            x, y = float(curve[i, 0]), float(curve[i, 1])
            if hold_direction:
                yaw = hold_direction_yaw
            elif i < n - 1:
                dx = curve[i + 1, 0] - curve[i, 0]
                dy = curve[i + 1, 1] - curve[i, 1]
                yaw = math.degrees(math.atan2(dy, dx))
            else:
                yaw = result[-1][3] if result else 0.0

            if end_turn and i >= int(n * 0.8):
                alpha = (i - int(n * 0.8)) / max(1, n - 1 - int(n * 0.8))
                diff = (end_turn_yaw - yaw + 180.0) % 360.0 - 180.0
                yaw = (yaw + alpha * diff + 180.0) % 360.0 - 180.0

            result.append((float(t_steps[i]), x, y, float(yaw)))

        return result, duration

    @classmethod
    def reverse_trajectory(
        cls,
        trajectory: Union[str, List[Tuple[float, float, float, float]]]
    ) -> Union[str, List[Tuple[float, float, float, float]]]:
        is_str = isinstance(trajectory, str)
        pts = cls.parse_trajectory_data(trajectory) if is_str else list(trajectory)
        if len(pts) <= 1:
            return trajectory

        n = len(pts)
        total_dur = pts[-1][0]
        reversed_pts: List[Tuple[float, float, float, float]] = []

        for idx, orig in enumerate(reversed(pts)):
            t_rev = (idx / (n - 1)) * total_dur if n > 1 else 0.0
            x, y = orig[1], orig[2]
            yaw_rev = (orig[3] + 180.0 + 180.0) % 360.0 - 180.0
            reversed_pts.append((float(t_rev), x, y, float(yaw_rev)))

        return cls.serialize_trajectory_data(reversed_pts) if is_str else reversed_pts


trajectory_compiler = TrajectoryCompiler()
StageSketchManager = StageSketchManager
SketchStrokeManager = StageSketchManager
reverse_trajectory_points = TrajectoryCompiler.reverse_trajectory

