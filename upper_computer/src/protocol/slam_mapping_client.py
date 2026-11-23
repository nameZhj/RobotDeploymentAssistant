# @file: src/protocol/slam_mapping_client.py
# @brief: Teleop mapping controller dispatching navctl/MOVE/PCD retrieval over Wi-Fi HTTP with LRMP frame tracking.
# @exports: MappingSessionState, SlamMappingClient

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Tuple

from src.core.paths import get_paths
from src.protocol.authority_state_machine import AuthorityStateMachine
from src.protocol.lrmp_codec import LrmpCodec
from src.protocol.robot_http_client import RobotHttpClient
from src.protocol.virtual_slam_generator import VirtualSlamGenerator


@dataclass
class MappingSessionState:
    """Live state of an interactive teleop SLAM mapping session."""

    active: bool = False
    target_id: str = "A"
    robot_ip: str = "192.168.123.101"
    mode: str = "HTTP"
    pose: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    point_count: int = 0
    last_frame_sent: str = ""


class SlamMappingClient:
    """Manages remote-controlled robot mapping lifecycle over Wi-Fi HTTP & ROS navctl."""

    WS_ENDPOINT_TEMPLATE = "ws://{ip}:{port}/api/v1/slam/pointcloud"

    def __init__(
        self,
        arbiter: Optional[AuthorityStateMachine] = None,
        frame_sender: Optional[Callable[[bytes], bool]] = None,
        http_client: Optional[RobotHttpClient] = None,
    ) -> None:
        self.arbiter = arbiter or AuthorityStateMachine()
        self._frame_sender = frame_sender
        self._http = http_client or RobotHttpClient(timeout_s=2.0)
        self.state = MappingSessionState()
        self._virtual_gen = VirtualSlamGenerator()

    def start_mapping(self, target_id: str, robot_ip: str = "192.168.123.101") -> Tuple[bool, str]:
        """Acquire MANUAL control authority, call Wi-Fi HTTP navctl start mapping, and initialize GAIT."""
        res = self.arbiter.acquire_manual(target_id)
        if not res.allowed:
            return False, res.reason
        self._emit_frame(LrmpCodec.encode(target_id, "STAND"))
        self._emit_frame(LrmpCodec.encode(target_id, "GAIT"))
        nav_res = self._http.navctl(robot_ip, "start mapping")
        self._virtual_gen = VirtualSlamGenerator()
        mode_str = "HTTP_ROS" if nav_res.ok else "HTTP_PENDING"
        self.state = MappingSessionState(
            active=True,
            target_id=target_id.upper(),
            robot_ip=robot_ip,
            mode=mode_str,
            pose=tuple(self._virtual_gen.robot_pose),  # type: ignore[arg-type]
            point_count=len(self._virtual_gen.get_points()),
            last_frame_sent=f"{target_id.upper()}|GAIT",
        )
        return True, f"已进入遥控建图态 ({self.state.target_id} @ {robot_ip}, {mode_str})"

    def send_teleop_move(self, vx: float, vy: float, vyaw: float, duration_s: float = 0.5) -> Tuple[bool, str]:
        """Emit validated LRMP MOVE command via Wi-Fi HTTP and step local preview pose."""
        if not self.state.active:
            return False, "请先点击启动建图"
        check = self.arbiter.apply_command(self.state.target_id, "MOVE")
        if not check.allowed:
            return False, check.reason
        frame = LrmpCodec.encode_move(self.state.target_id, vx, vy, vyaw, duration_s)
        self._emit_frame(frame)
        self._http.send_command(self.state.robot_ip, self.state.target_id, "MOVE", [f"{vx:.3f}", f"{vy:.3f}", f"{vyaw:.3f}", f"{duration_s:.2f}"])
        self.state.pose = self._virtual_gen.step_motion(vx, vy, vyaw, duration_s)
        self.state.point_count = len(self._virtual_gen.get_points())
        self.state.last_frame_sent = frame.decode("utf-8").strip()
        return True, self.state.last_frame_sent

    def save_live_map(self, map_name: str = "") -> Path:
        """Fetch real SLAM .pcd from robot over Wi-Fi HTTP when available, or persist current session scan."""
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_name = (map_name or f"slam_{self.state.target_id}_{stamp}").replace(".pcd", "")
        out_path = get_paths().maps_dir / f"{clean_name}.pcd"
        self._http.navctl(self.state.robot_ip, "finish-mapping")
        dl = self._http.download_slam_pcd(self.state.robot_ip, out_path)
        if not dl.ok:
            self._virtual_gen.save_ascii_pcd(out_path)
        return out_path

    def stop_mapping(self) -> Tuple[bool, str]:
        """Emit STOP and RELEASE commands over Wi-Fi HTTP to cleanly hand back MANUAL authority."""
        if not self.state.active:
            return True, "当前无进行中的建图会话"
        self._emit_frame(LrmpCodec.encode(self.state.target_id, "STOP"))
        rel_frame = LrmpCodec.encode(self.state.target_id, "RELEASE")
        self._emit_frame(rel_frame)
        self._http.send_command(self.state.robot_ip, self.state.target_id, "STOP")
        self._http.send_command(self.state.robot_ip, self.state.target_id, "RELEASE")
        self.arbiter.apply_command(self.state.target_id, "RELEASE")
        self.state.active = False
        self.state.last_frame_sent = rel_frame.decode("utf-8").strip()
        return True, f"已结束遥控建图并释放 {self.state.target_id} 控制权"

    def _emit_frame(self, raw_bytes: bytes) -> None:
        if self._frame_sender is not None:
            self._frame_sender(raw_bytes)
