# @file: src/ui/mapping/navigation_map_page.py
# @brief: 3-column Mapping & Navigation workspace with SSE stream, auto/manual ROS relocalization, 2D goals, and teleop SLAM.
# @exports: NavigationMapPage

from __future__ import annotations

import math
from typing import Any, Dict, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from src.core.event_bus import StudioEvent
from src.services.studio_state_service import StudioStateService
from src.ui.choreography.stage_canvas_2d import StageCanvas2D
from src.ui.common.async_task import TaskHandle, run_in_background
from src.ui.design_system.tokens import C_TEXT_2, FONT_MONO
from src.ui.design_system.u_buttons import UBadge, UButton, UIconButton, USegmented
from src.ui.design_system.u_panels import UPanel
from src.ui.mapping.nav_live_poller import NavLiveStreamWorker
from src.ui.mapping.nav_relocalize_helper import evaluate_nav_alert, extract_track_fallback_pose, format_nav_telemetry_line
from src.ui.mapping.pcd_map_library_dock import PcdMapLibraryDock
from src.ui.mapping.teleop_mapping_dock import TeleopMappingDock
from src.viewport3d.stage_viewport_3d import StageViewport3D


class NavigationMapPage(QWidget):
    """3-column PCD map, real-time ROS navigation/relocalization, and teleop SLAM workspace."""

    def __init__(self, state: StudioStateService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._last_alert_key: str = ""
        self.live_worker = NavLiveStreamWorker(state.http_rpc, self)
        self.live_worker.liveStateReceived.connect(self._on_live_state)
        self.live_worker.liveCloudReceived.connect(self._on_live_cloud)
        self.live_worker.streamStatusChanged.connect(self._on_stream_status)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        self.lib_dock = PcdMapLibraryDock(state, self)
        self.center_panel = UPanel(title="实时导航视口", header_widgets=[], parent=self)
        self.ros_badge = UBadge("ROS 待连接", tone="neutral", parent=self.center_panel)
        self.mode_switch = USegmented(["3D 点云", "2D 栅格"], default="2D 栅格", parent=self.center_panel)
        self.reset_b = UIconButton("home", tooltip="重置地图视角", size=24, parent=self.center_panel)
        hdr = self.center_panel.header_bar.layout()
        hdr.addWidget(self.ros_badge)
        hdr.addWidget(self.reset_b)
        hdr.addWidget(self.mode_switch)
        self.center_panel.set_help_text(
            "点击「重定位」优先触发下位机自动重定位；未收敛时自动切入 2D 拖拽手动重定位；支持 2D 点击导航与 3D/2D 切换。",
            title="导航视口",
        )

        ctrl_bar = QHBoxLayout()
        ctrl_bar.setContentsMargins(0, 0, 0, 4)
        ctrl_bar.setSpacing(5)
        bw = self.center_panel.body_widget
        self.btn_nav_loc = UButton("定位导航", variant="default", size="sm", parent=bw)
        self.btn_nav_map = UButton("建图模式", variant="default", size="sm", parent=bw)
        self.btn_nav_stop = UButton("停导航", variant="default", size="sm", parent=bw)
        self.btn_discover = UButton("ROS自省", variant="default", size="sm", parent=bw)
        self.btn_relocalize = UButton("重定位", variant="default", size="sm", parent=bw)
        self.btn_tool_view = UButton("浏览", variant="primary", size="sm", parent=bw)
        self.btn_tool_init = UButton("设初始位姿", variant="default", size="sm", parent=bw)
        self.btn_tool_goal = UButton("点击导航", variant="default", size="sm", parent=bw)
        self.btn_cancel_goal = UButton("取消导航", variant="danger", size="sm", parent=bw)
        for w in (
            self.btn_nav_loc, self.btn_nav_map, self.btn_nav_stop, self.btn_discover, self.btn_relocalize,
            self.btn_tool_view, self.btn_tool_init, self.btn_tool_goal, self.btn_cancel_goal,
        ):
            ctrl_bar.addWidget(w)
        ctrl_bar.addStretch(1)
        self.center_panel.body_layout.addLayout(ctrl_bar)

        self.telemetry_lbl = QLabel("就绪 · 请选择地图或点云", bw)
        self.telemetry_lbl.setStyleSheet(f"color: {C_TEXT_2}; font-family: {FONT_MONO}; font-size: 11px;")
        self.center_panel.body_layout.addWidget(self.telemetry_lbl)

        self.stack = QStackedWidget(bw)
        self.vp3d = StageViewport3D(state, self.stack)
        self.map2d = StageCanvas2D(state, self.stack)
        self.stack.addWidget(self.vp3d)
        self.stack.addWidget(self.map2d)
        self.stack.setCurrentIndex(1)
        self.center_panel.body_layout.addWidget(self.stack, 1)

        self.teleop_dock = TeleopMappingDock(state, self)
        lay.addWidget(self.lib_dock)
        lay.addWidget(self.center_panel, 1)
        lay.addWidget(self.teleop_dock)

        self.mode_switch.currentChanged.connect(lambda m: self.stack.setCurrentIndex(0 if "3D" in m else 1))
        self.reset_b.clicked.connect(lambda: self.vp3d.reset_view("iso") if self.stack.currentIndex() == 0 else self.map2d.reset_view())
        self.btn_nav_loc.clicked.connect(lambda: self._run_navctl("restart localization"))
        self.btn_nav_map.clicked.connect(lambda: self._run_navctl("restart mapping"))
        self.btn_nav_stop.clicked.connect(lambda: self._run_navctl("stop"))
        self.btn_discover.clicked.connect(self._run_discovery)
        self.btn_relocalize.clicked.connect(self._run_auto_relocalize)
        self.btn_tool_view.clicked.connect(lambda: self._set_map_tool("view"))
        self.btn_tool_init.clicked.connect(lambda: self._set_map_tool("set_initialpose"))
        self.btn_tool_goal.clicked.connect(lambda: self._set_map_tool("set_nav_goal"))
        self.btn_cancel_goal.clicked.connect(self._cancel_nav)
        self.map2d.initialPoseRequested.connect(self._send_initialpose)
        self.map2d.navGoalRequested.connect(self._send_nav_goal)

        self.lib_dock.cloudLoaded.connect(lambda _m, cloud: self.vp3d.set_point_cloud(cloud.points_xyz, cloud.colors_rgb))
        self.teleop_dock.slamCloudUpdated.connect(lambda pts, rgb: self.vp3d.set_point_cloud(pts, rgb))
        self.teleop_dock.targetChanged.connect(self._on_target_switched)
        state.bus.subscribe(StudioEvent.TRACKS_UPDATED, lambda _p: self.sync_active_robot_stream())
        self.destroyed.connect(lambda _=None: self.live_worker.stop_stream())

    def _on_target_switched(self, _tid: str, ip: str) -> None:
        self.lib_dock.active_robot_ip = ip.strip()
        self.live_worker.start_stream(ip)

    def _active_robot_ip(self) -> str:
        data = self.teleop_dock.target_sel.current_data()
        if isinstance(data, tuple) and len(data) >= 2 and data[1]:
            return str(data[1]).strip()
        return next((tr.robot_ip.strip() for tr in self.state.tracks if tr.robot_ip), "")

    def sync_active_robot_stream(self) -> None:
        ip = self._active_robot_ip()
        self.lib_dock.active_robot_ip = ip
        self.live_worker.start_stream(ip) if ip else self.live_worker.stop_stream()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.sync_active_robot_stream()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.live_worker.stop_stream()

    def _set_map_tool(self, tool: str) -> None:
        self.map2d.set_draw_mode(tool)
        if tool != "view":
            self.mode_switch.set_current("2D 栅格")
            self.stack.setCurrentIndex(1)
        for btn, key in ((self.btn_tool_view, "view"), (self.btn_tool_init, "set_initialpose"), (self.btn_tool_goal, "set_nav_goal")):
            btn.set_variant("primary" if key == tool else "default")

    def _run_navctl(self, action: str) -> Optional[TaskHandle]:
        ip = self._active_robot_ip()
        if not ip:
            self.state.notify("请先添加并选择配置了 Wi-Fi IP 的机器人轨道", "warn"); return None
        return run_in_background(
            lambda: self.state.http_rpc.navctl(ip, action),
            on_done=lambda res: self._on_navctl_done(action, res), busy_text=f"正在后台执行 navctl {action}...", notifier=self.state.notify,
        )

    def _on_navctl_done(self, action: str, res) -> None:
        self.state.notify(f"navctl {action}: {res.message}", "ok" if res.ok else "warn")
        if res.ok: self.sync_active_robot_stream(); self._run_discovery()

    def _run_discovery(self) -> Optional[TaskHandle]:
        ip = self._active_robot_ip()
        if not ip:
            self.state.notify("请先添加并选择配置了 Wi-Fi IP 的机器人轨道", "warn"); return None
        return run_in_background(
            lambda: self.state.http_rpc.fetch_nav_discovery(ip),
            on_done=self._on_discovery_done, busy_text="正在后台执行 ROS 动态自省...", notifier=self.state.notify,
        )

    def _on_discovery_done(self, res) -> Optional[Dict[str, Any]]:
        if not res.ok:
            self.state.notify(f"ROS 动态自省失败: {res.message}", "warn"); return None
        ep, maps = res.data.get("endpoints") or {}, (res.data.get("maps") or {}).get("count", 0)
        summary = f"Shell:{ep.get('shell_mode')} | Odom:{ep.get('odom_topic')} | Cloud:{ep.get('cloud_topic')} | Vel:{ep.get('cmd_vel_topic')} | 地图:{maps}个"
        self.telemetry_lbl.setText(summary); self.state.notify(f"ROS 动态自省完成: {summary}", "ok")
        return res.data

    def _run_auto_relocalize(self) -> Optional[TaskHandle]:
        """Trigger lower-computer auto-first ROS relocalization; falls back to manual 2D drag tool if needed."""
        ip = self._active_robot_ip()
        if not ip:
            self.state.notify("请先添加并选择配置了 Wi-Fi IP 的机器人轨道", "warn")
            return None
        fb = extract_track_fallback_pose(self.state.tracks, ip)
        return run_in_background(
            lambda: self.state.http_rpc.relocalize(ip, mode="auto", fallback_pose=fb, allow_restart=True),
            on_done=self._on_auto_relocalize_done, busy_widgets=[self.btn_relocalize],
            busy_text="正在执行下位机自动重定位...", notifier=self.state.notify,
        )

    def _on_auto_relocalize_done(self, res) -> None:
        if res.ok:
            self._set_map_tool("view")
            self.state.notify(res.message or "自动重定位成功", "ok")
            return
        if res.data.get("needs_manual") or res.status_code == 200:
            self._set_map_tool("set_initialpose")
            self.state.notify(res.message or "自动重定位未收敛，请在 2D 地图拖拽设初始位姿", "warn")
            return
        self.state.notify(f"重定位失败: {res.message}", "warn")

    def _send_initialpose(self, x: float, y: float, yaw: float) -> Optional[TaskHandle]:
        ip = self._active_robot_ip()
        if not ip:
            self.state.notify("未配置机器人 Wi-Fi IP，无法发布 /initialpose", "warn")
            return None
        self._set_map_tool("view")
        def _bg():
            resp = self.state.http_rpc.relocalize(ip, mode="manual", x=x, y=y, yaw=yaw, allow_restart=False)
            return self.state.http_rpc.set_initial_pose(ip, x, y, yaw) if resp.status_code == 404 else resp
        return run_in_background(
            _bg,
            on_done=lambda res: self._on_manual_relocalize_done(x, y, yaw, res),
            busy_text="正在下发手动重定位 /initialpose...", notifier=self.state.notify,
        )

    def _on_manual_relocalize_done(self, x: float, y: float, yaw: float, res) -> None:
        if not res.ok and isinstance(res.data, dict) and res.data.get("needs_manual"):
            self._set_map_tool("set_initialpose")
        self.state.notify(
            res.message or f"/initialpose ({x:.2f}, {y:.2f}, {math.degrees(yaw):.0f}°): {'已下发' if res.ok else '失败'}",
            "ok" if res.ok else "warn",
        )

    def _send_nav_goal(self, x: float, y: float, yaw: float) -> Optional[TaskHandle]:
        ip = self._active_robot_ip()
        if not ip:
            self.state.notify("未配置机器人 Wi-Fi IP，无法下发导航目标", "warn"); return None
        self._set_map_tool("view")
        return run_in_background(
            lambda: self.state.http_rpc.send_nav_goal(ip, x, y, yaw),
            on_done=lambda res: self._on_nav_goal_done(x, y, yaw, res), busy_text="正在后台下发导航目标...", notifier=self.state.notify,
        )

    def _on_nav_goal_done(self, x: float, y: float, yaw: float, res) -> None:
        if res.ok: self.map2d.set_live_nav_overlay(pose=self.map2d._live_nav.pose, active_goal=(x, y))
        self.state.notify(f"导航目标 ({x:.2f}, {y:.2f}, {math.degrees(yaw):.0f}°): {'已下发' if res.ok else res.message}", "ok" if res.ok else "warn")

    def _cancel_nav(self) -> Optional[TaskHandle]:
        ip = self._active_robot_ip()
        if not ip:
            self.state.notify("未配置机器人 Wi-Fi IP，无法取消导航", "warn"); return None
        self.map2d.set_live_nav_overlay(pose=self.map2d._live_nav.pose, active_goal=None)
        self.map2d._live_nav.active_goal = None; self.map2d.update()
        return run_in_background(
            lambda: self.state.http_rpc.cancel_navigation(ip),
            on_done=lambda res: self.state.notify(f"取消导航: {'成功' if res.ok else res.message}", "info" if res.ok else "warn"),
            busy_text="正在后台取消导航...", notifier=self.state.notify,
        )

    def _on_stream_status(self, ok: bool, msg: str) -> None:
        self.ros_badge.setText("SSE 实时" if ok else "ROS 待连接")
        self.ros_badge.set_tone("ok" if ok else "neutral")
        if not ok:
            self.telemetry_lbl.setText(msg)

    def _on_live_state(self, state: Dict[str, Any]) -> None:
        ros_ok = bool(state.get("ros_available", False))
        p = state.get("pose")
        pose_tuple = (float(p["x"]), float(p["y"]), float(p.get("yaw", 0.0))) if isinstance(p, dict) else None
        gpath = state.get("global_path") or []
        self.map2d._live_nav.pose = pose_tuple
        self.map2d._live_nav.global_path = [(float(pt[0]), float(pt[1])) for pt in gpath if len(pt) >= 2]
        self.map2d._live_nav.scan_xy = [(float(pt[0]), float(pt[1])) for pt in (state.get("scan_xy") or []) if len(pt) >= 2]
        self.vp3d._live_pose = pose_tuple
        self.vp3d._live_path = list(self.map2d._live_nav.global_path)
        rs = state.get("robot_state") if isinstance(state.get("robot_state"), dict) else {}
        tone, badge_txt, clear_goal, alert_msg = evaluate_nav_alert(rs)
        if clear_goal:
            self.map2d._live_nav.active_goal = None
        (self.map2d if self.stack.currentIndex() == 1 else self.vp3d).update()
        self.teleop_dock.update_live_telemetry(state)
        if tone:
            self.ros_badge.setText(badge_txt); self.ros_badge.set_tone(tone)
        else:
            self.ros_badge.setText("ROS 在线" if ros_ok else "ROS 未就绪"); self.ros_badge.set_tone("ok" if ros_ok else "warn")
        if alert_msg and alert_msg != self._last_alert_key:
            self._last_alert_key = alert_msg; self.state.notify(alert_msg, "warn")
        elif not alert_msg:
            self._last_alert_key = ""
        self.telemetry_lbl.setText(format_nav_telemetry_line(state, pose_tuple, rs))

    def _on_live_cloud(self, pts, _seq: int) -> None:
        self.vp3d.set_point_cloud(pts, None, repaint=(self.stack.currentIndex() == 0))
        self.teleop_dock.pose_lbl.setText(
            f"位姿: ({self.state.slam_client.state.pose[0]:.2f}, {self.state.slam_client.state.pose[1]:.2f}) | 真实点云: {len(pts):,}"
        )
