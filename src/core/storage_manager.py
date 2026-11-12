"""
@file: src/core/storage_manager.py
@brief: 统一文件存储与 SQLite 事务引擎，管理地图索引、轨迹、阵型与工程快照
@exports: StorageManager, storage_manager
"""
import contextlib
import json
import logging
import os
import sqlite3
import time
from typing import Any, Dict, Generator, List, Optional
from src.core.models import FormationModel, ProjectChoreoModel, TrajectoryModel

logger = logging.getLogger("StorageManager")


class StorageManager:
    """管理统一标准 data/ 目录体系与 SQLite 六核心表事务同步"""

    def __init__(self, base_dir: Optional[str] = None, db_path: Optional[str] = None) -> None:
        self.base_dir = os.path.abspath(base_dir or os.getcwd())
        self.data_dir = os.path.join(self.base_dir, "data")
        self.maps_dir = os.path.join(self.data_dir, "maps")
        self.trajectories_dir = os.path.join(self.data_dir, "trajectories")
        self.formations_dir = os.path.join(self.data_dir, "formations")
        self.projects_dir = os.path.join(self.data_dir, "projects")
        self.maps_index_path = os.path.join(self.maps_dir, "maps_index.json")
        self.db_path = db_path or os.path.join(self.data_dir, "choreo_database.db")
        self.init_storage()

    @contextlib.contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_storage(self) -> None:
        """初始化必要目录、maps_index.json 与 SQLite 表结构"""
        for d in [self.maps_dir, self.trajectories_dir, self.formations_dir, self.projects_dir]:
            os.makedirs(d, exist_ok=True)
        self._init_maps_index()
        self._init_database_tables()

    def _init_maps_index(self) -> None:
        idx: Dict[str, Any] = {"active_map_id": "", "maps": []}
        if os.path.exists(self.maps_index_path):
            try:
                with open(self.maps_index_path, "r", encoding="utf-8") as f:
                    idx = json.load(f)
            except Exception:
                pass
        else:
            with open(self.maps_index_path, "w", encoding="utf-8") as f:
                json.dump(idx, f, indent=2, ensure_ascii=False)

    def _init_database_tables(self) -> None:
        from src.infrastructure.storage.migration_engine import MigrationEngine
        with self.get_connection() as conn:
            MigrationEngine.apply_all(conn)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, scene_id TEXT NOT NULL, robot_id INTEGER NOT NULL,
                    lora_id TEXT NOT NULL, sn TEXT DEFAULT '', alias TEXT DEFAULT '', UNIQUE(scene_id, robot_id)
                );
                CREATE TABLE IF NOT EXISTS init_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, scene_id TEXT NOT NULL, cfg_id INTEGER DEFAULT 1, robot_id INTEGER NOT NULL,
                    x REAL DEFAULT 0.0, y REAL DEFAULT 0.0, yaw REAL DEFAULT 0.0, robot_alias TEXT DEFAULT '', model_type TEXT DEFAULT 'Unitree_G1',
                    UNIQUE(scene_id, cfg_id, robot_id)
                );
                CREATE TABLE IF NOT EXISTS track_state (
                    id TEXT PRIMARY KEY, scene_id TEXT DEFAULT 'scene_001', robot_id INTEGER NOT NULL, group_id INTEGER DEFAULT 0,
                    no INTEGER NOT NULL, type TEXT NOT NULL, name TEXT DEFAULT '', time REAL DEFAULT 0.0, start_time REAL DEFAULT 0.0,
                    end_time REAL DEFAULT 0.0, content_json TEXT DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS fragments (
                    fragment_id TEXT PRIMARY KEY, scene_id TEXT DEFAULT 'scene_001', name TEXT NOT NULL,
                    start_time REAL DEFAULT 0.0, duration REAL DEFAULT 10.0, content_json TEXT DEFAULT '{}'
                );
            """)

    def save_trajectory(self, traj: TrajectoryModel) -> str:
        """保存单条轨迹到 JSON 文件并同步写入 SQLite trajectories 表"""
        file_path = os.path.join(self.trajectories_dir, f"{traj.trajectory_id}.json")
        traj_data = traj.to_dict()
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(traj_data, f, indent=2, ensure_ascii=False)

        cps_json = json.dumps(traj_data["control_points"], ensure_ascii=False)
        sps_json = json.dumps(traj_data["sampled_points"], ensure_ascii=False)
        duration = traj.control_points[-1].t if traj.control_points else 3.0

        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO trajectories (
                    trajectory_id, scene_id, group_id, name, target_type, target_id,
                    formation_id, duration, max_velocity, interpolation,
                    control_points_json, sampled_points_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trajectory_id) DO UPDATE SET
                    scene_id=excluded.scene_id, group_id=excluded.group_id, name=excluded.name,
                    target_type=excluded.target_type, target_id=excluded.target_id,
                    formation_id=excluded.formation_id, duration=excluded.duration,
                    max_velocity=excluded.max_velocity, interpolation=excluded.interpolation,
                    control_points_json=excluded.control_points_json,
                    sampled_points_json=excluded.sampled_points_json;
                """,
                (
                    traj.trajectory_id, traj.scene_id, traj.formation_id, traj.name,
                    traj.target_type, traj.target_id, traj.formation_id, duration,
                    traj.max_velocity, traj.interpolation, cps_json, sps_json, time.time(),
                ),
            )
        return traj.trajectory_id

    def load_trajectory(self, trajectory_id: str) -> Optional[TrajectoryModel]:
        """从 JSON 或 SQLite 读取轨迹"""
        file_path = os.path.join(self.trajectories_dir, f"{trajectory_id}.json")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return TrajectoryModel.from_dict(json.load(f))

        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM trajectories WHERE trajectory_id = ?", (trajectory_id,)).fetchone()
            if not row:
                return None
            return TrajectoryModel(
                trajectory_id=row["trajectory_id"],
                name=row["name"],
                scene_id=row["scene_id"],
                target_type=row["target_type"],
                target_id=row["target_id"],
                formation_id=row["formation_id"],
                interpolation=row["interpolation"],
                max_velocity=row["max_velocity"],
                control_points=[json.loads(p) for p in json.loads(row["control_points_json"])],
                sampled_points=[json.loads(p) for p in json.loads(row["sampled_points_json"])],
            )

    def save_formation(self, formation: FormationModel) -> str:
        """保存阵型为 data/formations/<formation_id>.json"""
        file_path = os.path.join(self.formations_dir, f"{formation.formation_id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(formation.to_dict(), f, indent=2, ensure_ascii=False)
        return formation.formation_id

    def load_formation(self, formation_id: str) -> Optional[FormationModel]:
        file_path = os.path.join(self.formations_dir, f"{formation_id}.json")
        if not os.path.exists(file_path):
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            return FormationModel.from_dict(json.load(f))

    def save_project_choreo(self, project: ProjectChoreoModel) -> str:
        """原子事务保存工程至 SQLite 并同步导出 data/projects/<scene_id>_choreo.json"""
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO scenes (scene_id, name, active_map_id, music_path, music_title, music_duration_s, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scene_id) DO UPDATE SET
                    name=excluded.name, active_map_id=excluded.active_map_id,
                    music_path=excluded.music_path, music_title=excluded.music_title,
                    music_duration_s=excluded.music_duration_s, updated_at=excluded.updated_at;
                """,
                (project.scene_id, project.name, project.map_id, project.music_path,
                 project.music_title, project.music_duration_s, time.time()),
            )
            # 同步 tracks
            for t in project.tracks:
                conn.execute(
                    """
                    INSERT INTO tracks (scene_id, robot_id, lora_id, sn, alias) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(scene_id, robot_id) DO UPDATE SET lora_id=excluded.lora_id, sn=excluded.sn, alias=excluded.alias;
                    """,
                    (project.scene_id, int(t.get("robot_id", 1)), str(t.get("lora_id", "A")),
                     str(t.get("sn", "")), str(t.get("alias", ""))),
                )
            # 同步 init_points
            for ip in project.init_points:
                conn.execute(
                    """
                    INSERT INTO init_points (scene_id, cfg_id, robot_id, x, y, yaw, robot_alias, model_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(scene_id, cfg_id, robot_id) DO UPDATE SET
                        x=excluded.x, y=excluded.y, yaw=excluded.yaw,
                        robot_alias=excluded.robot_alias, model_type=excluded.model_type;
                    """,
                    (project.scene_id, int(ip.get("cfg_id", 1)), int(ip.get("robot_id", 1)),
                     float(ip.get("x", 0.0)), float(ip.get("y", 0.0)), float(ip.get("yaw", 0.0)),
                     str(ip.get("robot_alias", "")), str(ip.get("model_type", "Unitree_G1"))),
                )
            # 同步 track_state
            for ts in project.track_state:
                conn.execute(
                    """
                    INSERT INTO track_state (id, scene_id, robot_id, group_id, no, type, name, time, start_time, end_time, content_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name, time=excluded.time, start_time=excluded.start_time,
                        end_time=excluded.end_time, content_json=excluded.content_json;
                    """,
                    (str(ts.get("id")), project.scene_id, int(ts.get("robot_id", 1)), int(ts.get("group_id", 0)),
                     int(ts.get("no", 0)), str(ts.get("type", "motion")), str(ts.get("name", "")),
                     float(ts.get("time", 0.0)), float(ts.get("start_time", 0.0)), float(ts.get("end_time", 0.0)),
                     json.dumps(ts.get("content", {}), ensure_ascii=False)),
                )

        # 导出快照 JSON
        project_file = os.path.join(self.projects_dir, f"{project.scene_id}_choreo.json")
        with open(project_file, "w", encoding="utf-8") as f:
            json.dump(project.to_dict(), f, indent=2, ensure_ascii=False)
        return project.scene_id

    def load_project_choreo(self, scene_id: str) -> Optional[ProjectChoreoModel]:
        project_file = os.path.join(self.projects_dir, f"{scene_id}_choreo.json")
        if os.path.exists(project_file):
            with open(project_file, "r", encoding="utf-8") as f:
                return ProjectChoreoModel.from_dict(json.load(f))
        return None

    def get_maps_index(self) -> Dict[str, Any]:
        if not os.path.exists(self.maps_index_path):
            self._init_maps_index()
        with open(self.maps_index_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def update_maps_index(self, maps_index: Dict[str, Any]) -> None:
        with open(self.maps_index_path, "w", encoding="utf-8") as f:
            json.dump(maps_index, f, indent=2, ensure_ascii=False)


storage_manager = StorageManager()
