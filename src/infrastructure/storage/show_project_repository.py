"""
@file: src/infrastructure/storage/show_project_repository.py
@brief: 统一舞台编导工程项目、机器人、阵型、动作素材与各子模块仓储持久化门面
@exports: ShowProjectRepository, DEFAULT_DB_PATH
"""
import contextlib
import json
import logging
import os
import sqlite3
import time
from typing import Any, Dict, Generator, List, Optional, Tuple

from src.domain.project.show_project import (
    Formation, MotionAsset, Robot, RobotGroup, ShowProject
)

logger = logging.getLogger("ShowProjectRepository")
DEFAULT_DB_PATH = os.path.join("runtime", "shows", "studio_data.db")

DDL_INIT_SCRIPT = """
CREATE TABLE IF NOT EXISTS show_projects (
    project_id TEXT PRIMARY KEY, name TEXT NOT NULL, current_map_id TEXT DEFAULT '',
    coordinate_frame TEXT DEFAULT 'stage_world', created_at REAL NOT NULL, updated_at REAL NOT NULL,
    version INTEGER DEFAULT 1, metadata_json TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS project_robots (
    project_id TEXT NOT NULL, robot_id TEXT NOT NULL, model TEXT DEFAULT 'Unitree_G1',
    display_name TEXT DEFAULT '', status TEXT DEFAULT 'AVAILABLE', PRIMARY KEY (project_id, robot_id)
);
CREATE TABLE IF NOT EXISTS project_groups (
    project_id TEXT NOT NULL, group_id TEXT NOT NULL, name TEXT DEFAULT '',
    member_robot_ids_json TEXT DEFAULT '[]', default_formation_id TEXT DEFAULT '',
    PRIMARY KEY (project_id, group_id)
);
CREATE TABLE IF NOT EXISTS formations (
    formation_id TEXT PRIMARY KEY, name TEXT NOT NULL, formation_type TEXT DEFAULT 'LINE',
    slots_json TEXT DEFAULT '[]', member_mapping_json TEXT DEFAULT '{}', spacing_m REAL DEFAULT 1.2,
    heading_deg REAL DEFAULT 0.0, parameters_json TEXT DEFAULT '{}', version INTEGER DEFAULT 1,
    created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS motion_assets (
    motion_id TEXT PRIMARY KEY, name TEXT NOT NULL, file_path TEXT NOT NULL,
    robot_model TEXT DEFAULT 'Unitree_G1', joint_mapping_json TEXT DEFAULT '[]', frame_count INTEGER DEFAULT 0,
    duration_s REAL DEFAULT 0.0, fps REAL DEFAULT 30.0, angle_unit TEXT DEFAULT 'rad',
    sha256 TEXT DEFAULT '', source TEXT DEFAULT 'local', validation_status TEXT DEFAULT 'VALID', created_at REAL NOT NULL
);
"""


