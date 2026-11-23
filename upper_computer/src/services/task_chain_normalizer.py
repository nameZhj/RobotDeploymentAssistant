# @file: src/services/task_chain_normalizer.py
# @brief: Pure task-chain sequence ordering, formatting ("A - B - C"), and lower-computer payload compiler.
# @exports: ordered_track_chain, sequence_track_chain, format_track_chain_summary, active_chain_node_label, compile_track_chain_payload

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence
import numpy as np

from src.domain.action_entities import ActionEntity
from src.domain.timeline_entities import TimelineBlockEntity
from src.domain.track_entities import TrackEntity
from src.domain.trajectory_entities import TrajectoryEntity


def ordered_track_chain(blocks: Sequence[TimelineBlockEntity], track_id: int) -> List[TimelineBlockEntity]:
    """Return ordered task-chain nodes for a single robot track."""
    items = [b for b in blocks if b.track_id == track_id and not b.is_ignored]
    items.sort(key=lambda b: (round(b.start_time, 4), b.id or 0))
    return items


def sequence_track_chain(blocks: Sequence[TimelineBlockEntity], track_id: int) -> List[TimelineBlockEntity]:
    """Pack active nodes sequentially end-to-end with zero overlaps to form a continuous task chain."""
    ordered = ordered_track_chain(blocks, track_id)
    cursor = 0.0
    for blk in ordered:
        blk.start_time = round(cursor, 2)
        blk.duration = max(0.5, float(blk.duration))
        cursor += blk.duration
    return ordered


def format_track_chain_summary(blocks: Sequence[TimelineBlockEntity], track_id: Optional[int] = None) -> str:
    """Format chain strictly as pure action/nav titles: '导航到点1 - 太极 - 街舞 - 导航到点2'."""
    if track_id is not None:
        nodes = ordered_track_chain(blocks, track_id)
    else:
        nodes = sorted((b for b in blocks if not b.is_ignored), key=lambda b: (b.track_id, b.start_time, b.id or 0))
    return " - ".join(n.title for n in nodes if n.title) if nodes else "空任务链"


def active_chain_node_label(blocks: Sequence[TimelineBlockEntity], cursor: float, is_playing: bool = False) -> str:
    """Return currently active task-chain action name at preview cursor without showing seconds or step index."""
    ordered = [b for b in blocks if not b.is_ignored]
    if not ordered:
        return "空任务链"
    if cursor <= 1e-6 and not is_playing:
        return "原点待命"
    active = [b for b in ordered if b.start_time <= cursor <= b.end_time]
    if active:
        names = []
        for b in active:
            if b.title and b.title not in names:
                names.append(b.title)
        return " | ".join(names[:3])
    return "任务链完成"


def compile_track_chain_payload(
    track: TrackEntity,
    blocks: Sequence[TimelineBlockEntity],
    trajectories: Dict[int, TrajectoryEntity],
    sampled_trajs: Dict[int, np.ndarray],
    actions_by_id: Dict[int, ActionEntity],
    scene_id: int = 1,
    plan_id: str = "8001",
) -> Dict[str, Any]:
    """Compile a robot track's sequential blocks into an arrival-triggered lower-computer task chain JSON."""
    nodes = ordered_track_chain(blocks, track.id or 0)
    chain_nodes: List[Dict[str, Any]] = []
    cur_pose = (float(track.init_x), float(track.init_y), float(track.init_yaw))

    for blk in nodes:
        if blk.block_type == "trajectory":
            traj = trajectories.get(blk.ref_id)
            arr = sampled_trajs.get(blk.ref_id)
            tx, ty, tyaw = cur_pose
            waypoints: List[Dict[str, float]] = []
            if arr is not None and len(arr) > 0:
                tx, ty, tyaw = float(arr[-1, 1]), float(arr[-1, 2]), float(arr[-1, 3])
            elif traj and traj.control_points:
                last_cp = traj.control_points[-1]
                tx, ty, tyaw = float(last_cp.x), float(last_cp.y), float(last_cp.yaw)
            if traj and traj.control_points:
                waypoints = [{"x": float(p.x), "y": float(p.y), "yaw": float(p.yaw)} for p in traj.control_points]
            cur_pose = (tx, ty, tyaw)
            chain_nodes.append({
                "node_type": "trajectory",
                "title": blk.title,
                "target_x": round(tx, 4),
                "target_y": round(ty, 4),
                "target_yaw": round(tyaw, 4),
                "wait_for_arrival": True,
                "run_mode": traj.run_mode if traj else 504,
                "waypoints": waypoints,
            })
        else:
            act = actions_by_id.get(blk.ref_id)
            lrmp_code = (act.lrmp_code if act else "") or str(blk.extra.get("lrmpCode") or blk.code_no or blk.title)
            chain_nodes.append({
                "node_type": "action",
                "title": blk.title,
                "lrmp_code": lrmp_code.strip().upper(),
                "trigger": "AFTER_PREV_COMPLETED",
            })

    return {
        "scene_id": scene_id,
        "plan_id": plan_id,
        "target_id": track.target_id,
        "robot_ip": track.robot_ip,
        "origin_pose": {
            "x": float(track.init_x),
            "y": float(track.init_y),
            "yaw": float(track.init_yaw),
        },
        "chain_summary": " - ".join(n["title"] for n in chain_nodes),
        "chain_nodes": chain_nodes,
    }
