# @file: src/ros_bridge/ros_nav_diagnostics.py
# @brief: Deep ROS 1.17.4 graph, topic rate, TF map->base_link, global path, and TEB parameter inspector.
# @exports: RosNavDiagnostics

from __future__ import annotations

import math
import re
import shlex
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.config.ros_env_config import ROS_SERVICES, ROS_TOPICS, RosEnvConfig
from src.ros_bridge.ros_runtime_discovery import RosRuntimeDiscovery

ShellRunner = Callable[[str, float], Tuple[int, str, str]]


class RosNavDiagnostics:
    """Executes authentic ROS 1.17.4 inspection and TEB dynamic reconfigure commands from 下位机ros信息 §3."""

    def __init__(
        self,
        cfg: RosEnvConfig,
        shell_runner: ShellRunner,
        use_navctl_shell: bool = False,
        discovery: Optional[RosRuntimeDiscovery] = None,
    ) -> None:
        self.cfg = cfg
        self._raw_shell = shell_runner
        self.use_navctl_shell = use_navctl_shell
        self.discovery = discovery

    def run_ros_cmd(self, ros_cmd: str, timeout_s: float = 4.0) -> Tuple[int, str, str]:
        if self.discovery is not None:
            return self.discovery.run_ros_cmd(ros_cmd, timeout_s)
        if self.use_navctl_shell:
            wrapped = f"sudo -n {shlex.quote(self.cfg.navctl_bin)} shell -c {shlex.quote(ros_cmd)}"
            return self._raw_shell(wrapped, timeout_s)
        return self._raw_shell(ros_cmd, timeout_s)

    def query_versions(self) -> Dict[str, Any]:
        rc_d, dist, _ = self.run_ros_cmd("rosversion -d", 2.5)
        rc_l, rlaunch, _ = self.run_ros_cmd("rosversion roslaunch", 2.5)
        rc_p, rparam, _ = self.run_ros_cmd("rosparam get /rosversion", 2.5)
        return {
            "ok": rc_d == 0 or rc_l == 0,
            "distro": dist.strip() if rc_d == 0 else "",
            "roslaunch_version": rlaunch.strip() if rc_l == 0 else "",
            "rosparam_version": rparam.strip() if rc_p == 0 else "",
        }

    def inspect_graph(self) -> Dict[str, Any]:
        rc_n, nodes_out, err_n = self.run_ros_cmd("rosnode list", 3.0)
        if rc_n != 0:
            return {"ok": False, "reason": err_n or "rosnode list 执行失败", "nodes": [], "topics": [], "services": []}
        _, topics_out, _ = self.run_ros_cmd("rostopic list", 3.0)
        _, srvs_out, _ = self.run_ros_cmd("rosservice list", 3.0)
        _, teb_info, _ = self.run_ros_cmd("rosnode info /teb_polar_node", 3.0)
        return {
            "ok": True,
            "nodes": [n.strip() for n in nodes_out.splitlines() if n.strip()],
            "topics": [t.strip() for t in topics_out.splitlines() if t.strip()],
            "services": [s.strip() for s in srvs_out.splitlines() if s.strip()],
            "teb_polar_node_info": teb_info,
        }

    def read_tf_map_to_base_link(self) -> Optional[Tuple[float, float, float]]:
        """Read single transform from `rosrun tf tf_echo` across localization and mapping frame pairs."""
        for parent_f, child_f in (("map", "base_link"), ("camera_init", "body"), ("odom", "base_link")):
            rc, out, _ = self.run_ros_cmd(f"rosrun tf tf_echo {parent_f} {child_f} 1", 2.5)
            if rc != 0 or not out:
                continue
            mt = re.search(r"Translation:\s*\[\s*([-0-9.eE+]+)\s*,\s*([-0-9.eE+]+)\s*,\s*([-0-9.eE+]+)\s*\]", out)
            mr = re.search(r"in RPY \(radian\)\s*\[\s*([-0-9.eE+]+)\s*,\s*([-0-9.eE+]+)\s*,\s*([-0-9.eE+]+)\s*\]", out)
            if mt:
                return (float(mt.group(1)), float(mt.group(2)), float(mr.group(3)) if mr else 0.0)
        return None

    def read_cmd_vel(self) -> Optional[Tuple[float, float, float]]:
        topic = self.discovery.current.cmd_vel_topic if self.discovery else ROS_TOPICS["cmd_vel"]["topic"]
        rc, out, _ = self.run_ros_cmd(f"rostopic echo -n 1 {topic}", 2.5)
        if rc != 0 or not out:
            return None
        ml = re.search(r"linear:\s*\n\s*x:\s*([-0-9.eE+]+)\s*\n\s*y:\s*([-0-9.eE+]+)", out)
        ma = re.search(r"angular:\s*\n\s*x:\s*[-0-9.eE+]+\s*\n\s*y:\s*[-0-9.eE+]+\s*\n\s*z:\s*([-0-9.eE+]+)", out)
        if not ml:
            return None
        return (float(ml.group(1)), float(ml.group(2)), float(ma.group(1)) if ma else 0.0)

    def read_global_path(self) -> List[Dict[str, float]]:
        topic = self.discovery.current.global_path_topic if self.discovery else ROS_TOPICS["global_path"]["topic"]
        rc, out, _ = self.run_ros_cmd(f"rostopic echo -n 1 {topic}", 3.0)
        if rc != 0 or not out:
            return []
        pts: List[Dict[str, float]] = []
        for m in re.finditer(r"position:\s*\n\s*x:\s*([-0-9.eE+]+)\s*\n\s*y:\s*([-0-9.eE+]+)", out):
            pts.append({"x": float(m.group(1)), "y": float(m.group(2))})
        return pts

    def read_cad_scan_summary(self, robot_pose: Optional[Tuple[float, float, float]] = None) -> Dict[str, Any]:
        topic = self.discovery.current.scan_topic if self.discovery else ROS_TOPICS["cad_scan"]["topic"]
        rc, out, err_s = self.run_ros_cmd(f"rostopic echo -n 1 {topic}", 2.5)
        if rc != 0 or not out:
            return {"ok": False, "topic": topic, "reason": err_s or f"无 {topic} 数据"}
        ma = re.search(r"angle_min:\s*([-0-9.eE+]+)", out)
        mi = re.search(r"angle_increment:\s*([-0-9.eE+]+)", out)
        mr = re.search(r"ranges:\s*\[([^\]]+)\]", out)
        ang_min = float(ma.group(1)) if ma else -math.pi
        ang_inc = float(mi.group(1)) if mi else (2.0 * math.pi / 360.0)
        rx, ry, ryaw = robot_pose or (0.0, 0.0, 0.0)
        ranges: List[float] = []
        points_xy: List[List[float]] = []
        if mr:
            for idx, tok in enumerate(mr.group(1).split(",")[:360]):
                try:
                    v = float(tok.strip())
                    if math.isfinite(v) and v > 0.02:
                        ranges.append(round(v, 3))
                        ang = ryaw + ang_min + idx * ang_inc
                        points_xy.append([round(rx + v * math.cos(ang), 3), round(ry + v * math.sin(ang), 3)])
                except ValueError:
                    pass
        return {
            "ok": True,
            "topic": topic,
            "sample_count": len(ranges),
            "min_range_m": min(ranges) if ranges else None,
            "ranges_preview": ranges[:60],
            "points_xy": points_xy[:180],
        }

    def get_teb_parameters(self) -> Dict[str, Any]:
        rc, out, err_s = self.run_ros_cmd("rosparam get /teb_polar_node", 3.0)
        return {
            "ok": rc == 0,
            "node": "/teb_polar_node",
            "raw_yaml": out if rc == 0 else "",
            "reason": "" if rc == 0 else (err_s or "读取 /teb_polar_node 参数失败"),
        }

    def set_teb_parameters(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not params:
            return {"ok": False, "reason": "参数字典为空"}
        applied: List[str] = []
        for k, v in params.items():
            clean_k = re.sub(r"[^A-Za-z0-9_/]", "", str(k))
            if not clean_k:
                continue
            rc, _, err_s = self.run_ros_cmd(f"rosparam set /teb_polar_node/{clean_k} {repr(v)}", 2.5)
            if rc != 0:
                return {"ok": False, "applied": applied, "reason": err_s or f"设置 {clean_k} 失败"}
            applied.append(clean_k)
        srv = ROS_SERVICES["set_parameters"]
        rc_s, out_s, _ = self.run_ros_cmd(f"rosservice call {srv} \"{{}}\"", 3.0)
        return {"ok": True, "applied": applied, "service_called": rc_s == 0, "service_stdout": out_s}
