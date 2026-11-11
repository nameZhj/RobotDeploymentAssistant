"""
@file: src/domain/trajectory/group_trajectory_compiler.py
@brief: 机器人群组轨迹局部 Frenet 偏移至舞台全局坐标几何变换与独立弧长编译器
@exports: GroupMemberTrajectory, GroupTrajectoryCompiler, compile_group_trajectory
"""
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from src.domain.trajectory.group_trajectory import GroupTrajectory, GroupTrajectoryMember
from src.domain.trajectory.trajectory_asset import (
    ARC_LENGTH_TOLERANCE,
    TrajectoryAsset,
    TrajectoryPoint,
    normalize_angle_deg,
)


@dataclass
class GroupMemberTrajectory:
    """单个机器人成员在舞台全局坐标系下的展开轨迹结果。"""
    robot_id: str
    reference_trajectory_id: str
    coordinate_frame: str
    sampled_points: Tuple[TrajectoryPoint, ...]
    length_m: float

    def to_dict(self) -> Dict[str, Any]:
        """转换为标准字典格式。"""
        return {
            "robot_id": self.robot_id,
            "reference_trajectory_id": self.reference_trajectory_id,
            "coordinate_frame": self.coordinate_frame,
            "sampled_points": [p.to_dict() for p in self.sampled_points],
            "length_m": self.length_m,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroupMemberTrajectory":
        """从字典反序列化还原成员轨迹对象。"""
        if not isinstance(data, dict):
            raise TypeError(f"GroupMemberTrajectory 数据必须为 dict，得到: {type(data).__name__}")
        required_fields = ("robot_id", "reference_trajectory_id", "coordinate_frame", "sampled_points", "length_m")
        for k in required_fields:
            if k not in data:
                raise KeyError(f"缺少必需字段: '{k}'")

        raw_points = data["sampled_points"]
        if not isinstance(raw_points, (list, tuple)):
            raise TypeError(f"sampled_points 必须为列表或元组，得到: {type(raw_points).__name__}")

        pts: List[TrajectoryPoint] = []
        for idx, pt_data in enumerate(raw_points):
            if isinstance(pt_data, TrajectoryPoint):
                pts.append(pt_data)
            elif isinstance(pt_data, dict):
                pts.append(TrajectoryPoint.from_dict(pt_data))
            else:
                raise TypeError(f"sampled_points[{idx}] 必须为 TrajectoryPoint 或 dict，得到: {type(pt_data).__name__}")

        return cls(
            robot_id=str(data["robot_id"]),
            reference_trajectory_id=str(data["reference_trajectory_id"]),
            coordinate_frame=str(data["coordinate_frame"]),
            sampled_points=tuple(pts),
            length_m=float(data["length_m"]),
        )


class GroupTrajectoryCompiler:
    """机器人群组轨迹几何编译器：执行局部 Frenet 刚性旋转平移与独立弧长重新积分。"""

    @classmethod
    def compile(
        cls,
        group: GroupTrajectory,
        reference_asset: TrajectoryAsset,
    ) -> Tuple[GroupMemberTrajectory, ...]:
        """根据群组局部偏移与参考轨迹采样点，计算所有机器人的全局轨迹。"""
        cls._validate_inputs(group, reference_asset)

        results: List[GroupMemberTrajectory] = []
        for member in group.members:
            member_traj = cls._transform_member(member, reference_asset)
            results.append(member_traj)

        return tuple(results)

    @staticmethod
    def _validate_inputs(group: GroupTrajectory, reference_asset: TrajectoryAsset) -> None:
        """执行前置输入一致性及合法性严苛校验。"""
        if not isinstance(group, GroupTrajectory):
            raise TypeError(f"group 必须为 GroupTrajectory 实例，得到: {type(group).__name__}")
        if not isinstance(reference_asset, TrajectoryAsset):
            raise TypeError(f"reference_asset 必须为 TrajectoryAsset 实例，得到: {type(reference_asset).__name__}")

        if not group.is_committable():
            raise ValueError(
                f"群组轨迹尚未达到可提交门槛（至少包含 2 个不同机器人成员），当前成员数: {len(group.members)}"
            )

        if group.reference_trajectory_id != reference_asset.trajectory_id:
            raise ValueError(
                f"群组引用的参考轨迹 ID ('{group.reference_trajectory_id}') "
                f"与传入的参考素材 ID ('{reference_asset.trajectory_id}') 不一致"
            )

        if group.coordinate_frame != reference_asset.coordinate_frame:
            raise ValueError(
                f"坐标系不一致: 群组坐标系为 '{group.coordinate_frame}'，"
                f"参考素材坐标系为 '{reference_asset.coordinate_frame}'"
            )

        sampled = reference_asset.sampled_points
        if not sampled or len(sampled) < 2:
            raise ValueError(f"参考轨迹采样点不足，至少需要 2 个采样点，实际为: {len(sampled) if sampled else 0}")

        if reference_asset.length_m <= 0.0:
            raise ValueError(f"参考轨迹物理长度必须大于 0，实际为: {reference_asset.length_m}")

        prev_s = 0.0
        for idx, pt in enumerate(sampled):
            if not isinstance(pt, TrajectoryPoint):
                raise TypeError(f"参考轨迹采样点[{idx}] 必须为 TrajectoryPoint 实例")
            if not (math.isfinite(pt.x_m) and math.isfinite(pt.y_m) and math.isfinite(pt.yaw_deg) and math.isfinite(pt.s_m)):
                raise ValueError(f"参考轨迹采样点[{idx}] 包含 NaN 或 Infinity: {pt}")
            if pt.s_m < prev_s - 1e-9:
                raise ValueError(f"参考轨迹采样点弧长必须非递减: 点 {idx} 的 s_m ({pt.s_m}) 小于前点 ({prev_s})")
            prev_s = pt.s_m

    @staticmethod
    def _transform_member(
        member: GroupTrajectoryMember,
        reference_asset: TrajectoryAsset,
    ) -> GroupMemberTrajectory:
        """针对单个机器人成员计算全局采样点序列及物理累计弧长。"""
        dx = member.offset_x_m
        dy = member.offset_y_m
        delta_yaw = member.delta_yaw_deg

        transformed_points: List[TrajectoryPoint] = []
        accumulated_s = 0.0
        prev_x: float = 0.0
        prev_y: float = 0.0

        for idx, ref_pt in enumerate(reference_asset.sampled_points):
            theta_rad = math.radians(ref_pt.yaw_deg)
            cos_t = math.cos(theta_rad)
            sin_t = math.sin(theta_rad)

            # 局部 Frenet 坐标系到舞台全局坐标系刚性变换
            # dx 为前进切线方向，dy 为前进方向左侧法线方向
            x_world = ref_pt.x_m + dx * cos_t - dy * sin_t
            y_world = ref_pt.y_m + dx * sin_t + dy * cos_t
            yaw_world = normalize_angle_deg(ref_pt.yaw_deg + delta_yaw)

            if not (math.isfinite(x_world) and math.isfinite(y_world) and math.isfinite(yaw_world)):
                raise ValueError(f"变换后坐标或角度包含非有限数: x={x_world}, y={y_world}, yaw={yaw_world}")

            if idx == 0:
                accumulated_s = 0.0
            else:
                dist = math.hypot(x_world - prev_x, y_world - prev_y)
                accumulated_s += dist

            prev_x = x_world
            prev_y = y_world

            transformed_points.append(
                TrajectoryPoint(
                    x_m=x_world,
                    y_m=y_world,
                    yaw_deg=yaw_world,
                    s_m=accumulated_s,
                )
            )

        total_length_m = accumulated_s

        return GroupMemberTrajectory(
            robot_id=member.robot_id,
            reference_trajectory_id=reference_asset.trajectory_id,
            coordinate_frame=reference_asset.coordinate_frame,
            sampled_points=tuple(transformed_points),
            length_m=total_length_m,
        )


def compile_group_trajectory(
    group: GroupTrajectory,
    reference_asset: TrajectoryAsset,
) -> Tuple[GroupMemberTrajectory, ...]:
    """便捷计算函数：将群组轨迹及参考素材编译为每个机器人的全局轨迹序列。"""
    return GroupTrajectoryCompiler.compile(group, reference_asset)
