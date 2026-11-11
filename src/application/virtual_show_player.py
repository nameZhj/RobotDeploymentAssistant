"""
@file: src/application/virtual_show_player.py
@brief: 60Hz 舞台虚拟演播播放器与多机全身正向运动学协同推进服务
@exports: VirtualShowPlayer, virtual_show_player
"""
from typing import Any, Callable, Dict, List, Optional
from src.domain.kinematics.g1_fk_motion_blender import G1MotionBlender


class VirtualShowPlayer:
    """60Hz 演播推进控制器：支持倍速、拖拽Seek、循环及全场多机正向运动学实时采样"""

    def __init__(self, blender: Optional[G1MotionBlender] = None) -> None:
        self.blender = blender or G1MotionBlender()
        self.fps = 60
        self.frame_ms = int(1000 / self.fps)  # 16ms
        self._current_time_ms: int = 0
        self._duration_ms: int = 10000
        self._speed: float = 1.0
        self._loop: bool = True
        self._is_playing: bool = False

        self._init_points: List[Dict[str, Any]] = []
        self._track_state: List[Dict[str, Any]] = []
        self._traj_map: Dict[int, Any] = {}
        self._robot_ids: List[int] = []

        self._tick_listeners: List[Callable[[int, Dict[int, Dict[str, Any]]], None]] = []
        self._latest_states: Dict[int, Dict[str, Any]] = {}

    def load_scene(
        self,
        init_points: List[Dict[str, Any]],
        track_state: List[Dict[str, Any]],
        traj_map: Dict[int, Any],
        duration_ms: int = 10000
    ) -> None:
        self._init_points = list(init_points)
        self._track_state = list(track_state)
        self._traj_map = dict(traj_map)
        self._duration_ms = max(1000, duration_ms)

        ids = {int(p.get("robot_id", 0)) for p in self._init_points}
        ids.update({int(b.get("robot_id", 0)) for b in self._track_state})
        self._robot_ids = sorted(list(ids)) or [1]
        self._current_time_ms = 0
        self.sample_now()

    def play(self) -> None:
        self._is_playing = True

    def pause(self) -> None:
        self._is_playing = False

    def stop(self) -> None:
        self._is_playing = False
        self.seek(0)

    def toggle_play(self) -> None:
        self._is_playing = not self._is_playing

    def is_playing(self) -> bool:
        return self._is_playing

    def set_speed(self, speed: float) -> None:
        self._speed = max(0.1, min(5.0, float(speed)))

    def get_speed(self) -> float:
        return self._speed

    def set_loop(self, loop: bool) -> None:
        self._loop = bool(loop)

    def get_current_time_ms(self) -> int:
        return self._current_time_ms

    def seek(self, time_ms: int) -> Dict[int, Dict[str, Any]]:
        self._current_time_ms = max(0, min(self._duration_ms, int(time_ms)))
        return self.sample_now()

    def add_tick_listener(self, cb: Callable[[int, Dict[int, Dict[str, Any]]], None]) -> None:
        self._tick_listeners.append(cb)

    def sample_now(self) -> Dict[int, Dict[str, Any]]:
        t_sec = self._current_time_ms / 1000.0
        states: Dict[int, Dict[str, Any]] = {}
        for rid in self._robot_ids:
            st = self.blender.sample_robot_full_state(
                robot_id=rid,
                t_sec=t_sec,
                init_points=self._init_points,
                track_state=self._track_state,
                traj_map=self._traj_map
            )
            states[rid] = st

        self._latest_states = states
        for cb in self._tick_listeners:
            try:
                cb(self._current_time_ms, states)
            except Exception:
                pass
        return states

    def step(self, dt_ms: Optional[int] = None) -> Dict[int, Dict[str, Any]]:
        delta = dt_ms if dt_ms is not None else int(self.frame_ms * self._speed)
        next_t = self._current_time_ms + delta
        if next_t >= self._duration_ms:
            if self._loop:
                self._current_time_ms = next_t % max(1, self._duration_ms)
            else:
                self._current_time_ms = self._duration_ms
                self._is_playing = False
        else:
            self._current_time_ms = next_t

        return self.sample_now()


virtual_show_player = VirtualShowPlayer()

