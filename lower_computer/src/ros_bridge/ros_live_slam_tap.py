# @file: src/ros_bridge/ros_live_slam_tap.py
# @brief: ROS-rate-driven live odometry/path/scan/PointCloud2 tap with SSE backpressure and compact Float32 binary cache.
# @exports: RosLiveSlamTap

from __future__ import annotations

import base64
import json
import math
import shlex
import struct
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from src.ros_bridge.ros_runtime_discovery import RosRuntimeDiscovery

_ROSPY_WORKER_CODE = r"""
import base64, json, math, struct, sys, threading, time
import rospy, rostopic
from nav_msgs.msg import Odometry, Path
from sensor_msgs.msg import LaserScan, PointCloud2
from std_msgs.msg import Float32

cfg = json.loads(sys.argv[1])
state = {
    "pose": None, "localization_confidence": None, "localization_delay_ms": None,
    "local_nav_status": None, "global_path": [], "scan_xy": [], "cloud_seq": 0, "point_count": 0,
}
ev = threading.Event()
last_cloud_ts = [0.0]

def _emit_state():
    sys.stdout.write("S:" + json.dumps(state, separators=(",", ":")) + "\n")
    sys.stdout.flush()

def on_odom(msg):
    p, q = msg.pose.pose.position, msg.pose.pose.orientation
    yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
    state["pose"] = {"x": round(p.x, 4), "y": round(p.y, 4), "yaw": round(yaw, 4)}
    ev.set()

def on_conf(msg):
    state["localization_confidence"] = round(float(msg.data), 4)
    ev.set()

def on_delay(msg):
    state["localization_delay_ms"] = round(float(msg.data), 2)
    ev.set()

def on_status(msg):
    val = getattr(msg, "data", None)
    if val is None and hasattr(msg, "status_list") and msg.status_list:
        val = getattr(msg.status_list[-1], "text", "") or getattr(msg.status_list[-1], "status", "")
    state["local_nav_status"] = str(val if val is not None else msg)
    ev.set()

def on_path(msg):
    step = max(1, len(msg.poses) // 120)
    state["global_path"] = [[round(ps.pose.position.x, 3), round(ps.pose.position.y, 3)] for ps in msg.poses[::step]]
    ev.set()

def on_scan(msg):
    pts, a = [], msg.angle_min
    step = max(1, len(msg.ranges) // 180)
    pose = state["pose"] or {"x": 0.0, "y": 0.0, "yaw": 0.0}
    px, py, pyaw = pose["x"], pose["y"], pose["yaw"]
    for idx in range(0, len(msg.ranges), step):
        r = msg.ranges[idx]
        if msg.range_min < r < msg.range_max and math.isfinite(r):
            ang = pyaw + a + idx * msg.angle_increment
            pts.append([round(px + r * math.cos(ang), 3), round(py + r * math.sin(ang), 3)])
    state["scan_xy"] = pts
    ev.set()

def on_cloud(msg):
    now = time.monotonic()
    if now - last_cloud_ts[0] < 0.25:
        return
    last_cloud_ts[0] = now
    offs = {f.name: f.offset for f in msg.fields if f.name in ("x", "y", "z")}
    if len(offs) < 3:
        return
    w, h = max(1, int(msg.width)), max(1, int(msg.height))
    pstep, rstep = max(1, int(msg.point_step)), max(int(msg.row_step), w * max(1, int(msg.point_step)))
    total = w * h
    stride = max(1, total // 25000)
    fmt = ">f" if msg.is_bigendian else "<f"
    voxels, data = {}, msg.data
    ox, oy, oz = offs["x"], offs["y"], offs["z"]
    for i in range(0, total, stride):
        row, col = i // w, i % w
        base = row * rstep + col * pstep
        if base + oz + 4 > len(data):
            break
        x = struct.unpack_from(fmt, data, base + ox)[0]
        y = struct.unpack_from(fmt, data, base + oy)[0]
        z = struct.unpack_from(fmt, data, base + oz)[0]
        if math.isfinite(x) and math.isfinite(y) and math.isfinite(z):
            voxels.setdefault((int(x * 20), int(y * 20), int(z * 20)), (x, y, z))
            if len(voxels) >= 25000:
                break
    if not voxels:
        return
    raw = b"".join(struct.pack("<fff", *pt) for pt in voxels.values())
    state["cloud_seq"] += 1
    state["point_count"] = len(voxels)
    sys.stdout.write("C:" + str(state["cloud_seq"]) + ":" + str(len(voxels)) + ":" + base64.b64encode(raw).decode("ascii") + "\n")
    ev.set()

rospy.init_node("vsis_http_slam_tap", anonymous=True, disable_signals=True)
if cfg.get("odom"): rospy.Subscriber(cfg["odom"], Odometry, on_odom, queue_size=2)
if cfg.get("cloud"): rospy.Subscriber(cfg["cloud"], PointCloud2, on_cloud, queue_size=1)
if cfg.get("scan"): rospy.Subscriber(cfg["scan"], LaserScan, on_scan, queue_size=1)
if cfg.get("path"): rospy.Subscriber(cfg["path"], Path, on_path, queue_size=1)
if cfg.get("conf"): rospy.Subscriber(cfg["conf"], Float32, on_conf, queue_size=2)
if cfg.get("delay"): rospy.Subscriber(cfg["delay"], Float32, on_delay, queue_size=2)
if cfg.get("status"):
    cls, _, _ = rostopic.get_topic_class(cfg["status"], blocking=False)
    if cls is not None:
        rospy.Subscriber(cfg["status"], cls, on_status, queue_size=2)

while not rospy.is_shutdown():
    if ev.wait(timeout=0.5):
        ev.clear()
        _emit_state()
"""


