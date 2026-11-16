# @file: src/ui/formation/formation_group_dock.py
# @brief: Left 250px robot swarm source/target table & quick scatter dock inside FormationPlanningPage.
# @exports: FormationGroupDock

from __future__ import annotations

from typing import List, Tuple
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QTableWidgetItem, QWidget

from src.algorithms import generate_scatter_positions
from src.services.studio_state_service import StudioStateService
from src.ui.design_system.tokens import C_TEXT_2
from src.ui.design_system.u_buttons import UButton
from src.ui.design_system.u_panels import UPanel, UTable


class FormationGroupDock(UPanel):
    """Left dock managing initial robot fleet positions and target pair inspection."""

    scatterRequested = Signal(list)
    syncFromTracksRequested = Signal()

    def __init__(self, state: StudioStateService, parent: QWidget | None = None) -> None:
        super().__init__(title="集群点位表 (起止坐标)", header_widgets=[], parent=parent)
        self.state = state
        self.setFixedWidth(260)

        tip = QLabel("绿色圆为起点位姿，右侧面板生成目标队形与避障路径：", self.body_widget)
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color: {C_TEXT_2}; font-size: 11px;")
        self.body_layout.addWidget(tip)

        self.table = UTable(["轨道", "起点 (X,Y)", "目标 (X,Y)"], self.body_widget)
        self.body_layout.addWidget(self.table, 1)

        btns = QHBoxLayout()
        sync_b = UButton("读取舞台站位", variant="default", size="xs", icon_name="refresh", parent=self.body_widget)
        sync_b.clicked.connect(self.syncFromTracksRequested.emit)
        scat_b = UButton("安全分散预设", variant="default", size="xs", icon_name="target", parent=self.body_widget)
        scat_b.clicked.connect(self._on_scatter)
        btns.addWidget(sync_b)
        btns.addWidget(scat_b)
        self.body_layout.addLayout(btns)

    def _on_scatter(self) -> None:
        if not self.state.tracks:
            self.state.notify("暂无真实机器人，请先在『舞蹈编排』添加轨道", "warn")
            return
        pts = generate_scatter_positions(
            len(self.state.tracks),
            stage_width=float(self.state.scene.stage_width or 12.0),
            stage_height=float(self.state.scene.stage_height or 8.0),
        )
        self.scatterRequested.emit(pts)

    def update_pairs(
        self,
        sources: List[Tuple[float, float]],
        targets: List[Tuple[float, float]],
        assignment: List[int],
    ) -> None:
        self.table.setRowCount(len(sources))
        for i, (sx, sy) in enumerate(sources):
            name = self.state.tracks[i].name if i < len(self.state.tracks) else f"R{i+1}"
            self.table.setItem(i, 0, QTableWidgetItem(name))
            self.table.setItem(i, 1, QTableWidgetItem(f"{sx:.2f},{sy:.2f}"))
            if targets and i < len(assignment) and 0 <= assignment[i] < len(targets):
                tx, ty = targets[assignment[i]]
                self.table.setItem(i, 2, QTableWidgetItem(f"{tx:.2f},{ty:.2f}"))
            else:
                self.table.setItem(i, 2, QTableWidgetItem("-"))
