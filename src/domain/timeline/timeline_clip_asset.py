"""
@file: src/domain/timeline/timeline_clip_asset.py
@brief: 编排时间轴 Clip 领域模型、轨道类型定义与时间换算契约
@exports: TimelineClipAsset, TimelineClip, TrackLayerType, compute_trajectory_duration_ms
"""
from dataclasses import asdict, dataclass
import math
from typing import Any, Dict


class TrackLayerType:
    """双子层轨道层级定义"""
    ACTION = "UPPER_ACTION"       # 上层：舞蹈 / 肢体动作
    TRAJECTORY = "LOWER_TRAJ"     # 下层：移动轨迹 / 阵型轨迹


def compute_trajectory_duration_ms(length_m: float, recommended_speed_mps: float = 1.0) -> int:
    """根据空间弧长 (m) 与推荐线速度 (m/s) 确定性换算时间轴时长 (ms)，杜绝米数当秒数"""
    speed = max(0.05, float(recommended_speed_mps))
    dist = max(0.0, float(length_m))
    sec = dist / speed
    return max(500, int(round(sec * 1000.0)))


@dataclass
class TimelineClipAsset:
    """时间轴 Clip 领域实体：记录机器人执行目标、子层级、素材引用、绝对毫秒时序与拉伸约束"""
    clip_id: str
    task_name: str = "默认任务1"
    robot_id: str = "1"
    track_layer: str = TrackLayerType.ACTION
    ref_id: str = ""
    name: str = ""
    start_ms: int = 0
    duration_ms: int = 2000
    allow_stretch: bool = True
    is_group: bool = False
    project_id: str = ""
    version: int = 1

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.duration_ms

    @property
    def start_s(self) -> float:
        return round(self.start_ms / 1000.0, 3)

    @property
    def duration_s(self) -> float:
        return round(self.duration_ms / 1000.0, 3)

    def validate(self) -> None:
        """核心时序与绑定契约强校验"""
        if not self.clip_id or not str(self.clip_id).strip():
            raise ValueError("Clip ID 不能为空")
        if not self.robot_id or not str(self.robot_id).strip():
            raise ValueError("执行目标 robot_id 不能为空")
        if self.track_layer not in (TrackLayerType.ACTION, TrackLayerType.TRAJECTORY):
            raise ValueError(f"非法的轨道子层级: '{self.track_layer}'")
        if self.start_ms < 0:
            raise ValueError(f"起始时间必须 >= 0，得到: {self.start_ms} ms")
        if self.duration_ms < 200:
            raise ValueError(f"Clip 持续时间过短 (< 200ms)，得到: {self.duration_ms} ms")
        if self.is_group and self.robot_id != "GROUP":
            raise ValueError(f"群组素材必须绑定至群组轨道 (GROUP)，当前目标: '{self.robot_id}'")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TimelineClipAsset":
        st_ms = int(d.get("start_ms", round(float(d.get("start_s", 0.0)) * 1000)))
        dur_ms = int(d.get("duration_ms", round(float(d.get("duration_s", 2.0)) * 1000)))
        r_id = str(d.get("robot_id", "1"))
        layer = str(d.get("track_layer", TrackLayerType.ACTION))
        if layer in ("ACTION", "UPPER_ACTION"):
            layer = TrackLayerType.ACTION
        elif layer in ("TRAJ", "TRAJECTORY", "LOWER_TRAJ"):
            layer = TrackLayerType.TRAJECTORY

        is_grp = bool(d.get("is_group", r_id.upper() == "GROUP" or "GROUP" in str(d.get("ref_id", "")).upper()))
        return cls(
            clip_id=str(d.get("clip_id", d.get("id", ""))),
            task_name=str(d.get("task_name", "默认任务1")),
            robot_id=r_id,
            track_layer=layer,
            ref_id=str(d.get("ref_id", "")),
            name=str(d.get("name", d.get("title", ""))),
            start_ms=max(0, st_ms),
            duration_ms=max(200, dur_ms),
            allow_stretch=bool(d.get("allow_stretch", True)),
            is_group=is_grp,
            project_id=str(d.get("project_id", "")),
            version=int(d.get("version", 1)),
        )


TimelineClip = TimelineClipAsset
