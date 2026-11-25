# @file: src/persistence/studio_slice_merger.py
# @brief: Merges an exported stage JSON slice into the currently active Choreography task at a chosen time offset.
# @exports: merge_slice_into_current_task

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from src.domain.timeline_entities import TimelineBlockEntity
from src.domain.trajectory_entities import ControlPoint2D, TrajectoryEntity, TrajectoryGroupEntity
from src.persistence.csv_point_codec import CsvPointCodec
from src.persistence.studio_json_codec import _merge_action_row

if TYPE_CHECKING:
    from src.services.studio_state_service import StudioStateService


def merge_slice_into_current_task(state: StudioStateService, data: Dict[str, Any], offset_s: float = 0.0) -> int:
    """Merge tracks, trajectories, actions, and shifted blocks from a JSON slice into the active task."""
    scene_id = state.scene.id or 1
    task_id = state.task.id or 1
    shift = max(0.0, float(offset_s))

    by_no = {t.track_no: t for t in state.tracks}
    by_robot_id = {t.robot_id: t for t in state.tracks}
    init_by_rid = {int(ip["robotId"]): ip for ip in data.get("initPoints", []) if "robotId" in ip}
    track_by_rid = {}
    for tr_raw in data.get("tracks", []):
        rid = int(tr_raw.get("robotId", 1))
        sn = str(tr_raw.get("sn") or f"Robot_{rid}")
        existing = by_no.get(rid) or by_robot_id.get(sn)
        if existing is not None:
            track_by_rid[rid] = existing
            continue
        ip = init_by_rid.get(rid, {})
        from src.domain.scene_entities import TrackEntity

        created = state.scene_repo.upsert_track(
            TrackEntity(
                task_id=task_id,
                track_no=max([t.track_no for t in state.tracks], default=0) + 1,
                name=str(tr_raw.get("alias") or sn),
                target_id=str(tr_raw.get("targetId") or f"M{rid}"),
                robot_id=sn,
                robot_ip=str(tr_raw.get("robotIp") or f"192.168.123.{100 + rid}"),
                init_x=float(ip.get("x", 0.0)),
                init_y=float(ip.get("y", 0.0)),
                init_yaw=float(ip.get("yaw", 0.0)),
            )
        )
        by_no[created.track_no] = created
        by_robot_id[created.robot_id] = created
        track_by_rid[rid] = created

    groups = state.traj_repo.list_groups(scene_id)
    default_gid = groups[0].id or 1 if groups else (
        state.traj_repo.upsert_group(TrajectoryGroupEntity(scene_id=scene_id, name="导入切片分组")).id or 1
    )
    existing_trajs = {t.no: t for t in state.trajectories.values()}
    for t_raw in data.get("trajectories", []):
        no_val = int(t_raw.get("no", 100001))
        if no_val in existing_trajs:
            continue
        pts_csv = str(t_raw.get("trajectoryPointData", ""))
        cps_raw = t_raw.get("controlPoints") or []
        if not cps_raw and pts_csv:
            arr = CsvPointCodec.decode_points(pts_csv)
            cps = [ControlPoint2D(float(r[1]), float(r[2]), float(r[3])) for r in arr]
        else:
            cps = [ControlPoint2D(float(p["x"]), float(p["y"]), float(p.get("yaw", 0.0))) for p in cps_raw]
        existing_trajs[no_val] = state.traj_repo.upsert_trajectory(
            TrajectoryEntity(
                group_id=default_gid, no=no_val, name=str(t_raw.get("name", f"轨迹 {no_val}")),
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

    for a_raw in data.get("actions", []):
        _merge_action_row(state.action_repo, a_raw)

    raw_items = [it for it in data.get("trackState", []) if isinstance(it, dict)]
    min_t = min((float(it.get("startTime", 0.0)) for it in raw_items), default=0.0)
    added = 0
    for item in raw_items:
        rid = int(item.get("robotId", 1))
        tr = track_by_rid.get(rid) or by_no.get(rid)
        if tr is None:
            continue
        blk_type = str(item.get("type", "trajectory"))
        no_val = item.get("no", "")
        if blk_type == "trajectory":
            traj = existing_trajs.get(int(no_val)) if str(no_val).isdigit() else None
            ref_id = traj.id or 0 if traj else 0
        else:
            act = state.action_repo.find_by_code_or_no(str(item.get("lrmpCode") or no_val))
            ref_id = act.id or 0 if act else 0
        start_val = max(0.0, float(item.get("startTime", 0.0)) - min_t + shift)
        state.scene_repo.upsert_block(
            TimelineBlockEntity(
                task_id=task_id, track_id=tr.id or 1, block_type=blk_type, ref_id=ref_id,
                code_no=str(no_val), title=str(item.get("name", "导入块")),
                start_time=round(start_val, 3), duration=max(0.5, float(item.get("time", 5.0))),
                is_ignored=bool(item.get("ignored", False)),
            )
        )
        added += 1
    return added
