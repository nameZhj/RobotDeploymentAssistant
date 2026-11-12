"""
@file: tests/compatibility/test_flask_api_contracts.py
@brief: Flask RESTful API 契约与静态服务回归测试 (2026-10-01 前基线)
@exports: test_api_status_contract, test_api_disconnect_contract, test_static_asset_serving
"""
import pytest


def test_api_status_contract(client):
    """验证 GET /api/status 响应结构包含关键连接与网络字段。"""
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, dict)
    assert "connected" in data
    assert "host" in data
    assert "port" in data
    assert "latency_ms" in data
    assert "auto_detecting" in data


def test_api_disconnect_contract(client):
    """验证 POST /api/disconnect 能够安全断开连接并返回响应。"""
    resp = client.post("/api/disconnect")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert "已断开连接" in data["msg"]


def test_static_asset_serving(client):
    """验证主页依赖的关键静态资源能够正常通过 static_proxy 访问。"""
    resp_css = client.get("/css/style.css")
    assert resp_css.status_code == 200
    assert "text/css" in resp_css.content_type

    resp_js = client.get("/js/app.js")
    assert resp_js.status_code == 200
    assert "javascript" in resp_js.content_type
