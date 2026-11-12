"""
@file: src/domain/trajectory/group_trajectory.py
@brief: 机器人群组轨迹纯领域模型、成员偏移配置与数据契约
@exports: GroupTrajectoryMember, GroupTrajectory
"""
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.domain.trajectory.trajectory_asset import normalize_angle_deg


def _validate_finite_float(val: Any, field_name: str) -> float:
    """严格校验实数浮点数类型及有限数约束（拒绝 bool、str、NaN、Inf）。"""
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise TypeError(f"字段 '{field_name}' 必须为浮点数或整数，不支持: {type(val).__name__} ({val!r})")
    f_val = float(val)
    if not math.isfinite(f_val):
        raise ValueError(f"字段 '{field_name}' 禁止为 NaN 或 Infinity: {f_val}")
    return f_val


def _validate_non_empty_str(val: Any, field_name: str) -> str:
    """校验非空且非纯空白字符串。"""
    if not isinstance(val, str):
        raise TypeError(f"字段 '{field_name}' 必须为字符串，得到: {type(val).__name__}")
    stripped = val.strip()
    if not stripped:
        raise ValueError(f"字段 '{field_name}' 必须为非空且非纯空白字符串")
    return stripped


@dataclass
class GroupTrajectoryMember:
    """群组轨迹机器人成员配置（包含机器人唯一标识及相对参考轨迹切线的局部偏移）。"""
    robot_id: str
    offset_x_m: float = 0.0
    offset_y_m: float = 0.0
    delta_yaw_deg: float = 0.0

    def __post_init__(self) -> None:
        self.robot_id = _validate_non_empty_str(self.robot_id, "robot_id")
        self.offset_x_m = _validate_finite_float(self.offset_x_m, "offset_x_m")
        self.offset_y_m = _validate_finite_float(self.offset_y_m, "offset_y_m")
        raw_yaw = _validate_finite_float(self.delta_yaw_deg, "delta_yaw_deg")
        self.delta_yaw_deg = normalize_angle_deg(raw_yaw)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为标准 Python 字典。"""
        return {
            "robot_id": self.robot_id,
            "offset_x_m": self.offset_x_m,
            "offset_y_m": self.offset_y_m,
            "delta_yaw_deg": self.delta_yaw_deg,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroupTrajectoryMember":
        """从字典反序列化成员配置。"""
        if not isinstance(data, dict):
            raise TypeError(f"GroupTrajectoryMember 数据必须为 dict，得到: {type(data).__name__}")
        required_fields = ("robot_id", "offset_x_m", "offset_y_m", "delta_yaw_deg")
        for k in required_fields:
            if k not in data:
                raise KeyError(f"缺少必需字段: '{k}'")
        return cls(
            robot_id=data["robot_id"],
            offset_x_m=data["offset_x_m"],
            offset_y_m=data["offset_y_m"],
            delta_yaw_deg=data["delta_yaw_deg"],
        )


@dataclass
class GroupTrajectory:
    """机器人群组轨迹领域模型（纯空间素材引用与多机成员局部偏移配置，与时间轴解耦）。"""
    group_trajectory_id: str
    name: str
    reference_trajectory_id: str
    coordinate_frame: str = "stage_world"
    members: Tuple[GroupTrajectoryMember, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        self.validate(for_submission=False)

    def validate(self, for_submission: bool = False) -> None:
        """执行字段有效性、成员唯一性及提交门槛校验。"""
        self.group_trajectory_id = _validate_non_empty_str(
            self.group_trajectory_id, "group_trajectory_id"
        )
        self.name = _validate_non_empty_str(self.name, "name")
        self.reference_trajectory_id = _validate_non_empty_str(
            self.reference_trajectory_id, "reference_trajectory_id"
        )
        self.coordinate_frame = _validate_non_empty_str(
            self.coordinate_frame, "coordinate_frame"
        )

        if not isinstance(self.members, (list, tuple)):
            raise TypeError(f"members 必须为列表或元组，得到: {type(self.members).__name__}")

        seen_robot_ids = set()
        validated_members: List[GroupTrajectoryMember] = []
        for idx, m in enumerate(self.members):
            if not isinstance(m, GroupTrajectoryMember):
                raise TypeError(
                    f"members[{idx}] 必须为 GroupTrajectoryMember 实例，得到: {type(m).__name__}"
                )
            if m.robot_id in seen_robot_ids:
                raise ValueError(f"群组成员 robot_id 必须唯一，发现重复: '{m.robot_id}'")
            seen_robot_ids.add(m.robot_id)
            validated_members.append(m)

        self.members = tuple(validated_members)

        if for_submission and len(self.members) < 2:
            raise ValueError(
                f"群组轨迹提交至少需要包含 2 个不同机器人成员，当前仅有 {len(self.members)} 个"
            )

    def is_draft(self) -> bool:
        """判断是否为有效草稿（基础元数据完整即为草稿）。"""
        return bool(self.group_trajectory_id and self.name and self.reference_trajectory_id)

    def is_committable(self) -> bool:
        """判断是否满足群组轨迹可提交门槛（至少 2 个不同机器人成员）。"""
        return self.is_draft() and len(self.members) >= 2

    def is_submittable(self) -> bool:
        """别名：判断是否满足可提交门槛。"""
        return self.is_committable()

    def validate_for_submission(self) -> None:
        """严格校验是否达到可提交状态，未满足时抛出 ValueError。"""
        self.validate(for_submission=True)

    @property
    def robot_ids(self) -> Tuple[str, ...]:
        """获取所有成员的 robot_id 序列（保持原序）。"""
        return tuple(m.robot_id for m in self.members)

    def get_member(self, robot_id: str) -> Optional[GroupTrajectoryMember]:
        """按 robot_id 获取指定成员配置。"""
        for m in self.members:
            if m.robot_id == robot_id:
                return m
        return None

    def to_dict(self) -> Dict[str, Any]:
        """序列化为标准 Python 字典。"""
        return {
            "group_trajectory_id": self.group_trajectory_id,
            "name": self.name,
            "reference_trajectory_id": self.reference_trajectory_id,
            "coordinate_frame": self.coordinate_frame,
            "members": [m.to_dict() for m in self.members],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroupTrajectory":
        """从字典反序列化群组轨迹对象并执行数据校验。"""
        if not isinstance(data, dict):
            raise TypeError(f"GroupTrajectory 数据必须为 dict，得到: {type(data).__name__}")
        required_fields = ("group_trajectory_id", "name", "reference_trajectory_id", "members")
        for k in required_fields:
            if k not in data:
                raise KeyError(f"缺少必需字段: '{k}'")

        raw_members = data["members"]
        if not isinstance(raw_members, (list, tuple)):
            raise TypeError(f"members 必须为列表或元组，得到: {type(raw_members).__name__}")

        members_list: List[GroupTrajectoryMember] = []
        for idx, m_data in enumerate(raw_members):
            if isinstance(m_data, GroupTrajectoryMember):
                members_list.append(m_data)
            elif isinstance(m_data, dict):
                members_list.append(GroupTrajectoryMember.from_dict(m_data))
            else:
                raise TypeError(
                    f"members[{idx}] 必须为 GroupTrajectoryMember 实例或 dict，得到: {type(m_data).__name__}"
                )

        return cls(
            group_trajectory_id=data["group_trajectory_id"],
            name=data["name"],
            reference_trajectory_id=data["reference_trajectory_id"],
            coordinate_frame=data.get("coordinate_frame", "stage_world"),
            members=tuple(members_list),
        )
