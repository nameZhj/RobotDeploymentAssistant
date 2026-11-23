# @file: src/services/studio_state_ops.py
# @brief: Transactional CRUD, Undo/Redo, collision validation, serial sync, and settings helpers for StudioStateService.
# @exports: commit_block_change_op, delete_track_with_undo_op, load_fragment_at_op, apply_settings_update_op, upsert_track_validated_op, validate_init_points_op, clamp_robot_drag_xy_op, sync_actions_from_serial_op, bind_trajectory_tracks_op

from __future__ import annotations

import copy
import math
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

from src.core.event_bus import StudioEvent
from src.core.settings import get_settings, save_settings
from src.core.undo_stack import CallableUndoCommand
from src.domain.timeline_entities import TimelineBlockEntity
from src.domain.track_entities import TrackEntity

if TYPE_CHECKING:
    from src.services.studio_state_service import StudioStateService


def upsert_track_validated_op(svc: StudioStateService, track: TrackEntity) -> TrackEntity:
    """Validate uniqueness of track_no, target_id, and physical non-collision radius before saving."""
    tid_norm = track.target_id.strip().upper()
    if not tid_norm:
        raise ValueError("LRMP 目标符不能为空")
    track.target_id = tid_norm
    min_dist = float(get_settings().stage_defaults.safety_distance_m)
    for existing in svc.tracks:
        if existing.id == track.id:
            continue
        if existing.track_no == track.track_no:
            raise ValueError(f"轨道序号 {track.track_no} 已被 {existing.name} 占用")
        if existing.target_id.upper() == tid_norm:
            raise ValueError(f"LRMP 目标符 [{tid_norm}] 已被 {existing.name} 占用")
        dist = math.hypot(track.init_x - existing.init_x, track.init_y - existing.init_y)
        if dist < min_dist - 1e-6:
            raise ValueError(
                f"初始位置 ({track.init_x:.2f}, {track.init_y:.2f}) 与 [{existing.name}] 发生体积碰撞 "
                f"(距离 {dist:.2f}m < 安全阈值 {min_dist:.2f}m)"
            )
    saved = svc.scene_repo.upsert_track(track)
    svc.reload_all()
    svc.bus.publish(StudioEvent.TRACKS_UPDATED, saved.id)
    return saved


def delete_track_with_undo_op(svc: StudioStateService, track_id: int) -> Optional[str]:
    """Delete a robot track and its timeline blocks cleanly with full Undo/Redo support."""
    target = next((t for t in svc.tracks if t.id == track_id), None)
    if target is None:
        return None
    snap_track = copy.deepcopy(target)
    snap_blocks = [copy.deepcopy(b) for b in svc.blocks if b.track_id == track_id]
    holder = {"cur_track_id": track_id}

    def _redo() -> None:
        svc.scene_repo.delete_track(holder["cur_track_id"])
        svc.reload_all()
        svc.bus.publish(StudioEvent.TRACKS_UPDATED, None)
        svc.bus.publish(StudioEvent.TIMELINE_UPDATED, None)

    def _undo() -> None:
        restored = copy.deepcopy(snap_track)
        restored.id = None
        new_tr = svc.scene_repo.upsert_track(restored)
        holder["cur_track_id"] = new_tr.id or 0
        for blk in snap_blocks:
            rb = copy.deepcopy(blk)
            rb.id = None
            rb.track_id = holder["cur_track_id"]
            svc.scene_repo.upsert_block(rb)
        svc.reload_all()
        svc.bus.publish(StudioEvent.TRACKS_UPDATED, new_tr.id)
        svc.bus.publish(StudioEvent.TIMELINE_UPDATED, None)

    svc.undo_stack.push(CallableUndoCommand(f"删除轨道 {snap_track.name}", _redo, _undo), execute_redo=True)
    return snap_track.name


