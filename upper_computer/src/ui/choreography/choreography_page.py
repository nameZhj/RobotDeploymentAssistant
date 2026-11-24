# @file: src/ui/choreography/choreography_page.py
# @brief: Complete UniUni Page 1 Choreography layout pairing Left Stage+Timeline and Right 330px Libraries.
# @exports: ChoreographyPage

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QSplitter, QWidget

from src.services.playback_coordinator import PlaybackCoordinator
from src.services.studio_state_service import StudioStateService
from src.ui.choreography.action_lib_panel import ActionLibPanel
from src.ui.choreography.batch_choreo_drawer import BatchChoreoDrawer
from src.ui.choreography.preview_map_panel import PreviewMapPanel
from src.ui.choreography.task_editor_widget import TaskEditorWidget
from src.ui.choreography.track_lib_panel import TrackLibPanel
from src.ui.design_system.tokens import W_RIGHT_LIB
from src.ui.modals import (
    AddTrackDialog,
    FragmentSaveDialog,
    InitPointModal,
    PreDanceCheckModal,
    StageSizeModal,
    SwitchTaskModal,
    TaskJsonViewerModal,
)


class ChoreographyPage(QWidget):
    """Primary UniUni v3 Stage Choreography view (PreviewMap + TaskEditor | TrackLib + ActionLib)."""

    def __init__(self, state: StudioStateService, playback: PlaybackCoordinator, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.playback = playback

        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # Left column (flex 1): top PreviewMapPanel (70%) + bottom TaskEditorWidget (30%)
        left_split = QSplitter(Qt.Orientation.Vertical, self)
        left_split.setChildrenCollapsible(False)
        self.preview_panel = PreviewMapPanel(state, playback, left_split)
        self.task_editor = TaskEditorWidget(state, playback, left_split)
        self.preview_panel.setMinimumHeight(360)
        self.task_editor.setMinimumHeight(140)
        left_split.addWidget(self.preview_panel)
        left_split.addWidget(self.task_editor)
        left_split.setStretchFactor(0, 7)
        left_split.setStretchFactor(1, 3)
        left_split.setSizes([700, 300])
        self.left_split = left_split
        root.addWidget(left_split, 1)

        # Optional push drawer between center and right libraries
        self.batch_drawer = BatchChoreoDrawer(state, self)
        root.addWidget(self.batch_drawer)

        # Right column (fixed 330px): top TrackLibPanel + bottom ActionLibPanel
        right_split = QSplitter(Qt.Orientation.Vertical, self)
        right_split.setFixedWidth(W_RIGHT_LIB)
        right_split.setChildrenCollapsible(False)
        self.track_lib = TrackLibPanel(state, right_split)
        self.action_lib = ActionLibPanel(state, right_split)
        right_split.addWidget(self.track_lib)
        right_split.addWidget(self.action_lib)
        right_split.setSizes([340, 360])
        root.addWidget(right_split)

        self._ratio_applied = False
        self._wire_modals()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._ratio_applied:
            self._ratio_applied = True
            h = max(600, self.left_split.height() or self.height() or 800)
            self.left_split.setSizes([int(h * 0.70), int(h * 0.30)])

    def _wire_modals(self) -> None:
        hdr = self.task_editor.header
        hdr.playToggleClicked.connect(self.playback.toggle_play)
        hdr.stopClicked.connect(self.playback.reset_preview)
        hdr.saveClicked.connect(self.state.save_project_snapshot)
        self.preview_panel.stageSizeClicked.connect(lambda: StageSizeModal(self.state, self).exec())
        hdr.addTrackClicked.connect(lambda: AddTrackDialog(self.state, self).exec())
        hdr.switchTaskClicked.connect(lambda: SwitchTaskModal(self.state, self).exec())
        hdr.initPointsClicked.connect(lambda: InitPointModal(self.state, self).exec())
        hdr.saveFragmentClicked.connect(lambda: FragmentSaveDialog(self.state, self.state.playhead_s, self).exec())
        hdr.preCheckClicked.connect(lambda: PreDanceCheckModal(self.state, self, mode="check").exec())
        hdr.jsonViewClicked.connect(lambda: TaskJsonViewerModal(self.state, self).exec())
        hdr.httpDeployClicked.connect(lambda: PreDanceCheckModal(self.state, self, mode="deploy").exec())
        self.task_editor.lane_view.rulerDoubleClicked.connect(
            lambda t: FragmentSaveDialog(self.state, t, self).exec()
        )
        self.task_editor.lane_view.blockSelected.connect(self._on_timeline_block_selected)
        self.task_editor.opbar.toolClicked.connect(
            lambda act: self.batch_drawer.setVisible(not self.batch_drawer.isVisible()) if act == "batch" else None
        )

    def _on_timeline_block_selected(self, blk) -> None:
        self.preview_panel.canvas_2d.highlighted_track_id = blk.track_id if blk else None
        self.preview_panel.canvas_2d.update()
        if blk is not None:
            tr = next((t for t in self.state.tracks if t.id == blk.track_id), None)
            label = tr.target_id or tr.name if tr else f"轨道#{blk.track_id}"
            self.state.notify(f"选中 [{label}] {blk.title}", "info")
