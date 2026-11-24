# @file: src/protocol/slam_mapping_client.py
# @brief: Authentic ROS/Wi-Fi HTTP teleop SLAM mapping client without synthetic point cloud or fake map fallbacks.
# @exports: MappingSessionState, SlamMappingClient

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
import numpy as np

from src.core.paths import get_paths
from src.protocol.authority_state_machine import AuthorityStateMachine
from src.protocol.lrmp_codec import LrmpCodec
from src.protocol.robot_http_client import RobotHttpClient


@dataclass
class MappingSessionState:
    """Live state of an interactive real-robot teleop SLAM mapping session."""

    active: bool = False
    target_id: str = "A"
    robot_ip: str = ""
    mode: str = "HTTP_SSE"
    pose: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    point_count: int = 0
    cloud_seq: int = 0
    last_frame_sent: str = ""
    discovered_topics: Dict[str, Any] = field(default_factory=dict)


class SlamMappingClient:
    """Manages real robot teleop SLAM mapping, velocity hold, and remote .pcd retrieval over Wi-Fi HTTP."""

    def __init__(
        self,
        arbiter: Optional[AuthorityStateMachine] = None,
        frame_sender: Optional[Callable[[bytes], bool]] = None,
        http_client: Optional[RobotHttpClient] = None,
    ) -> None:
        self.arbiter = arbiter or AuthorityStateMachine()
        self._frame_sender = frame_sender
        self._http = http_client or RobotHttpClient(timeout_s=2.5)
        self.state = MappingSessionState()

    def start_mapping(self, target_id: str, robot_ip: str) -> Tuple[bool, str]:
        """Acquire MANUAL control authority and launch real onboard ROS mapping via navctl + GAIT."""
        ip = (robot_ip or "").strip()
        if not ip:
            return False, "尚未配置机器人 Wi-Fi 局域网 IP，无法启动真实建图"
        res = self.arbiter.acquire_manual(target_id)
        if not res.allowed:
            return False, res.reason

        nav_res = self._http.navctl(ip, "restart mapping")
        if not nav_res.ok:
            nav_res = self._http.navctl(ip, "start mapping")
        if not nav_res.ok:
            self.arbiter.apply_command(target_id, "RELEASE")
            return False, f"启动建图失败 ({nav_res.message})"

        self._http.send_posture(ip, "STAND")
        self._http.send_posture(ip, "GAIT")
        disc = self._http.fetch_nav_discovery(ip)
        snap = self._http.fetch_slam_live_state(ip)
        p = snap.data.get("pose") if snap.ok else None
        pose = (float(p["x"]), float(p["y"]), float(p["yaw"])) if isinstance(p, dict) else (0.0, 0.0, 0.0)
        self.state = MappingSessionState(
            active=True,
            target_id=target_id.upper(),
            robot_ip=ip,
            mode="HTTP_SSE",
            pose=pose,
            point_count=int(snap.data.get("point_count", 0)) if snap.ok else 0,
            cloud_seq=int(snap.data.get("cloud_seq", 0)) if snap.ok else 0,
            last_frame_sent=f"{target_id.upper()}|GAIT",
            discovered_topics=dict(disc.data.get("endpoints") or {}) if disc.ok else {},
        )
        return True, f"已进入真实 ROS 遥控建图 ({self.state.target_id} @ {ip})"

    def send_teleop_move(self, vx: float, vy: float, vyaw: float, duration_s: float = 0.6) -> Tuple[bool, str]:
        """Dispatch real HTTP velocity hold command to lower computer."""
        if not self.state.active:
            return False, "请先点击「启动建图」"
        check = self.arbiter.apply_command(self.state.target_id, "MOVE")
        if not check.allowed:
            return False, check.reason

        resp = self._http.send_velocity(
            self.state.robot_ip,
            {"vx": round(float(vx), 3), "vy": round(float(vy), 3), "vyaw": round(float(vyaw), 3), "duration": round(float(duration_s), 2)},
        )
        if not resp.ok:
            return False, f"遥控速度下发失败: {resp.message}"
        frame = LrmpCodec.encode_move(
            self.state.target_id, max(-1.0, min(1.0, vx)), max(-1.0, min(1.0, vy)), max(-1.0, min(1.0, vyaw)), duration_s
        )
        if self._frame_sender is not None:
            self._frame_sender(frame)
        self.state.last_frame_sent = frame.decode("utf-8").strip()
        return True, self.state.last_frame_sent

    def fetch_live_cloud(self, since_seq: int = 0) -> Tuple[Optional[np.ndarray], int]:
        """Fetch latest real Float32 XYZ point cloud from lower computer when updated."""
        if not self.state.robot_ip:
            return None, since_seq
        resp = self._http.fetch_slam_live_cloud(self.state.robot_ip, since_seq=since_seq)
        if resp.status_code == 200 and resp.raw_bytes and len(resp.raw_bytes) >= 12:
            usable = len(resp.raw_bytes) - (len(resp.raw_bytes) % 12)
            pts = np.frombuffer(resp.raw_bytes[:usable], dtype=np.float32).reshape(-1, 3).copy()
            seq = int(resp.data.get("cloud_seq", since_seq + 1))
            self.state.cloud_seq = seq
            self.state.point_count = len(pts)
            return pts, seq
        return None, since_seq

    def save_live_map(self, map_name: str = "", finish_mapping: bool = True, remote_path: str = "") -> Path:
        """Finalize mapping if active and download the real onboard .pcd map over HTTP; raise on failure."""
        if not self.state.robot_ip:
            raise RuntimeError("未配置机器人 Wi-Fi IP，无法拉取机载真实 .pcd 地图")
        if finish_mapping and self.state.active and not remote_path:
            fin = self._http.navctl(self.state.robot_ip, "finish-mapping")
            if not fin.ok:
                raise RuntimeError(f"结束建图并落盘地图失败: {fin.message}")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_name = (map_name or f"slam_{self.state.target_id}_{stamp}").replace(".pcd", "")
        out_path = get_paths().maps_dir / f"{clean_name}.pcd"
        dl = self._http.download_slam_pcd(self.state.robot_ip, out_path, remote_path=remote_path)
        if not dl.ok:
            raise RuntimeError(f"下载机载真实 .pcd 失败: {dl.message}")
        return out_path

    def stop_mapping(self) -> Tuple[bool, str]:
        """Emit HTTP STOP and RELEASE commands to safely hand back MANUAL control authority."""
        if not self.state.active:
            return True, "当前无进行中的建图会话"
        stop_res = self._http.send_stop(self.state.robot_ip, emergency=False)
        rel_res = self._http.send_posture(self.state.robot_ip, "RELEASE")
        self.arbiter.apply_command(self.state.target_id, "RELEASE")
        self.state.active = False
        self.state.last_frame_sent = f"{self.state.target_id}|RELEASE"
        if not stop_res.ok or not rel_res.ok:
            return False, f"停止/释放部分异常: {stop_res.message or rel_res.message}"
        return True, f"已结束遥控建图并释放 {self.state.target_id} 控制权"
