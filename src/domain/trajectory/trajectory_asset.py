"""
@file: src/domain/trajectory/trajectory_asset.py
@brief: 统一轨迹空间资产领域模型与采样点数据结构
@exports: TrajectoryPoint, TrajectoryAsset, normalize_angle_deg, ARC_LENGTH_TOLERANCE
"""
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Tuple, Union

ARC_LENGTH_TOLERANCE: float = 1e-3


def normalize_angle_deg(angle_deg: float) -> float:
    """将角度规范化到 [-180.0, 180.0) 区间。"""
    if not math.isfinite(angle_deg):
        raise ValueError(f"角度值必须为有效实数: {angle_deg}")
    normalized = ((angle_deg + 180.0) % 360.0) - 180.0
    return 0.0 if abs(normalized) < 1e-12 else normalized


def _validate_finite_float(val: Any, field_name: str, allow_negative: bool = True) -> float:
    """严格校验实数浮点数类型及非负约束。"""
    if isinstance(val, (bool, str)) or not isinstance(val, (int, float)):
        raise TypeError(f"字段 '{field_name}' 必须为浮点数或整数，不支持: {type(val).__name__} ({val!r})")
    f_val = float(val)
    if not math.isfinite(f_val):
        raise ValueError(f"字段 '{field_name}' 禁止为 NaN 或 Infinity: {f_val}")
    if not allow_negative and f_val < 0.0:
        raise ValueError(f"字段 '{field_name}' 禁止为负数: {f_val}")
    return f_val


@dataclass
class TrajectoryPoint:
    """空间轨迹密集采样点（包含位置、偏航角及累积弧长）。"""
    x_m: float
    y_m: float
    yaw_deg: float
    s_m: float

    def __post_init__(self) -> None:
        self.x_m = _validate_finite_float(self.x_m, "x_m", allow_negative=True)
        self.y_m = _validate_finite_float(self.y_m, "y_m", allow_negative=True)
        raw_yaw = _validate_finite_float(self.yaw_deg, "yaw_deg", allow_negative=True)
        self.yaw_deg = normalize_angle_deg(raw_yaw)
        self.s_m = _validate_finite_float(self.s_m, "s_m", allow_negative=False)

    def to_dict(self) -> Dict[str, float]:
        return {
            "x_m": self.x_m,
            "y_m": self.y_m,
            "yaw_deg": self.yaw_deg,
            "yaw_rad": self.yaw_rad,
            "s_m": self.s_m,
            "t_ms": self.t_ms,
        }

    @property
    def yaw_rad(self) -> float:
        return math.radians(self.yaw_deg)

    @property
    def t_ms(self) -> int:
        return max(0, int(round((self.s_m / 1.0) * 1000.0)))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrajectoryPoint":
        if not isinstance(data, dict):
            raise TypeError(f"Point 数据必须为 dict，得到: {type(data).__name__}")
        return cls(
            x_m=data["x_m"],
            y_m=data["y_m"],
            yaw_deg=data["yaw_deg"],
            s_m=data["s_m"],
        )


