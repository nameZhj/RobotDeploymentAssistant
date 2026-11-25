# @file: src/ui/mapping/teleop_mapping_dock.py
# @brief: Right 296px Teleop SLAM control panel sending real HTTP velocity hold commands in background tasks and downloading authentic .pcd maps.
# @exports: TeleopMappingDock

from __future__ import annotations

import threading
from typing import Any, Dict, Optional, Tuple
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QWidget

from src.core.event_bus import StudioEvent
from src.domain.map_entities import PcdMapEntity
from src.persistence.pcd_grid_generator import generate_occupancy_grid_png
from src.persistence.pcd_parser import load_pcd
from src.core.paths import get_paths
from src.services.studio_state_service import StudioStateService
from src.ui.common.async_task import TaskHandle, run_in_background
from src.ui.design_system.tokens import C_TEXT_2, FONT_MONO
from src.ui.design_system.u_buttons import UBadge, UButton
from src.ui.design_system.u_inputs import UInputNumber, USelect
from src.ui.design_system.u_panels import UPanel


class TeleopMappingDock(UPanel):
    """Teleop SLAM panel wired to real lower-computer ROS velocity hold & finish-mapping HTTP APIs."""

    slamCloudUpdated = Signal(object, object)  # (xyz, rgb)
    targetChanged = Signal(str, str)  # (target_id, robot_ip)

    def __init__(self, state: StudioStateService, parent: QWidget | None = None) -> None:
        super().__init__(
            title="遥控建图",
            header_widgets=[],
            parent=parent,
            help_text="连接机器人后可通过遥控指令实时建图，完成后保存并导出 .PCD 点云地图。",
        )
        self.state = state
        self.setFixedWidth(296)
        self.body_layout.setSpacing(8)
        self._teleop_lock = threading.Lock()  # serializes velocity-hold commands so order is preserved

        row1 = QHBoxLayout()
        self.target_sel = USelect([], self.body_widget)
        self.target_sel.currentIndexChanged.connect(self._on_target_changed)
        self.status_badge = UBadge("未激活", tone="neutral", parent=self.body_widget)
        row1.addWidget(self.target_sel, 1)
        row1.addWidget(self.status_badge)
        self.body_layout.addLayout(row1)
        state.bus.subscribe(StudioEvent.TRACKS_UPDATED, lambda _p: self.refresh_targets())
        self.refresh_targets()

        row2 = QHBoxLayout()
        self.start_b = UButton("启动建图", variant="primary", size="sm", icon_name="play", parent=self.body_widget)
        self.start_b.clicked.connect(self._on_start)
        self.stop_b = UButton("结束释放", variant="danger", size="sm", parent=self.body_widget)
        self.stop_b.clicked.connect(self._on_stop)
        row2.addWidget(self.start_b)
        row2.addWidget(self.stop_b)
        self.body_layout.addLayout(row2)

        sp_row = QHBoxLayout()
        self.lin_speed = UInputNumber(0.5, 0.1, 1.0, 0.1, 1, "m/s", self.body_widget)
        self.ang_speed = UInputNumber(0.6, 0.1, 1.0, 0.1, 1, "r/s", self.body_widget)
        sp_row.addWidget(QLabel("线速:", self.body_widget))
        sp_row.addWidget(self.lin_speed)
        sp_row.addWidget(QLabel("角速:", self.body_widget))
        sp_row.addWidget(self.ang_speed)
        self.body_layout.addLayout(sp_row)

        pad = QGridLayout()
        pad.setSpacing(6)
        dirs = (
            (0, 0, "↖ 左转", 0.3, 0.0, 1.0),
            (0, 1, "↑ 前进", 1.0, 0.0, 0.0),
            (0, 2, "↗ 右转", 0.3, 0.0, -1.0),
            (1, 0, "← 左移", 0.0, 1.0, 0.0),
            (1, 1, "■ 悬停", 0.0, 0.0, 0.0),
            (1, 2, "→ 右移", 0.0, -1.0, 0.0),
            (2, 1, "↓ 后退", -1.0, 0.0, 0.0),
        )
        for r, c, label, sx, sy, sz in dirs:
            is_hover = (sz == 0 and sx == 0 and sy == 0)
            btn = UButton(label, variant="danger" if is_hover else "default", size="sm", parent=self.body_widget)
            btn.clicked.connect(lambda _=False, vx=sx, vy=sy, vz=sz: self._step_move(vx, vy, vz))
            pad.addWidget(btn, r, c)
        self.body_layout.addLayout(pad)

        self.pose_lbl = QLabel("位姿: (0.00, 0.00) | 真实点云: 0", self.body_widget)
        self.pose_lbl.setStyleSheet(f"color: {C_TEXT_2}; font-family: {FONT_MONO}; font-size: 11px;")
        self.body_layout.addWidget(self.pose_lbl)

        self.map_name_edit = QLineEdit("slam_scan_01", self.body_widget)
        save_b = UButton("完成建图并保存", variant="primary", size="md", icon_name="save", parent=self.body_widget)
        save_b.clicked.connect(self.save_and_register_map)
        self.body_layout.addWidget(self.map_name_edit)
        self.body_layout.addWidget(save_b)
        self.body_layout.addStretch(1)

    def _on_target_changed(self) -> None:
        data = self.target_sel.current_data()
        if isinstance(data, tuple) and len(data) >= 2:
            self.targetChanged.emit(str(data[0]), str(data[1]))

    def refresh_targets(self) -> None:
        self.target_sel.clear()
        if not self.state.tracks:
            self.target_sel.addItem("请先添加机器人轨道", None)
            return
        for t in self.state.tracks:
            self.target_sel.addItem(f"{t.name} [{t.target_id}]", (t.target_id, t.robot_ip))

    def _on_start(self) -> Optional[TaskHandle]:
        data = self.target_sel.current_data()
        if not isinstance(data, tuple):
            self.state.notify("暂无真实机器人轨道，请先添加机器人后再建图", "warn")
            return None
        tgt, ip = str(data[0]), str(data[1])
        self.status_badge.setText("建图启动中...")
        return run_in_background(
            lambda: self._start_mapping_bg(tgt, ip),
            on_done=lambda payload: self._on_start_done(tgt, ip, payload),
            busy_widgets=[self.start_b, self.stop_b],
            busy_text=f"正在后台启动机器人 {tgt} 的遥控建图会话...",
            notifier=self.state.notify,
        )

    def _start_mapping_bg(self, tgt: str, ip: str) -> Tuple[bool, str, Any]:
        ok, msg = self.state.slam_client.start_mapping(tgt, ip)
        pts = None
        if ok:
            pts, _ = self.state.slam_client.fetch_live_cloud(0)
        return ok, msg, pts

    def _on_start_done(self, tgt: str, ip: str, payload: Tuple[bool, str, Any]) -> None:
        ok, msg, pts = payload
        self.status_badge.setText("建图中 (MANUAL)" if ok else "启动失败")
        self.status_badge.set_tone("ok" if ok else "danger")
        if ok:
            if pts is not None and len(pts) > 0:
                self.slamCloudUpdated.emit(pts, None)
            self.targetChanged.emit(tgt, ip)
        self.state.notify(msg, "ok" if ok else "warn")

    def _step_move(self, sx: float, sy: float, sz: float) -> Optional[TaskHandle]:
        if sx == 0.0 and sy == 0.0 and sz == 0.0 and self.state.slam_client.state.robot_ip:
            ip = self.state.slam_client.state.robot_ip
            return run_in_background(
                lambda: self.state.http_rpc.send_stop(ip, emergency=False),
                on_done=lambda res: self.state.notify(
                    "已发送悬停归零指令" if res.ok else res.message, "info" if res.ok else "warn"
                ),
            )
        v = self.lin_speed.value()
        w = self.ang_speed.value()
        vx, vy, vz = sx * v, sy * v, sz * w

        def _move_bg():
            with self._teleop_lock:
                return self.state.slam_client.send_teleop_move(vx, vy, vz, duration_s=0.6)

        return run_in_background(
            _move_bg,
            on_done=lambda payload: self.state.notify(payload[1], "warn") if not payload[0] else None,
        )

    def update_live_telemetry(self, live: Dict[str, Any]) -> None:
        p = live.get("pose")
        if isinstance(p, dict):
            self.state.slam_client.state.pose = (float(p["x"]), float(p["y"]), float(p.get("yaw", 0.0)))
        pts = int(live.get("point_count", self.state.slam_client.state.point_count) or 0)
        pose = self.state.slam_client.state.pose
        rs = live.get("robot_state") if isinstance(live.get("robot_state"), dict) else {}
        faults = [f for f in (rs.get("active_faults") or []) if isinstance(f, dict)]
        if rs.get("safety_locked"):
            self.status_badge.setText(f"联锁: {rs.get('motion_state') or 'FAULT'}")
            self.status_badge.set_tone("danger")
        elif self.state.slam_client.state.active:
            self.status_badge.setText("建图中 (告警)" if faults else "建图中 (MANUAL)")
            self.status_badge.set_tone("warn" if faults else "ok")
        elif rs.get("motion_state"):
            self.status_badge.setText(f"{rs['motion_state']}" + ("·告警" if faults else ""))
            self.status_badge.set_tone("warn" if faults else "neutral")
        warn_s = f" | 故障:{faults[0].get('code', '')}" if faults else ""
        self.pose_lbl.setText(f"位姿: ({pose[0]:.2f}, {pose[1]:.2f}) | 真实点云: {pts:,}{warn_s}")

    def _on_stop(self) -> Optional[TaskHandle]:
        return run_in_background(
            self.state.slam_client.stop_mapping,
            on_done=self._on_stop_done,
            busy_widgets=[self.stop_b, self.start_b],
            busy_text="正在后台结束建图会话并释放控制权...",
            notifier=self.state.notify,
        )

    def _on_stop_done(self, payload: Tuple[bool, str]) -> None:
        ok, msg = payload
        self.status_badge.setText("已释放 (FREE)" if ok else "异常")
        self.status_badge.set_tone("neutral" if ok else "warn")
        self.state.notify(msg, "info" if ok else "warn")

    def save_and_register_map(self) -> Optional[TaskHandle]:
        data = self.target_sel.current_data()
        if isinstance(data, tuple) and not self.state.slam_client.state.robot_ip:
            self.state.slam_client.state.robot_ip = str(data[1])
            self.state.slam_client.state.target_id = str(data[0]).upper()
        name = self.map_name_edit.text().strip() or "slam_scan_01"
        return run_in_background(
            lambda: self._save_map_bg(name),
            on_done=self._on_map_saved,
            on_error=lambda err: self.state.notify(f"保存建图失败: {err.splitlines()[0]}", "warn"),
            busy_widgets=[self.start_b, self.stop_b],
            busy_text="正在后台结束建图、下载真实 .pcd 地图并生成栅格...",
            notifier=self.state.notify,
        )

    def _save_map_bg(self, name: str) -> PcdMapEntity:
        out_pcd = self.state.slam_client.save_live_map(name)
        cloud = load_pcd(out_pcd, max_points=100000)
        png = get_paths().pcd_cache_dir / f"{out_pcd.stem}_grid.png"
        grid = generate_occupancy_grid_png(cloud, png)
        ent = PcdMapEntity(
            name=out_pcd.stem,
            file_path=str(out_pcd),
            file_size=out_pcd.stat().st_size,
            point_count=cloud.header.points,
            grid_png_path=grid.png_path,
            resolution=grid.resolution,
            origin_x=grid.origin_x,
            origin_y=grid.origin_y,
        )
        saved = self.state.map_repo.upsert_map(ent)
        self.state.scene.active_map_id = saved.id
        self.state.scene_repo.update_scene(self.state.scene)
        self.state.reload_all()
        return saved

    def _on_map_saved(self, saved: PcdMapEntity) -> None:
        self.state.bus.publish(StudioEvent.MAP_LIST_UPDATED, saved.id)
        self.state.bus.publish(StudioEvent.MAP_LOADED, saved.id)
        self.state.notify(f"已从机器人保存真实建图 {saved.name}.pcd 并入库", "ok")
