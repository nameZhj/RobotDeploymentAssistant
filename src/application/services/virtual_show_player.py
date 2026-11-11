"""
@file: src/application/services/virtual_show_player.py
@brief: 60Hz 演播推进 Qt 信号集成播放器
@exports: VirtualShowPlayer
"""
import logging
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QObject, QTimer, Signal
from src.core.event_bus import event_bus
from src.domain.simulation.stage_performance_sampler import (
    AvatarSimulationState,
    StagePerformanceSampler,
)

logger = logging.getLogger("VirtualShowPlayer")


class VirtualShowPlayer(QObject):
    """
    60Hz virtual show orchestrator service driving multi-robot spatial trajectories
    and full-body articulated skeletal dance postures along the timeline.
    """

    tick = Signal(int, dict)
    timeChanged = Signal(int)
    playbackStateChanged = Signal(bool)
    posesUpdated = Signal(dict)
    playbackFinished = Signal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._fps = 60
        self._interval_ms = int(1000 / self._fps)  # 16ms
        self._timer = QTimer(self)
        self._timer.setInterval(self._interval_ms)
        self._timer.timeout.connect(self._on_timer_tick)

        self._current_time_ms: int = 0
        self._duration_ms: int = 10000
        self._is_playing: bool = False
        self._speed: float = 1.0
        self._loop: bool = True

        self._sampler = StagePerformanceSampler()
        self._robot_tracks: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        self._latest_poses: Dict[str, AvatarSimulationState] = {}
        self._init_default_tracks()

    def _init_default_tracks(self) -> None:
        self._robot_tracks = {
            "Robot_1": {
                "trajectories": [{
                    "start_ms": 1000,
                    "duration_ms": 5000,
                    "waypoints": [(-2.0, 0.0), (-1.5, 1.5), (0.0, 2.5), (1.5, 1.5), (2.0, 0.0)],
                }],
                "actions": [
                    {"name": "POPPING1", "start_ms": 1000, "duration_ms": 3000},
                    {"name": "POPPING2", "start_ms": 4500, "duration_ms": 2500},
                ],
            },
            "Robot_2": {
                "trajectories": [{
                    "start_ms": 1500,
                    "duration_ms": 5000,
                    "waypoints": [(2.0, 0.0), (1.5, -1.5), (0.0, -2.5), (-1.5, -1.5), (-2.0, 0.0)],
                }],
                "actions": [
                    {"name": "中华武术", "start_ms": 1500, "duration_ms": 4000},
                ],
            },
        }

    def set_track_data(self, robot_alias: str, trajectories: List[Dict[str, Any]], actions: List[Dict[str, Any]]) -> None:
        self._robot_tracks[robot_alias] = {
            "trajectories": trajectories,
            "actions": actions,
        }

    def set_tracks(self, tracks: Dict[str, Dict[str, Any]]) -> None:
        """批量全量设置机群编排轨道并刷新当前帧"""
        self._robot_tracks = dict(tracks)
        self._sample_and_dispatch()

    def play(self) -> None:
        if not self._is_playing:
            self._is_playing = True
            self._timer.start()
            self.playbackStateChanged.emit(True)
            event_bus.publish("VIRTUAL_SHOW_PLAYING", {"is_playing": True, "time_ms": self._current_time_ms})
            logger.info("VirtualShowPlayer started 60Hz playback loop.")

    def resume(self) -> None:
        """从当前暂停的时间戳继续播放"""
        self.play()

    def pause(self) -> None:
        if self._is_playing:
            self._is_playing = False
            self._timer.stop()
            self.playbackStateChanged.emit(False)
            event_bus.publish("VIRTUAL_SHOW_PLAYING", {"is_playing": False, "time_ms": self._current_time_ms})
            logger.info("VirtualShowPlayer paused.")

    def stop(self) -> None:
        self.pause()
        self.seek(0)

    def cleanup(self) -> None:
        """页面隐藏或窗口关闭时安全释放定时器生命周期"""
        self.pause()
        if self._timer.isActive():
            self._timer.stop()

    def toggle_play(self, play_state: Optional[bool] = None) -> None:
        target = (not self._is_playing) if play_state is None else play_state
        if target:
            self.play()
        else:
            self.pause()

    def seek(self, time_ms: int) -> None:
        self._current_time_ms = max(0, min(self._duration_ms, time_ms))
        self._sample_and_dispatch()

    def set_speed(self, speed: float) -> None:
        self._speed = max(0.1, min(5.0, speed))

    def get_speed(self) -> float:
        return self._speed

    def is_paused(self) -> bool:
        return not self._is_playing

    def set_loop(self, loop: bool) -> None:
        self._loop = loop

    def set_duration_ms(self, duration_ms: int) -> None:
        self._duration_ms = max(1000, duration_ms)

    def is_playing(self) -> bool:
        return self._is_playing

    def get_current_time_ms(self) -> int:
        return self._current_time_ms

    def get_current_time_s(self) -> float:
        return round(self._current_time_ms / 1000.0, 3)

    def get_latest_poses(self) -> Dict[str, AvatarSimulationState]:
        return self._latest_poses

    def _on_timer_tick(self) -> None:
        step = int(self._interval_ms * self._speed)
        next_time = self._current_time_ms + step

        if next_time >= self._duration_ms:
            if self._loop:
                self._current_time_ms = 0
            else:
                self._current_time_ms = self._duration_ms
                self.pause()
                self._sample_and_dispatch()
                self.playbackFinished.emit()
                return
        else:
            self._current_time_ms = next_time

        self._sample_and_dispatch()

    def _sample_and_dispatch(self) -> None:
        curr_s = self._current_time_ms / 1000.0
        poses: Dict[str, AvatarSimulationState] = {}

        for alias, track in self._robot_tracks.items():
            pose = self._sampler.sample_robot_pose(
                robot_alias=alias,
                current_time_s=curr_s,
                trajectory_blocks=track.get("trajectories", []),
                action_blocks=track.get("actions", []),
            )
            poses[alias] = pose

        self._latest_poses = poses
        self.posesUpdated.emit(poses)
        self.timeChanged.emit(self._current_time_ms)
        self.tick.emit(self._current_time_ms, poses)
        event_bus.publish("VIRTUAL_SHOW_TICK", {"time_ms": self._current_time_ms, "poses": poses})

