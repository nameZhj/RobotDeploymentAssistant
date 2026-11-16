# @file: src/ui/mapping/teleop_mapping_dock.py
# @brief: Right 290px Teleop SLAM control panel sending LRMP MOVE commands & saving simulated/live .pcd maps.
# @exports: TeleopMappingDock

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QWidget

from src.core.event_bus import StudioEvent
from src.domain.map_entities import PcdMapEntity
from src.persistence.pcd_grid_generator import generate_occupancy_grid_png
from src.persistence.pcd_parser import load_pcd
from src.core.paths import get_paths
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.tokens import C_TEXT_2, FONT_MONO
from src.ui.design_system.u_buttons import UBadge, UButton
from src.ui.design_system.u_inputs import UInputNumber, USelect
from src.ui.design_system.u_panels import UPanel


class TeleopMappingDock(UPanel):
    """Reserved teleop SLAM interface adhering to LRMP MANUAL + MOVE protocol rules."""

    slamCloudUpdated = Signal(object, object)  # (xyz, rgb)

    def __init__(self, state: StudioStateService, parent: QWidget | None = None) -> None:
        super().__init__(title="遥控建图 (预留实时接口)", header_widgets=[], parent=parent)
        self.state = state
        self.setFixedWidth(296)
        self.body_layout.setSpacing(8)

        row1 = QHBoxLayout()
        self.target_sel = USelect([], self.body_widget)
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

        # Speed tuning
        sp_row = QHBoxLayout()
        self.lin_speed = UInputNumber(0.5, 0.1, 1.0, 0.1, 1, "m/s", self.body_widget)
        self.ang_speed = UInputNumber(0.6, 0.1, 1.0, 0.1, 1, "r/s", self.body_widget)
        sp_row.addWidget(QLabel("线速:", self.body_widget))
        sp_row.addWidget(self.lin_speed)
        sp_row.addWidget(QLabel("角速:", self.body_widget))
        sp_row.addWidget(self.ang_speed)
        self.body_layout.addLayout(sp_row)

        # Clean 3x3 D-pad (never squeezed!)
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
            btn = UButton(label, variant="danger" if sz == 0 and sx == 0 and sy == 0 else "default", size="sm", parent=self.body_widget)
            btn.clicked.connect(lambda _=False, vx=sx, vy=sy, vz=sz: self._step_move(vx, vy, vz))
            pad.addWidget(btn, r, c)
        self.body_layout.addLayout(pad)

        self.pose_lbl = QLabel("位姿: (0.00, 0.00) | 累计点云: 0", self.body_widget)
        self.pose_lbl.setStyleSheet(f"color: {C_TEXT_2}; font-family: {FONT_MONO}; font-size: 11px;")
        self.body_layout.addWidget(self.pose_lbl)

        self.map_name_edit = QLineEdit("slam_scan_01", self.body_widget)
        save_b = UButton("保存实时扫描地图 (.PCD)", variant="primary", size="md", icon_name="save", parent=self.body_widget)
        save_b.clicked.connect(self.save_and_register_map)
        self.body_layout.addWidget(self.map_name_edit)
        self.body_layout.addWidget(save_b)
        self.body_layout.addStretch(1)

    def refresh_targets(self) -> None:
        self.target_sel.clear()
        if not self.state.tracks:
            self.target_sel.addItem("请先添加机器人轨道", None)
            return
        for t in self.state.tracks:
            self.target_sel.addItem(f"{t.name} [{t.target_id}]", (t.target_id, t.robot_ip))

    def _on_start(self) -> None:
        data = self.target_sel.current_data()
        if not isinstance(data, tuple):
            self.state.notify("暂无真实机器人轨道，请先添加机器人后再建图", "warn")
            return
        tgt, ip = data
        ok, msg = self.state.slam_client.start_mapping(str(tgt), str(ip))
        self.status_badge.setText("建图中 (MANUAL)" if ok else "拒绝")
        self.status_badge.set_tone("ok" if ok else "danger")
        self._emit_cloud()
        self.state.notify(msg, "ok" if ok else "warn")

    def _step_move(self, sx: float, sy: float, sz: float) -> None:
        v = self.lin_speed.value()
        w = self.ang_speed.value()
        ok, msg = self.state.slam_client.send_teleop_move(sx * v, sy * v, sz * w, duration_s=0.6)
        if not ok:
            self.state.notify(msg, "warn")
            return
        self._emit_cloud()

    def _emit_cloud(self) -> None:
        st = self.state.slam_client.state
        pts = self.state.slam_client._virtual_gen.get_points()
        self.pose_lbl.setText(f"位姿: ({st.pose[0]:.2f}, {st.pose[1]:.2f}) | 点云: {len(pts)}")
        self.slamCloudUpdated.emit(pts, None)

    def _on_stop(self) -> None:
        ok, msg = self.state.slam_client.stop_mapping()
        self.status_badge.setText("已释放 (FREE)" if ok else "异常")
        self.status_badge.set_tone("neutral")
        self.state.notify(msg, "info")

    def save_and_register_map(self) -> PcdMapEntity:
        name = self.map_name_edit.text().strip() or "slam_scan_01"
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
        self.state.bus.publish(StudioEvent.MAP_LIST_UPDATED, saved.id)
        self.state.bus.publish(StudioEvent.MAP_LOADED, saved.id)
        self.state.notify(f"已保存遥控建图 {saved.name}.pcd 并入库", "ok")
        return saved
