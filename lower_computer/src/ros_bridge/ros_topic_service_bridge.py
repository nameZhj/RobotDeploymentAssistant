# @file: src/ros_bridge/ros_topic_service_bridge.py
# @brief: Authentic ROS 1.17.4 topic/TF/service bridge without synthetic or demo telemetry.
# @exports: RosTelemetrySnapshot, RosTopicServiceBridge

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlparse

from src.config.ros_env_config import ROS_SERVICES, ROS_TOPICS, RosEnvConfig
from src.ros_bridge.ros_nav_diagnostics import RosNavDiagnostics


@dataclass
class RosTelemetrySnapshot:
    """Real snapshot read from ROS topics and TF; fields remain None when ROS is unavailable."""

    ros_available: bool
    master_reachable: bool
    pose: Optional[Tuple[float, float, float]] = None
    localization_confidence: Optional[float] = None
    localization_delay_ms: Optional[float] = None
    local_nav_status: Optional[str] = None
    cmd_vel: Optional[Tuple[float, float, float]] = None
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ros_available": self.ros_available,
            "master_reachable": self.master_reachable,
            "pose": {"x": self.pose[0], "y": self.pose[1], "yaw": self.pose[2]} if self.pose else None,
            "localization_confidence": self.localization_confidence,
            "localization_delay_ms": self.localization_delay_ms,
            "local_nav_status": self.local_nav_status,
            "cmd_vel": (
                {"vx": self.cmd_vel[0], "vy": self.cmd_vel[1], "vyaw": self.cmd_vel[2]}
                if self.cmd_vel else None
            ),
            "reason": self.reason,
        }


ShellRunner = Callable[[str, float], Tuple[int, str, str]]


def _default_shell_runner(cmd: str, timeout_s: float) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout_s, check=False)
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"命令执行超时 ({timeout_s:.1f}s)"
    except OSError as ex:
        return 127, "", f"系统调用失败: {ex}"


def _yaw_to_quat_zw(yaw: float) -> Tuple[float, float]:
    return math.sin(yaw * 0.5), math.cos(yaw * 0.5)


