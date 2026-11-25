# @file: src/ros_bridge/relocalize_helper.py
# @brief: Auto-first ROS relocalization engine (ROS service -> prior /initialpose -> navctl restart) with manual initialpose support.
# @exports: RosRelocalizer

from __future__ import annotations

import re
import time
from typing import Any, Dict, Optional, Tuple

from src.ros_bridge.navctl_runner import NavctlRunner
from src.ros_bridge.ros_live_slam_tap import RosLiveSlamTap
from src.ros_bridge.ros_runtime_discovery import RosRuntimeDiscovery
from src.ros_bridge.ros_topic_service_bridge import RosTopicServiceBridge

_RELOC_SRV_RE = re.compile(r"(relocaliz|global_localization|reinit_loc|reset_loc)", re.IGNORECASE)


class RosRelocalizer:
    """Runs lower-computer auto-first relocalization against open3d_loc/FAST-LIO and validates convergence."""

    def __init__(
        self,
        ros_bridge: RosTopicServiceBridge,
        discovery: RosRuntimeDiscovery,
        slam_tap: RosLiveSlamTap,
        navctl: NavctlRunner,
    ) -> None:
        self.ros_bridge = ros_bridge
        self.discovery = discovery
        self.slam_tap = slam_tap
        self.navctl = navctl

    @staticmethod
    def _norm_pose(raw: Optional[Dict[str, Any]]) -> Optional[Tuple[float, float, float]]:
        if not isinstance(raw, dict) or "x" not in raw or "y" not in raw:
            return None
        return (float(raw["x"]), float(raw["y"]), float(raw.get("yaw", 0.0)))

    def _sample_telemetry(
        self, fresh_only: bool = False, min_state_seq: int = 0,
    ) -> Tuple[Optional[Dict[str, float]], Optional[float], Optional[float]]:
        tap = self.slam_tap.get_live_state()
        tap_pose = tap.get("pose") if isinstance(tap.get("pose"), dict) else None
        tap_conf = tap.get("localization_confidence")
        tap_delay = tap.get("localization_delay_ms")
        if self.slam_tap.is_streaming():
            if fresh_only and int(tap.get("state_seq", 0)) <= min_state_seq:
                return None, None, None
            return tap_pose, tap_conf, tap_delay
        snap = self.ros_bridge.read_telemetry_snapshot()
        snap_pose = {"x": snap.pose[0], "y": snap.pose[1], "yaw": snap.pose[2]} if snap.pose is not None else None
        if snap.pose is not None:
            self.slam_tap.push_external_frame(
                pose=snap_pose, confidence=snap.localization_confidence, delay_ms=snap.localization_delay_ms,
                nav_status=snap.local_nav_status, ros_available=snap.ros_available,
            )
        if fresh_only:
            return snap_pose, snap.localization_confidence, snap.localization_delay_ms
        return (
            snap_pose if snap_pose is not None else tap_pose,
            snap.localization_confidence if snap.localization_confidence is not None else tap_conf,
            snap.localization_delay_ms if snap.localization_delay_ms is not None else tap_delay,
        )

    def _wait_convergence(
        self, min_confidence: float, timeout_s: float, min_state_seq: int = 0,
    ) -> Tuple[bool, Optional[Dict[str, float]], Optional[float], Optional[float], bool]:
        t0 = time.monotonic()
        deadline = t0 + max(0.2, float(timeout_s))
        conf_topic = self.discovery.current.confidence_topic
        has_conf_topic = conf_topic in (self.discovery.current.all_topics or {})
        last_pose, last_conf, last_delay = None, None, None
        conf_seen = self.slam_tap.has_confidence_telemetry()
        while True:
            pose, conf, delay = self._sample_telemetry(fresh_only=True, min_state_seq=min_state_seq)
            if pose is not None:
                last_pose = pose
            if conf is not None:
                last_conf = float(conf)
                conf_seen = True
            if delay is not None:
                last_delay = float(delay)
            if last_pose is not None and last_conf is not None and last_conf >= min_confidence:
                return True, last_pose, last_conf, last_delay, True
            elapsed = time.monotonic() - t0
            if time.monotonic() >= deadline:
                break
            if not conf_seen and not has_conf_topic and elapsed >= min(0.35, timeout_s):
                break
            time.sleep(min(0.2, max(0.05, deadline - time.monotonic())))
        return False, last_pose, last_conf, last_delay, conf_seen

    def _find_relocalize_service(self) -> Optional[str]:
        rc, out, _ = self.ros_bridge.diagnostics.run_ros_cmd("rosservice list", 2.5)
        if rc != 0 or not out:
            return None
        for line in out.splitlines():
            srv = line.strip()
            if srv and _RELOC_SRV_RE.search(srv):
                return srv
        return None

    def relocalize(
        self,
        mode: str = "auto",
        pose: Optional[Tuple[float, float, float]] = None,
        fallback_pose: Optional[Tuple[float, float, float]] = None,
        min_confidence: float = 0.65,
        timeout_s: float = 6.0,
        allow_restart: bool = True,
    ) -> Dict[str, Any]:
        """Execute auto-first or manual ROS relocalization and report real convergence metrics."""
        norm_mode = (mode or "auto").strip().lower()
        if norm_mode not in ("auto", "manual"):
            return {"ok": False, "converged": False, "status_code": 400, "ros_available": False, "message": f"不支持的重定位模式: {mode}"}
        self.ros_bridge.cancel_planning()
        self.ros_bridge.stop_cmd_vel()
        if not self.ros_bridge.is_ros_master_reachable():
            return {
                "ok": False, "converged": False, "status_code": 503, "ros_available": False,
                "mode": norm_mode, "strategy_used": "", "pose": None, "confidence": None, "delay_ms": None,
                "min_confidence": min_confidence, "needs_manual": True, "message": "ROS Master 不可达，无法重定位",
            }
        self.discovery.discover_topics()
        if norm_mode == "manual":
            if pose is None:
                return {"ok": False, "converged": False, "status_code": 400, "ros_available": True, "message": "手动重定位缺少 x, y 坐标"}
            seq0 = int(self.slam_tap.get_live_state().get("state_seq", 0))
            pub = self.ros_bridge.publish_initial_pose(pose[0], pose[1], pose[2], xy_var=0.25, yaw_var=0.25)
            if not pub.get("ok"):
                return {
                    "ok": False, "converged": False, "status_code": 503, "ros_available": bool(pub.get("ros_available", False)),
                    "mode": "manual", "strategy_used": "manual_initialpose", "needs_manual": True,
                    "message": str(pub.get("reason") or "发布 /initialpose 失败"),
                }
            conv, p_out, conf, delay, conf_seen = self._wait_convergence(min_confidence, timeout_s, min_state_seq=seq0)
            ok = conv if conf_seen else True
            if conv and conf is not None:
                msg = f"手动重定位已收敛 (置信度 {conf:.2f})"
            elif conf_seen:
                msg = f"手动重定位未收敛 (置信度 {conf:.2f} < {min_confidence:.2f})" if conf is not None else "手动重定位未收敛 (超时未收到新置信度反馈)"
            else:
                msg = f"已下发手动 /initialpose ({pose[0]:.2f}, {pose[1]:.2f})"
            return {
                "ok": ok, "converged": conv, "status_code": 200, "ros_available": True,
                "mode": "manual", "strategy_used": "manual_initialpose", "pose": p_out or {"x": pose[0], "y": pose[1], "yaw": pose[2]},
                "confidence": conf, "delay_ms": delay, "min_confidence": min_confidence,
                "needs_manual": not ok, "message": msg,
            }

        # Auto Stage 1: native ROS relocalization service (if provided by open3d_loc build)
        srv = self._find_relocalize_service()
        last_pose, last_conf, last_delay, strat = None, None, None, "auto_none"
        if srv:
            seq1 = int(self.slam_tap.get_live_state().get("state_seq", 0))
            rc, _, _ = self.ros_bridge.diagnostics.run_ros_cmd(f"rosservice call {srv} \"{{}}\"", 3.5)
            if rc == 0:
                strat = f"ros_service:{srv}"
                conv, last_pose, last_conf, last_delay, _ = self._wait_convergence(min_confidence, min(timeout_s, 3.0), min_state_seq=seq1)
                if conv:
                    return {
                        "ok": True, "converged": True, "status_code": 200, "ros_available": True,
                        "mode": "auto", "strategy_used": strat, "pose": last_pose, "confidence": last_conf,
                        "delay_ms": last_delay, "min_confidence": min_confidence, "needs_manual": False,
                        "message": f"自动重定位成功 ({strat}, 置信度 {last_conf:.2f})",
                    }

        # Auto Stage 2: publish /initialpose from best prior seed with relaxed covariance
        cur_pose, _, _ = self._sample_telemetry()
        seed = (
            pose or self._norm_pose(self.slam_tap.get_last_good_pose())
            or fallback_pose or self._norm_pose(cur_pose) or (0.0, 0.0, 0.0)
        )
        seq2 = int(self.slam_tap.get_live_state().get("state_seq", 0))
        pub2 = self.ros_bridge.publish_initial_pose(seed[0], seed[1], seed[2], xy_var=1.0, yaw_var=0.5)
        if pub2.get("ok"):
            strat = "auto_initialpose"
            conv, last_pose, last_conf, last_delay, _ = self._wait_convergence(min_confidence, timeout_s, min_state_seq=seq2)
            if conv:
                return {
                    "ok": True, "converged": True, "status_code": 200, "ros_available": True,
                    "mode": "auto", "strategy_used": strat, "pose": last_pose, "confidence": last_conf,
                    "delay_ms": last_delay, "min_confidence": min_confidence, "needs_manual": False,
                    "message": f"先验位姿重定位收敛 (置信度 {last_conf:.2f})",
                }

        # Auto Stage 3: navctl restart localization global fallback
        if allow_restart and self.navctl.is_available():
            nav_res = self.navctl.execute("restart localization")
            if nav_res.ok:
                strat = "navctl_restart_localization"
                self.discovery.discover_topics(force=True)
                self.slam_tap.start()
                seq3 = int(self.slam_tap.get_live_state().get("state_seq", 0))
                self.ros_bridge.publish_initial_pose(seed[0], seed[1], seed[2], xy_var=1.5, yaw_var=0.8)
                conv, last_pose, last_conf, last_delay, _ = self._wait_convergence(min_confidence, timeout_s, min_state_seq=seq3)
                if conv:
                    return {
                        "ok": True, "converged": True, "status_code": 200, "ros_available": True,
                        "mode": "auto", "strategy_used": strat, "pose": last_pose, "confidence": last_conf,
                        "delay_ms": last_delay, "min_confidence": min_confidence, "needs_manual": False,
                        "message": f"重启定位节点后重定位收敛 (置信度 {last_conf:.2f})",
                    }

        conf_txt = f"当前置信度 {last_conf:.2f} < {min_confidence:.2f}" if last_conf is not None else "未检测到有效定位置信度反馈"
        return {
            "ok": False, "converged": False, "status_code": 200, "ros_available": True,
            "mode": "auto", "strategy_used": strat, "pose": last_pose, "confidence": last_conf,
            "delay_ms": last_delay, "min_confidence": min_confidence, "needs_manual": True,
            "message": f"自动重定位未收敛（{conf_txt}），请在 2D 地图拖拽手动重定位",
        }
