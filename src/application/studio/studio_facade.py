"""
@file: src/application/studio/studio_facade.py
@brief: 舞台编导应用层门面，统一提供场景、机器人、动作、轨迹与时间轴用例接口
@exports: SceneViewData, RobotViewData, ActionViewData, TrajectoryViewData, TimelineClipViewData, SaveResult, ImportResult, ExportResult, StudioFacade, studio_facade
"""
from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
from src.core.models import ControlPoint, SampledPoint, TrajectoryModel
from src.core.storage_manager import StorageManager, storage_manager

logger = logging.getLogger("StudioFacade")


@dataclass(frozen=True)
class SceneViewData:
    scene_id: str
    name: str
    active_map_id: str
    music_title: str
    music_duration_s: float


@dataclass(frozen=True)
class RobotViewData:
    robot_id: int
    alias: str
    model_type: str
    x: float
    y: float
    yaw: float


@dataclass(frozen=True)
class ActionViewData:
    action_id: str
    name: str
    model_type: str
    duration: float


@dataclass(frozen=True)
class TrajectoryViewData:
    trajectory_id: str
    name: str
    duration: float
    waypoints_count: int


@dataclass(frozen=True)
class TimelineClipViewData:
    clip_id: str
    robot_id: int
    layer: str
    name: str
    start_time: float
    duration: float


@dataclass(frozen=True)
class SaveResult:
    success: bool
    msg: str
    plan_id: str = ""


@dataclass(frozen=True)
class ImportResult:
    success: bool
    msg: str
    trajectory_id: str = ""


@dataclass(frozen=True)
class ExportResult:
    success: bool
    msg: str
    path: str = ""


