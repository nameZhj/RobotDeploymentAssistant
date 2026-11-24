# @file: tests/test_phase5_design_system.py
# @brief: Offscreen GUI tests validating UniUni v3 tokens, SVG icons, QSS compilation, and zero-truncation U* widgets.
# @exports: test_design_system_widgets_render_no_truncation, test_help_icon_popup_and_panel_dialog_integration

from __future__ import annotations

import os
import pytest
from PySide6.QtCore import QEvent, QPointF
from PySide6.QtGui import QEnterEvent
from PySide6.QtWidgets import QApplication

from src.ui.design_system import (
    UBadge,
    UButton,
    UCollapsibleGroup,
    UDialog,
    UDrawer,
    UHelpIcon,
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


def test_help_icon_popup_and_panel_dialog_integration(qt_app) -> None:
    help_icon = UHelpIcon("操作详情说明", title="操作指南")
    assert help_icon.toolTip() == ""
    help_icon.show()
    enter_ev = QEnterEvent(QPointF(6.0, 6.0), QPointF(6.0, 6.0), QPointF(6.0, 6.0))
    help_icon.enterEvent(enter_ev)
    assert help_icon._popup is not None
    assert help_icon._popup.isVisible()
    assert help_icon._popup._title_lbl.text() == "操作指南"
    assert help_icon._popup._body_lbl.text() == "操作详情说明"

    help_icon.leaveEvent(QEvent(QEvent.Type.Leave))
    assert not help_icon._popup.isVisible()
    help_icon._cleanup_popup()
    help_icon.close()

    panel = UPanel("导航视口", header_widgets=[UBadge("ROS", tone="ok")], help_text="初始说明")
    assert panel._help_icon is not None
    panel.set_help_text("更新说明", title="视口提示")
    assert panel._help_icon.toolTip() == ""
    hl = panel.header_bar.layout()
    assert hl.itemAt(hl.count() - 1).widget() is panel._help_icon
    panel._help_icon._cleanup_popup()
    panel.close()

    dlg = UDialog("测试弹窗", help_text="弹窗提示")
    dlg_helps = dlg.findChildren(UHelpIcon)
    assert len(dlg_helps) == 1 and dlg_helps[0]._help_text == "弹窗提示"
    dlg_helps[0]._cleanup_popup()
    dlg.close()

    drawer = UDrawer("测试抽屉", help_text="抽屉提示")
    drw_helps = drawer.findChildren(UHelpIcon)
    assert len(drw_helps) == 1 and drw_helps[0]._help_text == "抽屉提示"
    drw_helps[0]._cleanup_popup()
    drawer.close()
