# @file: src/ui/choreography/timeline_context_menus.py
# @brief: Track header and task-chain node right-click context menus, chain reordering, and split/undo helpers.
# @exports: show_track_context_menu, show_block_context_menu, split_block_at_time, reorder_block_in_chain

from __future__ import annotations

import copy
from typing import Optional
from PySide6.QtWidgets import QMenu, QWidget

from src.core.event_bus import StudioEvent
from src.core.undo_stack import CallableUndoCommand
from src.domain.timeline_entities import TimelineBlockEntity
from src.domain.track_entities import TrackEntity
from src.services.studio_state_service import StudioStateService


def show_track_context_menu(
    parent: QWidget, state: StudioStateService, tr: Optional[TrackEntity], global_pt
) -> Optional[int]:
    """Show right-click track menu (Edit, Mute, Lock, Delete); return remaining selected track_id."""
    if tr is None or tr.id is None:
        return None
    menu = QMenu(parent)
    act_edit = menu.addAction(f"编辑 {tr.name} [{tr.target_id}]...")
    act_mute = menu.addAction("取消静音" if tr.muted else "静音轨道 (Mute)")
    act_lock = menu.addAction("解锁轨道" if tr.locked else "锁定轨道 (Lock)")
    act_del = menu.addAction("删除机器人轨道")
    chosen = menu.exec(global_pt)
    if chosen == act_edit:
        from src.ui.modals.add_track_dialog import AddTrackDialog
        AddTrackDialog(state, parent, track=tr).exec()
    elif chosen == act_mute:
        tr.muted = not tr.muted
        state.scene_repo.upsert_track(tr)
        state.reload_all()
        state.bus.publish(StudioEvent.TRACKS_UPDATED, tr.id)
    elif chosen == act_lock:
        tr.locked = not tr.locked
        state.scene_repo.upsert_track(tr)
        state.reload_all()
        state.bus.publish(StudioEvent.TRACKS_UPDATED, tr.id)
    elif chosen == act_del:
        name = state.delete_track_with_undo(tr.id)
        if name:
            state.notify(f"已删除轨道 {name} (支持 Ctrl+Z 撤销)", "info")
            return None
    return tr.id


def show_block_context_menu(lane_view, blk: TimelineBlockEntity, global_pt) -> None:
    menu = QMenu(lane_view)
    a_prev = menu.addAction("前移节点 (←)")
    a_next = menu.addAction("后移节点 (→)")
    menu.addSeparator()
    a_split = menu.addAction("在当前游标处分割")
    a_dup = menu.addAction("追加复制节点")
    a_ign = menu.addAction("恢复启用" if blk.is_ignored else "忽略跳过")
    a_del = menu.addAction("删除节点 (Del)")
    chosen = menu.exec(global_pt)
    if chosen == a_prev:
        reorder_block_in_chain(lane_view.state, blk, -1)
    elif chosen == a_next:
        reorder_block_in_chain(lane_view.state, blk, +1)
    elif chosen == a_split:
        lane_view.split_selected_or_at_playhead()
    elif chosen == a_dup:
        lane_view.duplicate_selected_block()
    elif chosen == a_ign:
        lane_view.toggle_ignore_selected_block()
    elif chosen == a_del:
        lane_view.delete_selected_block()


def reorder_block_in_chain(state: StudioStateService, blk: TimelineBlockEntity, delta: int) -> bool:
    """Swap a task-chain node with its left (-1) or right (+1) neighbor and repack sequentially with Undo/Redo."""
    ordered = sorted(
        (b for b in state.blocks if b.track_id == blk.track_id and not b.is_ignored),
        key=lambda b: (round(b.start_time, 4), b.id or 0),
    )
    idx = next((i for i, b in enumerate(ordered) if b.id == blk.id), -1)
    nxt = idx + delta
    if idx < 0 or not (0 <= nxt < len(ordered)):
        return False
    before_snaps = [copy.deepcopy(b) for b in ordered]
    swapped = [copy.deepcopy(b) for b in ordered]
    swapped[idx], swapped[nxt] = swapped[nxt], swapped[idx]
    cursor = 0.0
    for item in swapped:
        item.start_time = round(cursor, 2)
        cursor += max(0.5, float(item.duration))

    def _apply(snaps) -> None:
        for item in snaps:
            state.scene_repo.upsert_block(copy.deepcopy(item))
        state.reload_all()
        state.bus.publish(StudioEvent.TIMELINE_UPDATED, blk.id)

    direction = "前移" if delta < 0 else "后移"
    state.undo_stack.push(
        CallableUndoCommand(f"{direction}任务节点 {blk.title}", lambda: _apply(swapped), lambda: _apply(before_snaps)),
        execute_redo=True,
    )
    return True


def split_block_at_time(state: StudioStateService, cand: TimelineBlockEntity, t: float) -> None:
    snap_before = copy.deepcopy(cand)
    left_dur, right_dur = round(t - cand.start_time, 2), round(cand.end_time - t, 2)
    ref_holder = {"right_id": None}

    def _redo() -> None:
        left = copy.deepcopy(snap_before)
        left.duration = left_dur
        state.scene_repo.upsert_block(left)
        right = copy.deepcopy(snap_before)
        right.id, right.start_time, right.duration = None, round(t, 2), right_dur
        ref_holder["right_id"] = state.scene_repo.upsert_block(right).id
        state.reload_all()
        state.bus.publish(StudioEvent.TIMELINE_UPDATED, None)

    def _undo() -> None:
        if ref_holder["right_id"] is not None:
            state.scene_repo.delete_block(ref_holder["right_id"])
        state.scene_repo.upsert_block(snap_before)
        state.reload_all()
        state.bus.publish(StudioEvent.TIMELINE_UPDATED, None)

    state.undo_stack.push(CallableUndoCommand(f"分割 {cand.title}", _redo, _undo), execute_redo=True)