@dataclass
class TrajectoryAsset:
    """纯空间轨迹素材领域模型（与时间轴解耦，支持多机多时段共享引用）。"""
    trajectory_id: str
    name: str
    coordinate_frame: str = "stage_world"
    control_points: List[Tuple[float, float]] = field(default_factory=list)
    sampled_points: List[TrajectoryPoint] = field(default_factory=list)
    length_m: float = 0.0
    recommended_speed_mps: float = 0.5
    spline_type: str = "catmull_rom"
    project_id: str = ""
    map_id: str = ""
    target_type: str = "SINGLE_ROBOT"
    target_id: str = ""
    version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """执行全字段类型校验及空间几何一致性规则校验。"""
        if not isinstance(self.trajectory_id, str) or not self.trajectory_id.strip():
            raise ValueError("trajectory_id 必须为非空字符串")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name 必须为非空字符串")
        if not isinstance(self.coordinate_frame, str) or not self.coordinate_frame.strip():
            raise ValueError("coordinate_frame 必须为非空字符串")
        if not isinstance(self.spline_type, str) or not self.spline_type.strip():
            raise ValueError("spline_type 必须为非空字符串")

        self.length_m = _validate_finite_float(self.length_m, "length_m", allow_negative=False)
        self.recommended_speed_mps = _validate_finite_float(
            self.recommended_speed_mps, "recommended_speed_mps", allow_negative=False
        )

        self._validate_control_points()
        self._validate_sampled_points()

    def _validate_control_points(self) -> None:
        """校验控制点列表格式与数值有效性（草稿允许至少 1 点，严禁空列表）。"""
        if not isinstance(self.control_points, (list, tuple)):
            raise TypeError(f"control_points 必须为列表或元组序列，得到: {type(self.control_points).__name__}")
        if len(self.control_points) < 1:
            raise ValueError("control_points 不能为空，至少需包含 1 个控制点")

        validated_ctrl: List[Tuple[float, float]] = []
        for idx, pt in enumerate(self.control_points):
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                x = _validate_finite_float(pt[0], f"control_points[{idx}][0]")
                y = _validate_finite_float(pt[1], f"control_points[{idx}][1]")
                validated_ctrl.append((x, y))
            else:
                raise TypeError(f"control_points[{idx}] 必须为包含 (x, y) 的二元组，得到: {pt!r}")
        self.control_points = validated_ctrl

    def _validate_sampled_points(self) -> None:
        """校验采样点序列单调性、起点弧长及全长一致性。"""
        if not isinstance(self.sampled_points, list):
            raise TypeError(f"sampled_points 必须为 List[TrajectoryPoint]，得到: {type(self.sampled_points).__name__}")
        if not self.sampled_points:
            return

        first_s = self.sampled_points[0].s_m
        if abs(first_s) > ARC_LENGTH_TOLERANCE:
            raise ValueError(f"采样点起点弧长 s_m 必须为 0.0，实际为: {first_s:.6f}")

        prev_s = 0.0
        for idx, pt in enumerate(self.sampled_points):
            if not isinstance(pt, TrajectoryPoint):
                raise TypeError(f"sampled_points[{idx}] 必须为 TrajectoryPoint 实例")
            if pt.s_m < prev_s - 1e-9:
                raise ValueError(
                    f"采样点弧长 s_m 必须非递减: 点 {idx} 的 s_m ({pt.s_m:.6f}) 小于前一点 ({prev_s:.6f})"
                )
            prev_s = pt.s_m

        last_s = self.sampled_points[-1].s_m
        if abs(last_s - self.length_m) > ARC_LENGTH_TOLERANCE:
            raise ValueError(
                f"轨迹总长 length_m ({self.length_m:.6f}) 与最终采样点弧长 ({last_s:.6f}) 不一致"
            )

    def is_draft(self) -> bool:
        """是否为草稿状态（至少有 1 个控制点即为草稿）。"""
        return len(self.control_points) >= 1

    def is_committable(self) -> bool:
        """是否达到可确认/可提交运动轨迹门槛（至少 2 个控制点、2 个采样点且长度大于 0）。"""
        if len(self.control_points) < 2:
            return False
        if len(self.sampled_points) < 2:
            return False
        if self.length_m <= 0.0:
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        """将轨迹素材转换为标准纯字典（无外部框架依赖）。"""
        return {
            "trajectory_id": self.trajectory_id,
            "name": self.name,
            "coordinate_frame": self.coordinate_frame,
            "control_points": [list(pt) for pt in self.control_points],
            "sampled_points": [pt.to_dict() for pt in self.sampled_points],
            "length_m": self.length_m,
            "recommended_speed_mps": self.recommended_speed_mps,
            "spline_type": self.spline_type,
            "project_id": self.project_id,
            "map_id": self.map_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrajectoryAsset":
        """从字典还原轨迹素材并执行严格合法性校验。"""
        if not isinstance(data, dict):
            raise TypeError(f"TrajectoryAsset 数据必须为 dict，得到: {type(data).__name__}")

        raw_sampled = data.get("sampled_points", [])
        sampled = [TrajectoryPoint.from_dict(p) if isinstance(p, dict) else p for p in raw_sampled]
        raw_ctrl = data.get("control_points", [])
        ctrl = [tuple(p[:2]) if isinstance(p, (list, tuple)) else p for p in raw_ctrl]

        return cls(
            trajectory_id=str(data.get("trajectory_id", "")),
            name=str(data.get("name", "")),
            coordinate_frame=str(data.get("coordinate_frame", "stage_world")),
            control_points=ctrl,
            sampled_points=sampled,
            length_m=float(data.get("length_m", 0.0)),
            recommended_speed_mps=float(data.get("recommended_speed_mps", 0.5)),
            spline_type=str(data.get("spline_type", "catmull_rom")),
            project_id=str(data.get("project_id", "")),
            map_id=str(data.get("map_id", "")),
            target_type=str(data.get("target_type", "SINGLE_ROBOT")),
            target_id=str(data.get("target_id", "")),
            version=int(data.get("version", 1)),
        )