def commit_block_change_op(
    svc: StudioStateService,
    before: Optional[TimelineBlockEntity],
    after: Optional[TimelineBlockEntity],
    description: str,
) -> Optional[TimelineBlockEntity]:
    """Persist block insert/update/delete onto timeline with Undo/Redo registration."""
    snap_before = copy.deepcopy(before) if before is not None else None
    snap_after = copy.deepcopy(after) if after is not None else None
    state_ref: dict[str, Any] = {"saved": None, "active_id": (before.id if before else None)}

    def _apply(target: Optional[TimelineBlockEntity], fallback_del_id: Optional[int]) -> None:
        if target is None:
            if fallback_del_id is not None:
                svc.scene_repo.delete_block(fallback_del_id)
            state_ref["saved"] = None
            state_ref["active_id"] = None
        else:
            ent = copy.deepcopy(target)
            if state_ref["active_id"] is not None:
                ent.id = state_ref["active_id"]
            saved = svc.scene_repo.upsert_block(ent)
            state_ref["saved"] = saved
            state_ref["active_id"] = saved.id
        svc.reload_all()
        svc.bus.publish(StudioEvent.TIMELINE_UPDATED, state_ref["active_id"])

    def _redo() -> None:
        _apply(snap_after, state_ref["active_id"])

    def _undo() -> None:
        _apply(snap_before, state_ref["active_id"])

    svc.undo_stack.push(CallableUndoCommand(description, _redo, _undo), execute_redo=True)
    return state_ref["saved"]


def load_fragment_at_op(svc: StudioStateService, fragment_id: int, insert_time_s: float) -> int:
    """Instantiate saved TimelineFragmentEntity blocks onto matching tracks starting at insert_time_s."""
    frags = svc.map_repo.list_fragments(svc.scene.id or 1)
    frag = next((f for f in frags if f.id == fragment_id), None)
    if frag is None:
        return 0
    raw_items = list(frag.payload.get("trackState", []))
    by_no = {t.track_no: t for t in svc.tracks}
    inserted = 0
    created_ids: list[int] = []
    snapshots: list[TimelineBlockEntity] = []
    for item in raw_items:
        rno = int(item.get("robotId", 1))
        tr = by_no.get(rno) or (svc.tracks[0] if svc.tracks else None)
        if tr is None:
            continue
        btype = str(item.get("type", "action"))
        code_no = str(item.get("no", ""))
        title = str(item.get("name", frag.name))
        dur = max(0.5, float(item.get("time", 5.0)))
        t_off = max(0.0, float(item.get("startTime", 0.0)))
        ref_id = 0
        if btype == "action":
            act = svc.action_repo.find_by_code_or_no(str(item.get("lrmpCode", "") or code_no))
            ref_id = act.id or 0 if act else 0
        else:
            match_tr = next((t for t in svc.trajectories.values() if str(t.no) == code_no or t.name == title), None)
            ref_id = match_tr.id or 0 if match_tr else 0
        snapshots.append(
            TimelineBlockEntity(
                task_id=svc.task.id or 1,
                track_id=tr.id or 1,
                block_type=btype,
                ref_id=ref_id,
                code_no=code_no,
                title=title,
                start_time=round(insert_time_s + t_off, 2),
                duration=dur,
            )
        )
    if not snapshots:
        return 0

    def _redo() -> None:
        created_ids.clear()
        for b in snapshots:
            clone = copy.deepcopy(b)
            clone.id = None
            saved = svc.scene_repo.upsert_block(clone)
            if saved.id is not None:
                created_ids.append(saved.id)
        svc.reload_all()
        svc.bus.publish(StudioEvent.TIMELINE_UPDATED, None)

    def _undo() -> None:
        for bid in created_ids:
            svc.scene_repo.delete_block(bid)
        svc.reload_all()
        svc.bus.publish(StudioEvent.TIMELINE_UPDATED, None)

    svc.undo_stack.push(CallableUndoCommand(f"载入片段 {frag.name}", _redo, _undo), execute_redo=True)
    inserted = len(snapshots)
    return inserted


def apply_settings_update_op(svc: StudioStateService, safety_dist: float, http_virtual_fallback: bool) -> None:
    """Persist updated safety threshold & HTTP virtual mode to user_settings.yaml and refresh collisions."""
    cfg = get_settings()
    cfg.stage_defaults.safety_distance_m = round(max(0.2, float(safety_dist)), 2)
    cfg.virtual_interfaces.http_upload_virtual_fallback = bool(http_virtual_fallback)
    save_settings(cfg)
    svc.http_client.virtual_fallback = bool(http_virtual_fallback)
    svc.recompute_collisions()


