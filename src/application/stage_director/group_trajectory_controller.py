"""
@file: src/application/stage_director/group_trajectory_controller.py
@brief: 机器人群组轨迹控制器：参考轨迹选择、成员增删、局部偏移编辑、阵型集成、编译安全与存储协调
@exports: GroupTrajectoryController
"""
import logging
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.domain.trajectory.formation_matrix_planner import FormationMatrixPlanner
from src.domain.trajectory.group_trajectory import GroupTrajectory, GroupTrajectoryMember
from src.domain.trajectory.group_trajectory_compiler import (
    GroupMemberTrajectory,
    compile_group_trajectory,
)
from src.domain.trajectory.group_trajectory_safety import (
    GroupTrajectorySafetyReport,
    validate_group_trajectory_safety,
)
from src.domain.trajectory.trajectory_asset import TrajectoryAsset, normalize_angle_deg
from src.infrastructure.storage.choreo_sqlite_store import ChoreoSqliteStore
from src.infrastructure.storage.group_trajectory_sqlite_adapter import (
    GroupTrajectorySqliteAdapter,
)
from src.infrastructure.storage.trajectory_sqlite_adapter import (
    TrajectorySqliteAdapter,
)

logger = logging.getLogger("GroupTrajectoryController")


class GroupTrajectoryController:
    """协调参考轨迹加载、成员编辑、阵型规划算法、群组几何编译及安全校验流水线。"""

    def __init__(self, store: Optional[Any] = None) -> None:
        self.store = store or ChoreoSqliteStore()
        self._available_references: List[TrajectoryAsset] = []
        self._current_reference: Optional[TrajectoryAsset] = None
        self._members: List[GroupTrajectoryMember] = []
        self._last_compiled_trajectories: Tuple[GroupMemberTrajectory, ...] = ()
        self._last_safety_report: Optional[GroupTrajectorySafetyReport] = None
        self._active_group: Optional[GroupTrajectory] = None

    # --- 1. 参考轨迹管理 (04C-D2) ---

    def load_available_references(self) -> List[TrajectoryAsset]:
        """从主数据库中加载所有可用的单机器人轨迹素材。"""
        try:
            self._available_references = TrajectorySqliteAdapter.list_assets(self.store)
        except Exception as e:
            logger.error(f"加载参考轨迹素材失败: {e}", exc_info=True)
            self._available_references = []
        return self._available_references

    def select_reference_trajectory(self, trajectory_id: str) -> Optional[TrajectoryAsset]:
        """选中指定 ID 的参考轨迹并置为当前群组基准。"""
        tid = str(trajectory_id).strip()
        asset = next((a for a in self._available_references if str(a.trajectory_id) == tid), None)
        if not asset:
            asset = TrajectorySqliteAdapter.load_asset(self.store, tid)
        self._current_reference = asset
        return self._current_reference

    def set_reference_asset(self, asset: Optional[TrajectoryAsset]) -> None:
        """支持直接设置参考轨迹实例（用于测试或画布直接传值）。"""
        self._current_reference = asset

    def get_reference_trajectory(self) -> Optional[TrajectoryAsset]:
        """获取当前选中的参考轨迹。"""
        return self._current_reference

    # --- 2. 群组成员与局部偏移管理 (04C-D2) ---

    def add_member(
        self,
        robot_id: str,
        offset_x_m: float = 0.0,
        offset_y_m: float = 0.0,
        delta_yaw_deg: float = 0.0,
    ) -> GroupTrajectoryMember:
        """向群组添加新机器人成员。严格阻止重复添加相同 robot_id。"""
        rid = str(robot_id).strip()
        if not rid:
            raise ValueError("机器人 ID 不能为空")
        if any(m.robot_id == rid for m in self._members):
            raise ValueError(f"机器人 '{rid}' 已存在于成员列表中，禁止重复添加")

        member = GroupTrajectoryMember(
            robot_id=rid,
            offset_x_m=offset_x_m,
            offset_y_m=offset_y_m,
            delta_yaw_deg=delta_yaw_deg,
        )
        self._members.append(member)
        return member

    def remove_member(self, robot_id: str) -> bool:
        """从成员列表中移除指定机器人。"""
        rid = str(robot_id).strip()
        before_len = len(self._members)
        self._members = [m for m in self._members if m.robot_id != rid]
        return len(self._members) < before_len

    def update_member_offset(
        self,
        robot_id: str,
        offset_x_m: float,
        offset_y_m: float,
        delta_yaw_deg: float,
    ) -> GroupTrajectoryMember:
        """更新指定机器人的局部 Frenet 偏移量与航向偏角。"""
        rid = str(robot_id).strip()
        for idx, m in enumerate(self._members):
            if m.robot_id == rid:
                updated = GroupTrajectoryMember(
                    robot_id=rid,
                    offset_x_m=offset_x_m,
                    offset_y_m=offset_y_m,
                    delta_yaw_deg=delta_yaw_deg,
                )
                self._members[idx] = updated
                return updated
        raise KeyError(f"未找到机器人 '{rid}'，无法更新偏移")

    def get_members(self) -> List[GroupTrajectoryMember]:
        """获取当前所有成员配置。"""
        return list(self._members)

    def clear_members(self) -> None:
        """清空成员列表。"""
        self._members.clear()

    # --- 3. 阵型规划集成 (04C-D3) ---

    def _apply_calculated_poses(self, poses: List[Tuple[float, float, float]]) -> None:
        """将生成的相对姿态列表赋值给当前成员。"""
        for idx, (px, py, pyaw) in enumerate(poses):
            if idx < len(self._members):
                self._members[idx] = GroupTrajectoryMember(
                    robot_id=self._members[idx].robot_id,
                    offset_x_m=round(px, 3),
                    offset_y_m=round(py, 3),
                    delta_yaw_deg=normalize_angle_deg(pyaw),
                )

    def apply_grid_formation(
        self,
        rows: int,
        cols: int,
        spacing_m: float = 1.2,
        heading_deg: float = 0.0,
    ) -> None:
        """利用 FormationMatrixPlanner 对当前已有成员计算居中方阵排布并应用偏移。"""
        if not self._members:
            raise ValueError("请先添加机器人成员，然后再生成阵型")
        poses = FormationMatrixPlanner.generate_grid_formation(
            num_robots=len(self._members),
            rows=rows,
            cols=cols,
            spacing=spacing_m,
            center_x=0.0,
            center_y=0.0,
            heading_deg=heading_deg,
        )
        self._apply_calculated_poses(poses)

    def apply_line_formation(self, spacing_m: float = 1.2, heading_deg: float = 0.0) -> None:
        """应用横队（横向侧翼并排，dy分布，dx=0）排布。"""
        if not self._members:
            raise ValueError("请先添加机器人成员，然后再生成阵型")
        n = len(self._members)
        st_y = -((n - 1) * spacing_m) / 2.0
        poses = [(0.0, round(st_y + i * spacing_m, 3), heading_deg) for i in range(n)]
        self._apply_calculated_poses(poses)

    def apply_column_formation(self, spacing_m: float = 1.2, heading_deg: float = 0.0) -> None:
        """应用纵队（纵向前呼后应，dx分布，dy=0）排布。"""
        if not self._members:
            raise ValueError("请先添加机器人成员，然后再生成阵型")
        n = len(self._members)
        st_x = ((n - 1) * spacing_m) / 2.0
        poses = [(round(st_x - i * spacing_m, 3), 0.0, heading_deg) for i in range(n)]
        self._apply_calculated_poses(poses)

    def apply_circle_formation(self, radius_m: float = 2.0, heading_deg: float = 0.0) -> None:
        """应用圆阵排布并赋予成员局部偏移。"""
        if not self._members:
            raise ValueError("请先添加机器人成员，然后再生成阵型")
        poses = FormationMatrixPlanner.generate_circle_formation(
            num_robots=len(self._members), radius_m=radius_m, heading_deg=heading_deg
        )
        self._apply_calculated_poses(poses)

    # --- 4. 编译与安全检测流水线 (04C-D2 & 04C-D3) ---

    def compile_and_validate(
        self,
        name: str = "群组编队",
        group_id: Optional[str] = None,
        required_clearance_m: float = 0.6,
    ) -> Tuple[GroupTrajectory, Tuple[GroupMemberTrajectory, ...], GroupTrajectorySafetyReport]:
        """聚合参考轨迹与成员偏移，构造领域模型，编译全局几何并执行安全检测。"""
        if not self._current_reference:
            raise ValueError("尚未选择参考轨迹，无法生成群组轨迹")
        if len(self._members) < 2:
            raise ValueError("群组成员至少需要 2 台机器人方可生成群组轨迹")

        gid = group_id or f"grp_{int(time.time() * 1000)}"
        group = GroupTrajectory(
            group_trajectory_id=gid,
            name=name,
            reference_trajectory_id=str(self._current_reference.trajectory_id),
            members=tuple(self._members),
        )
        group.validate(for_submission=True)

        trajs = compile_group_trajectory(group, self._current_reference)
        report = validate_group_trajectory_safety(trajs, required_clearance_m=required_clearance_m)

        self._active_group = group
        self._last_compiled_trajectories = trajs
        self._last_safety_report = report
        return group, trajs, report

    # --- 5. 持久化存储管理 (04C-D4) ---

    def save_current_group(
        self,
        group_id: Optional[str] = None,
        name: Optional[str] = None,
        allow_overwrite: bool = True,
    ) -> GroupTrajectory:
        """保存当前配置到数据库。"""
        if not self._current_reference:
            raise ValueError("尚未选择参考轨迹，无法保存群组配置")
        gid = group_id or (self._active_group.group_trajectory_id if self._active_group else f"grp_{int(time.time() * 1000)}")
        gname = name or (self._active_group.name if self._active_group else "群组轨迹配置")

        group = GroupTrajectory(
            group_trajectory_id=gid,
            name=gname,
            reference_trajectory_id=str(self._current_reference.trajectory_id),
            members=tuple(self._members),
        )
        GroupTrajectorySqliteAdapter.save_group(self.store, group, allow_overwrite=allow_overwrite)
        self._active_group = group
        return group

    def load_group(self, group_id: str) -> GroupTrajectory:
        """从数据库读取群组配置并还原为当前编辑状态。"""
        group = GroupTrajectorySqliteAdapter.get_group(self.store, group_id)
        if not group:
            raise ValueError(f"未找到群组轨迹配置: '{group_id}'")
        self._active_group = group
        self._members = list(group.members)
        self.select_reference_trajectory(group.reference_trajectory_id)
        return group

    def delete_group(self, group_id: str) -> bool:
        """删除数据库中保存的群组配置。"""
        deleted = GroupTrajectorySqliteAdapter.delete_group(self.store, group_id)
        if self._active_group and self._active_group.group_trajectory_id == group_id:
            self._active_group = None
        return deleted

    def list_saved_groups(self) -> List[Dict[str, Any]]:
        """获取所有已保存群组配置摘要。"""
        return GroupTrajectorySqliteAdapter.list_groups(self.store)
