"""
时间轴播放与演播控制服务
驱动 30FPS 游标走位更新、轨迹姿态插值与不可变 LRMP plan_id 编译保存
"""
import json
import math
import time
from typing import Any, Dict, List, Optional, Tuple
from PySide6.QtCore import QObject, QTimer, Signal

from src.domain.choreo.ugc_safety_guard import UgcSafetyGuard
from src.infrastructure.storage.choreo_sqlite_store import ChoreoSqliteStore
from src.infrastructure.storage.project_archive_io import compile_lrmp_plan


class TimelinePlayerService(QObject):
    """时间轴播放驱动与工程编译保存服务"""

    frameUpdated = Signal(float, dict)
    cursorMoved = Signal(float)
    playbackStateChanged = Signal(bool)
    planSaved = Signal(dict)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.is_playing = False
        self.current_time_s = 0.0
        self.max_duration_s = 120.0
        self.playback_speed = 1.0

        self.clips: List[Dict[str, Any]] = []
        self.trajectories_cache: Dict[str, Dict[str, Any]] = {}
        self.robot_spawns: Dict[str, Tuple[float, float]] = {
            "1": (-2.0, 0.0),
            "2": (2.0, 0.0)
        }
        self.store = ChoreoSqliteStore()

        self.timer = QTimer(self)
        self.timer.setInterval(33)  # 30 FPS
        self.timer.timeout.connect(self._on_timer_tick)

    def set_clips(self, clips: List[Dict[str, Any]]) -> None:
        self.clips = list(clips)
        if self.clips:
            self.max_duration_s = max([c["start_s"] + c["duration_s"] for c in self.clips], default=60.0)

    def cache_trajectory(self, traj_id: str, traj_data: Dict[str, Any]) -> None:
        wps_raw = traj_data.get("waypoints_json", "[]")
        wps = json.loads(wps_raw) if isinstance(wps_raw, str) else wps_raw
        coords = [(float(p.get("x", 0.0)), float(p.get("y", 0.0))) for p in wps]
        samples = UgcSafetyGuard.sample_trajectory(coords, speed=0.6, dt=0.033)
        self.trajectories_cache[traj_id] = {
            "duration": float(traj_data.get("duration", 2.04)),
            "waypoints": coords,
            "waypoints_json": wps_raw,
            "samples": samples
        }

    def play(self) -> None:
        if not self.is_playing:
            self.is_playing = True
            self.timer.start()
            self.playbackStateChanged.emit(True)

    def pause(self) -> None:
        if self.is_playing:
            self.is_playing = False
            self.timer.stop()
            self.playbackStateChanged.emit(False)

    def toggle_play(self) -> None:
        if self.is_playing:
            self.pause()
        else:
            self.play()

    def seek(self, t_sec: float) -> None:
        self.current_time_s = max(0.0, min(t_sec, self.max_duration_s + 5.0))
        states = self.evaluate_robot_states(self.current_time_s)
        self.cursorMoved.emit(self.current_time_s)
        self.frameUpdated.emit(self.current_time_s, states)

    def _on_timer_tick(self) -> None:
        self.current_time_s += 0.0333 * self.playback_speed
        if self.current_time_s > self.max_duration_s + 1.0:
            self.current_time_s = 0.0

        states = self.evaluate_robot_states(self.current_time_s)
        self.cursorMoved.emit(self.current_time_s)
        self.frameUpdated.emit(self.current_time_s, states)

    def evaluate_robot_states(self, t: float) -> Dict[str, Dict[str, Any]]:
        """计算当前时刻各机器人的位置 (x, y, yaw) 与动作名"""
        states: Dict[str, Dict[str, Any]] = {}
        target_rids = set(self.robot_spawns.keys()) | {c["robot_id"] for c in self.clips}

        for rid in target_rids:
            spawn = self.robot_spawns.get(rid, (0.0, 0.0))
            x, y, yaw = spawn[0], spawn[1], 0.0
            action_name = "IDLE"

            # 评估上层动作
            for c in self.clips:
                if c["robot_id"] == rid and c["track_layer"] == "UPPER_ACTION":
                    s_t = float(c["start_s"])
                    e_t = s_t + float(c["duration_s"])
                    if s_t <= t <= e_t:
                        action_name = c.get("name", "ACTION")
                        break

            # 评估下层走位轨迹
            for c in self.clips:
                if c["robot_id"] == rid and c["track_layer"] == "LOWER_TRAJ":
                    s_t = float(c["start_s"])
                    e_t = s_t + float(c["duration_s"])
                    tid = str(c.get("ref_id", ""))
                    traj = self.trajectories_cache.get(tid)
                    if traj and traj.get("samples"):
                        samples = traj["samples"]
                        if s_t <= t <= e_t:
                            rel_t = t - s_t
                            x, y = UgcSafetyGuard.interpolate_position(samples, rel_t)
                            # 计算瞬时朝向角 yaw
                            x_next, y_next = UgcSafetyGuard.interpolate_position(samples, min(rel_t + 0.1, traj["duration"]))
                            if math.hypot(x_next - x, y_next - y) > 1e-4:
                                yaw = math.atan2(y_next - y, x_next - x)
                            break
                        elif t > e_t:
                            # 停在轨迹终点
                            x, y = samples[-1]["x"], samples[-1]["y"]

            states[rid] = {
                "x": round(x, 3),
                "y": round(y, 3),
                "yaw": round(yaw, 3),
                "action": action_name
            }

        return states

    def save_and_compile(self, task_name: str = "默认任务1") -> Dict[str, Any]:
        """将当前编排持久化至 SQLite，执行安全碰撞检测，并编译生成不可变 LRMP 任务包"""
        self.store.clear_clips(task_name)
        for c in self.clips:
            self.store.save_clip(
                clip_id=c["clip_id"],
                robot_id=str(c["robot_id"]),
                track_layer=c["track_layer"],
                ref_id=str(c["ref_id"]),
                start_ms=int(c["start_s"] * 1000),
                duration_ms=int(c["duration_s"] * 1000),
                task_name=task_name
            )

        # 构建集群轨迹序列并运行碰撞扫描
        fleet_data: Dict[str, Dict[str, Any]] = {}
        for c in self.clips:
            if c["track_layer"] == "LOWER_TRAJ":
                rid = str(c["robot_id"])
                tid = str(c["ref_id"])
                traj = self.trajectories_cache.get(tid)
                if traj and traj.get("samples"):
                    fleet_data[rid] = {
                        "start_time": c["start_s"],
                        "samples": traj["samples"]
                    }

        collisions = UgcSafetyGuard.check_fleet_collisions(fleet_data, safe_radius=0.6, time_step_s=0.1)

        # 编译不可变 LRMP plan_id
        plan_id, plan_doc, plan_path = compile_lrmp_plan(task_name, self.clips, self.trajectories_cache)

        result = {
            "success": True,
            "plan_id": plan_id,
            "plan_path": plan_path,
            "task_name": task_name,
            "compiled_at": time.time(),
            "collisions": collisions,
            "collision_count": len(collisions)
        }
        self.planSaved.emit(result)
        return result
