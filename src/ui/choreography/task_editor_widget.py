# @file: src/ui/choreography/task_editor_widget.py
# @brief: UniUni TaskEditor container combining 38px TimelineHeader, 40px EditorOpbar, and scrollable TimelineLaneView.
# @exports: TaskEditorWidget

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from src.services.playback_coordinator import PlaybackCoordinator
from src.services.studio_state_service import StudioStateService
from src.ui.choreography.editor_opbar import EditorOpbar
from src.ui.choreography.timeline_header import TimelineHeader
from src.ui.choreography.timeline_lane_view import TimelineLaneView
from src.ui.design_system.tokens import C_BASE, LINE


class TaskEditorWidget(QFrame):
    """Bottom-left multi-track timeline editor composite widget."""

    def __init__(self, state: StudioStateService, playback: PlaybackCoordinator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.playback = playback
        self.setStyleSheet(f"TaskEditorWidget {{ background: {C_BASE}; border: 1px solid {LINE}; border-radius: 6px; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header = TimelineHeader(state, self)
        root.addWidget(self.header)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.opbar = EditorOpbar(self)
        self.opbar.toolClicked.connect(self._on_op)
        body.addWidget(self.opbar)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.lane_view = TimelineLaneView(state, playback, self.scroll)
        self.scroll.setWidget(self.lane_view)
        body.addWidget(self.scroll, 1)

        root.addLayout(body, 1)

    def _on_op(self, action: str) -> None:
        if action == "select":
            self.lane_view.setFocus()
            self.state.notify("时间轴已切换至选择与拖拽模式", "info")
        elif action == "delete":
            self.lane_view.delete_selected_block()
        elif action == "split":
            self.lane_view.split_selected_or_at_playhead()
        elif action == "duplicate":
            self.lane_view.duplicate_selected_block()
        elif action == "ignore":
            self.lane_view.toggle_ignore_selected_block()
        elif action == "zoom_in":
            self.lane_view.zoom(1.18)
        elif action == "zoom_out":
            self.lane_view.zoom(0.84)
        elif action == "snap" and self.opbar.snap_btn is not None:
            self.lane_view.snap_enabled = self.opbar.snap_btn.isChecked()
        elif action == "undo":
            desc = self.state.undo_stack.undo()
            if desc:
                self.state.notify(f"已撤销: {desc}", "ok")
        elif action == "redo":
            desc = self.state.undo_stack.redo()
            if desc:
                self.state.notify(f"已重做: {desc}", "ok")
