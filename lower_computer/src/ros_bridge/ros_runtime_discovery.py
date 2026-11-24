# @file: src/ros_bridge/ros_runtime_discovery.py
# @brief: Dynamically discovers ROS 1.17.4 topics, message types, navctl/docker shell command, and real PCD map paths.
# @exports: RosDiscoveredEndpoints, RosRuntimeDiscovery

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
import shlex
import shutil
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.config.ros_env_config import RosEnvConfig

ShellRunner = Callable[[str, float], Tuple[int, str, str]]


@dataclass
class RosDiscoveredEndpoints:
    """Dynamically resolved ROS topics and execution mode without hardcoded assumptions."""

    shell_mode: str = "direct"  # "direct" | "navctl_shell" | "docker_exec"
    odom_topic: str = "/Odometry_loc"
    cloud_topic: str = "/cloud_registered"
    cmd_vel_topic: str = "/teb_polar_node/cmd_vel"
    global_path_topic: str = "/global_planner/path"
    scan_topic: str = "/cad_scan"
    nav_status_topic: str = "/local_nav_status"
    nav_status_type: str = "std_msgs/String"
    goal_topic: str = "/move_base_simple/goal"
    initialpose_topic: str = "/initialpose"
    confidence_topic: str = "/localization_3d_confidence"
    delay_topic: str = "/localization_3d_delay_ms"
    all_topics: Dict[str, str] = field(default_factory=dict)
    subscribed_topics: List[str] = field(default_factory=list)
    map_search_dirs: List[str] = field(default_factory=list)
    discovered_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RosRuntimeDiscovery:
    """Queries live ROS graph, rosparam, rospack, and /opt/vsis_nav/navctl to avoid hardcoded config."""

    def __init__(
        self,
        cfg: RosEnvConfig,
        shell_runner: ShellRunner,
        use_navctl_shell: bool = False,
    ) -> None:
        self.cfg = cfg
        self._shell = shell_runner
        self._force_navctl = use_navctl_shell
        self._docker_prefix: Optional[str] = None
        self._shell_probed = False
        self._cached = RosDiscoveredEndpoints()

    @property
    def current(self) -> RosDiscoveredEndpoints:
        return self._cached

    def wrap_ros_cmd(self, ros_cmd: str) -> str:
        mode = self._resolve_shell_mode()
        if mode == "docker_exec" and self._docker_prefix:
            full = (
                "for s in /opt/ros/*/setup.bash /root/*/devel/setup.bash /home/ubuntu/*/devel/setup.bash; "
                "do [ -f \"$s\" ] && source \"$s\"; done; " + ros_cmd
            )
            return f"{self._docker_prefix} bash -lc {shlex.quote(full)}"
        if mode == "navctl_shell":
            return f"sudo -n {shlex.quote(self.cfg.navctl_bin)} shell -c {shlex.quote(ros_cmd)}"
        return ros_cmd

    def run_ros_cmd(self, ros_cmd: str, timeout_s: float = 4.0) -> Tuple[int, str, str]:
        return self._shell(self.wrap_ros_cmd(ros_cmd), timeout_s)

    def _resolve_shell_mode(self) -> str:
        if self._force_navctl:
            return "navctl_shell"
        if self._shell_probed:
            return self._cached.shell_mode
        self._shell_probed = True
        if shutil.which("rostopic") is not None:
            self._cached.shell_mode = "direct"
            return "direct"
        navctl_p = Path(self.cfg.navctl_bin)
        if navctl_p.exists():
            rc, _, _ = self._shell(f"sudo -n {shlex.quote(self.cfg.navctl_bin)} shell -c 'command -v rostopic'", 2.5)
            if rc == 0:
                self._cached.shell_mode = "navctl_shell"
                return "navctl_shell"
            docker_pref = self._parse_docker_prefix_from_navctl(navctl_p)
            if docker_pref:
                self._docker_prefix = docker_pref
                self._cached.shell_mode = "docker_exec"
                return "docker_exec"
            self._cached.shell_mode = "navctl_shell"
            return "navctl_shell"
        self._cached.shell_mode = "direct"
        return "direct"

    @staticmethod
    def _parse_docker_prefix_from_navctl(navctl_path: Path) -> Optional[str]:
        try:
            text = navctl_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None
        m = re.search(r"docker\s+exec\s+(?:-[a-zA-Z]+\s+)*\"?\$?([A-Za-z0-9_.-]+)\"?", text)
        if m:
            cname = m.group(1)
            vm = re.search(rf"{re.escape(cname)}\s*=\s*['\"]?([A-Za-z0-9_.-]+)", text)
            return f"docker exec {vm.group(1) if vm else cname}"
        return None

    def discover_topics(self, force: bool = False) -> RosDiscoveredEndpoints:
        if not force and (time.monotonic() - self._cached.discovered_at) < 4.0 and self._cached.all_topics:
            return self._cached
        rc, out, _ = self.run_ros_cmd("rostopic list -v", 3.5)
        if rc != 0 or not out:
            return self._cached

        topics: Dict[str, str] = {}
        subscribed: List[str] = []
        section = ""
        for line in out.splitlines():
            s = line.strip()
            if s.lower().startswith("published topics"):
                section = "pub"
                continue
            if s.lower().startswith("subscribed topics"):
                section = "sub"
                continue
            m = re.match(r"^\*\s+([^\s]+)\s+\[([^\]]+)\]", s)
            if m:
                tname, ttype = m.group(1), m.group(2)
                topics[tname] = ttype
                if section == "sub" and tname not in subscribed:
                    subscribed.append(tname)

        if not topics:
            rc2, out2, _ = self.run_ros_cmd("rostopic list", 2.5)
            if rc2 == 0 and out2:
                for line in out2.splitlines():
                    t = line.strip()
                    if t.startswith("/"):
                        topics[t] = topics.get(t, "")

        ep = self._cached
        ep.all_topics = topics
        ep.subscribed_topics = subscribed
        ep.odom_topic = self._pick_topic(topics, "nav_msgs/Odometry", ["/Odometry_loc", "/Odometry", "/aft_mapped_to_init", "/odom"], ep.odom_topic)
        ep.cloud_topic = self._pick_topic(topics, "sensor_msgs/PointCloud2", ["/cloud_registered", "/Laser_map", "/cloud_registered_body", "/velodyne_points", "/livox/lidar"], ep.cloud_topic)
        ep.cmd_vel_topic = self._pick_cmd_vel(topics, subscribed, ep.cmd_vel_topic)
        ep.global_path_topic = self._pick_topic(topics, "nav_msgs/Path", ["/global_planner/path", "/path"], ep.global_path_topic)
        ep.scan_topic = self._pick_topic(topics, "sensor_msgs/LaserScan", ["/cad_scan", "/scan"], ep.scan_topic)
        ep.goal_topic = self._pick_topic(topics, "geometry_msgs/PoseStamped", ["/move_base_simple/goal"], ep.goal_topic)
        ep.initialpose_topic = self._pick_topic(topics, "geometry_msgs/PoseWithCovarianceStamped", ["/initialpose"], ep.initialpose_topic)
        if "/local_nav_status" in topics:
            ep.nav_status_topic = "/local_nav_status"
            ep.nav_status_type = topics["/local_nav_status"] or ep.nav_status_type
        elif "/nav_status" in topics:
            ep.nav_status_topic = "/nav_status"
            ep.nav_status_type = topics["/nav_status"] or ep.nav_status_type
        if ep.nav_status_topic and not ep.nav_status_type:
            rc_t, tp_out, _ = self.run_ros_cmd(f"rostopic type {shlex.quote(ep.nav_status_topic)}", 2.0)
            if rc_t == 0 and tp_out.strip():
                ep.nav_status_type = tp_out.strip()
        ep.discovered_at = time.monotonic()
        return ep

    @staticmethod
    def _pick_topic(topics: Dict[str, str], msg_type: str, prefs: List[str], default: str) -> str:
        for p in prefs:
            if p in topics and (not topics[p] or topics[p] == msg_type):
                return p
        for tname, ttype in topics.items():
            if ttype == msg_type:
                return tname
        return default

    @staticmethod
    def _pick_cmd_vel(topics: Dict[str, str], subscribed: List[str], default: str) -> str:
        for candidate in ("/teb_polar_node/cmd_vel", "/cmd_vel"):
            if candidate in subscribed:
                return candidate
        for tname in subscribed:
            if topics.get(tname) == "geometry_msgs/Twist" or "cmd_vel" in tname:
                return tname
        for candidate in ("/teb_polar_node/cmd_vel", "/cmd_vel"):
            if candidate in topics:
                return candidate
        return default

    def discover_pcd_maps(self) -> Dict[str, Any]:
        """Dynamically locate real .pcd map directories via rosparam, rospack, navctl, and cfg.maps_dir."""
        search_dirs: List[Path] = []
        direct_files: List[Tuple[Path, str]] = []

        def _add_path(raw: str, source: str) -> None:
            clean = raw.strip().strip("'\"")
            if not clean or (not clean.startswith("/") and not Path(clean).is_absolute()):
                return
            p = Path(clean)
            if clean.lower().endswith(".pcd") and p.exists():
                direct_files.append((p, source))
            elif p.exists() and p.is_dir() and p not in search_dirs:
                search_dirs.append(p)

        rc_p, p_list, _ = self.run_ros_cmd("rosparam list", 2.5)
        if rc_p == 0 and p_list:
            for pname in p_list.splitlines():
                pl = pname.strip().lower()
                if any(k in pl for k in ("pcd", "map_file", "map_path", "save_dir", "map_dir")):
                    rc_v, pval, _ = self.run_ros_cmd(f"rosparam get {shlex.quote(pname.strip())}", 2.0)
                    if rc_v == 0 and pval:
                        _add_path(pval, f"rosparam:{pname.strip()}")

        for pkg in ("fast_lio", "open3d_loc", "teb_polar"):
            rc_pk, pk_out, _ = self.run_ros_cmd(f"rospack find {pkg}", 2.0)
            if rc_pk == 0 and pk_out:
                pkg_dir = Path(pk_out.splitlines()[0].strip())
                for sub in ("PCD", "pcd", "map", "maps"):
                    _add_path(str(pkg_dir / sub), f"rospack:{pkg}/{sub}")

        navctl_p = Path(self.cfg.navctl_bin)
        if navctl_p.exists():
            try:
                ntext = navctl_p.read_text(encoding="utf-8", errors="ignore")
                for m in re.finditer(r"(/[A-Za-z0-9_./-]*(?:map|pcd|PCD)[A-Za-z0-9_./-]*)", ntext):
                    _add_path(m.group(1), "navctl")
            except OSError:
                pass

        if self.cfg.maps_dir.exists() and self.cfg.maps_dir not in search_dirs:
            search_dirs.append(self.cfg.maps_dir)

        seen_paths: set[str] = set()
        maps: List[Dict[str, Any]] = []
        for fp, src in direct_files:
            key = str(fp)
            if key not in seen_paths and fp.is_file():
                seen_paths.add(key)
                st = fp.stat()
                maps.append({"name": fp.stem, "path": key, "size_bytes": st.st_size, "mtime": st.st_mtime, "source": src})

        for d in search_dirs:
            try:
                cand_files = sorted(d.rglob("*.pcd"), key=lambda x: x.stat().st_mtime, reverse=True)
            except OSError:
                continue
            for fp in cand_files:
                key = str(fp)
                if key not in seen_paths and fp.is_file():
                    seen_paths.add(key)
                    st = fp.stat()
                    maps.append({"name": fp.stem, "path": key, "size_bytes": st.st_size, "mtime": st.st_mtime, "source": str(d)})

        maps.sort(key=lambda item: item["mtime"], reverse=True)
        self._cached.map_search_dirs = [str(d) for d in search_dirs]
        return {"ok": True, "search_dirs": self._cached.map_search_dirs, "maps": maps, "count": len(maps)}
