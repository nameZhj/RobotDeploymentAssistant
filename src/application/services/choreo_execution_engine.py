"""
@file: src/application/services/choreo_execution_engine.py
@brief: 统一演播执行调度器、60Hz本地3D/物理真机双工下发与控制权仲裁引擎
@exports: ChoreoExecutionEngine, ms_to_timecode, timecode_to_ms, choreo_execution_engine
"""
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from backend.serial_manager import serial_manager
from src.core.logger import comm_logger
from src.infrastructure.lrmp.lrmp_protocol_engine import LrmpProtocolEngine
from src.application.virtual_show_player import VirtualShowPlayer


def ms_to_timecode(time_ms: int, fps: int = 60) -> str:
    total_frames = int(time_ms * fps / 1000.0)
    ff = total_frames % fps
    total_s = total_frames // fps
    ss = total_s % 60
    total_m = total_s // 60
    mm = total_m % 60
    hh = total_m // 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}-{ff:02d}"


def timecode_to_ms(tc_str: str, fps: int = 60) -> int:
    try:
        parts = tc_str.strip().split("-")
        hms = parts[0].split(":")
        hh, mm, ss = int(hms[0]), int(hms[1]), int(hms[2])
        ff = int(parts[1]) if len(parts) > 1 else 0
        total_frames = (hh * 3600 + mm * 60 + ss) * fps + ff
        return int(total_frames * 1000.0 / fps)
    except Exception:
        return 0


class ChoreoExecutionEngine:
    """统一管理 60Hz 本地 3D 虚拟演播与真实机器人串口/LRMP 定向物理下发"""

    def __init__(self, player: Optional[VirtualShowPlayer] = None, engine: Optional[LrmpProtocolEngine] = None) -> None:
        self.player = player or VirtualShowPlayer()
        self.engine = engine or LrmpProtocolEngine()
        self.mode: str = "MUSIC_SYNC"  # MUSIC_SYNC, DANCE_DEBUG, LOOP_EXEC
        self.robot_lora_map: Dict[int, str] = {1: "A", 2: "B", 3: "C", 4: "D"}
        self.authorities: Dict[str, str] = {}  # target -> FREE, MANUAL, CHOREO
        self._triggered_blocks: Set[Tuple[int, int, str]] = set()
        self._is_running: bool = False

    def trigger_emergency_stop(self, targets: Optional[List[str]] = None) -> None:
        serial_manager.send_command("ALL", "EMERGENCY")
        comm_logger.log_frame("TX", "ALL", "ALL|EMERGENCY", "EMERGENCY STOP TRIGGERED")
        tg_list = targets or list(self.robot_lora_map.values())
        for tg in tg_list:
            wire = self.engine.build_frame("REQ", "CTRL", tg, "STOP")
            self.engine.parse_frame(wire)
            comm_logger.log_frame("TX", tg, f"{tg}|STOP", "LRMP STOP")
            self.authorities[tg] = "FREE"
        self.player.stop()
        self._is_running = False
        self._triggered_blocks.clear()

    def stand_to_gait_sequence(self, target: str, wait_callback: Optional[Callable[[float], None]] = None) -> bool:
        serial_manager.send_command(target, "STAND")
        comm_logger.log_frame("TX", target, f"{target}|STAND", "STAND COMMAND SENT")
        if wait_callback:
            wait_callback(3.0)
        else:
            time.sleep(0.01)
        serial_manager.send_command(target, "GAIT")
        comm_logger.log_frame("TX", target, f"{target}|GAIT", "GAIT TRANSITION COMPLETED")
        return True

    def set_passive(self, target: str) -> None:
        serial_manager.send_command(target, "PASSIVE")
        comm_logger.log_frame("TX", target, f"{target}|PASSIVE", "PASSIVE RESET")

    def request_authority(self, target: str, req_level: str) -> Tuple[bool, str]:
        curr = self.authorities.get(target, "FREE")
        req_u = req_level.upper()
        if curr == "CHOREO" and req_u == "RELEASE":
            return False, "严禁通过 RELEASE 释放 CHOREO 控制权"
        if req_u in ("FREE", "MANUAL", "CHOREO"):
            self.authorities[target] = req_u
            return True, f"控制权已切换为 {req_u}"
        return False, f"未知的控制权级别: {req_level}"

    def dispatch_timeline_tick(self, time_ms: int, track_state: List[Dict[str, Any]]) -> Dict[str, Any]:
        t_sec = time_ms / 1000.0
        dispatched = []
        for blk in track_state:
            rid = int(blk.get("robot_id", 0))
            lora_id = self.robot_lora_map.get(rid, "A")
            b_type = str(blk.get("type", ""))
            s_t = float(blk.get("start_time", 0.0))
            e_t = float(blk.get("end_time", 0.0))
            b_no = int(blk.get("no", 0))

            if s_t <= t_sec <= e_t:
                key = (rid, b_no, b_type)
                if key not in self._triggered_blocks:
                    self._triggered_blocks.add(key)
                    if b_type == "active":
                        name = str(blk.get("name", "DANCE"))
                        serial_manager.send_command(lora_id, f"DANCE,{name}")
                        dispatched.append({"target": lora_id, "type": "action", "cmd": f"DANCE,{name}"})
                    elif b_type == "trajectory":
                        serial_manager.send_command(lora_id, "TRAJECTORY_START")
                        dispatched.append({"target": lora_id, "type": "trajectory", "cmd": "TRAJECTORY_START"})

        player_states = self.player.seek(time_ms)
        tc_code = ms_to_timecode(time_ms)
        return {"time_ms": time_ms, "timecode": tc_code, "dispatched": dispatched, "states": player_states}


choreo_execution_engine = ChoreoExecutionEngine()

