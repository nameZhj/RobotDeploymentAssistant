# @file: src/ui/modals/bpm_info_modal.py
# @brief: Modal dialog configuring stage music BPM, time signature, and audio accompaniment path.
# @exports: BpmInfoModal

from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QWidget

from src.core.event_bus import StudioEvent
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.u_buttons import UButton
from src.ui.design_system.u_dialog import UDialog
from src.ui.design_system.u_inputs import UInputNumber, USelect


class BpmInfoModal(UDialog):
    """Updates scene musical tempo and optional audio track reference."""

    def __init__(self, state: StudioStateService, parent: QWidget | None = None) -> None:
        super().__init__("背景音乐与节拍设置", width=440, height=250, confirm_text="保存节拍", parent=parent)
        self.state = state
        form = QFormLayout()
        form.setSpacing(10)

        self.bpm_spin = UInputNumber(state.scene.bpm, 40.0, 240.0, 1.0, 0, "BPM", self)
        self.sig_sel = USelect([("4/4 拍", "4/4"), ("3/4 拍", "3/4"), ("2/4 拍", "2/4")], self)
        self.sig_sel.set_current_data(state.scene.time_signature)

        arow = QHBoxLayout()
        self.audio_edit = QLineEdit(state.scene.audio_path, self)
        brw = UButton("浏览...", variant="default", size="sm", parent=self)
        brw.clicked.connect(self._pick_audio)
        arow.addWidget(self.audio_edit, 1)
        arow.addWidget(brw)

        form.addRow("音乐 BPM", self.bpm_spin)
        form.addRow("拍号", self.sig_sel)
        form.addRow("配乐文件", arow)
        self.body_layout.addLayout(form)

        if self.confirm_btn:
            self.confirm_btn.clicked.disconnect()
            self.confirm_btn.clicked.connect(self._on_save)

    def _pick_audio(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "选择伴奏音乐", "", "Audio (*.mp3 *.wav *.ogg)")
        if p:
            self.audio_edit.setText(p)

    def _on_save(self) -> None:
        sc = self.state.scene
        sc.bpm = self.bpm_spin.value()
        sc.time_signature = str(self.sig_sel.current_data() or "4/4")
        sc.audio_path = self.audio_edit.text().strip()
        self.state.scene_repo.update_scene(sc)
        self.state.bus.publish(StudioEvent.SCENE_CHANGED, sc.id)
        self.accept()
