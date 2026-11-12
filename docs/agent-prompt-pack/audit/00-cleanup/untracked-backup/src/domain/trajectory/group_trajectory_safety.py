"""
@file: src/domain/trajectory/group_trajectory_safety.py
@brief: 机器人群组轨迹几何安全检测与舞台边界校验器
@exports: BoundaryViolation, PairwiseClearance, GroupTrajectorySafetyReport, GroupTrajectorySafetyValidator, validate_group_trajectory_safety
"""
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.domain.trajectory.group_trajectory_compiler import GroupMemberTrajectory
from src.domain.trajectory.trajectory_asset import TrajectoryPoint

DEFAULT_STAGE_BOUNDS: Tuple[float, float, float, float] = (-50.0, 50.0, -50.0, 50.0)
DEFAULT_REQUIRED_CLEARANCE_M: float = 0.6


@dataclass(frozen=True)
class BoundaryViolation:
    """机器人轨迹点超出舞台工作区域记录。"""
    robot_id: str
    point_index: int
    x_m: float
    y_m: float
    boundary: str

    def to_dict(self) -> Dict[str, Any]:
        return {"robot_id": self.robot_id, "point_index": self.point_index, "x_m": self.x_m, "y_m": self.y_m, "boundary": self.boundary}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BoundaryViolation":
        return cls(str(data["robot_id"]), int(data["point_index"]), float(data["x_m"]), float(data["y_m"]), str(data["boundary"]))


@dataclass(frozen=True)
class PairwiseClearance:
    """两台机器人分段线性中心轨迹间的最短欧氏间距及安全判定。"""
    robot_id_a: str
    robot_id_b: str
    min_distance_m: float
    required_clearance_m: float
    is_clear: bool
    segment_index_a: int
    segment_index_b: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "robot_id_a": self.robot_id_a, "robot_id_b": self.robot_id_b,
            "min_distance_m": self.min_distance_m, "required_clearance_m": self.required_clearance_m,
            "is_clear": self.is_clear, "segment_index_a": self.segment_index_a, "segment_index_b": self.segment_index_b,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PairwiseClearance":
        return cls(
            str(data["robot_id_a"]), str(data["robot_id_b"]), float(data["min_distance_m"]),
            float(data["required_clearance_m"]), bool(data["is_clear"]), int(data["segment_index_a"]), int(data["segment_index_b"]),
        )


@dataclass(frozen=True)
class GroupTrajectorySafetyReport:
    """群组轨迹静态空间几何安全筛查报告。"""
    is_safe: bool
    boundary_violations: Tuple[BoundaryViolation, ...]
    pairwise_clearances: Tuple[PairwiseClearance, ...]
    violation_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_safe": self.is_safe,
            "boundary_violations": [v.to_dict() for v in self.boundary_violations],
            "pairwise_clearances": [c.to_dict() for c in self.pairwise_clearances],
            "violation_count": self.violation_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroupTrajectorySafetyReport":
        return cls(
            bool(data["is_safe"]),
            tuple(BoundaryViolation.from_dict(v) for v in data.get("boundary_violations", ())),
            tuple(PairwiseClearance.from_dict(c) for c in data.get("pairwise_clearances", ())),
            int(data["violation_count"]),
        )


def _ccw(a: Tuple[float, float], b: Tuple[float, float], c: Tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_seg(p: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]) -> bool:
    eps = 1e-9
    return min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps and min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps


def _segments_intersect(p0: Tuple[float, float], p1: Tuple[float, float], q0: Tuple[float, float], q1: Tuple[float, float]) -> bool:
    d1, d2, d3, d4 = _ccw(p0, p1, q0), _ccw(p0, p1, q1), _ccw(q0, q1, p0), _ccw(q0, q1, p1)
    if ((d1 > 1e-9 and d2 < -1e-9) or (d1 < -1e-9 and d2 > 1e-9)) and ((d3 > 1e-9 and d4 < -1e-9) or (d3 < -1e-9 and d4 > 1e-9)):
        return True
    return any((abs(d) <= 1e-9 and _on_seg(pt, sa, sb)) for d, pt, sa, sb in [
        (d1, q0, p0, p1), (d2, q1, p0, p1), (d3, p0, q0, q1), (d4, p1, q0, q1)
    ])


