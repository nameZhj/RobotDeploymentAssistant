# @file: src/ui/modals/stage_size_modal.py
# @brief: Modal dialog editing physical stage width, height, and safety perimeter margin.
# @exports: StageSizeModal

from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QLineEdit, QWidget

from src.core.event_bus import StudioEvent
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.u_dialog import UDialog
from src.ui.design_system.u_inputs import UInputNumber


class StageSizeModal(UDialog):
    """Updates SceneEntity name & physical dimensions cleanly and updates 2D/3D viewports."""

    def __init__(self, state: StudioStateService, parent: QWidget | None = None) -> None:
        super().__init__("舞台与场景配置", width=400, height=290, confirm_text="应用配置", parent=parent)
        self.state = state
        sc = state.scene
        form = QFormLayout()
        form.setSpacing(10)
        self.name_edit = QLineEdit(sc.name, self)
        self.width_spin = UInputNumber(sc.stage_width, 2.0, 200.0, 1.0, 1, "m", self)
        self.height_spin = UInputNumber(sc.stage_height, 2.0, 200.0, 1.0, 1, "m", self)
        self.margin_spin = UInputNumber(sc.safety_margin, 0.1, 5.0, 0.1, 2, "m", self)
        form.addRow("场景名称", self.name_edit)
        form.addRow("舞台长度 (X)", self.width_spin)
        form.addRow("舞台宽度 (Y)", self.height_spin)
        form.addRow("安全边界余量", self.margin_spin)
        self.body_layout.addLayout(form)

        if self.confirm_btn:
            self.confirm_btn.clicked.disconnect()
            self.confirm_btn.clicked.connect(self._on_apply)

    def _on_apply(self) -> None:
        sc = self.state.scene
        sc.name = self.name_edit.text().strip() or sc.name or "默认舞台"
        sc.stage_width = self.width_spin.value()
        sc.stage_height = self.height_spin.value()
        sc.safety_margin = self.margin_spin.value()
        self.state.scene_repo.update_scene(sc)
        self.state.bus.publish(StudioEvent.SCENE_CHANGED, sc.id)
        self.state.notify(f"舞台 [{sc.name}] 已更新为 {sc.stage_width:.1f} × {sc.stage_height:.1f} m", "ok")
        self.accept()
