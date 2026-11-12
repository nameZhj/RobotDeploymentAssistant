import json
import math
from pathlib import Path
import sqlite3
import sys
import time
from PySide6.QtCore import QObject, QTimer, Signal

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT_DIR / "data" / "choreo_database.db"
LOG_PATH = ROOT_DIR / "runtime" / "logs" / "lrmp_session.log"


class StudioController(QObject):
    """全局唯一业务与交互接线中枢：所有 UI 按钮、画布、时间轴必须绑定到此控制器"""
    trajectories_changed = Signal(object)        # 刷新右上角『轨迹库』表格
    actions_changed = Signal(object)             # 刷新右下角『动作库』表格
    timeline_changed = Signal(object)            # 刷新底部『双层时间轴』蓝/绿块
    playhead_updated = Signal(float, object)     # (当前秒数, {robot_id: (x, y, yaw, action_name, joints_dict)})
    swarm_status_changed = Signal(object)        # 刷新『表演监测』在线机器人卡片与底栏状态
    log_appended = Signal(str)                   # 刷新『运行日志』

    def __init__(self) -> None:
        super().__init__()
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.current_time_s = 0.0
        self.is_playing = False
        self.draw_mode = "NONE"  # NONE | TRAJ | SKETCH
        self.active_robot_id = 1
        self.temp_waypoints: list[tuple[float, float]] = []
        self.sketch_lines: list[list[tuple[float, float]]] = []
        self.robots_online: dict[str, dict] = {}
        self.current_plan_id = 8001
        self.current_run_id = 9001

        self.timer = QTimer(self)
        self.timer.setInterval(33)  # 30 FPS 帧驱动
        self.timer.timeout.connect(self._on_frame_tick)
        self._init_sqlite()

    def _init_sqlite(self) -> None:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS trajectories (id INTEGER PRIMARY KEY, robot_id INT, name TEXT, pts TEXT, duration REAL)")
            conn.execute("CREATE TABLE IF NOT EXISTS actions (id INTEGER PRIMARY KEY, name TEXT, model TEXT, duration REAL)")
            conn.execute("CREATE TABLE IF NOT EXISTS clips (id INTEGER PRIMARY KEY AUTOINCREMENT, robot_id INT, layer TEXT, ref_id INT, title TEXT, start_s REAL, duration_s REAL)")

    def refresh_all_views(self) -> None:
        with sqlite3.connect(DB_PATH) as conn:
            cols_t = [c[1] for c in conn.execute("PRAGMA table_info(trajectories)").fetchall()]
            t_id = "id" if "id" in cols_t else "traj_id"
            t_rid = "robot_id" if "robot_id" in cols_t else "robot_group"
            t_pts = "pts" if "pts" in cols_t else "waypoints_json"
            trajs = conn.execute(f"SELECT {t_id}, {t_rid}, name, {t_pts}, duration FROM trajectories").fetchall()

            cols_a = [c[1] for c in conn.execute("PRAGMA table_info(actions)").fetchall()]
            a_id = "id" if "id" in cols_a else "action_id"
            a_mod = "model" if "model" in cols_a else "model_type"
            acts = conn.execute(f"SELECT {a_id}, name, {a_mod}, duration FROM actions").fetchall()

            clips = conn.execute("SELECT id, robot_id, layer, ref_id, title, start_s, duration_s FROM clips ORDER BY start_s").fetchall()
        self.trajectories_changed.emit(trajs)
        self.actions_changed.emit(acts)
        self.timeline_changed.emit(clips)
        self._emit_pose_at(self.current_time_s)

    def add_canvas_waypoint(self, x_m: float, y_m: float) -> None:
        if self.draw_mode in ("TRAJ", "TRAJECTORY", "SKETCH"):
            self.temp_waypoints.append((round(x_m, 2), round(y_m, 2)))

    def finish_current_trajectory(self) -> None:
        if len(self.temp_waypoints) < 2:
            return
        dist = sum(math.hypot(self.temp_waypoints[i][0] - self.temp_waypoints[i - 1][0], self.temp_waypoints[i][1] - self.temp_waypoints[i - 1][1]) for i in range(1, len(self.temp_waypoints)))
        dur = round(max(1.2, dist / 1.2), 2)
        new_id = int(time.time() * 10) % 100000 + 100003
        name = f"轨迹-traj_{int(time.time()*1000)}_{len(self.temp_waypoints)}"
        with sqlite3.connect(DB_PATH) as conn:
            cols_t = [c[1] for c in conn.execute("PRAGMA table_info(trajectories)").fetchall()]
            if "traj_id" in cols_t:
                conn.execute(
                    "INSERT INTO trajectories (traj_id, robot_group, name, waypoints_json, duration, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (str(new_id), f"Robot_{self.active_robot_id}", name, json.dumps(self.temp_waypoints), dur, time.time())
                )
            else:
                conn.execute("INSERT INTO trajectories VALUES (?, ?, ?, ?, ?)", (new_id, self.active_robot_id, name, json.dumps(self.temp_waypoints), dur))
            conn.execute("INSERT INTO clips (robot_id, layer, ref_id, title, start_s, duration_s) VALUES (?, 'TRAJ', ?, '轨...', ?, ?)", (self.active_robot_id, new_id, self.current_time_s, dur))
        self.temp_waypoints.clear()
        self.refresh_all_views()

    def add_action_to_timeline(self, act_id: int, name: str, dur: float, robot_id: int = 1) -> None:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute("SELECT MAX(start_s + duration_s) FROM clips WHERE robot_id=? AND layer='ACTION'", (robot_id,)).fetchone()
            start_s = round(row[0] or 0.0, 2)
            conn.execute("INSERT INTO clips (robot_id, layer, ref_id, title, start_s, duration_s) VALUES (?, 'ACTION', ?, ?, ?, ?)", (robot_id, act_id, name, start_s, dur))
        self.refresh_all_views()

    def toggle_playback(self) -> bool:
        self.is_playing = not self.is_playing
        if self.is_playing:
            self.timer.start()
        else:
            self.timer.stop()
        return self.is_playing

    def seek_time(self, time_s: float) -> None:
        self.current_time_s = max(0.0, time_s)
        self._emit_pose_at(self.current_time_s)

    def _on_frame_tick(self) -> None:
        self.current_time_s += 0.033
        if self.current_time_s > 120.0:
            self.current_time_s = 0.0
        self._emit_pose_at(self.current_time_s)

    def _emit_pose_at(self, t: float) -> None:
        with sqlite3.connect(DB_PATH) as conn:
            cols_t = [c[1] for c in conn.execute("PRAGMA table_info(trajectories)").fetchall()]
            t_id = "id" if "id" in cols_t else "traj_id"
            t_pts = "pts" if "pts" in cols_t else "waypoints_json"
            trajs_raw = conn.execute(f"SELECT {t_id}, name, {t_pts} FROM trajectories").fetchall()
            trajs = {}
            for r in trajs_raw:
                try:
                    pts = json.loads(r[2])
                    if pts and isinstance(pts[0], dict):
                        pts = [[p.get("x", 0.0), p.get("y", 0.0)] for p in pts]
                    trajs[r[0]] = pts
                    trajs[int(r[0])] = pts
                except Exception:
                    pass
            clips = conn.execute("SELECT robot_id, layer, ref_id, title, start_s, duration_s FROM clips").fetchall()
        poses = {}
        for rid in (1, 2):
            x, y, yaw, act_name = (-2.0 if rid == 1 else 2.0), (0.0 if rid == 1 else 0.0), 0.0, "STAND"
            for c_rid, layer, ref_id, title, st, dur in clips:
                if c_rid == rid and st <= t <= st + dur:
                    if layer == "ACTION":
                        act_name = title
                    elif layer == "TRAJ" and ref_id in trajs:
                        pts = trajs[ref_id]
                        if len(pts) >= 2:
                            ratio = (t - st) / max(0.01, dur)
                            idx = min(int(ratio * (len(pts) - 1)), len(pts) - 2)
                            local_r = ratio * (len(pts) - 1) - idx
                            x = pts[idx][0] + (pts[idx + 1][0] - pts[idx][0]) * local_r
                            y = pts[idx][1] + (pts[idx + 1][1] - pts[idx][1]) * local_r
                            yaw = math.atan2(pts[idx + 1][1] - pts[idx][1], pts[idx + 1][0] - pts[idx][0])
            joints = {
                "l_shoulder_pitch": 0.0,
                "r_shoulder_pitch": 0.0,
                "l_hip_pitch": 0.0,
                "r_hip_pitch": 0.0,
                "torso_yaw": 0.0,
            }
            poses[rid] = (x, y, yaw, act_name, joints)
        self.playhead_updated.emit(t, poses)

    def send_lrmp(self, targets: list[str], cmd: str, params: str = "") -> None:
        for tgt in targets:
            raw = f"{tgt}|{cmd}" + (f",{params}" if params else "")
            log_line = f"[REQ -> {tgt}] {raw} (DISPATCHED)"
            with LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(log_line + "\n")
            self.log_appended.emit(log_line)

    def generate_ai_formation(self) -> None:
        pts1 = [[-2.5, -1.0], [-1.2, 1.2], [0.0, 1.8], [1.2, 1.2], [2.5, -1.0]]
        pts2 = [[2.5, -1.0], [1.2, 1.2], [0.0, 1.8], [-1.2, 1.2], [-2.5, -1.0]]
        dur = 8.0
        with sqlite3.connect(DB_PATH) as conn:
            cols_t = [c[1] for c in conn.execute("PRAGMA table_info(trajectories)").fetchall()]
            if "traj_id" in cols_t:
                conn.execute("INSERT OR REPLACE INTO trajectories (traj_id, robot_group, name, waypoints_json, duration, created_at) VALUES ('100001', 'Robot_1', 'AI对称轨迹-1', ?, ?, ?)", (json.dumps(pts1), dur, time.time()))
                conn.execute("INSERT OR REPLACE INTO trajectories (traj_id, robot_group, name, waypoints_json, duration, created_at) VALUES ('100002', 'Robot_2', 'AI对称轨迹-2', ?, ?, ?)", (json.dumps(pts2), dur, time.time()))
            else:
                conn.execute("INSERT OR REPLACE INTO trajectories VALUES (100001, 1, 'AI对称轨迹-1', ?, ?)", (json.dumps(pts1), dur))
                conn.execute("INSERT OR REPLACE INTO trajectories VALUES (100002, 2, 'AI对称轨迹-2', ?, ?)", (json.dumps(pts2), dur))
            conn.execute("DELETE FROM clips WHERE layer='TRAJ'")
            conn.execute("INSERT INTO clips (robot_id, layer, ref_id, title, start_s, duration_s) VALUES (1, 'TRAJ', 100001, 'AI轨-1', 0.0, ?)", (dur,))
            conn.execute("INSERT INTO clips (robot_id, layer, ref_id, title, start_s, duration_s) VALUES (2, 'TRAJ', 100002, 'AI轨-2', 0.0, ?)", (dur,))
        self.refresh_all_views()