def _pt_to_seg_dist(p: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]) -> float:
    ab_x, ab_y = b[0] - a[0], b[1] - a[1]
    l2 = ab_x * ab_x + ab_y * ab_y
    if l2 < 1e-14:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ab_x + (p[1] - a[1]) * ab_y) / l2))
    return math.hypot(p[0] - (a[0] + t * ab_x), p[1] - (a[1] + t * ab_y))


def _seg_to_seg_dist(p0: Tuple[float, float], p1: Tuple[float, float], q0: Tuple[float, float], q1: Tuple[float, float]) -> float:
    if _segments_intersect(p0, p1, q0, q1):
        return 0.0
    return min(_pt_to_seg_dist(p0, q0, q1), _pt_to_seg_dist(p1, q0, q1), _pt_to_seg_dist(q0, p0, p1), _pt_to_seg_dist(q1, p0, p1))


class GroupTrajectorySafetyValidator:
    """群组轨迹几何安全校验器：执行舞台边界合规性与轨迹中心线最短距离两两筛查。"""

    @classmethod
    def validate(
        cls,
        trajectories: Sequence[GroupMemberTrajectory],
        required_clearance_m: float = DEFAULT_REQUIRED_CLEARANCE_M,
        stage_bounds: Optional[Tuple[float, float, float, float]] = None,
    ) -> GroupTrajectorySafetyReport:
        bounds = stage_bounds if stage_bounds is not None else DEFAULT_STAGE_BOUNDS
        cls._validate_inputs(trajectories, required_clearance_m, bounds)

        b_violations = cls._check_boundary_violations(trajectories, bounds)
        p_clearances = cls._check_pairwise_clearances(trajectories, required_clearance_m)

        total_violations = len(b_violations) + sum(1 for c in p_clearances if not c.is_clear)
        return GroupTrajectorySafetyReport(
            is_safe=(total_violations == 0),
            boundary_violations=tuple(b_violations),
            pairwise_clearances=tuple(p_clearances),
            violation_count=total_violations,
        )

    @staticmethod
    def _validate_inputs(
        trajectories: Sequence[GroupMemberTrajectory], required_clearance_m: float, bounds: Tuple[float, float, float, float]
    ) -> None:
        if not isinstance(trajectories, (list, tuple)) or len(trajectories) < 2:
            raise ValueError(f"群组轨迹安全校验至少需要包含 2 个机器人成员，得到: {len(trajectories) if isinstance(trajectories, (list, tuple)) else 0}")
        if isinstance(required_clearance_m, bool) or not isinstance(required_clearance_m, (int, float)):
            raise TypeError("安全距离阈值 required_clearance_m 必须为实数浮点数")
        f_clear = float(required_clearance_m)
        if not math.isfinite(f_clear) or f_clear < 0.0:
            raise ValueError(f"安全距离阈值不能为负数或非有限数: {f_clear}")

        if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
            raise TypeError("舞台边界 stage_bounds 必须为 (x_min, x_max, y_min, y_max) 四元组")
        x_min, x_max, y_min, y_max = (float(v) for v in bounds)
        if not (math.isfinite(x_min) and math.isfinite(x_max) and math.isfinite(y_min) and math.isfinite(y_max)):
            raise ValueError("舞台边界必须为有效有限数")
        if x_min >= x_max or y_min >= y_max:
            raise ValueError(f"舞台边界无效: 最小值必须严格小于最大值: {bounds}")

        seen_rids = set()
        first_frame = trajectories[0].coordinate_frame
        for idx, t in enumerate(trajectories):
            if not isinstance(t, GroupMemberTrajectory):
                raise TypeError(f"trajectories[{idx}] 必须为 GroupMemberTrajectory 实例")
            if not t.robot_id or not t.robot_id.strip():
                raise ValueError(f"trajectories[{idx}] 的 robot_id 不能为空")
            if t.robot_id in seen_rids:
                raise ValueError(f"检测到重复的 robot_id: '{t.robot_id}'")
            seen_rids.add(t.robot_id)
            if t.coordinate_frame != first_frame:
                raise ValueError(f"成员轨迹坐标系不一致: '{t.coordinate_frame}' vs '{first_frame}'")
            if not t.sampled_points or len(t.sampled_points) < 2:
                raise ValueError(f"机器人 '{t.robot_id}' 采样点不足，至少需要 2 个采样点")

            prev_s = 0.0
            for p_idx, pt in enumerate(t.sampled_points):
                if not isinstance(pt, TrajectoryPoint):
                    raise TypeError(f"点位必须为 TrajectoryPoint，得到: {type(pt).__name__}")
                if not (math.isfinite(pt.x_m) and math.isfinite(pt.y_m) and math.isfinite(pt.yaw_deg) and math.isfinite(pt.s_m)):
                    raise ValueError(f"点位包含 NaN 或 Infinity: {pt}")
                if pt.s_m < prev_s - 1e-9:
                    raise ValueError(f"采样点弧长必须非递减: 点 {p_idx} 的 s_m ({pt.s_m}) < {prev_s}")
                prev_s = pt.s_m

    @staticmethod
    def _check_boundary_violations(trajectories: Sequence[GroupMemberTrajectory], bounds: Tuple[float, float, float, float]) -> List[BoundaryViolation]:
        x_min, x_max, y_min, y_max = bounds
        violations: List[BoundaryViolation] = []
        for t in trajectories:
            for idx, pt in enumerate(t.sampled_points):
                if pt.x_m < x_min:
                    violations.append(BoundaryViolation(t.robot_id, idx, pt.x_m, pt.y_m, "x_min"))
                elif pt.x_m > x_max:
                    violations.append(BoundaryViolation(t.robot_id, idx, pt.x_m, pt.y_m, "x_max"))
                if pt.y_m < y_min:
                    violations.append(BoundaryViolation(t.robot_id, idx, pt.x_m, pt.y_m, "y_min"))
                elif pt.y_m > y_max:
                    violations.append(BoundaryViolation(t.robot_id, idx, pt.x_m, pt.y_m, "y_max"))
        return violations

    @staticmethod
    def _check_pairwise_clearances(trajectories: Sequence[GroupMemberTrajectory], required_clearance_m: float) -> List[PairwiseClearance]:
        n = len(trajectories)
        results: List[PairwiseClearance] = []
        for i in range(n):
            for j in range(i + 1, n):
                ta, tb = trajectories[i], trajectories[j]
                min_dist, seg_a, seg_b = GroupTrajectorySafetyValidator._min_distance(ta, tb)
                results.append(PairwiseClearance(
                    robot_id_a=ta.robot_id, robot_id_b=tb.robot_id, min_distance_m=min_dist,
                    required_clearance_m=required_clearance_m, is_clear=(min_dist >= required_clearance_m),
                    segment_index_a=seg_a, segment_index_b=seg_b,
                ))
        return results

    @staticmethod
    def _min_distance(ta: GroupMemberTrajectory, tb: GroupMemberTrajectory) -> Tuple[float, int, int]:
        pts_a, pts_b = ta.sampled_points, tb.sampled_points
        best_dist, best_seg_a, best_seg_b = float("inf"), 0, 0
        for i in range(len(pts_a) - 1):
            p0, p1 = (pts_a[i].x_m, pts_a[i].y_m), (pts_a[i + 1].x_m, pts_a[i + 1].y_m)
            for j in range(len(pts_b) - 1):
                q0, q1 = (pts_b[j].x_m, pts_b[j].y_m), (pts_b[j + 1].x_m, pts_b[j + 1].y_m)
                d = _seg_to_seg_dist(p0, p1, q0, q1)
                if d < best_dist:
                    best_dist, best_seg_a, best_seg_b = d, i, j
                    if best_dist <= 1e-12:
                        return 0.0, best_seg_a, best_seg_b
        return best_dist, best_seg_a, best_seg_b


def validate_group_trajectory_safety(
    trajectories: Sequence[GroupMemberTrajectory],
    required_clearance_m: float = DEFAULT_REQUIRED_CLEARANCE_M,
    stage_bounds: Optional[Tuple[float, float, float, float]] = None,
) -> GroupTrajectorySafetyReport:
    """便捷调用入口：校验多机器人展开轨迹的舞台边界与分段线性中心线两两间距。"""
    return GroupTrajectorySafetyValidator.validate(trajectories, required_clearance_m, stage_bounds)
