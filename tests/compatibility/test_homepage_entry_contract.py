"""
@file: tests/compatibility/test_homepage_entry_contract.py
@brief: 主页入口、导航条按钮及舞台编导唤起契约测试 (2026-10-01 前基线)
@exports: test_homepage_renders_200, test_homepage_has_single_studio_button, test_open_studio_api_success
"""
import pytest
from main import _studio_manager, launch_studio_window
from src.ui.windows.main_studio_window import MainStudioWindow


def test_homepage_renders_200(client):
    """验证 Flask GET / 正常渲染主页并返回 200 OK。"""
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "<title>" in html
    assert "RobotDeploymentAssistant" in html or "部署" in html or "Robot" in html


def test_homepage_has_single_studio_button(client):
    """验证主页响应中恰好存在且仅存在一个 id='btn-open-studio-window'。"""
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="btn-open-studio-window"' in html
    assert html.count('id="btn-open-studio-window"') == 1
    assert "🎬 舞台编导" in html


def test_open_studio_api_success(client):
    """验证 POST /api/system/open-studio 返回标准 JSON 且包含 success 字段。"""
    resp = client.post("/api/system/open-studio")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, dict)
    assert "success" in data
    assert data["success"] is True
    assert "msg" in data


def test_studio_window_singleton_lifecycle(qapp):
    """验证连续唤起窗口时复用单例实例，不重复创建多个窗口。"""
    _studio_manager.ensure_qt_running()
    success1, _ = launch_studio_window()
    assert success1 is True
    win1 = _studio_manager._window
    assert win1 is not None
    assert isinstance(win1, MainStudioWindow)

    success2, _ = launch_studio_window()
    assert success2 is True
    win2 = _studio_manager._window
    assert win1 is win2
