"""
@file: tests/compatibility/test_license_contracts.py
@brief: License 授权与机器码匹配契约测试 (2026-10-01 前基线)
@exports: test_license_parser_valid_content, test_license_parser_mismatched_machine_id, test_license_empty_content
"""
import json
import pytest
from backend.license_parser import LicenseParser


def test_license_parser_valid_content():
    """验证合法的测试 License JSON 字符串被正确解析。"""
    sample_license = {
        "machine_id": "UNITREE_G1_TEST_001",
        "customer": "自动化演播中心",
        "product": "Unitree G1",
        "expire_at": "2028-12-31",
        "dances": ["DANCE_A", "DANCE_B", "DANCE_C"],
        "signature": "MOCK_TEST_SIG_ABC123"
    }
    raw_str = json.dumps(sample_license)
    res = LicenseParser.parse_license_content(raw_str)
    assert res["success"] is True
    data = res["data"]
    assert data["machine_id"] == "unitree_g1_test_001"
    assert data["customer"] == "自动化演播中心"
    assert data["dance_count"] == 3
    assert "DANCE_A" in data["dances"]

    # 机器码匹配验证
    verify_match = LicenseParser.verify_license(data, current_machine_id="UNITREE_G1_TEST_001")
    assert verify_match["is_match"] is True
    assert "完全匹配" in verify_match["msg"]


def test_license_parser_mismatched_machine_id():
    """验证当机器码不一致时，精确识别不匹配并给出明确警示。"""
    sample_license = {
        "machine_id": "TARGET_ROBOT_888",
        "customer": "测试客户",
        "dances": ["DANCE_X"]
    }
    res = LicenseParser.parse_license_content(json.dumps(sample_license))
    assert res["success"] is True
    data = res["data"]

    verify_diff = LicenseParser.verify_license(data, current_machine_id="DIFFERENT_ROBOT_999")
    assert verify_diff["is_match"] is False
    assert "机器码不匹配" in verify_diff["msg"]


def test_license_empty_content():
    """验证空内容或格式损坏的 License 文件给出优雅的错误结构，不崩溃。"""
    res_empty = LicenseParser.parse_license_content("")
    assert res_empty["success"] is False
    assert "为空" in res_empty["msg"]

    res_corrupt = LicenseParser.parse_license_content("{corrupted_json_string::}")
    assert res_corrupt["success"] is False
    assert "失败" in res_corrupt["msg"]
