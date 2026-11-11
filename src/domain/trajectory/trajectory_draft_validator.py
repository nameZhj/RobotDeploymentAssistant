"""
@file: src/domain/trajectory/trajectory_draft_validator.py
@brief: 2D/3D 轨迹草稿控制点校验、位姿锚定、素材组装及持久化映射
@exports: TrajectoryDraftValidator
"""
import math
import time
from typing import Any, Dict, List, Optional, Tuple
from src.domain.trajectory.spline_builder import SplineTrajectoryBuilder
from src.domain.trajectory.trajectory_asset import TrajectoryAsset, TrajectoryPoint


class TrajectoryDraftValidator:
    """提供轨迹草稿在生成平滑样条前的数据契约合规性、空间锚定校验及资产组装与持久化映射"""

    MAX_STAGE_BOUND_M: float = 50.0
    MAX_START_DEVIATION_M: float = 3.0
    MIN_CONSECUTIVE_DISTANCE_M: float = 0.01

    @classmethod
    def resolve_robot_pose(
        cls, robot_id: str, current_poses: Dict[Any, Any], completed_trajs: List[Dict[str, Any]], robot_spawns: List[Dict[str, Any]]
    ) -> Optional[Tuple[float, float, float]]:
        """根据当前动态位姿、历史已完结轨迹终点或初始站位确定机器人当前参考位姿"""
        rid = str(robot_id)
        if current_poses and rid in current_poses:
            p = current_poses[rid]
            return float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0
        r_completed = [t for t in completed_trajs if str(t.get("robot_id")) == rid]
        if r_completed and r_completed[-1].get("waypoints"):
            last_wp = r_completed[-1]["waypoints"][-1]
            return float(last_wp[0]), float(last_wp[1]), 0.0
        for r in robot_spawns:
            if str(r.get("id")) == rid or str(r.get("name")) == rid:
                pos = r.get("pos", (0.0, 0.0))
                return float(pos[0]), float(pos[1]), float(r.get("yaw_deg", 0.0))
        return None

    @classmethod
    def validate(
        cls, waypoints: List[Tuple[float, float]], robot_id: Optional[str],
        robot_pose: Optional[Tuple[float, float, float]] = None, max_deviation_m: Optional[float] = None
    ) -> Tuple[bool, str]:
        """校验控制点数量、有限性、工作区边界、重叠点以及与机器人位姿的偏差"""
        if len(waypoints) < 2:
            return False, "控制点不足：至少需要 2 个控制点方可生成有效轨迹"
        if not robot_id:
            return False, "未选中目标机器人：请先指定关联机器人"
        for idx, (x, y) in enumerate(waypoints):
            if not (math.isfinite(x) and math.isfinite(y)):
                return False, f"控制点 P{idx + 1} 坐标非法 (非有限浮点数): ({x}, {y})"
            if abs(x) > cls.MAX_STAGE_BOUND_M or abs(y) > cls.MAX_STAGE_BOUND_M:
                return False, f"控制点 P{idx + 1} ({x:.2f}, {y:.2f}) 超出舞台有效工作区 (±{cls.MAX_STAGE_BOUND_M}m)"
        for i in range(1, len(waypoints)):
            if math.hypot(waypoints[i][0] - waypoints[i - 1][0], waypoints[i][1] - waypoints[i - 1][1]) < cls.MIN_CONSECUTIVE_DISTANCE_M:
                return False, f"控制点 P{i} 与 P{i + 1} 重叠或间距过小 (<{cls.MIN_CONSECUTIVE_DISTANCE_M}m)"
        if robot_pose is not None:
            dist = math.hypot(waypoints[0][0] - robot_pose[0], waypoints[0][1] - robot_pose[1])
            limit = max_deviation_m or cls.MAX_START_DEVIATION_M
            if dist > limit:
                return False, f"轨迹起点距机器人 '{robot_id}' 站位偏差过大 ({dist:.2f}m > {limit:.2f}m)"
        return True, ""

    @classmethod
    def build_trajectory_asset(
        cls, waypoints: List[Tuple[float, float]], robot_id: str, sequence_num: int = 1
    ) -> Tuple[TrajectoryAsset, Dict[str, Any]]:
        """使用向心样条平滑插值，计算物理切线角与累计弧长，组装统一领域模型与前端载荷"""
        pts = list(waypoints)
        curve, s_cum, total_len = SplineTrajectoryBuilder.fit_spline_curve(pts, alpha=0.5)
        sampled: List[TrajectoryPoint] = []
        for i in range(len(curve)):
            yaw = 0.0
            if len(curve) > 1:
                i_next, i_prev = min(i + 1, len(curve) - 1), max(0, i - 1)
                yaw = math.degrees(math.atan2(curve[i_next, 1] - curve[i_prev, 1], curve[i_next, 0] - curve[i_prev, 0]))
            sampled.append(TrajectoryPoint(x_m=float(curve[i, 0]), y_m=float(curve[i, 1]), yaw_deg=round(yaw, 2), s_m=round(float(s_cum[i]), 4)))
        traj_id = f"traj_{robot_id}_{int(time.time() * 1000) % 100000}"
        asset = TrajectoryAsset(
            trajectory_id=traj_id, name=f"轨迹-{robot_id}-{sequence_num:02d}", coordinate_frame="stage_world",
            control_points=pts, sampled_points=sampled, length_m=round(float(total_len), 4),
            recommended_speed_mps=0.8, spline_type="catmull_rom"
        )
        payload = {
            "id": asset.trajectory_id, "name": asset.name, "robot_id": str(robot_id), "waypoints": pts,
            "spline_points": [(float(p[0]), float(p[1])) for p in curve],
            "length": round(float(total_len), 3), "duration": round(max(float(total_len) / 0.8, 1.0), 2), "asset": asset,
        }
        return asset, payload

    @classmethod
    def find_closest_waypoint(
        cls, waypoints: List[Tuple[float, float]], stage_pos: Tuple[float, float], max_dist_m: float = 0.5
    ) -> Optional[int]:
        if not waypoints:
            return None
        closest_idx, min_d = None, max_dist_m
        for idx, (wx, wy) in enumerate(waypoints):
            d = math.hypot(wx - stage_pos[0], wy - stage_pos[1])
            if d <= min_d:
                min_d, closest_idx = d, idx
        return closest_idx

    @classmethod
    def update_waypoint(
        cls, waypoints: List[Tuple[float, float]], index: int, new_pos: Tuple[float, float]
    ) -> List[Tuple[float, float]]:
        if not (0 <= index < len(waypoints)):
            return list(waypoints)
        updated = list(waypoints)
        updated[index] = (round(float(new_pos[0]), 3), round(float(new_pos[1]), 3))
        return updated

    @classmethod
    def insert_waypoint(
        cls, waypoints: List[Tuple[float, float]], index: int, new_point: Tuple[float, float]
    ) -> List[Tuple[float, float]]:
        updated = list(waypoints)
        updated.insert(max(0, min(index, len(updated))), (round(float(new_point[0]), 3), round(float(new_point[1]), 3)))
        return updated

    @classmethod
    def delete_waypoint(
        cls, waypoints: List[Tuple[float, float]], index: int
    ) -> Tuple[bool, List[Tuple[float, float]], str]:
        if len(waypoints) <= 2:
            return False, list(waypoints), "无法删除控制点：轨迹至少需要保留 2 个控制点"
        if not (0 <= index < len(waypoints)):
            return False, list(waypoints), f"非法控制点索引: {index}"
        updated = list(waypoints)
        updated.pop(index)
        return True, updated, ""

    @classmethod
    def refresh_trajectory_preview(cls, item: Dict[str, Any]) -> None:
        curve, _, total_len = SplineTrajectoryBuilder.fit_spline_curve(item["waypoints"], alpha=0.5)
        item["spline_points"] = [(float(p[0]), float(p[1])) for p in curve]
        item["length"] = round(float(total_len), 3)
        item["duration"] = round(max(float(total_len) / 0.8, 1.0), 2)

    @classmethod
    def save_trajectory_to_store(
        cls, store: Any, item: Dict[str, Any], allow_overwrite_referenced: bool = False
    ) -> Tuple[bool, str]:
        if not store:
            return True, f"轨迹 '{item['name']}' 已更新 (无持久化存储)"
        asset, _ = cls.build_trajectory_asset(item["waypoints"], item["robot_id"], 1)
        asset.trajectory_id, asset.name = item["id"], item["name"]
        item["asset"] = asset
        try:
            store.save_trajectory_asset(asset, robot_group=item["robot_id"], allow_overwrite_referenced=allow_overwrite_referenced)
            return True, f"轨迹 '{item['name']}' 已成功保存"
        except Exception as e:
            return False, f"保存失败: {e}"

    @classmethod
    def delete_trajectory_from_store(cls, store: Any, traj_id: str) -> Tuple[bool, str]:
        if not store:
            return True, f"轨迹 '{traj_id}' 已删除"
        try:
            store.delete_trajectory_asset(str(traj_id))
            return True, f"轨迹 '{traj_id}' 已成功删除"
        except Exception as e:
            return False, f"删除失败: {e}"

    @classmethod
    def insert_and_refresh(cls, trajectories: List[Dict[str, Any]], traj_id: str, index: int, pos: Tuple[float, float]) -> bool:
        item = next((t for t in trajectories if str(t.get("id")) == str(traj_id)), None)
        if not item:
            return False
        item["waypoints"] = cls.insert_waypoint(item["waypoints"], index, pos)
        cls.refresh_trajectory_preview(item)
        return True

    @classmethod
    def delete_and_refresh(cls, trajectories: List[Dict[str, Any]], traj_id: str, index: int) -> Tuple[bool, str]:
        item = next((t for t in trajectories if str(t.get("id")) == str(traj_id)), None)
        if not item:
            return False, "未找到目标轨迹"
        ok, updated, err = cls.delete_waypoint(item["waypoints"], index)
        if not ok:
            return False, err
        item["waypoints"] = updated
        cls.refresh_trajectory_preview(item)
        return True, ""

    @classmethod
    def save_current(
        cls, store: Any, trajectories: List[Dict[str, Any]], traj_id: Optional[str],
        default_robot_id: Optional[str], allow_overwrite: bool = False
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        tid = str(traj_id or "")
        item = next((t for t in trajectories if str(t.get("id")) == tid), None)
        if not item:
            return False, "无选中轨迹可供保存", None
        valid, err = cls.validate(item["waypoints"], item.get("robot_id", default_robot_id))
        if not valid:
            return False, f"保存校验失败: {err}", None
        ok, msg = cls.save_trajectory_to_store(store, item, allow_overwrite)
        return ok, msg, (item if ok else None)

    @classmethod
    def delete_trajectory(cls, store: Any, trajectories: List[Dict[str, Any]], traj_id: str) -> Tuple[bool, str]:
        ok, msg = cls.delete_trajectory_from_store(store, traj_id)
        if not ok:
            return False, msg
        rem = [t for t in trajectories if str(t.get("id")) != str(traj_id)]
        trajectories.clear()
        trajectories.extend(rem)
        return True, msg

    @classmethod
    def load_trajectories_from_store(
        cls, store: Any, robot_group: Optional[str] = None, default_robot_id: str = "A"
    ) -> List[Dict[str, Any]]:
        if not store:
            return []
        assets = store.list_trajectory_assets(robot_group=robot_group)
        results: List[Dict[str, Any]] = []
        for a in assets:
            curve, _, _ = SplineTrajectoryBuilder.fit_spline_curve(a.control_points, alpha=0.5)
            rid = str(robot_group or default_robot_id)
            if hasattr(store, "get_trajectory"):
                row = store.get_trajectory(a.trajectory_id)
                if row and "robot_group" in row:
                    rid = str(row["robot_group"])
            results.append({
                "id": a.trajectory_id, "name": a.name, "robot_id": rid, "waypoints": list(a.control_points),
                "spline_points": [(float(p[0]), float(p[1])) for p in curve],
                "length": round(a.length_m, 3), "duration": round(max(a.length_m / 0.8, 1.0), 2), "asset": a,
            })
        return results
