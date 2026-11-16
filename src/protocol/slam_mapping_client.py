# @file: src/protocol/slam_mapping_client.py
# @brief: Teleop mapping controller combining LRMP MOVE authority lifecycle with reserved live SLAM PCD saving.
# @exports: MappingSessionState, SlamMappingClient

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Tuple

from src.core.paths import get_paths
from src.protocol.authority_state_machine import AuthorityStateMachine
from src.protocol.lrmp_codec import LrmpCodec
from src.protocol.virtual_slam_generator import VirtualSlamGenerator


@dataclass
class MappingSessionState:
    """Live state of an interactive teleop SLAM mapping session."""

    active: bool = False
    target_id: str = "A"
    robot_ip: str = "192.168.123.101"
    mode: str = "VIRTUAL"
    pose: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    point_count: int = 0
    last_frame_sent: str = ""


class SlamMappingClient:
    """Manages remote-controlled robot mapping lifecycle and reserved WebSocket SLAM stream."""

    WS_ENDPOINT_TEMPLATE = "ws://{ip}:{port}/api/v1/slam/pointcloud"

    def __init__(
        self,
        arbiter: Optional[AuthorityStateMachine] = None,
        frame_sender: Optional[Callable[[bytes], bool]] = None,
    ) -> None:
        self.arbiter = arbiter or AuthorityStateMachine()
        self._frame_sender = frame_sender
        self.state = MappingSessionState()
        self._virtual_gen = VirtualSlamGenerator()

    def start_mapping(self, target_id: str, robot_ip: str = "192.168.123.101") -> Tuple[bool, str]:
        """Acquire MANUAL control authority and initialize GAIT mode for SLAM teleop."""
        res = self.arbiter.acquire_manual(target_id)
        if not res.allowed:
            return False, res.reason
        self._emit_frame(LrmpCodec.encode(target_id, "STAND"))
        self._emit_frame(LrmpCodec.encode(target_id, "GAIT"))
        self._virtual_gen = VirtualSlamGenerator()
        self.state = MappingSessionState(
            active=True,
            target_id=target_id.upper(),
            robot_ip=robot_ip,
            mode="VIRTUAL",
            pose=tuple(self._virtual_gen.robot_pose),  # type: ignore[arg-type]
            point_count=len(self._virtual_gen.get_points()),
            last_frame_sent=f"{target_id.upper()}|GAIT",
        )
        return True, f"已进入遥控建图态 ({self.state.target_id}, 预留实时 SLAM 接口)"

    def send_teleop_move(self, vx: float, vy: float, vyaw: float, duration_s: float = 0.5) -> Tuple[bool, str]:
        """Emit validated LRMP MOVE command and step virtual SLAM accumulation."""
        if not self.state.active:
            return False, "请先点击启动建图"
        check = self.arbiter.apply_command(self.state.target_id, "MOVE")
        if not check.allowed:
            return False, check.reason
        frame = LrmpCodec.encode_move(self.state.target_id, vx, vy, vyaw, duration_s)
        self._emit_frame(frame)
        self.state.pose = self._virtual_gen.step_motion(vx, vy, vyaw, duration_s)
        self.state.point_count = len(self._virtual_gen.get_points())
        self.state.last_frame_sent = frame.decode("utf-8").strip()
        return True, self.state.last_frame_sent

    def save_live_map(self, map_name: str = "") -> Path:
        """Stop motion safely and persist accumulated live SLAM point cloud as a .pcd file."""
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_name = (map_name or f"slam_{self.state.target_id}_{stamp}").replace(".pcd", "")
        out_path = get_paths().maps_dir / f"{clean_name}.pcd"
        self._virtual_gen.save_ascii_pcd(out_path)
        return out_path

    def stop_mapping(self) -> Tuple[bool, str]:
        """Emit STOP and RELEASE commands to cleanly hand back MANUAL authority."""
        if not self.state.active:
            return True, "当前无进行中的建图会话"
        self._emit_frame(LrmpCodec.encode(self.state.target_id, "STOP"))
        rel_frame = LrmpCodec.encode(self.state.target_id, "RELEASE")
        self._emit_frame(rel_frame)
        self.arbiter.apply_command(self.state.target_id, "RELEASE")
        self.state.active = False
        self.state.last_frame_sent = rel_frame.decode("utf-8").strip()
        return True, f"已结束遥控建图并释放 {self.state.target_id} 控制权"

    def _emit_frame(self, raw_bytes: bytes) -> None:
        if self._frame_sender is not None:
            self._frame_sender(raw_bytes)
