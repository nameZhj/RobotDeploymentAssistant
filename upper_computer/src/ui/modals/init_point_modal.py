# @file: src/ui/modals/init_point_modal.py
# @brief: Multi-robot initial pose editor & full preset CRUD loader/saver/deleter (InitPointConfig).
# @exports: InitPointModal

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QInputDialog, QLabel, QTableWidgetItem, QWidget

from src.core.event_bus import StudioEvent
from src.domain.track_entities import InitPointConfig, InitPointItem
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.tokens import C_DANGER, C_TEXT_3
from src.ui.design_system.u_buttons import UButton
from src.ui.design_system.u_dialog import UDialog
from src.ui.design_system.u_inputs import USelect
from src.ui.design_system.u_panels import UTable


class InitPointModal(UDialog):
    """Edits starting (x, y, yaw) coordinates for real tracks and manages InitPoint presets."""

    def __init__(self, state: StudioStateService, parent: QWidget | None = None) -> None:
        super().__init__("初始站位与朝向配置", width=650, height=450, confirm_text="保存并应用", parent=parent)
        self.state = state
        self._active_preset_name = ""

        top = QHBoxLayout()
        self.preset_sel = USelect([], self)
        load_btn = UButton("载入预设", variant="default", size="sm", parent=self)
        load_btn.clicked.connect(self._load_preset)
        save_as_btn = UButton("存为新预设", variant="default", size="sm", icon_name="save", parent=self)
        save_as_btn.clicked.connect(self._save_preset_as)
        del_btn = UButton("删除预设", variant="danger", size="sm", icon_name="trash", parent=self)
        del_btn.clicked.connect(self._delete_preset)
        top.addWidget(self.preset_sel, 1)
        top.addWidget(load_btn)
        top.addWidget(save_as_btn)
        top.addWidget(del_btn)
        self.body_layout.addLayout(top)
        self._reload_presets()

        if not state.tracks:
            hint = QLabel("当前舞台尚无真实机器人轨道，请先点击任务链上方『+ 轨道』添加机器人后再配置初始站位。", self)
            hint.setWordWrap(True)
            hint.setStyleSheet(f"color: {C_TEXT_3}; padding: 12px;")
            self.body_layout.addWidget(hint)

        self.table = UTable(["轨道", "目标", "初始 X (m)", "初始 Y (m)", "朝向 Yaw (rad)"], self)
        self.table.setRowCount(len(state.tracks))
        for r, tr in enumerate(state.tracks):
            self.table.setItem(r, 0, QTableWidgetItem(tr.name))
            self.table.setItem(r, 1, QTableWidgetItem(tr.target_id))
            self.table.setItem(r, 2, QTableWidgetItem(f"{tr.init_x:.3f}"))
            self.table.setItem(r, 3, QTableWidgetItem(f"{tr.init_y:.3f}"))
            self.table.setItem(r, 4, QTableWidgetItem(f"{tr.init_yaw:.3f}"))
        self.body_layout.addWidget(self.table, 1)

        self.err_lbl = QLabel("", self)
        self.err_lbl.setWordWrap(True)
        self.err_lbl.setStyleSheet(f"color: {C_DANGER}; font-size: 11px;")
        self.body_layout.addWidget(self.err_lbl)

        if self.confirm_btn:
            self.confirm_btn.clicked.disconnect()
            self.confirm_btn.clicked.connect(self._apply)

    def _reload_presets(self, select_id: int | None = None) -> None:
        cfgs = self.state.list_init_configs()
        self.preset_sel.clear()
        if not cfgs:
            self.preset_sel.addItem("暂无已保存预设", 0)
            return
        for c in cfgs:
            self.preset_sel.addItem(c.name, c.id)
        if select_id is not None:
            self.preset_sel.set_current_data(select_id)

    def _load_preset(self) -> None:
        cid = int(self.preset_sel.current_data() or 0)
        cfg = next((c for c in self.state.list_init_configs() if c.id == cid), None)
        if not cfg:
            return
        by_no = {p.track_no: p for p in cfg.points}
        for r, tr in enumerate(self.state.tracks):
            pt = by_no.get(tr.track_no)
            if pt:
                self.table.item(r, 2).setText(f"{pt.x:.3f}")
                self.table.item(r, 3).setText(f"{pt.y:.3f}")
                self.table.item(r, 4).setText(f"{pt.yaw:.3f}")
        self._active_preset_name = cfg.name
        self.state.notify(f"已填充预设 [{cfg.name}] 到编辑表", "info")

    def _save_preset_as(self) -> None:
        if not self.state.tracks:
            self.state.notify("暂无真实轨道可保存为站位预设", "warn")
            return
        name, ok = QInputDialog.getText(self, "保存站位预设", "预设名称:")
        if not ok or not name.strip():
            return
        items = [
            InitPointItem(
                track_no=tr.track_no,
                target_id=tr.target_id,
                x=float(self.table.item(r, 2).text()),
                y=float(self.table.item(r, 3).text()),
                yaw=float(self.table.item(r, 4).text()),
            )
            for r, tr in enumerate(self.state.tracks)
        ]
        saved = self.state.scene_repo.save_init_config(
            InitPointConfig(scene_id=self.state.scene.id or 1, name=name.strip(), points=items)
        )
        self._active_preset_name = saved.name
        self._reload_presets(select_id=saved.id)
        self.state.notify(f"已保存预设 [{saved.name}]", "ok")

    def _delete_preset(self) -> None:
        cid = int(self.preset_sel.current_data() or 0)
        if cid <= 0:
            return
        self.state.scene_repo.delete_init_config(cid)
        self._reload_presets()
        self.state.notify("已删除选中站位预设", "info")

    def _apply(self) -> None:
        proposed = []
        for r, tr in enumerate(self.state.tracks):
            try:
                x = float(self.table.item(r, 2).text())
                y = float(self.table.item(r, 3).text())
                yaw = float(self.table.item(r, 4).text())
            except ValueError:
                self.err_lbl.setText(f"第 {r + 1} 行坐标格式无效")
                return
            proposed.append((tr, x, y, yaw))
        try:
            self.state.validate_init_points([(tr.name, x, y) for tr, x, y, _ in proposed])
        except ValueError as exc:
            self.err_lbl.setText(str(exc))
            self.state.notify(str(exc), "err")
            return
        for tr, x, y, yaw in proposed:
            tr.init_x, tr.init_y, tr.init_yaw = x, y, yaw
            self.state.scene_repo.upsert_track(tr)
        self.state.reload_all()
        self.state.bus.publish(StudioEvent.TRACKS_UPDATED, None)
        self.state.bus.publish(StudioEvent.INIT_POINTS_UPDATED, self._active_preset_name or "自定义站位")
        self.accept()
