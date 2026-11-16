# @file: tests/test_phase5_design_system.py
# @brief: Offscreen GUI tests validating UniUni v3 tokens, SVG icons, QSS compilation, and zero-truncation U* widgets.
# @exports: test_design_system_widgets_render_no_truncation

from __future__ import annotations

import os
import pytest
from PySide6.QtWidgets import QApplication

from src.ui.design_system import (
    UBadge,
    UButton,
    UCollapsibleGroup,
    UDialog,
    UIconButton,
    UInputNumber,
    UPanel,
    USegmented,
    UTable,
    UTimeInput,
    build_ugc_v3_stylesheet,
    render_svg_icon,
)
from src.ui.theme import apply_uniuni_theme


@pytest.fixture(scope="module")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    apply_uniuni_theme(app)
    return app


def test_design_system_widgets_render_no_truncation(qt_app) -> None:
    qss = build_ugc_v3_stylesheet()
    assert "#0b0c0f" in qss and "#2e7bf7" in qss
    assert not render_svg_icon("play").isNull()

    labels = ["载入地图", "绘制轨迹", "HTTP上传(虚拟)", "一键导出至轨迹库", "播放/暂停"]
    for text in labels:
        btn = UButton(text, variant="primary", size="sm")
        btn.adjustSize()
        assert btn.width() >= btn.sizeHint().width()

    ibtn = UIconButton("save", tooltip="保存")
    assert ibtn.width() == 28 and ibtn.height() == 28

    seg = USegmented(["3D", "2D"], default="2D")
    assert seg.current() == "2D"
    seg.set_current("3D")
    assert seg.current() == "3D"

    num = UInputNumber(12.0, 1.0, 50.0, unit="m")
    assert num.value() == 12.0

    t_in = UTimeInput(65.5)
    assert t_in.text() == "01:05.50"

    grp = UCollapsibleGroup(1, "开场散开队形", robot_count=4, item_count=4, bound_track_no=1)
    assert not grp.content_holder.isHidden()
    grp.toggle()
    assert grp.content_holder.isHidden()

    tbl = UTable(["编号", "名称", "时间"])
    assert tbl.columnCount() == 3

    panel = UPanel("轨迹库", header_widgets=[UBadge("4组", tone="accent")])
    assert panel.header_bar is not None

    dlg = UDialog("测试弹窗")
    assert dlg.confirm_btn is not None and dlg.cancel_btn is not None
