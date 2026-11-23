# @file: src/persistence/uniuni_json_codec.py
# @brief: Lossless bidirectional JSON serializer compatible with UniUni.exe exports and time-range slicing.
# @exports: UniUniJsonCodec

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from src.domain.action_entities import ActionEntity
from src.domain.timeline_entities import TimelineBlockEntity
from src.domain.track_entities import TrackEntity
from src.domain.trajectory_entities import ControlPoint2D, TrajectoryEntity, TrajectoryGroupEntity
from src.persistence.csv_point_codec import CsvPointCodec
from src.persistence.db_engine import StudioDatabase
from src.persistence.action_repo import ActionRepository
from src.persistence.scene_task_repo import SceneTaskRepository
from src.persistence.trajectory_repo import TrajectoryRepository


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class UniUniJsonCodec:
    """Imports and exports complete or time-ranged choreography packages in UniUni schema."""

    def __init__(self, db: StudioDatabase) -> None:
        self.db = db
        self.scene_repo = SceneTaskRepository(db)
        self.traj_repo = TrajectoryRepository(db)
        self.action_repo = ActionRepository(db)

    def export_task_to_dict(
        self,
        t_start: Optional[float] = None,
        t_end: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Serialize active scene/task, tracks, groups, trajectories, actions, and initPoints."""
        scene = self.scene_repo.get_active_scene()
        task = self.scene_repo.get_active_task(scene.id or 1)
        tracks = self.scene_repo.list_tracks(task.id or 1)
        track_by_id = {t.id: t for t in tracks}
        groups = self.traj_repo.list_groups(scene.id or 1)
        trajs = self.traj_repo.list_trajectories()
        traj_by_id = {tr.id: tr for tr in trajs}
        actions = self.action_repo.list_actions()
        action_by_id = {a.id: a for a in actions}
        blocks = self.scene_repo.list_blocks(task.id or 1)

        if t_start is not None or t_end is not None:
            lo = float(t_start or 0.0)
            hi = float(t_end if t_end is not None else 1e9)
            blocks = [b for b in blocks if b.end_time > lo and b.start_time < hi]

        track_state_items: List[Dict[str, Any]] = []
        offset = float(t_start or 0.0)
        for idx, blk in enumerate(blocks, 1):
            tr_obj = track_by_id.get(blk.track_id)
            robot_no = tr_obj.track_no if tr_obj else 1
            item: Dict[str, Any] = {
                "id": f"trackContent_{robot_no}_{blk.block_type}_{idx}",
                "sceneId": scene.id or 1,
                "robotId": robot_no,
                "type": blk.block_type,
                "no": int(blk.code_no) if str(blk.code_no).isdigit() else blk.code_no,
                "name": blk.title,
                "time": blk.duration,
                "startTime": round(max(0.0, blk.start_time - offset), 3),
                "endTime": round(max(0.0, blk.end_time - offset), 3),
                "ignored": blk.is_ignored,
            }
            if blk.block_type == "trajectory":
                traj = traj_by_id.get(blk.ref_id)
                if traj is not None:
                    item.update({
                        "groupId": traj.group_id,
                        "no": traj.no,
                        "maxAcc": traj.max_acc,
                        "holdDirection": int(traj.hold_direction),
                        "holdDirectionYaw": traj.hold_yaw,
                        "endTurn": int(traj.end_turn),
                        "endTurnYaw": traj.end_yaw,
                        "interpolationMode": traj.interpolation_mode,
                        "trajectoryPointData": traj.point_data_csv,
                        "controlPoints": [{"x": p.x, "y": p.y, "yaw": p.yaw} for p in traj.control_points],
                        "runMode": traj.run_mode,
                    })
            else:
                act = action_by_id.get(blk.ref_id)
                if act is not None:
                    item["lrmpCode"] = act.lrmp_code
            track_state_items.append(item)

        return {
            "name": task.name,
            "sceneId": scene.id or 1,
            "stageConfig": {"width": scene.stage_width, "height": scene.stage_height, "margin": scene.safety_margin},
            "actions": [
                {
                    "id": a.id, "sceneId": scene.id or 1, "no": a.no, "type": a.category,
                    "name": a.name, "time": a.duration, "lrmpCode": a.lrmp_code, "robotModel": a.robot_model,
                }
                for a in actions
            ],
            "trajectoryGroups": [
                {"id": g.id, "name": g.name, "trackId": g.bound_track_no or 1, "robotCount": g.robot_count}
                for g in groups
            ],
            "trajectories": [
                {
                    "no": t.no, "name": t.name, "groupId": t.group_id, "time": t.duration,
                    "interpolationMode": t.interpolation_mode,
                    "holdDirection": int(t.hold_direction), "holdDirectionYaw": t.hold_yaw,
                    "endTurn": int(t.end_turn), "endTurnYaw": t.end_yaw, "maxAcc": t.max_acc,
                    "runMode": t.run_mode, "trajectoryPointData": t.point_data_csv,
                    "controlPoints": [{"x": p.x, "y": p.y, "yaw": p.yaw} for p in t.control_points],
                    "createTime": _now_str(),
                }
                for t in trajs
            ],
            "trackState": track_state_items,
            "tracks": [
                {
                    "robotId": t.track_no, "sn": t.robot_id, "alias": t.name,
                    "targetId": t.target_id, "robotIp": t.robot_ip,
                }
                for t in tracks
            ],
            "initPoints": [
                {"robotId": t.track_no, "x": t.init_x, "y": t.init_y, "yaw": t.init_yaw}
                for t in tracks
            ],
        }

    def import_task_from_dict(self, data: Dict[str, Any], task_name_override: Optional[str] = None) -> int:
        """Import a UniUni JSON fixture into SQLite as the active task; return new task_id."""
        scene = self.scene_repo.get_active_scene()
        stage_cfg = data.get("stageConfig") or {}
        if stage_cfg:
            scene.stage_width = float(stage_cfg.get("width", scene.stage_width))
            scene.stage_height = float(stage_cfg.get("height", scene.stage_height))
            scene.safety_margin = float(stage_cfg.get("margin", scene.safety_margin))
            self.scene_repo.update_scene(scene)

        task_name = task_name_override or str(data.get("name", "导入编排任务"))
        from src.domain.scene_entities import TaskEntity
        task = self.scene_repo.create_task(TaskEntity(scene_id=scene.id or 1, name=task_name), set_active=True)

        init_by_rid = {int(ip["robotId"]): ip for ip in data.get("initPoints", []) if "robotId" in ip}
        track_by_rid: Dict[int, TrackEntity] = {}
        for tr_raw in data.get("tracks", []):
            rid = int(tr_raw.get("robotId", len(track_by_rid) + 1))
            ip = init_by_rid.get(rid, {})
            tr = self.scene_repo.upsert_track(
                TrackEntity(
                    task_id=task.id or 1,
                    track_no=rid,
                    name=str(tr_raw.get("alias") or tr_raw.get("sn") or f"机器人 {rid}"),
                    target_id=str(tr_raw.get("targetId") or ""),
                    robot_id=str(tr_raw.get("sn") or f"Robot_{rid}"),
                    robot_ip=str(tr_raw.get("robotIp") or f"192.168.123.{100 + rid}"),
                    init_x=float(ip.get("x", 0.0)),
                    init_y=float(ip.get("y", 0.0)),
                    init_yaw=float(ip.get("yaw", 0.0)),
                )
            )
            track_by_rid[rid] = tr

        group_id_map: Dict[int, int] = {}
        for g_raw in data.get("trajectoryGroups", []):
            old_gid = int(g_raw.get("id", 0))
            grp = self.traj_repo.upsert_group(
                TrajectoryGroupEntity(
                    scene_id=scene.id or 1,
                    name=str(g_raw.get("name", "导入分组")),
                    robot_count=int(g_raw.get("robotCount", 1)),
                    bound_track_no=int(g_raw["trackId"]) if g_raw.get("trackId") else None,
                )
            )
            group_id_map[old_gid] = grp.id or 1

        default_gid = next(iter(group_id_map.values()), self.traj_repo.list_groups(scene.id or 1)[0].id or 1)
        traj_by_no: Dict[int, TrajectoryEntity] = {}
        for t_raw in data.get("trajectories", []):
            no_val = int(t_raw.get("no", 100001))
            gid = group_id_map.get(int(t_raw.get("groupId", 0)), default_gid)
            pts_csv = str(t_raw.get("trajectoryPointData", ""))
            cps_raw = t_raw.get("controlPoints") or []
            if not cps_raw and pts_csv:
                arr = CsvPointCodec.decode_points(pts_csv)
                cps = [ControlPoint2D(float(r[1]), float(r[2]), float(r[3])) for r in arr]
            else:
                cps = [ControlPoint2D(float(p["x"]), float(p["y"]), float(p.get("yaw", 0.0))) for p in cps_raw]
            tr_ent = self.traj_repo.upsert_trajectory(
                TrajectoryEntity(
                    group_id=gid, no=no_val, name=str(t_raw.get("name", f"轨迹 {no_val}")),
                    duration=float(t_raw.get("time", 5.0)), control_points=cps,
                    interpolation_mode=str(t_raw.get("interpolationMode", "uniform")),
                    hold_direction=bool(t_raw.get("holdDirection", False)),
                    hold_yaw=float(t_raw.get("holdDirectionYaw", 0.0)),
                    end_turn=bool(t_raw.get("endTurn", False)),
                    end_yaw=float(t_raw.get("endTurnYaw", 0.0)),
                    max_acc=float(t_raw.get("maxAcc", 1.5)),
                    run_mode=int(t_raw.get("runMode", 504)),
                    point_data_csv=pts_csv,
                )
            )
            traj_by_no[no_val] = tr_ent

        self._import_actions(data.get("actions", []))
        self._import_track_state(task.id or 1, data.get("trackState", []), track_by_rid, traj_by_no, default_gid)
        return task.id or 1

    def _import_actions(self, actions_raw: List[Dict[str, Any]]) -> None:
        for a_raw in actions_raw:
            _merge_action_row(self.action_repo, a_raw)

    def _import_track_state(
        self,
        task_id: int,
        raw_state: Any,
        track_by_rid: Dict[int, TrackEntity],
        traj_by_no: Dict[int, TrajectoryEntity],
        default_gid: int,
    ) -> None:
        items = raw_state if isinstance(raw_state, list) else []
        for item in items:
            rid = int(item.get("robotId", 1))
            track = track_by_rid.get(rid)
            if track is None:
                track = self.scene_repo.upsert_track(TrackEntity(task_id=task_id, track_no=rid))
                track_by_rid[rid] = track
            blk_type = str(item.get("type", "trajectory"))
            no_val = item.get("no", "")
            ref_id = 0
            if blk_type == "trajectory":
                traj = traj_by_no.get(int(no_val)) if str(no_val).isdigit() else None
                if traj is None and item.get("trajectoryPointData"):
                    arr = CsvPointCodec.decode_points(item["trajectoryPointData"])
                    cps = [ControlPoint2D(float(r[1]), float(r[2]), float(r[3])) for r in arr]
                    traj = self.traj_repo.upsert_trajectory(
                        TrajectoryEntity(
                            group_id=default_gid,
                            no=int(no_val) if str(no_val).isdigit() else self.traj_repo.next_trajectory_no(rid),
                            name=str(item.get("name", "导入轨迹")),
                            duration=float(item.get("time", 5.0)),
                            control_points=cps,
                            interpolation_mode=str(item.get("interpolationMode", "uniform")),
                            hold_direction=bool(item.get("holdDirection", False)),
                            hold_yaw=float(item.get("holdDirectionYaw", 0.0)),
                            end_turn=bool(item.get("endTurn", False)),
                            end_yaw=float(item.get("endTurnYaw", 0.0)),
                            max_acc=float(item.get("maxAcc", 1.5)),
                            point_data_csv=str(item.get("trajectoryPointData", "")),
                        )
                    )
                    traj_by_no[traj.no] = traj
                ref_id = traj.id or 0 if traj else 0
            else:
                act = self.action_repo.find_by_code_or_no(str(item.get("lrmpCode") or no_val))
                ref_id = act.id or 0 if act else 0

            self.scene_repo.upsert_block(
                TimelineBlockEntity(
                    task_id=task_id,
                    track_id=track.id or 1,
                    block_type=blk_type,
                    ref_id=ref_id,
                    code_no=str(no_val),
                    title=str(item.get("name", "未命名块")),
                    start_time=float(item.get("startTime", 0.0)),
                    duration=float(item.get("time", 5.0)),
                    is_ignored=bool(item.get("ignored", False)),
                )
            )


def _merge_action_row(action_repo: Any, a_raw: Dict[str, Any]) -> None:
    """Upsert a single imported action dictionary row into action_repo if not already present."""
    no_str = str(a_raw.get("no", ""))
    code = str(a_raw.get("lrmpCode") or a_raw.get("name") or no_str)
    if action_repo.find_by_code_or_no(no_str) is not None:
        return
    action_repo.upsert_action(
        ActionEntity(
            no=int(no_str) if no_str.isdigit() else 900001,
            name=str(a_raw.get("name", code)),
            category=str(a_raw.get("type") or "IMPORTED"),
            lrmp_code=code,
            robot_model=str(a_raw.get("robotModel", "G1")),
            duration=float(a_raw.get("time", 10.0)),
            is_builtin=False,
            sync_status="new",
        )
    )
