# @file: src/ui/choreography/preview_map_panel.py
# @brief: UniUni PreviewMap container pairing stacked 3D/2D viewports, inline trajectory draw bar, and scrubber.
# @exports: PreviewMapPanel

from __future__ import annotations

from typing import List
from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from src.core.event_bus import StudioEvent
from src.domain.trajectory_entities import ControlPoint2D
from src.services.playback_coordinator import PlaybackCoordinator
from src.services.studio_state_service import StudioStateService
from src.ui.choreography.playback_progress_bar import PlaybackProgressBar
from src.ui.choreography.stage_canvas_2d import StageCanvas2D
from src.ui.choreography.stage_draw_overlay import StageDrawToolbar, StageHintFooter
from src.ui.design_system.u_buttons import UButton, UIconButton, USegmented
from src.ui.design_system.u_dialog import UFloatBar
from src.ui.design_system.u_panels import UPanel
from src.viewport3d.stage_viewport_3d import StageViewport3D


class PreviewMapPanel(UPanel):
    """Upper-left choreography viewport host featuring live 3D G1 preview, inline 2D draw canvas, and scrubber."""

    def __init__(self, state: StudioStateService, playback: PlaybackCoordinator, parent=None) -> None:
        from PySide6.QtCore import Signal
        _ = Signal
        super().__init__(title="舞台预览 & 轨迹绘制", header_widgets=[], parent=parent)
        self.state = state
        self.playback = playback

        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(0)

        self.stage_pill = UButton(
            self._stage_label(), variant="ghost", size="xs", icon_name="sliders",
            tooltip="点击修改舞台区尺寸 (Length × Width)", parent=self,
        )
        self.traj_toggle = UButton("预览轨迹", variant="default", size="xs", tooltip="显示 / 隐藏 2D 样条轨迹", parent=self)
        self.traj_toggle.setCheckable(True)
        self.traj_toggle.setChecked(True)
        self.traj_toggle.toggled.connect(self._on_toggle_traj)

        self.reset_cam_btn = UIconButton("home", tooltip="重置视角", size=24, parent=self)
        self.reset_cam_btn.clicked.connect(self._reset_camera)

        self.mode_switch = USegmented(["3D", "2D"], default="2D", parent=self)
        self.mode_switch.currentChanged.connect(self._on_mode_changed)

        hdr_lay = self.header_bar.layout()
        for w in (self.stage_pill, self.traj_toggle, self.reset_cam_btn, self.mode_switch):
            hdr_lay.addWidget(w)

        holder = QWidget(self.body_widget)
        v_lay = QVBoxLayout(holder)
        v_lay.setContentsMargins(0, 0, 0, 6)
        v_lay.setSpacing(4)

        self.draw_toolbar = StageDrawToolbar(holder)
        v_lay.addWidget(self.draw_toolbar)

        self.stack = QStackedWidget(holder)
        self.canvas_2d = StageCanvas2D(state, self.stack)
        self.viewport_3d = StageViewport3D(state, self.stack)
        self.stack.addWidget(self.canvas_2d)   # idx 0 -> 2D
        self.stack.addWidget(self.viewport_3d) # idx 1 -> 3D
        self.stack.setCurrentIndex(0)
        v_lay.addWidget(self.stack, 1)

        self.hint_footer = StageHintFooter(holder)
        v_lay.addWidget(self.hint_footer)

        float_wrap = UFloatBar(holder)
        float_wrap.setFixedHeight(44)
        self.progress_bar = PlaybackProgressBar(state, playback, float_wrap)
        float_wrap.bar_layout.addWidget(self.progress_bar, 1)
        v_lay.addWidget(float_wrap)

        self.body_layout.addWidget(holder, 1)

        self.draw_toolbar.modeChanged.connect(self._on_draw_mode)
        self.draw_toolbar.clearSketchClicked.connect(self.canvas_2d.clear_sketches)
        self.draw_toolbar.clearDraftClicked.connect(self.canvas_2d.clear_draft)
        self.draw_toolbar.saveDraftClicked.connect(lambda: self._open_save_drawn(self.canvas_2d.draft_points))
        self.canvas_2d.hoverCoordChanged.connect(self.draw_toolbar.update_coord)
        self.canvas_2d.draftPointsChanged.connect(self.draw_toolbar.update_draft_status)
        self.canvas_2d.trajectoryFinishRequested.connect(self._open_save_drawn)
        state.bus.subscribe(StudioEvent.SCENE_CHANGED, lambda _s: self.stage_pill.setText(self._stage_label()))

    @property
    def stageSizeClicked(self):
        return self.stage_pill.clicked

    def _on_draw_mode(self, mode: str) -> None:
        if mode != "view" and self.stack.currentIndex() != 0:
            self.mode_switch.set_current("2D")
        self.canvas_2d.set_draw_mode(mode)

    def _open_save_drawn(self, points: List[ControlPoint2D]) -> None:
        if len(points) < 2:
            self.state.notify("请先在画布至少点击 2 个轨迹控制点", "warn")
            return
        from src.ui.modals.trajectory_editor_modal import TrajectoryEditorModal
        dlg = TrajectoryEditorModal(self.state, traj=None, initial_points=points, parent=self)
        if dlg.exec():
            self.canvas_2d.clear_draft()
            self.draw_toolbar.reset_to_view()

    def _stage_label(self) -> str:
        sc = self.state.scene
        return f"舞台 {sc.stage_width:.0f}×{sc.stage_height:.0f}m"

    def _on_toggle_traj(self, checked: bool) -> None:
        self.canvas_2d.show_trajectories = checked
        self.canvas_2d.update()

    def _reset_camera(self) -> None:
        if self.stack.currentIndex() == 0:
            self.canvas_2d.reset_view()
        else:
            self.viewport_3d.reset_view("iso")

    def _on_mode_changed(self, mode: str) -> None:
        self.stack.setCurrentIndex(1 if mode == "3D" else 0)
        self.draw_toolbar.setVisible(mode == "2D")
        self.hint_footer.setVisible(mode == "2D")
