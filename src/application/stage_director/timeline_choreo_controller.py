"""
@file: src/application/stage_director/timeline_choreo_controller.py
@brief: 时间轴编排控制器：素材拖放放置、轨道匹配校验、持续时间微调与撤销恢复
@exports: TimelineChoreoController
"""
import time
from typing import Any, Dict, List, Optional, Tuple
from src.domain.timeline.timeline_clip_asset import (
    TimelineClipAsset,
    TrackLayerType,
    compute_trajectory_duration_ms,
)
from src.infrastructure.storage.timeline_clip_sqlite_adapter import TimelineClipSqliteAdapter


class TimelineChoreoController:
    """负责时间轴编排业务：单机/群组轨道规则仲裁、时序换算、拖放放置与持久化同步"""

    def __init__(self, db_path: Optional[str] = None, task_name: str = "默认任务1") -> None:
        self.task_name = task_name
        self.adapter = TimelineClipSqliteAdapter(db_path)
        self._undo_stack: List[List[Dict[str, Any]]] = []
        self._redo_stack: List[List[Dict[str, Any]]] = []

    def create_clip_from_dropped_asset(
        self,
        asset_data: Dict[str, Any],
        target_track_id: str,
        target_sub_layer: str,
        start_ms: int
    ) -> Tuple[bool, str, Optional[TimelineClipAsset]]:
        """从素材库拖放数据在时间轴目标轨道与时间戳创建持久化 Clip"""
        raw_type = str(asset_data.get("asset_type", "")).upper()
        asset_id = str(asset_data.get("asset_id", asset_data.get("id", ""))).strip()
        name = str(asset_data.get("name", "未命名素材")).strip()
        st_ms = max(0, int(start_ms))

        # 1. 轨道与素材归属强规则校验
        is_group_asset = (raw_type == "GROUP_TRAJECTORY" or "GROUP" in raw_type)
        is_group_track = (str(target_track_id).upper() == "GROUP")

        if is_group_asset and not is_group_track:
            return False, "群组轨迹素材必须放置于群组轨道 (GROUP)，禁止绑定为单机器人轨迹", None

        if not is_group_asset and is_group_track:
            return False, "单机器人素材禁止直接绑定至群组编队轨道", None

        # 2. 子层级自动纠偏与绑定
        if is_group_asset:
            track_layer = TrackLayerType.TRAJECTORY
        elif raw_type in ("ACTION", "DANCE"):
            track_layer = TrackLayerType.ACTION
        else:
            track_layer = TrackLayerType.TRAJECTORY

        # 3. 时间语义与时长换算（绝对毫秒）
        if "duration_ms" in asset_data:
            dur_ms = int(asset_data["duration_ms"])
        elif "length_m" in asset_data:
            spd = float(asset_data.get("recommended_speed_mps", 1.0))
            dur_ms = compute_trajectory_duration_ms(float(asset_data["length_m"]), spd)
        else:
            dur_s = float(asset_data.get("duration", asset_data.get("time", 3.0)))
            dur_ms = max(500, int(round(dur_s * 1000.0)))

        # 4. 构建 Clip 实体并安全保存
        ts_suffix = int(time.time() * 1000) % 100000
        type_prefix = "grp" if is_group_asset else ("act" if track_layer == TrackLayerType.ACTION else "trj")
        clip_id = f"clip_{type_prefix}_{target_track_id}_{asset_id}_{st_ms}_{ts_suffix}"

        clip = TimelineClipAsset(
            clip_id=clip_id,
            task_name=self.task_name,
            robot_id=str(target_track_id),
            track_layer=track_layer,
            ref_id=asset_id,
            name=name,
            start_ms=st_ms,
            duration_ms=dur_ms,
            allow_stretch=bool(asset_data.get("allow_stretch", True)),
            is_group=is_group_asset,
        )

        try:
            self._record_snapshot()
            self.adapter.save_clip(clip)
            return True, f"已成功将 '{name}' 编排至轨道 {target_track_id}", clip
        except Exception as e:
            return False, f"时间轴 Clip 保存失败: {e}", None

    def move_clip(self, clip_id: str, new_start_ms: int) -> bool:
        """移动 Clip 的时间轴位置并持久化"""
        self._record_snapshot()
        return self.adapter.update_clip_position(clip_id, max(0, new_start_ms))

    def resize_clip(self, clip_id: str, new_duration_ms: int) -> bool:
        """调整 Clip 的持续时长并持久化"""
        clip = self.adapter.get_clip(clip_id)
        if not clip:
            return False
        if not clip.allow_stretch:
            return False
        self._record_snapshot()
        return self.adapter.update_clip_duration(clip_id, max(200, new_duration_ms))

    def delete_clip(self, clip_id: str) -> bool:
        """删除指定 Clip 并持久化释放素材引用"""
        self._record_snapshot()
        return self.adapter.delete_clip(clip_id)

    def list_clips(self) -> List[TimelineClipAsset]:
        return self.adapter.list_clips(self.task_name)

    def get_clip(self, clip_id: str) -> Optional[TimelineClipAsset]:
        return self.adapter.get_clip(clip_id)

    def _record_snapshot(self) -> None:
        try:
            curr = [c.to_dict() for c in self.list_clips()]
            self._undo_stack.append(curr)
            if len(self._undo_stack) > 50:
                self._undo_stack.pop(0)
            self._redo_stack.clear()
        except Exception:
            pass

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        curr = [c.to_dict() for c in self.list_clips()]
        self._redo_stack.append(curr)
        prev = self._undo_stack.pop()
        # 恢复状态
        for c in self.list_clips():
            self.adapter.delete_clip(c.clip_id)
        for d in prev:
            self.adapter.save_clip(TimelineClipAsset.from_dict(d))
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        curr = [c.to_dict() for c in self.list_clips()]
        self._undo_stack.append(curr)
        next_state = self._redo_stack.pop()
        for c in self.list_clips():
            self.adapter.delete_clip(c.clip_id)
        for d in next_state:
            self.adapter.save_clip(TimelineClipAsset.from_dict(d))
        return True
