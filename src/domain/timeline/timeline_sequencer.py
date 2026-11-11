"""
@file: src/domain/timeline/timeline_sequencer.py
@brief: 双子层时间轴自动排布、插入顺延、8大编辑工具与50步撤销重做状态机
@exports: TimelineBlock, TimelineSequencerEngine, timeline_sequencer_engine
"""
import copy
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple
from src.domain.timeline.beat_and_collision_service import BpmTimeConverter, export_current_positions as _exp_pos


@dataclass
class TimelineBlock:
    """双子层时间轴块数据模型（支持动作块与轨迹块）"""
    block_id: str; robot_id: int; type: str; no: int; start_time: float; end_time: float; time: float
    name: str = ""; ignored: bool = False; dirty: bool = False; conflict: bool = False
    selected: bool = False; allow_move: bool = True; allow_stretch: bool = False; group_id: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TimelineBlock":
        st = float(d.get("start_time", d.get("start_s", 0.0)))
        dur = float(d.get("time", d.get("duration_s", max(0.0, float(d.get("end_time", st)) - st))))
        b_type = str(d.get("type", "active" if d.get("sub_layer", "ACTION") == "ACTION" else "trajectory"))
        return cls(
            block_id=str(d.get("block_id", d.get("clip_id", ""))), robot_id=int(d.get("robot_id", d.get("track_id", 1))),
            type=b_type, no=int(d.get("no", d.get("ref_id", 0))), start_time=st, end_time=float(d.get("end_time", st + dur)),
            time=dur, name=str(d.get("name", d.get("title", ""))), ignored=bool(d.get("ignored", False)),
            dirty=bool(d.get("dirty", False)), conflict=bool(d.get("conflict", False)), selected=bool(d.get("selected", False)),
            allow_move=bool(d.get("allow_move", True)), allow_stretch=bool(d.get("allow_stretch", False)), group_id=int(d.get("group_id", 0))
        )