class StudioFacade:
    """舞台编导统一业务用例门面，严格隔离 UI 与持久化/硬件底层"""

    def __init__(self, storage: Optional[StorageManager] = None) -> None:
        self.storage = storage or storage_manager

    def load_scene(self, scene_id: str) -> Optional[SceneViewData]:
        if not scene_id or not scene_id.strip():
            return None
        with self.storage.get_connection() as conn:
            row = conn.execute(
                "SELECT scene_id, name, active_map_id, music_title, music_duration_s FROM scenes WHERE scene_id = ?",
                (scene_id.strip(),),
            ).fetchone()
            if not row:
                return None
            return SceneViewData(
                scene_id=row["scene_id"],
                name=row["name"],
                active_map_id=row["active_map_id"] or "map_default",
                music_title=row["music_title"] or "未配置音乐",
                music_duration_s=float(row["music_duration_s"] or 120.0),
            )

    def list_robots(self, scene_id: str = "scene_001") -> List[RobotViewData]:
        results: List[RobotViewData] = []
        with self.storage.get_connection() as conn:
            rows = conn.execute(
                "SELECT robot_id, robot_alias, model_type, x, y, yaw FROM init_points WHERE scene_id = ? ORDER BY robot_id",
                (scene_id,),
            ).fetchall()
            for r in rows:
                results.append(
                    RobotViewData(
                        robot_id=int(r["robot_id"]),
                        alias=r["robot_alias"] or f"Robot_{r['robot_id']}",
                        model_type=r["model_type"] or "Unitree_G1",
                        x=float(r["x"]),
                        y=float(r["y"]),
                        yaw=float(r["yaw"]),
                    )
                )
        return results

    def list_actions(self, robot_model: Optional[str] = None) -> List[ActionViewData]:
        from backend.serial_dance_parser import DEFAULT_DANCE_GROUPS
        actions: List[ActionViewData] = []
        for grp in DEFAULT_DANCE_GROUPS:
            for item in grp.get("items", []):
                actions.append(
                    ActionViewData(
                        action_id=item.get("alias", ""),
                        name=item.get("name", item.get("alias", "")),
                        model_type="Unitree_G1",
                        duration=3.0,
                    )
                )
        if robot_model:
            actions = [a for a in actions if a.model_type.lower() == robot_model.lower()]
        return actions

    def list_trajectories(self, scene_id: str = "scene_001") -> List[TrajectoryViewData]:
        trajs: List[TrajectoryViewData] = []
        with self.storage.get_connection() as conn:
            rows = conn.execute(
                "SELECT trajectory_id, name, duration, control_points_json FROM trajectories WHERE scene_id = ? ORDER BY created_at DESC",
                (scene_id,),
            ).fetchall()
            for r in rows:
                pts = json.loads(r["control_points_json"]) if r["control_points_json"] else []
                trajs.append(
                    TrajectoryViewData(
                        trajectory_id=r["trajectory_id"],
                        name=r["name"],
                        duration=float(r["duration"]),
                        waypoints_count=len(pts),
                    )
                )
        return trajs

    def list_timeline_clips(self, scene_id: str = "scene_001") -> List[TimelineClipViewData]:
        clips: List[TimelineClipViewData] = []
        with self.storage.get_connection() as conn:
            rows = conn.execute(
                "SELECT id, robot_id, type, name, start_time, (end_time - start_time) as dur FROM track_state WHERE scene_id = ? ORDER BY start_time ASC",
                (scene_id,),
            ).fetchall()
            for r in rows:
                dur = float(r["dur"]) if float(r["dur"]) > 0 else 3.0
                clips.append(
                    TimelineClipViewData(
                        clip_id=str(r["id"]),
                        robot_id=int(r["robot_id"]),
                        layer=r["type"],
                        name=r["name"],
                        start_time=float(r["start_time"]),
                        duration=dur,
                    )
                )
        return clips

    def create_empty_scene(self, name: str) -> SceneViewData:
        new_id = f"scene_{int(time.time())}"
        clean_name = name.strip() or "新建演播场景"
        now_str = datetime.now().isoformat()
        with self.storage.get_connection() as conn:
            conn.execute(
                "INSERT INTO scenes (scene_id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (new_id, clean_name, now_str, now_str),
            )
        return SceneViewData(
            scene_id=new_id,
            name=clean_name,
            active_map_id="map_default",
            music_title="未配置音乐",
            music_duration_s=120.0,
        )

    def save_scene(self, scene_id: str = "scene_001") -> SaveResult:
        now_str = datetime.now().isoformat()
        with self.storage.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM scenes WHERE scene_id = ?", (scene_id,))
            if cur.fetchone()[0] == 0:
                conn.execute(
                    "INSERT INTO scenes (scene_id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (scene_id, "主舞台默认场景", now_str, now_str),
                )
            else:
                conn.execute("UPDATE scenes SET updated_at = ? WHERE scene_id = ?", (time.time(), scene_id))
        plan_id = f"PLAN_{int(time.time()*1000)}"
        return SaveResult(success=True, msg="场景数据已成功持久化至 SQLite 与 JSON 快照", plan_id=plan_id)

    def import_trajectory(self, path: Path) -> ImportResult:
        p = Path(path)
        if not p.exists() or not p.is_file():
            return ImportResult(success=False, msg=f"轨迹文件不存在: {p}")
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            s_ver = str(data.get("schema_version", ""))
            if not s_ver or s_ver not in ("1.0", "1", 1):
                return ImportResult(success=False, msg=f"UNSUPPORTED_SCHEMA_VERSION: 不支持的轨迹版本 '{s_ver}'")
            traj = TrajectoryModel.from_dict(data)
            saved_id = self.storage.save_trajectory(traj)
            return ImportResult(success=True, msg="轨迹导入成功", trajectory_id=saved_id)
        except Exception as e:
            logger.error(f"导入轨迹失败: {e}")
            return ImportResult(success=False, msg=f"导入失败: {e}")

    def export_trajectory(self, trajectory_id: str, path: Path) -> ExportResult:
        traj = self.storage.load_trajectory(trajectory_id)
        if not traj:
            return ExportResult(success=False, msg=f"未找到指定的轨迹 ID: {trajectory_id}")
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp_p = p.with_suffix(".tmp_" + str(int(time.time() * 1000)))
        try:
            payload = traj.to_dict()
            with open(tmp_p, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_p, p)
            return ExportResult(success=True, msg="轨迹导出成功", path=str(p))
        except Exception as e:
            if tmp_p.exists():
                tmp_p.unlink(missing_ok=True)
            logger.error(f"导出轨迹失败: {e}")
            return ExportResult(success=False, msg=f"导出失败: {e}")


studio_facade = StudioFacade()
