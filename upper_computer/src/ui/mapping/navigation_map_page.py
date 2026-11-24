# @file: src/ui/mapping/navigation_map_page.py
# @brief: 3-column Mapping & Navigation workspace with live ROS SSE stream, 2D goal/initialpose interaction, and teleop SLAM.
# @exports: NavigationMapPage

from __future__ import annotations

import math
from typing import Any, Dict, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from src.core.event_bus import StudioEvent
from src.services.studio_state_service import StudioStateService
from src.ui.choreography.stage_canvas_2d import StageCanvas2D
from src.ui.design_system.tokens import C_TEXT_2, FONT_MONO
from src.ui.design_system.u_buttons import UBadge, UButton, UIconButton, USegmented
from src.ui.design_system.u_panels import UPanel
from src.ui.mapping.nav_live_poller import NavLiveStreamWorker
from src.ui.mapping.pcd_map_library_dock import PcdMapLibraryDock
from src.ui.mapping.teleop_mapping_dock import TeleopMappingDock
from src.viewport3d.stage_viewport_3d import StageViewport3D


class NavigationMapPage(QWidget):
    """3-column PCD map, real-time ROS navigation, and teleop SLAM workspace."""

    def __init__(self, state: StudioStateService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
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
            "2D 模式下支持左键拖拽设初始位姿 (/initialpose) 或单点发送导航目标；右上角切换 3D 点云与 2D 栅格。",
            title="导航视口",
        )

        # Compact interactive navigation & navctl toolbar
        ctrl_bar = QHBoxLayout()
        ctrl_bar.setContentsMargins(0, 0, 0, 4)
        ctrl_bar.setSpacing(5)
        self.btn_nav_loc = UButton("定位导航", variant="default", size="sm", parent=self.center_panel.body_widget)
        self.btn_nav_map = UButton("建图模式", variant="default", size="sm", parent=self.center_panel.body_widget)
        self.btn_nav_stop = UButton("停导航", variant="default", size="sm", parent=self.center_panel.body_widget)
        self.btn_discover = UButton("ROS自省", variant="default", size="sm", parent=self.center_panel.body_widget)
        self.btn_tool_view = UButton("浏览", variant="primary", size="sm", parent=self.center_panel.body_widget)
        self.btn_tool_init = UButton("设初始位姿", variant="default", size="sm", parent=self.center_panel.body_widget)
        self.btn_tool_goal = UButton("点击导航", variant="default", size="sm", parent=self.center_panel.body_widget)
        self.btn_cancel_goal = UButton("取消导航", variant="danger", size="sm", parent=self.center_panel.body_widget)
        for w in (
            self.btn_nav_loc, self.btn_nav_map, self.btn_nav_stop, self.btn_discover,
            self.btn_tool_view, self.btn_tool_init, self.btn_tool_goal, self.btn_cancel_goal,
        ):
            ctrl_bar.addWidget(w)
        ctrl_bar.addStretch(1)
        self.center_panel.body_layout.addLayout(ctrl_bar)

        self.telemetry_lbl = QLabel("就绪 · 请选择地图或点云", self.center_panel.body_widget)
        self.telemetry_lbl.setStyleSheet(f"color: {C_TEXT_2}; font-family: {FONT_MONO}; font-size: 11px;")
        self.center_panel.body_layout.addWidget(self.telemetry_lbl)

        self.stack = QStackedWidget(self.center_panel.body_widget)
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
        self.reset_b.clicked.connect(
            lambda: self.vp3d.reset_view("iso") if self.stack.currentIndex() == 0 else self.map2d.reset_view()
        )
        self.btn_nav_loc.clicked.connect(lambda: self._run_navctl("restart localization"))
        self.btn_nav_map.clicked.connect(lambda: self._run_navctl("restart mapping"))
        self.btn_nav_stop.clicked.connect(lambda: self._run_navctl("stop"))
        self.btn_discover.clicked.connect(self._run_discovery)
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
        for tr in self.state.tracks:
            if tr.robot_ip:
                return tr.robot_ip.strip()
        return ""

    def sync_active_robot_stream(self) -> None:
        ip = self._active_robot_ip()
        self.lib_dock.active_robot_ip = ip
        if ip:
            self.live_worker.start_stream(ip)
        else:
            self.live_worker.stop_stream()

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
        for btn, key in (
            (self.btn_tool_view, "view"),
            (self.btn_tool_init, "set_initialpose"),
            (self.btn_tool_goal, "set_nav_goal"),
        ):
            btn.set_variant("primary" if key == tool else "default")

    def _run_navctl(self, action: str) -> bool:
        ip = self._active_robot_ip()
        if not ip:
            self.state.notify("请先添加并选择配置了 Wi-Fi IP 的机器人轨道", "warn")
            return False
        res = self.state.http_rpc.navctl(ip, action)
        self.state.notify(f"navctl {action}: {res.message}", "ok" if res.ok else "warn")
        if res.ok:
            self.sync_active_robot_stream()
            self._run_discovery()
        return res.ok

    def _run_discovery(self) -> Optional[Dict[str, Any]]:
        ip = self._active_robot_ip()
        if not ip:
            self.state.notify("请先添加并选择配置了 Wi-Fi IP 的机器人轨道", "warn")
            return None
        res = self.state.http_rpc.fetch_nav_discovery(ip)
        if not res.ok:
            self.state.notify(f"ROS 动态自省失败: {res.message}", "warn")
            return None
        ep = res.data.get("endpoints") or {}
        maps = (res.data.get("maps") or {}).get("count", 0)
        summary = (
            f"Shell:{ep.get('shell_mode')} | Odom:{ep.get('odom_topic')} | "
            f"Cloud:{ep.get('cloud_topic')} | Vel:{ep.get('cmd_vel_topic')} | 地图:{maps}个"
        )
        self.telemetry_lbl.setText(summary)
        self.state.notify(f"ROS 动态自省完成: {summary}", "ok")
        return res.data

    def _send_initialpose(self, x: float, y: float, yaw: float) -> bool:
        ip = self._active_robot_ip()
        if not ip:
            self.state.notify("未配置机器人 Wi-Fi IP，无法发布 /initialpose", "warn")
            return False
        res = self.state.http_rpc.set_initial_pose(ip, x, y, yaw)
        self.state.notify(
            f"/initialpose ({x:.2f}, {y:.2f}, {math.degrees(yaw):.0f}°): {'已下发' if res.ok else res.message}",
            "ok" if res.ok else "warn",
        )
        self._set_map_tool("view")
        return res.ok

    def _send_nav_goal(self, x: float, y: float, yaw: float) -> bool:
        ip = self._active_robot_ip()
        if not ip:
            self.state.notify("未配置机器人 Wi-Fi IP，无法下发导航目标", "warn")
            return False
        res = self.state.http_rpc.send_nav_goal(ip, x, y, yaw)
        self.state.notify(
            f"导航目标 ({x:.2f}, {y:.2f}, {math.degrees(yaw):.0f}°): {'已下发' if res.ok else res.message}",
            "ok" if res.ok else "warn",
        )
        self._set_map_tool("view")
        return res.ok

    def _cancel_nav(self) -> bool:
        ip = self._active_robot_ip()
        if not ip:
            self.state.notify("未配置机器人 Wi-Fi IP，无法取消导航", "warn")
            return False
        res = self.state.http_rpc.cancel_navigation(ip)
        self.map2d.set_live_nav_overlay(pose=self.map2d._live_nav.pose, active_goal=None)
        self.map2d._live_nav.active_goal = None
        self.map2d.update()
        self.state.notify(f"取消导航: {'成功' if res.ok else res.message}", "info" if res.ok else "warn")
        return res.ok

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
        if self.stack.currentIndex() == 1:
            self.map2d.update()
        else:
            self.vp3d.update()
        self.teleop_dock.update_live_telemetry(state)
        self.ros_badge.setText("ROS 在线" if ros_ok else "ROS 未就绪")
        self.ros_badge.set_tone("ok" if ros_ok else "warn")
        conf = state.get("localization_confidence")
        delay = state.get("localization_delay_ms")
        nav_st = state.get("local_nav_status") or "-"
        pts = int(state.get("point_count", 0) or 0)
        pose_s = f"({pose_tuple[0]:.2f},{pose_tuple[1]:.2f},{math.degrees(pose_tuple[2]):.0f}°)" if pose_tuple else "(--)"
        conf_s = f"{conf:.2f}" if isinstance(conf, (int, float)) else "-"
        delay_s = f"{delay:.1f}ms" if isinstance(delay, (int, float)) else "-"
        self.telemetry_lbl.setText(f"位姿:{pose_s} | 置信度:{conf_s} | 延迟:{delay_s} | 状态:{nav_st} | 点云:{pts:,}")

    def _on_live_cloud(self, pts, _seq: int) -> None:
        self.vp3d.set_point_cloud(pts, None, repaint=(self.stack.currentIndex() == 0))
        self.teleop_dock.pose_lbl.setText(
            f"位姿: ({self.state.slam_client.state.pose[0]:.2f}, {self.state.slam_client.state.pose[1]:.2f}) | 真实点云: {len(pts):,}"
        )
