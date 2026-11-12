"""
@file: tests/compatibility/test_ssh_sftp_contracts.py
@brief: SSH 终端与 SFTP 传输层契约测试 (2026-10-01 前基线)
@exports: test_ssh_credentials_and_connect_mock, test_sftp_upload_missing_file
"""
import io
from unittest.mock import MagicMock, patch
import pytest
from backend.ssh_client import SSHManager


def test_ssh_credentials_and_connect_mock():
    """验证 SSH 凭据配置及连接建立流程（带参数校验与连接保护）。"""
    mgr = SSHManager()
    mgr.set_credentials(host="192.168.123.164", port=22, username="unitree", password="123")
    assert mgr.host == "192.168.123.164"
    assert mgr.port == 22
    assert mgr.username == "unitree"

    fake_client = MagicMock()
    with patch("paramiko.SSHClient", return_value=fake_client):
        fake_client.connect.return_value = None
        ok, msg = mgr.connect(timeout=2.0)
        assert ok is True
        assert mgr.is_connected() is True

        # 测试断开
        mgr.disconnect()
        assert mgr.is_connected() is False


def test_sftp_upload_missing_file():
    """验证当本地待上传文件不存在时，精确拦截并返回失败提示。"""
    mgr = SSHManager()
    ok, msg = mgr.upload_file("non_existent_local_file.vsis", "/remote/target.vsis")
    assert ok is False
    assert "不存在" in msg
