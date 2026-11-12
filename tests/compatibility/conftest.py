"""
@file: tests/compatibility/conftest.py
@brief: 2026-10-01 前历史兼容性测试公共 fixtures 与配置
@exports: client, qapp, fixtures_dir
"""
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pytest
from app import app


@pytest.fixture(scope="session")
def fixtures_dir():
    """返回测试 fixture 目录。"""
    p = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fixtures", "compatibility"))
    os.makedirs(p, exist_ok=True)
    return p


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """保证 PySide6 QApplication 全局实例在主线程存在。"""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    app_inst = QApplication.instance()
    if app_inst is None:
        app_inst = QApplication([])
    from main import _studio_manager
    _studio_manager.ensure_qt_running()
    yield app_inst


@pytest.fixture
def client():
    """Flask 独立测试客户端。"""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