class RosTopicServiceBridge:
    """Interfaces with real ROS 1.17.4 topics, TF, and TEB services per 下位机ros信息."""

    def __init__(
        self,
        cfg: Optional[RosEnvConfig] = None,
        shell_runner: Optional[ShellRunner] = None,
        master_checker: Optional[Callable[[], bool]] = None,
        use_navctl_shell: bool = False,
    ) -> None:
        self.cfg = cfg or RosEnvConfig()
        self._shell = shell_runner or _default_shell_runner
        self._master_check_fn = master_checker
        self.diagnostics = RosNavDiagnostics(self.cfg, self._shell, use_navctl_shell=use_navctl_shell)

    def is_ros_master_reachable(self) -> bool:
        if self._master_check_fn is not None:
            return bool(self._master_check_fn())
        uri = os.environ.get("ROS_MASTER_URI", self.cfg.ros_master_uri)
        parsed = urlparse(uri)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 11311
        try:
            with socket.create_connection((host, port), timeout=0.4):
                return True
        except OSError:
            return False

    def has_rostopic_cli(self) -> bool:
        return shutil.which("rostopic") is not None

    def _check_ready(self) -> Optional[str]:
        if not self.is_ros_master_reachable():
            return f"ROS Master ({self.cfg.ros_master_uri}) 不可达"
        if self._shell is _default_shell_runner:
            if self.diagnostics.use_navctl_shell:
                if not Path(self.cfg.navctl_bin).exists():
                    return f"未找到 {self.cfg.navctl_bin}，无法进入 ROS 容器环境"
            elif not self.has_rostopic_cli():
                return "未检测到 rostopic/rosservice CLI 工具（需在 ROS 1.17.4 或 navctl shell 环境中运行）"
        return None

    def read_telemetry_snapshot(self) -> RosTelemetrySnapshot:
        err = self._check_ready()
        if err:
            return RosTelemetrySnapshot(ros_available=False, master_reachable=False, reason=err)

        pose = self._echo_odometry_pose()
        if pose is None:
            pose = self.diagnostics.read_tf_map_to_base_link()
        conf = self._echo_float_topic(ROS_TOPICS["loc_confidence"]["topic"])
        delay = self._echo_float_topic(ROS_TOPICS["loc_delay_ms"]["topic"])
        nav_st = self._echo_string_topic(ROS_TOPICS["local_nav_status"]["topic"])
        cmd_v = self.diagnostics.read_cmd_vel()
        return RosTelemetrySnapshot(
            ros_available=True,
            master_reachable=True,
            pose=pose,
            localization_confidence=conf,
            localization_delay_ms=delay,
            local_nav_status=nav_st,
            cmd_vel=cmd_v,
            reason="" if pose is not None else "已连接 ROS Master，等待 /Odometry_loc 或 TF map->base_link 发布",
        )

    def _echo_odometry_pose(self) -> Optional[Tuple[float, float, float]]:
        rc, out, _ = self.diagnostics.run_ros_cmd(f"rostopic echo -n 1 {ROS_TOPICS['odometry_loc']['topic']}", 2.5)
        if rc != 0 or not out:
            return None
        mx = re.search(r"position:\s*\n\s*x:\s*([-0-9.eE+]+)\s*\n\s*y:\s*([-0-9.eE+]+)", out)
        mq = re.search(r"orientation:\s*\n\s*x:\s*([-0-9.eE+]+)\s*\n\s*y:\s*([-0-9.eE+]+)\s*\n\s*z:\s*([-0-9.eE+]+)\s*\n\s*w:\s*([-0-9.eE+]+)", out)
        if not mx:
            return None
        x, y = float(mx.group(1)), float(mx.group(2))
        yaw = 0.0
        if mq:
            qz, qw = float(mq.group(3)), float(mq.group(4))
            yaw = math.atan2(2.0 * qw * qz, 1.0 - 2.0 * qz * qz)
        return (x, y, yaw)

    def _echo_float_topic(self, topic: str) -> Optional[float]:
        rc, out, _ = self.diagnostics.run_ros_cmd(f"rostopic echo -n 1 {topic}", 2.0)
        if rc != 0:
            return None
        m = re.search(r"data:\s*([-0-9.eE+]+)", out)
        return float(m.group(1)) if m else None

    def _echo_string_topic(self, topic: str) -> Optional[str]:
        rc, out, _ = self.diagnostics.run_ros_cmd(f"rostopic echo -n 1 {topic}", 2.0)
        if rc != 0:
            return None
        m = re.search(r"data:\s*['\"]?([^\r\n'\"]+)['\"]?", out)
        return m.group(1).strip() if m else None

    def publish_nav_goal(self, x: float, y: float, yaw: float, frame_id: str = "map") -> Dict[str, Any]:
        err = self._check_ready()
        if err:
            return {"ok": False, "ros_available": False, "reason": err}
        qz, qw = _yaw_to_quat_zw(yaw)
        yaml_msg = (
            f"{{header: {{frame_id: '{frame_id}'}}, "
            f"pose: {{position: {{x: {x:.4f}, y: {y:.4f}, z: 0.0}}, "
            f"orientation: {{x: 0.0, y: 0.0, z: {qz:.6f}, w: {qw:.6f}}}}}}}"
        )
        cmd = f"rostopic pub -1 {ROS_TOPICS['move_base_goal']['topic']} {ROS_TOPICS['move_base_goal']['type']} \"{yaml_msg}\""
        rc, out, err_s = self.diagnostics.run_ros_cmd(cmd, 5.0)
        return {
            "ok": rc == 0,
            "ros_available": True,
            "topic": ROS_TOPICS["move_base_goal"]["topic"],
            "goal": {"x": x, "y": y, "yaw": yaw, "frame_id": frame_id},
            "stdout": out,
            "reason": "" if rc == 0 else (err_s or f"rostopic pub 退出码 {rc}"),
        }

    def publish_initial_pose(self, x: float, y: float, yaw: float, frame_id: str = "map") -> Dict[str, Any]:
        err = self._check_ready()
        if err:
            return {"ok": False, "ros_available": False, "reason": err}
        qz, qw = _yaw_to_quat_zw(yaw)
        yaml_msg = (
            f"{{header: {{frame_id: '{frame_id}'}}, "
            f"pose: {{pose: {{position: {{x: {x:.4f}, y: {y:.4f}, z: 0.0}}, "
            f"orientation: {{x: 0.0, y: 0.0, z: {qz:.6f}, w: {qw:.6f}}}}}}}}}"
        )
        cmd = f"rostopic pub -1 {ROS_TOPICS['initialpose']['topic']} {ROS_TOPICS['initialpose']['type']} \"{yaml_msg}\""
        rc, out, err_s = self.diagnostics.run_ros_cmd(cmd, 5.0)
        return {
            "ok": rc == 0,
            "ros_available": True,
            "topic": ROS_TOPICS["initialpose"]["topic"],
            "stdout": out,
            "reason": "" if rc == 0 else (err_s or f"rostopic pub 退出码 {rc}"),
        }

    def publish_cmd_vel(self, vx: float, vy: float, vyaw: float) -> Dict[str, Any]:
        err = self._check_ready()
        if err:
            return {"ok": False, "ros_available": False, "reason": err}
        yaml_msg = (
            f"{{linear: {{x: {vx:.4f}, y: {vy:.4f}, z: 0.0}}, "
            f"angular: {{x: 0.0, y: 0.0, z: {vyaw:.4f}}}}}"
        )
        cmd = f"rostopic pub -1 {ROS_TOPICS['cmd_vel']['topic']} {ROS_TOPICS['cmd_vel']['type']} \"{yaml_msg}\""
        rc, out, err_s = self.diagnostics.run_ros_cmd(cmd, 3.0)
        return {
            "ok": rc == 0,
            "ros_available": True,
            "topic": ROS_TOPICS["cmd_vel"]["topic"],
            "cmd_vel": {"vx": vx, "vy": vy, "vyaw": vyaw},
            "stdout": out,
            "reason": "" if rc == 0 else (err_s or f"rostopic pub cmd_vel 退出码 {rc}"),
        }

    def cancel_planning(self) -> Dict[str, Any]:
        err = self._check_ready()
        if err:
            return {"ok": False, "ros_available": False, "reason": err}
        srv = ROS_SERVICES["cancel_planning"]
        rc, out, err_s = self.diagnostics.run_ros_cmd(f"rosservice call {srv}", 4.0)
        return {
            "ok": rc == 0,
            "ros_available": True,
            "service": srv,
            "stdout": out,
            "reason": "" if rc == 0 else (err_s or f"rosservice call 退出码 {rc}"),
        }
