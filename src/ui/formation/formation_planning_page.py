# @file: src/ui/formation/formation_planning_page.py
# @brief: Complete UniUni Page 2 Swarm Formation Design & Multi-Robot Action Planning workspace.
# @exports: FormationPlanningPage

from __future__ import annotations

import math
from typing import List, Tuple
from PySide6.QtWidgets import QHBoxLayout, QWidget

from src.algorithms import (
    PotentialFieldParams,
    SwarmSimulationResult,
    assign_targets_2opt,
    generate_formation,
    solve_swarm_potential_field,
)
from src.core.event_bus import StudioEvent
from src.domain.timeline_entities import TimelineBlockEntity
from src.domain.trajectory_entities import ControlPoint2D, TrajectoryEntity, TrajectoryGroupEntity
from src.math.trajectory_sampler import sample_trajectory_50fps
from src.services.studio_state_service import StudioStateService
from src.ui.formation.formation_control_dock import FormationControlDock
from src.ui.formation.formation_group_dock import FormationGroupDock
from src.ui.formation.formation_planner_canvas import FormationPlannerCanvas


class FormationPlanningPage(QWidget):
    """UniUni Formation Planning View (Sources/Targets Table | 2D Planner Canvas | Solver Dock)."""

    def __init__(self, state: StudioStateService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._last_result: SwarmSimulationResult | None = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        self.group_dock = FormationGroupDock(state, self)
        self.canvas = FormationPlannerCanvas(state, self)
        self.ctrl_dock = FormationControlDock(self)

        lay.addWidget(self.group_dock)
        lay.addWidget(self.canvas, 1)
        lay.addWidget(self.ctrl_dock)

        self.group_dock.syncFromTracksRequested.connect(self.sync_from_tracks)
        self.group_dock.scatterRequested.connect(self._on_scatter_sources)
        self.ctrl_dock.generateClicked.connect(self.generate_targets)
        self.ctrl_dock.solveClicked.connect(self.solve_paths)
        self.ctrl_dock.applyToChoreoClicked.connect(self.commit_to_library)
        self.ctrl_dock.previewSliderChanged.connect(self._on_preview_slider)
        self.canvas.targetsEdited.connect(self._recompute_2opt_only)

        state.bus.subscribe(StudioEvent.TRACKS_UPDATED, lambda _p: self.sync_from_tracks())
        self.sync_from_tracks()
        self.generate_targets()

    def sync_from_tracks(self) -> None:
        self.canvas.sources = [(t.init_x, t.init_y) for t in self.state.tracks]
        if not self.canvas.sources:
            self.canvas.targets.clear()
            self.canvas.knots.clear()
            self._last_result = None
        self._recompute_2opt_only()

    def _on_scatter_sources(self, pts: List[Tuple[float, float]]) -> None:
        if not self.state.tracks:
            self.state.notify("暂无真实机器人轨道", "warn")
            return
        self.canvas.sources = pts
        self._recompute_2opt_only()

    def generate_targets(self) -> None:
        if not self.canvas.sources:
            self.canvas.targets.clear()
            self.canvas.knots.clear()
            self.group_dock.update_pairs([], [], [])
            self.canvas.update()
            self.state.notify("暂无真实机器人，请先在『舞蹈编排』点击『+ 轨道』添加机器人", "warn")
            return
        n = len(self.canvas.sources)
        self.canvas.targets = generate_formation(
            kind=str(self.ctrl_dock.kind_sel.current_data() or "grid"),
            count=n,
            spacing=self.ctrl_dock.spacing_spin.value(),
            radius=self.ctrl_dock.radius_spin.value(),
            cols=int(self.ctrl_dock.cols_spin.value()),
            rotation_rad=self.ctrl_dock.rotation_rad(),
            text_content=self.ctrl_dock.text_edit.text(),
            text_width_m=max(2.5, self.ctrl_dock.radius_spin.value() * 2.0),
        )
        self.canvas.knots.clear()
        self._last_result = None
        self._recompute_2opt_only()

    def _recompute_2opt_only(self) -> None:
        if self.canvas.sources and self.canvas.targets:
            self.canvas.assignment = assign_targets_2opt(self.canvas.sources, self.canvas.targets)
        else:
            self.canvas.assignment = []
        self.group_dock.update_pairs(self.canvas.sources, self.canvas.targets, self.canvas.assignment)
        self.canvas.update()

    def solve_paths(self) -> SwarmSimulationResult:
        if not self.canvas.sources:
            self.state.notify("暂无真实机器人可规划路径，请先添加轨道", "warn")
            return SwarmSimulationResult([], [], 0.0, float("inf"), False, 0)
        if not self.canvas.targets:
            self.generate_targets()
        params = PotentialFieldParams(
            safety_dist=self.ctrl_dock.safety_spin.value(),
            repel_range=max(0.8, self.ctrl_dock.safety_spin.value() * 1.9),
            max_speed=self.ctrl_dock.speed_spin.value(),
        )
        res = solve_swarm_potential_field(
            self.canvas.sources, self.canvas.targets, assignment=self.canvas.assignment, params=params
        )
        self._last_result = res
        self.canvas.assignment = list(res.assignment)
        self.canvas.knots = res.simplified_knots
        self.canvas.sim_progress = 1.0
        self.ctrl_dock.preview_slider.setValue(100)
        self.ctrl_dock.set_metrics(res.min_distance, res.total_sim_time, res.converged)
        self.group_dock.update_pairs(self.canvas.sources, self.canvas.targets, self.canvas.assignment)
        self.canvas.update()
        return res

    def _on_preview_slider(self, ratio: float) -> None:
        self.canvas.sim_progress = ratio
        self.canvas.update()

    def commit_to_library(self) -> TrajectoryGroupEntity | None:
        if not self.state.tracks:
            self.state.notify("暂无真实机器人轨道，请先添加机器人", "warn")
            return None
        if self._last_result is None or not self._last_result.simplified_knots:
            self.solve_paths()
        assert self._last_result is not None
        gname = self.ctrl_dock.group_name_edit.text().strip() or "队形规划组"
        grp = self.state.traj_repo.upsert_group(
            TrajectoryGroupEntity(
                scene_id=self.state.scene.id or 1,
                name=gname,
                robot_count=len(self._last_result.simplified_knots),
                bound_track_no=self.state.tracks[0].track_no if self.state.tracks else 1,
            )
        )
        dur = max(3.0, round(self._last_result.total_sim_time, 1))
        for idx, knots in enumerate(self._last_result.simplified_knots):
            tr = self.state.tracks[idx] if idx < len(self.state.tracks) else None
            track_no = tr.track_no if tr else (idx + 1)
            cps = [ControlPoint2D(round(x, 3), round(y, 3), 0.0) for x, y in knots]
            for k in range(1, len(cps)):
                cps[k].yaw = round(math.atan2(cps[k].y - cps[k - 1].y, cps[k].x - cps[k - 1].x), 4)
            traj = TrajectoryEntity(
                group_id=grp.id or 1,
                no=self.state.traj_repo.next_trajectory_no(track_no),
                name=f"{gname}-{track_no}",
                duration=dur,
                control_points=cps,
            )
            sample_trajectory_50fps(traj)
            saved_traj = self.state.traj_repo.upsert_trajectory(traj)
            if tr is not None:
                blk = TimelineBlockEntity(
                    task_id=self.state.task.id or 1,
                    track_id=tr.id or 1,
                    block_type="trajectory",
                    ref_id=saved_traj.id or 0,
                    code_no=str(saved_traj.no),
                    title=saved_traj.name,
                    start_time=self.state.next_track_end_time(tr.id or 1),
                    duration=dur,
                )
                self.state.scene_repo.upsert_block(blk)

        self.state.reload_all()
        self.state.bus.publish(StudioEvent.TRAJECTORY_LIB_UPDATED, grp.id)
        self.state.bus.publish(StudioEvent.TIMELINE_UPDATED, None)
        self.state.notify(f"已生成队形组 [{gname}] 并同步 {len(self._last_result.simplified_knots)} 条防碰撞轨迹", "ok")
        return grp
