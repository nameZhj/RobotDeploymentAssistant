"""
@file: src/infrastructure/storage/trajectory_sqlite_adapter.py
@brief: TrajectoryAsset 与 SQLite trajectories 表双向适配与引用防护
@exports: TrajectorySqliteAdapter
"""
import json
import logging
import math
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple
from src.domain.trajectory.spline_builder import SplineTrajectoryBuilder
from src.domain.trajectory.trajectory_asset import TrajectoryAsset, TrajectoryPoint
from src.domain.trajectory.trajectory_compiler import TrajectoryCompiler

logger = logging.getLogger("TrajectorySqliteAdapter")


class TrajectorySqliteAdapter:
    """处理 TrajectoryAsset 空间素材与 SQLite 数据库之间的持久化映射、旧格式重建及引用保护"""

    @classmethod
    def ensure_columns(cls, conn: sqlite3.Connection) -> None:
        """平滑追加 asset_json 扩展字段，保证旧数据库零破坏兼容"""
        cols = [c[1] for c in conn.execute("PRAGMA table_info(trajectories)").fetchall()]
        if "asset_json" not in cols:
            conn.execute("ALTER TABLE trajectories ADD COLUMN asset_json TEXT")
            conn.commit()

    @classmethod
    def check_reference_count(cls, conn: sqlite3.Connection, traj_id: str) -> int:
        """检查轨迹在 timeline_clips、clips 以及 group_trajectories 表中的总引用计数"""
        tid = str(traj_id)
        cur_tc = conn.execute("SELECT COUNT(*) FROM timeline_clips WHERE ref_id = ?", (tid,))
        count_tc = cur_tc.fetchone()[0]

        count_c = 0
        count_gt = 0
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if "clips" in tables:
            ref_int = int(tid) if tid.isdigit() else -999999
            cur_c = conn.execute("SELECT COUNT(*) FROM clips WHERE ref_id = ? OR ref_id = ?", (tid, ref_int))
            count_c = cur_c.fetchone()[0]

        if "group_trajectories" in tables:
            cur_gt = conn.execute("SELECT COUNT(*) FROM group_trajectories WHERE reference_trajectory_id = ?", (tid,))
            count_gt = cur_gt.fetchone()[0]

        return count_tc + count_c + count_gt

    @classmethod
    def _write_trajectory_row(
        cls,
        conn: sqlite3.Connection,
        traj_id: str,
        robot_group: str,
        name: str,
        waypoints_json: str,
        duration: float,
        asset_json: Optional[str]
    ) -> None:
        """使用安全的 UPDATE 或 INSERT，杜绝 INSERT OR REPLACE 删除旧行产生的外键与引用副作用"""
        tid = str(traj_id)
        existing = conn.execute("SELECT traj_id FROM trajectories WHERE traj_id = ?", (tid,)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE trajectories
                SET robot_group = ?, name = ?, waypoints_json = ?, duration = ?, asset_json = ?
                WHERE traj_id = ?
                """,
                (robot_group, name, waypoints_json, duration, asset_json, tid)
            )
        else:
            conn.execute(
                """
                INSERT INTO trajectories
                (traj_id, robot_group, name, waypoints_json, duration, created_at, asset_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (tid, robot_group, name, waypoints_json, duration, time.time(), asset_json)
            )

    @classmethod
    def save_asset(
        cls,
        store: Any,
        asset: TrajectoryAsset,
        robot_group: str = "Robot_1",
        allow_overwrite_referenced: bool = False
    ) -> None:
        """持久化保存 TrajectoryAsset，原子写入扩展 JSON 与旧兼容字段，被引用时默认禁止覆盖更新"""
        if not isinstance(asset, TrajectoryAsset):
            raise TypeError(f"必须传入 TrajectoryAsset 实例，得到: {type(asset).__name__}")
        asset.validate()

        tid = str(asset.trajectory_id)
        with store.get_connection() as conn:
            cls.ensure_columns(conn)
            try:
                conn.execute("BEGIN IMMEDIATE")
                if not allow_overwrite_referenced:
                    existing = conn.execute("SELECT traj_id FROM trajectories WHERE traj_id = ?", (tid,)).fetchone()
                    if existing:
                        total_refs = cls.check_reference_count(conn, tid)
                        if total_refs > 0:
                            raise ValueError(
                                f"轨迹素材 '{tid}' 正被 {total_refs} 处时间轴片段引用，默认禁止覆盖更新。"
                                "如需强制更新请显式指定 allow_overwrite_referenced=True"
                            )

                asset_json = json.dumps(asset.to_dict())
                wps_json = json.dumps([list(p) for p in asset.control_points])
                dur = round(asset.length_m / max(0.1, asset.recommended_speed_mps), 2)
                cls._write_trajectory_row(conn, tid, robot_group, asset.name, wps_json, dur, asset_json)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    @classmethod
    def save_legacy(
        cls,
        store: Any,
        traj_id: str,
        robot_group: str,
        name: str,
        waypoints_json: str,
        duration: float,
        allow_overwrite_referenced: bool = False
    ) -> None:
        """保存旧格式轨迹记录，同样遵循时间轴引用保护策略，更新时使 asset_json 失效"""
        tid = str(traj_id)
        with store.get_connection() as conn:
            cls.ensure_columns(conn)
            try:
                conn.execute("BEGIN IMMEDIATE")
                if not allow_overwrite_referenced:
                    existing = conn.execute("SELECT traj_id FROM trajectories WHERE traj_id = ?", (tid,)).fetchone()
                    if existing:
                        total_refs = cls.check_reference_count(conn, tid)
                        if total_refs > 0:
                            raise ValueError(
                                f"轨迹素材 '{tid}' 正被 {total_refs} 处时间轴片段引用，默认禁止覆盖更新。"
                                "如需强制更新请显式指定 allow_overwrite_referenced=True"
                            )

                cls._write_trajectory_row(conn, tid, robot_group, name, waypoints_json, duration, None)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    @classmethod
    def load_asset(cls, store: Any, trajectory_id: str) -> Optional[TrajectoryAsset]:
        """根据 ID 加载 TrajectoryAsset，支持新版完整格式与历史旧数据无缝兼容"""
        with store.get_connection() as conn:
            cls.ensure_columns(conn)
            row = conn.execute("SELECT * FROM trajectories WHERE traj_id = ?", (str(trajectory_id),)).fetchone()
            if not row:
                return None
            return cls.row_to_asset(row)

    @classmethod
    def row_to_asset(cls, row: sqlite3.Row) -> TrajectoryAsset:
        """单行数据还原为 TrajectoryAsset；若缺少 asset_json 则由历史字段确定性重建"""
        keys = row.keys() if hasattr(row, "keys") else [d[0] for d in row.description]
        raw_json = row["asset_json"] if "asset_json" in keys else None

        if raw_json and isinstance(raw_json, str) and raw_json.strip():
            try:
                data = json.loads(raw_json)
                if isinstance(data, dict):
                    return TrajectoryAsset.from_dict(data)
            except Exception as e:
                raise ValueError(f"轨迹 '{row['traj_id']}' 的 asset_json 数据已损坏: {e}")

        # 历史记录兼容路径（旧字段: waypoints_json, duration, name）
        tid = str(row["traj_id"])
        name = str(row["name"])
        wps_raw = str(row["waypoints_json"] if "waypoints_json" in keys else "[]")
        ctrl_pts = cls._parse_legacy_control_points(wps_raw)

        if len(ctrl_pts) >= 2:
            curve, _, total_len = SplineTrajectoryBuilder.fit_spline_curve(ctrl_pts)
            s_acc = 0.0
            s_list = [0.0]
            for i in range(1, len(curve)):
                s_acc += float(((curve[i, 0] - curve[i - 1, 0]) ** 2 + (curve[i, 1] - curve[i - 1, 1]) ** 2) ** 0.5)
                s_list.append(s_acc)
            sampled = []
            for i in range(len(curve)):
                yaw = float(math.degrees(math.atan2(curve[min(i + 1, len(curve) - 1), 1] - curve[max(0, i - 1), 1],
                                                    curve[min(i + 1, len(curve) - 1), 0] - curve[max(0, i - 1), 0]))) if len(curve) > 1 else 0.0
                sampled.append(TrajectoryPoint(x_m=float(curve[i, 0]), y_m=float(curve[i, 1]), yaw_deg=yaw, s_m=round(s_list[i], 6)))
            return TrajectoryAsset(trajectory_id=tid, name=name, control_points=ctrl_pts, sampled_points=sampled, length_m=round(s_list[-1], 6))

        return TrajectoryAsset(trajectory_id=tid, name=name, control_points=ctrl_pts if ctrl_pts else [(0.0, 0.0)], length_m=0.0)

    @classmethod
    def _parse_legacy_control_points(cls, wps_raw: str) -> List[Tuple[float, float]]:
        """从旧 JSON 或 CSV 提取控制点坐标二元组"""
        clean = wps_raw.strip()
        if not clean:
            return [(0.0, 0.0)]
        if clean.startswith("["):
            try:
                data = json.loads(clean)
                if isinstance(data, list):
                    pts: List[Tuple[float, float]] = []
                    for item in data:
                        if isinstance(item, (list, tuple)) and len(item) >= 2:
                            pts.append((float(item[0]), float(item[1])))
                        elif isinstance(item, dict) and "x" in item and "y" in item:
                            pts.append((float(item["x"]), float(item["y"])))
                    if pts:
                        return pts
            except Exception:
                pass
        csv_pts = TrajectoryCompiler.parse_trajectory_data(clean)
        return [(p[1], p[2]) for p in csv_pts] if csv_pts else [(0.0, 0.0)]

    @classmethod
    def list_assets(cls, store: Any, robot_group: Optional[str] = None) -> List[TrajectoryAsset]:
        """批量获取所有轨迹素材"""
        with store.get_connection() as conn:
            cls.ensure_columns(conn)
            query = "SELECT * FROM trajectories"
            params: List[Any] = []
            if robot_group:
                query += " WHERE robot_group = ?"
                params.append(robot_group)
            query += " ORDER BY created_at ASC"
            rows = conn.execute(query, params).fetchall()
            assets: List[TrajectoryAsset] = []
            for r in rows:
                try:
                    assets.append(cls.row_to_asset(r))
                except Exception as e:
                    logger.warning(f"跳过损坏轨迹 {r['traj_id']}: {e}")
            return assets

    @classmethod
    def delete_asset(cls, store: Any, trajectory_id: str) -> bool:
        """受控删除轨迹素材，在同一原子写事务中完成引用检查与物理删除，并发安全"""
        tid = str(trajectory_id)
        with store.get_connection() as conn:
            cls.ensure_columns(conn)
            try:
                conn.execute("BEGIN IMMEDIATE")
                total_refs = cls.check_reference_count(conn, tid)
                if total_refs > 0:
                    raise ValueError(f"轨迹 '{tid}' 正被时间轴引用 (引用计数: {total_refs})，禁止直接删除")

                cur = conn.execute("DELETE FROM trajectories WHERE traj_id = ?", (tid,))
                conn.commit()
                return cur.rowcount > 0
            except Exception:
                conn.rollback()
                raise
