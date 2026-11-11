"""
@file: src/infrastructure/storage/group_trajectory_sqlite_adapter.py
@brief: 机器人群组轨迹配置 SQLite 持久化适配器与引用完整性校验
@exports: GroupTrajectorySqliteAdapter
"""
import json
import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

from src.domain.trajectory.group_trajectory import GroupTrajectory, GroupTrajectoryMember

logger = logging.getLogger("GroupTrajectorySqliteAdapter")


class GroupTrajectorySqliteAdapter:
    """处理 GroupTrajectory 配置与 SQLite 数据库之间的持久化映射、引用完整性及事务防护。"""

    TABLE_SCHEMA = """
        CREATE TABLE IF NOT EXISTS group_trajectories (
            group_trajectory_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            reference_trajectory_id TEXT NOT NULL,
            coordinate_frame TEXT NOT NULL DEFAULT 'stage_world',
            members_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
    """

    @classmethod
    def ensure_tables(cls, conn: sqlite3.Connection) -> None:
        """确保 group_trajectories 表结构就绪。"""
        conn.execute(cls.TABLE_SCHEMA)

    @classmethod
    def save_group(
        cls,
        store: Any,
        group: GroupTrajectory,
        allow_overwrite: bool = True,
    ) -> None:
        """在事务中持久化群组配置。强制校验参考轨迹存在性，杜绝 INSERT OR REPLACE 级联副作用。"""
        if not isinstance(group, GroupTrajectory):
            raise TypeError(f"必须传入 GroupTrajectory 实例，得到: {type(group).__name__}")
        group.validate(for_submission=False)

        gid = str(group.group_trajectory_id)
        ref_id = str(group.reference_trajectory_id)
        members_data = [m.to_dict() for m in group.members]
        members_json = json.dumps(members_data, ensure_ascii=False)
        now = time.time()

        with store.get_connection() as conn:
            cls.ensure_tables(conn)
            try:
                conn.execute("BEGIN IMMEDIATE")
                # 1. 严格检查参考轨迹存在性
                ref_row = conn.execute(
                    "SELECT traj_id FROM trajectories WHERE traj_id = ?", (ref_id,)
                ).fetchone()
                if not ref_row:
                    raise ValueError(f"引用的单机器人参考轨迹 '{ref_id}' 在数据库中不存在")

                # 2. 检查群组是否已存在并做确定性更新或插入
                existing = conn.execute(
                    "SELECT group_trajectory_id FROM group_trajectories WHERE group_trajectory_id = ?",
                    (gid,),
                ).fetchone()
                if existing:
                    if not allow_overwrite:
                        raise ValueError(f"群组轨迹 '{gid}' 已存在且未授权覆盖")
                    conn.execute(
                        """
                        UPDATE group_trajectories
                        SET name = ?, reference_trajectory_id = ?, coordinate_frame = ?,
                            members_json = ?, updated_at = ?
                        WHERE group_trajectory_id = ?
                        """,
                        (group.name, ref_id, group.coordinate_frame, members_json, now, gid),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO group_trajectories
                        (group_trajectory_id, name, reference_trajectory_id, coordinate_frame,
                         members_json, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (gid, group.name, ref_id, group.coordinate_frame, members_json, now, now),
                    )
                conn.commit()
                logger.info(f"群组轨迹 '{gid}' 成功保存至 SQLite")
            except Exception:
                conn.rollback()
                raise

    @classmethod
    def get_group(cls, store: Any, group_id: str) -> Optional[GroupTrajectory]:
        """按 ID 查询并反序列化 GroupTrajectory。"""
        gid = str(group_id).strip()
        with store.get_connection() as conn:
            cls.ensure_tables(conn)
            row = conn.execute(
                "SELECT * FROM group_trajectories WHERE group_trajectory_id = ?", (gid,)
            ).fetchone()
            if not row:
                return None
            return cls._row_to_group(row)

    @classmethod
    def list_groups(cls, store: Any) -> List[Dict[str, Any]]:
        """列出所有保存的群组轨迹摘要。"""
        with store.get_connection() as conn:
            cls.ensure_tables(conn)
            cur = conn.execute(
                "SELECT group_trajectory_id, name, reference_trajectory_id, coordinate_frame, "
                "members_json, created_at, updated_at FROM group_trajectories ORDER BY updated_at DESC"
            )
            rows = cur.fetchall()
            summaries: List[Dict[str, Any]] = []
            for r in rows:
                try:
                    m_list = json.loads(r["members_json"])
                    m_count = len(m_list) if isinstance(m_list, list) else 0
                except Exception:
                    m_count = 0
                summaries.append({
                    "group_trajectory_id": str(r["group_trajectory_id"]),
                    "name": str(r["name"]),
                    "reference_trajectory_id": str(r["reference_trajectory_id"]),
                    "coordinate_frame": str(r["coordinate_frame"]),
                    "member_count": m_count,
                    "created_at": float(r["created_at"]),
                    "updated_at": float(r["updated_at"]),
                })
            return summaries

    @classmethod
    def delete_group(cls, store: Any, group_id: str) -> bool:
        """删除指定的群组轨迹配置。"""
        gid = str(group_id).strip()
        with store.get_connection() as conn:
            cls.ensure_tables(conn)
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "DELETE FROM group_trajectories WHERE group_trajectory_id = ?", (gid,)
                )
                deleted = cur.rowcount > 0
                conn.commit()
                return deleted
            except Exception:
                conn.rollback()
                raise

    @classmethod
    def _row_to_group(cls, row: sqlite3.Row) -> GroupTrajectory:
        raw_json = row["members_json"]
        members: List[GroupTrajectoryMember] = []
        if raw_json and isinstance(raw_json, str):
            try:
                data = json.loads(raw_json)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            members.append(GroupTrajectoryMember.from_dict(item))
            except Exception as e:
                logger.warning(f"解析群组成员数据异常: {e}")

        return GroupTrajectory(
            group_trajectory_id=str(row["group_trajectory_id"]),
            name=str(row["name"]),
            reference_trajectory_id=str(row["reference_trajectory_id"]),
            coordinate_frame=str(row["coordinate_frame"] if "coordinate_frame" in row.keys() else "stage_world"),
            members=tuple(members),
        )