def validate_init_points_op(points: List[Tuple[str, float, float]]) -> None:
    """Raise ValueError if any two proposed robot initial positions violate the collision radius."""
    min_dist = float(get_settings().stage_defaults.safety_distance_m)
    for i in range(len(points)):
        na, xa, ya = points[i]
        for j in range(i + 1, len(points)):
            nb, xb, yb = points[j]
            dist = math.hypot(xa - xb, ya - yb)
            if dist < min_dist - 1e-6:
                raise ValueError(f"[{na}] 与 [{nb}] 初始位置发生体积碰撞 ({dist:.2f}m < {min_dist:.2f}m)")


def clamp_robot_drag_xy_op(svc: StudioStateService, track: TrackEntity, wx: float, wy: float) -> Tuple[float, float]:
    """Push dragged robot position cleanly outside all other robots' collision radii."""
    min_dist = float(get_settings().stage_defaults.safety_distance_m)
    px, py = float(wx), float(wy)
    others = [(t.init_x, t.init_y) for t in svc.tracks if t.id != track.id]
    for _ in range(3):
        for ox, oy in others:
            dx, dy = px - ox, py - oy
            dist = math.hypot(dx, dy)
            if dist < min_dist - 1e-4:
                if dist < 1e-5:
                    dx, dy, dist = 1.0, 0.0, 1.0
                scale = (min_dist + 0.01) / dist
                px, py = ox + dx * scale, oy + dy * scale
    return round(px, 2), round(py, 2)


def sync_actions_from_serial_op(svc: StudioStateService, timeout: float = 3.0) -> Tuple[bool, int, str]:
    """Synchronize authentic onboard robot actions exclusively from serial GETDANCELIST / RX cache."""
    sm = svc.serial_manager
    groups: list = []
    if sm is not None:
        connected = bool(sm.is_connected() if callable(getattr(sm, "is_connected", None)) else getattr(sm, "is_connected", False))
        if connected and hasattr(sm, "request_dance_list"):
            res = sm.request_dance_list(timeout=timeout, force=True)
            groups = list(res.get("groups") or [])
        elif getattr(sm, "latest_dance_list_parsed", None):
            groups = list(sm.latest_dance_list_parsed)

    if not groups:
        svc.action_repo.clear_serial_actions()
        svc.bus.publish(StudioEvent.ACTION_LIB_UPDATED, None)
        msg = "LoRa 串口未连接或机载端尚未返回 dance_map，未加载真实动作"
        svc.notify(msg, "warn")
        return False, 0, msg

    cnt = svc.action_repo.replace_serial_actions(groups)
    svc.bus.publish(StudioEvent.ACTION_LIB_UPDATED, None)
    msg = f"已从串口同步 {cnt} 个真实机载动作"
    svc.notify(msg, "ok")
    return True, cnt, msg


def bind_trajectory_tracks_op(
    svc: StudioStateService,
    traj_id: int,
    track_nos: List[int],
    sync_to_timeline: bool = True,
) -> int:
    """Bind a saved trajectory to one or more robot track numbers and optionally place non-overlapping blocks."""
    traj = svc.trajectories.get(traj_id) or svc.traj_repo.get_trajectory(traj_id)
    if traj is None:
        return 0
    clean_nos = sorted({int(n) for n in track_nos if int(n) > 0})
    traj.bound_track_nos = clean_nos
    svc.traj_repo.upsert_trajectory(traj)

    added = 0
    if sync_to_timeline:
        by_no = {t.track_no: t for t in svc.tracks}
        for rno in clean_nos:
            tr = by_no.get(rno)
            if tr is None or tr.id is None or tr.locked:
                continue
            already = any(b.track_id == tr.id and b.block_type == "trajectory" and b.ref_id == traj_id for b in svc.blocks)
            if already:
                continue
            t0 = svc.next_track_end_time(tr.id)
            blk = TimelineBlockEntity(
                task_id=svc.task.id or 1, track_id=tr.id, block_type="trajectory",
                ref_id=traj.id or 0, code_no=str(traj.no), title=traj.name,
                start_time=t0, duration=traj.duration,
            )
            svc.commit_block_change(None, blk, f"绑定轨迹 {traj.name} -> {tr.name}")
            added += 1

    svc.reload_all()
    svc.bus.publish(StudioEvent.TRAJECTORY_LIB_UPDATED, traj_id)
    return added