class RosLiveSlamTap:
    """Streams live ROS pose/path/scan at actual ROS publish rate and serves compact Float32 cloud buffers."""

    def __init__(self, discovery: RosRuntimeDiscovery) -> None:
        self.discovery = discovery
        self._cond = threading.Condition()
        self._state_seq: int = 0
        self._cloud_seq: int = 0
        self._point_count: int = 0
        self._cloud_bytes: bytes = b""
        self._latest_state: Dict[str, Any] = {
            "ros_available": False, "state_seq": 0, "cloud_seq": 0, "point_count": 0,
            "pose": None, "localization_confidence": None, "localization_delay_ms": None,
            "local_nav_status": None, "global_path": [], "scan_xy": [], "tap_mode": "idle",
            "topics": {}, "robot_state": {}, "reason": "尚未启动实时 ROS 监听",
        }
        self._last_good_pose: Optional[Dict[str, float]] = None
        self._confidence_seen: bool = False
        self._proc: Optional[subprocess.Popen[str]] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_req = threading.Event()

    def start(self) -> bool:
        """Start native onboard rospy subscriber worker in resolved ROS shell."""
        self.stop()
        ep = self.discovery.discover_topics(force=True)
        cfg = json.dumps({
            "odom": ep.odom_topic, "cloud": ep.cloud_topic, "scan": ep.scan_topic,
            "path": ep.global_path_topic, "status": ep.nav_status_topic,
            "conf": ep.confidence_topic, "delay": ep.delay_topic,
        })
        cmd = self.discovery.wrap_ros_cmd(f"python3 -c {shlex.quote(_ROSPY_WORKER_CODE)} {shlex.quote(cfg)}")
        if "rospy" not in cmd:
            return False
        import shutil
        from pathlib import Path
        has_env = shutil.which("rostopic") is not None or Path(self.discovery.cfg.navctl_bin).exists()
        if not has_env and self.discovery.current.shell_mode != "docker_exec":
            with self._cond:
                self._latest_state["tap_mode"] = "cli_sync"
                self._latest_state["topics"] = ep.to_dict()
            return False
        try:
            self._stop_req.clear()
            self._proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
            self._reader_thread = threading.Thread(target=self._read_loop, daemon=True, name="RosSlamTapReader")
            self._reader_thread.start()
            with self._cond:
                self._latest_state.update({"tap_mode": "rospy_stream", "topics": ep.to_dict(), "reason": ""})
            return True
        except Exception as ex:
            with self._cond:
                self._latest_state.update({"tap_mode": "cli_fallback", "reason": f"rospy tap 启动失败，将使用 CLI 查询: {ex}"})
            return False

    def stop(self) -> None:
        self._stop_req.set()
        if self._proc is not None:
            for fn in (self._proc.terminate, self._proc.kill):
                try:
                    fn()
                    self._proc.wait(timeout=0.8)
                    break
                except Exception:
                    pass
            self._proc = None
        with self._cond:
            self._cond.notify_all()

    def is_streaming(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _read_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        for line in self._proc.stdout:
            if self._stop_req.is_set():
                break
            s = line.strip()
            if s.startswith("S:"):
                try:
                    p = json.loads(s[2:])
                    self.push_external_frame(pose=p.get("pose"), confidence=p.get("localization_confidence"), delay_ms=p.get("localization_delay_ms"), nav_status=p.get("local_nav_status"), global_path=p.get("global_path"), scan_xy=p.get("scan_xy"), ros_available=True, tap_mode="rospy_stream")
                except Exception:
                    pass
            elif s.startswith("C:"):
                try:
                    _, seq_s, cnt_s, b64 = s.split(":", 3)
                    self.push_cloud_bytes(base64.b64decode(b64), int(cnt_s), cloud_seq=int(seq_s))
                except Exception:
                    pass

    def push_external_frame(
        self, pose: Optional[Dict[str, float]] = None, confidence: Optional[float] = None,
        delay_ms: Optional[float] = None, nav_status: Optional[str] = None,
        global_path: Optional[List[List[float]]] = None, scan_xy: Optional[List[List[float]]] = None,
        ros_available: bool = True, tap_mode: str = "cli_sync", reason: str = "",
    ) -> int:
        with self._cond:
            self._state_seq += 1
            if confidence is not None:
                self._confidence_seen = True
            if isinstance(pose, dict) and "x" in pose and "y" in pose:
                if (confidence is not None and float(confidence) >= 0.65) or (not self._confidence_seen and confidence is None):
                    self._last_good_pose = {"x": float(pose["x"]), "y": float(pose["y"]), "yaw": float(pose.get("yaw", 0.0))}
            self._latest_state.update({
                "ros_available": ros_available, "state_seq": self._state_seq, "cloud_seq": self._cloud_seq,
                "point_count": self._point_count, "pose": pose, "localization_confidence": confidence,
                "localization_delay_ms": delay_ms, "local_nav_status": nav_status,
                "global_path": global_path if global_path is not None else self._latest_state.get("global_path", []),
                "scan_xy": scan_xy if scan_xy is not None else self._latest_state.get("scan_xy", []),
                "tap_mode": tap_mode, "topics": self.discovery.current.to_dict(), "reason": reason,
            })
            self._cond.notify_all()
            return self._state_seq

    def set_robot_state(self, robot_state: Dict[str, Any]) -> int:
        with self._cond:
            self._state_seq += 1
            self._latest_state["state_seq"] = self._state_seq
            self._latest_state["robot_state"] = dict(robot_state)
            self._cond.notify_all()
            return self._state_seq

    def get_last_good_pose(self) -> Optional[Dict[str, float]]:
        with self._cond:
            return dict(self._last_good_pose) if self._last_good_pose else None

    def has_confidence_telemetry(self) -> bool:
        with self._cond:
            return self._confidence_seen

    def push_cloud_bytes(self, raw_float32_xyz: bytes, point_count: Optional[int] = None, cloud_seq: Optional[int] = None) -> int:
        cnt = point_count if point_count is not None else len(raw_float32_xyz) // 12
        with self._cond:
            self._cloud_seq = cloud_seq if cloud_seq is not None else (self._cloud_seq + 1)
            self._point_count, self._cloud_bytes = cnt, raw_float32_xyz
            self._state_seq += 1
            self._latest_state.update({"state_seq": self._state_seq, "cloud_seq": self._cloud_seq, "point_count": cnt})
            self._cond.notify_all()
            return self._cloud_seq

    def push_points_list(self, xyz_points: List[Tuple[float, float, float]]) -> int:
        if not xyz_points:
            return self._cloud_seq
        return self.push_cloud_bytes(b"".join(struct.pack("<fff", float(x), float(y), float(z)) for x, y, z in xyz_points), len(xyz_points))

    def get_live_state(self) -> Dict[str, Any]:
        with self._cond:
            return dict(self._latest_state)

    def wait_for_update(self, last_seq: int, timeout_s: float = 2.0) -> Tuple[int, Dict[str, Any]]:
        with self._cond:
            if self._state_seq <= last_seq:
                self._cond.wait(timeout=timeout_s)
            return self._state_seq, dict(self._latest_state)

    def get_live_cloud_bytes(self, since_seq: int = 0, max_points: int = 30000) -> Tuple[int, int, bytes]:
        with self._cond:
            if self._cloud_seq == 0 or (since_seq > 0 and self._cloud_seq <= since_seq):
                return self._cloud_seq, 0, b""
            raw, cnt = self._cloud_bytes, self._point_count
            if cnt > max_points > 0:
                raw, cnt = raw[: max_points * 12], max_points
            return self._cloud_seq, cnt, raw