class TimelineSequencerEngine:
    """双子层编排状态机，负责动作与轨迹级联顺延、工具操作、BPM换算及历史栈"""

    def __init__(self, initial_clips: Optional[List[Dict[str, Any]]] = None) -> None:
        self.blocks: List[TimelineBlock] = [TimelineBlock.from_dict(c) for c in initial_clips] if initial_clips else []
        self._undo_stack: List[List[Dict[str, Any]]] = []
        self._redo_stack: List[List[Dict[str, Any]]] = []
        self._fragments: Dict[int, Dict[str, Any]] = {}
        self.max_history: int = 50
        self.playhead_s: float = 0.0

    @property
    def clips(self) -> List[Dict[str, Any]]:
        return [b.to_dict() for b in self.blocks]

    def _snapshot(self) -> None:
        self._undo_stack.append([b.to_dict() for b in self.blocks])
        if len(self._undo_stack) > self.max_history:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        self._redo_stack.append([b.to_dict() for b in self.blocks])
        self.blocks = [TimelineBlock.from_dict(d) for d in self._undo_stack.pop()]
        self.validate_conflicts()
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        self._undo_stack.append([b.to_dict() for b in self.blocks])
        self.blocks = [TimelineBlock.from_dict(d) for d in self._redo_stack.pop()]
        self.validate_conflicts()
        return True

    def validate_conflicts(self) -> None:
        for b in self.blocks:
            b.conflict = False
        by_r: Dict[int, List[TimelineBlock]] = {}
        for b in self.blocks:
            if not b.ignored:
                by_r.setdefault(b.robot_id, []).append(b)
        for r_blks in by_r.values():
            for i, b1 in enumerate(r_blks):
                for j in range(i + 1, len(r_blks)):
                    b2 = r_blks[j]
                    if max(b1.start_time, b2.start_time) < min(b1.end_time, b2.end_time) - 1e-4:
                        if b1.type == b2.type or (not b1.allow_move or not b2.allow_move):
                            b1.conflict = b2.conflict = True

    def add_block(self, block: TimelineBlock) -> bool:
        self._snapshot()
        self.blocks.append(block)
        self.validate_conflicts()
        return True

    def insert_active_block(
        self, robot_id: int, no: int, time: float, start_time: Optional[float] = None,
        name: str = "", allow_move: bool = True, allow_stretch: bool = False
    ) -> TimelineBlock:
        self._snapshot()
        st = start_time if start_time is not None else max([b.end_time for b in self.blocks if b.robot_id == robot_id and b.type == "active"], default=0.0)
        if start_time is not None:
            for b in [b for b in self.blocks if b.robot_id == robot_id and b.start_time >= st]:
                b.start_time, b.end_time = round(b.start_time + time, 3), round(b.start_time + time + b.time, 3)
        blk = TimelineBlock(f"act_{robot_id}_{no}_{int(st * 100)}", robot_id, "active", no, st, st + time, time, name, allow_move=allow_move, allow_stretch=allow_stretch)
        self.blocks.append(blk)
        self.validate_conflicts()
        return blk

    def insert_trajectory_block(
        self, robot_id: int, group_bound_track_id: Optional[int], no: int, time: float,
        start_time: Optional[float] = None, name: str = "轨迹", allow_stretch: bool = False
    ) -> TimelineBlock:
        if group_bound_track_id is not None and group_bound_track_id != robot_id:
            raise ValueError(f"轨迹所属分组绑定轨道 {group_bound_track_id} 与目标轨道 {robot_id} 不匹配！")
        self._snapshot()
        st = start_time if start_time is not None else max([b.end_time for b in self.blocks if b.robot_id == robot_id], default=0.0)
        subs = [b for b in self.blocks if b.robot_id == robot_id and b.start_time >= st]
        if subs and min(b.start_time for b in subs) < st + time:
            shift = (st + time) - min(b.start_time for b in subs)
            for b in subs:
                b.start_time, b.end_time = round(b.start_time + shift, 3), round(b.start_time + shift + b.time, 3)
        blk = TimelineBlock(f"traj_{robot_id}_{no}_{int(st * 100)}", robot_id, "trajectory", no, st, st + time, time, name, allow_stretch=allow_stretch)
        self.blocks.append(blk)
        self.validate_conflicts()
        return blk

    def split_block(self, block_id: str, split_time_s: float) -> Tuple[TimelineBlock, TimelineBlock]:
        t = next((b for b in self.blocks if b.block_id == block_id), None)
        if not t or split_time_s <= t.start_time or split_time_s >= t.end_time:
            raise ValueError(f"分割时间 {split_time_s} 不在片段有效区间内")
        self._snapshot()
        ldur, rdur = split_time_s - t.start_time, t.end_time - split_time_s
        t.time, t.end_time = round(ldur, 3), round(split_time_s, 3)
        rb = copy.deepcopy(t)
        rb.block_id, rb.start_time, rb.end_time, rb.time = f"{t.block_id}_split", round(split_time_s, 3), round(split_time_s + rdur, 3), round(rdur, 3)
        self.blocks.append(rb)
        self.validate_conflicts()
        return t, rb

    def move_block(self, block_id: str, new_start_s: float, snap_enabled: bool = True) -> float:
        b = next((x for x in self.blocks if x.block_id == block_id), None)
        if not b:
            return 0.0
        self._snapshot()
        st = max(0.0, float(new_start_s))
        if snap_enabled:
            snaps = [c for ob in self.blocks if ob.block_id != block_id and ob.robot_id == b.robot_id for c in (ob.start_time, ob.end_time) if abs(c - st) < 0.25]
            if snaps:
                st = min(snaps, key=lambda c: abs(c - st))
        b.start_time, b.end_time, b.dirty = round(st, 3), round(st + b.time, 3), True
        self.validate_conflicts()
        return b.start_time

    def stretch_block(self, block_id: str, new_duration_s: float) -> bool:
        b = next((x for x in self.blocks if x.block_id == block_id), None)
        if not b:
            return False
        if not b.allow_stretch:
            raise ValueError(f"块 [{b.block_id}] 设置了禁止拉伸 (allow_stretch=False)！")
        self._snapshot()
        b.time, b.end_time, b.dirty = max(0.1, float(new_duration_s)), round(b.start_time + max(0.1, float(new_duration_s)), 3), True
        self.validate_conflicts()
        return True

    def delete_block(self, block_id: str) -> bool:
        idx = next((i for i, x in enumerate(self.blocks) if x.block_id == block_id), None)
        if idx is None: return False
        self._snapshot(); self.blocks.pop(idx); self.validate_conflicts(); return True

    def delete_track(self, robot_id: int) -> bool:
        self._snapshot(); self.blocks = [b for b in self.blocks if b.robot_id != robot_id]
        self.validate_conflicts(); return True

    def toggle_ignore_by_type(self, block_type: str) -> bool:
        targets = [b for b in self.blocks if b.type == block_type]
        if not targets: return False
        self._snapshot(); new_state = not all(b.ignored for b in targets)
        for b in targets: b.ignored = new_state
        self.validate_conflicts(); return True

    def export_sequence_by_range(
        self, start_s: float, end_s: float, robot_ids: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        r_set = set(robot_ids) if robot_ids else None
        res: List[Dict[str, Any]] = []
        for b in self.blocks:
            if (not r_set or b.robot_id in r_set) and max(b.start_time, start_s) < min(b.end_time, end_s) - 1e-4:
                d = b.to_dict()
                d["start_time"] = round(max(0.0, b.start_time - start_s), 3)
                d["end_time"] = round(d["start_time"] + b.time, 3)
                res.append(d)
        return res

    def import_sequence_by_range(
        self, sequence: List[Dict[str, Any]], target_start_s: float, target_robot_map: Optional[Dict[int, int]] = None
    ) -> List[str]:
        self._snapshot(); rmap = target_robot_map or {}; added: List[str] = []
        for d in sequence:
            c = TimelineBlock.from_dict(d)
            c.robot_id = rmap.get(c.robot_id, c.robot_id)
            c.start_time, c.end_time = round(target_start_s + d.get("start_time", 0.0), 3), round(target_start_s + d.get("start_time", 0.0) + c.time, 3)
            c.block_id = f"imp_{c.type}_{c.robot_id}_{c.no}_{int(c.start_time * 100)}"
            self.blocks.append(c); added.append(c.block_id)
        self.validate_conflicts(); return added

    def refresh_trajectory_snapshots(self, traj_dict_map: Dict[int, Any]) -> None:
        self._snapshot()
        for b in self.blocks:
            if b.type == "trajectory" and b.no in traj_dict_map:
                info = traj_dict_map[b.no]
                dur = float(info.get("time", b.time)) if isinstance(info, dict) else b.time
                b.time, b.end_time, b.dirty = dur, round(b.start_time + dur, 3), True
        self.validate_conflicts()

    def save_fragment(self, frag_no: int, name: str, blocks: List[TimelineBlock]) -> bool:
        if not (1 <= int(frag_no) <= 99):
            raise ValueError(f"片段编号必须在 01~99 范围内，输入为: {frag_no}")
        min_st = min((b.start_time for b in blocks), default=0.0)
        norm = [{**b.to_dict(), "start_time": round(b.start_time - min_st, 3), "end_time": round(b.start_time - min_st + b.time, 3)} for b in blocks]
        self._fragments[int(frag_no)] = {"frag_no": int(frag_no), "name": name, "blocks": norm}
        return True

    def load_fragment(self, frag_no: int) -> Optional[Dict[str, Any]]:
        return copy.deepcopy(self._fragments.get(int(frag_no)))

    def sec_to_measure_beat(self, sec: float, bpm: float = 120.0, numerator: int = 4) -> str:
        return BpmTimeConverter(bpm, numerator).sec_to_measure_beat(sec)

    def measure_beat_to_sec(self, mb_str: str, bpm: float = 120.0, numerator: int = 4) -> float:
        return BpmTimeConverter(bpm, numerator).measure_beat_to_sec(mb_str)

    def export_current_positions(
        self, t_sec: float, robot_ids: List[int], init_points: List[Dict[str, Any]], traj_dict_map: Dict[int, Any]
    ) -> List[Dict[str, Any]]:
        return _exp_pos(t_sec, robot_ids, init_points, [b.to_dict() for b in self.blocks], traj_dict_map)


timeline_sequencer_engine = TimelineSequencerEngine()