class ShowProjectRepository:
    """管理工程项目全景持久化、机器人集群配置、阵型与动作素材的 SQLite 核心仓储"""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._ensure_tables()

    @contextlib.contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_tables(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(DDL_INIT_SCRIPT)
            conn.commit()

    def save_project(
        self, project: ShowProject, robots: Optional[List[Robot]] = None,
        groups: Optional[List[RobotGroup]] = None
    ) -> Tuple[bool, str]:
        """原子保存项目元数据及关联的机器人与群组配置"""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO show_projects (project_id, name, current_map_id, coordinate_frame, "
                    "created_at, updated_at, version, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(project_id) DO UPDATE SET name=excluded.name, current_map_id=excluded.current_map_id, "
                    "coordinate_frame=excluded.coordinate_frame, updated_at=excluded.updated_at, "
                    "version=excluded.version, metadata_json=excluded.metadata_json",
                    (
                        project.project_id, project.name, project.current_map_id,
                        project.coordinate_frame, project.created_at, time.time(),
                        project.version, json.dumps(project.metadata, ensure_ascii=False)
                    )
                )
                if robots is not None:
                    conn.execute("DELETE FROM project_robots WHERE project_id = ?", (project.project_id,))
                    for r in robots:
                        conn.execute(
                            "INSERT INTO project_robots (project_id, robot_id, model, display_name, status) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (project.project_id, r.robot_id, r.model, r.display_name, r.status)
                        )
                if groups is not None:
                    conn.execute("DELETE FROM project_groups WHERE project_id = ?", (project.project_id,))
                    for g in groups:
                        conn.execute(
                            "INSERT INTO project_groups (project_id, group_id, name, member_robot_ids_json, "
                            "default_formation_id) VALUES (?, ?, ?, ?, ?)",
                            (
                                project.project_id, g.group_id, g.name,
                                json.dumps(g.member_robot_ids, ensure_ascii=False),
                                g.default_formation_id
                            )
                        )
                conn.commit()
            return True, "项目保存成功"
        except Exception as e:
            logger.error("保存项目失败: %s", e, exc_info=True)
            return False, f"保存项目失败: {e}"

    def get_project(self, project_id: str) -> Optional[ShowProject]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM show_projects WHERE project_id = ?", (project_id,)).fetchone()
            return self._row_to_project(row) if row else None

    def list_projects(self) -> List[ShowProject]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM show_projects ORDER BY updated_at DESC").fetchall()
            return [self._row_to_project(r) for r in rows]

    @staticmethod
    def _row_to_project(r: sqlite3.Row) -> ShowProject:
        return ShowProject(
            project_id=str(r["project_id"]), name=str(r["name"]),
            current_map_id=str(r["current_map_id"]), coordinate_frame=str(r["coordinate_frame"]),
            created_at=float(r["created_at"]), updated_at=float(r["updated_at"]),
            version=int(r["version"]), metadata=json.loads(r["metadata_json"] or "{}"),
        )

    def list_project_robots(self, project_id: str) -> List[Robot]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM project_robots WHERE project_id = ? ORDER BY robot_id", (project_id,)).fetchall()
            return [Robot(robot_id=str(r["robot_id"]), model=str(r["model"]), display_name=str(r["display_name"]), status=str(r["status"])) for r in rows]

    def list_project_groups(self, project_id: str) -> List[RobotGroup]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM project_groups WHERE project_id = ? ORDER BY group_id", (project_id,)).fetchall()
            return [
                RobotGroup(
                    group_id=str(r["group_id"]), name=str(r["name"]),
                    member_robot_ids=json.loads(r["member_robot_ids_json"] or "[]"),
                    default_formation_id=str(r["default_formation_id"]),
                ) for r in rows
            ]

    def save_formation(self, formation: Formation) -> Tuple[bool, str]:
        try:
            now = time.time()
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO formations (formation_id, name, formation_type, slots_json, "
                    "member_mapping_json, spacing_m, heading_deg, parameters_json, version, "
                    "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(formation_id) DO UPDATE SET name=excluded.name, formation_type=excluded.formation_type, "
                    "slots_json=excluded.slots_json, member_mapping_json=excluded.member_mapping_json, "
                    "spacing_m=excluded.spacing_m, heading_deg=excluded.heading_deg, "
                    "parameters_json=excluded.parameters_json, version=excluded.version, updated_at=excluded.updated_at",
                    (
                        formation.formation_id, formation.name, formation.formation_type,
                        json.dumps(formation.slots, ensure_ascii=False),
                        json.dumps(formation.member_mapping, ensure_ascii=False),
                        formation.spacing_m, formation.heading_deg,
                        json.dumps(formation.parameters, ensure_ascii=False),
                        formation.version, now, now
                    )
                )
                conn.commit()
            return True, "阵型保存成功"
        except Exception as e:
            logger.error("保存阵型失败: %s", e, exc_info=True)
            return False, f"保存阵型失败: {e}"

    def get_formation(self, formation_id: str) -> Optional[Formation]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM formations WHERE formation_id = ?", (formation_id,)).fetchone()
            return self._row_to_formation(row) if row else None

    def list_formations(self) -> List[Formation]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM formations ORDER BY updated_at DESC").fetchall()
            return [self._row_to_formation(r) for r in rows]

    @staticmethod
    def _row_to_formation(r: sqlite3.Row) -> Formation:
        return Formation(
            formation_id=str(r["formation_id"]), name=str(r["name"]),
            formation_type=str(r["formation_type"]), slots=json.loads(r["slots_json"] or "[]"),
            member_mapping=json.loads(r["member_mapping_json"] or "{}"), spacing_m=float(r["spacing_m"]),
            heading_deg=float(r["heading_deg"]), parameters=json.loads(r["parameters_json"] or "{}"),
            version=int(r["version"]),
        )

    def save_motion_asset(self, motion: MotionAsset) -> Tuple[bool, str]:
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO motion_assets (motion_id, name, file_path, robot_model, "
                    "joint_mapping_json, frame_count, duration_s, fps, angle_unit, sha256, "
                    "source, validation_status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(motion_id) DO UPDATE SET name=excluded.name, file_path=excluded.file_path, "
                    "robot_model=excluded.robot_model, joint_mapping_json=excluded.joint_mapping_json, "
                    "frame_count=excluded.frame_count, duration_s=excluded.duration_s, fps=excluded.fps, "
                    "angle_unit=excluded.angle_unit, sha256=excluded.sha256, source=excluded.source, "
                    "validation_status=excluded.validation_status",
                    (
                        motion.motion_id, motion.name, motion.file_path, motion.robot_model,
                        json.dumps(motion.joint_mapping, ensure_ascii=False),
                        motion.frame_count, motion.duration_s, motion.fps, motion.angle_unit,
                        motion.sha256, motion.source, motion.validation_status, time.time()
                    )
                )
                conn.commit()
            return True, "动作素材保存成功"
        except Exception as e:
            logger.error("保存动作素材失败: %s", e, exc_info=True)
            return False, f"保存动作素材失败: {e}"

    def get_motion_asset(self, motion_id: str) -> Optional[MotionAsset]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM motion_assets WHERE motion_id = ?", (motion_id,)).fetchone()
            return self._row_to_motion_asset(row) if row else None

    def list_motion_assets(self) -> List[MotionAsset]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM motion_assets ORDER BY motion_id ASC").fetchall()
            return [self._row_to_motion_asset(r) for r in rows]

    @staticmethod
    def _row_to_motion_asset(r: sqlite3.Row) -> MotionAsset:
        return MotionAsset(
            motion_id=str(r["motion_id"]), name=str(r["name"]), file_path=str(r["file_path"]),
            robot_model=str(r["robot_model"]), joint_mapping=json.loads(r["joint_mapping_json"] or "[]"),
            frame_count=int(r["frame_count"]), duration_s=float(r["duration_s"]), fps=float(r["fps"]),
            angle_unit=str(r["angle_unit"]), sha256=str(r["sha256"]), source=str(r["source"]),
            validation_status=str(r["validation_status"]),
        )
