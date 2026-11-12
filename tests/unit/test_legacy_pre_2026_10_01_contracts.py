"""
@file: tests/unit/test_legacy_pre_2026_10_01_contracts.py
@brief: 2026-10-01 前核心功能（舞蹈ZIP升级、串口映射、G1模型注入与Web路由）契约保护测试
@exports: test_legacy_dance_groups_contract, test_legacy_serial_dance_parser, test_legacy_dance_zip_update_no_file, test_legacy_g1_urdf_models_exist, test_legacy_preview_manager_loaded
"""
import io
import os
import zipfile
import pytest

from app import app
from backend.serial_dance_parser import DEFAULT_DANCE_GROUPS, parse_dance_map_yaml
from backend.preview_manager import preview_manager


@pytest.fixture
def client():
    """Flask 测试客户端。"""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_legacy_dance_groups_contract():
    """验证 2026-10-01 前定义的 33 支舞蹈动作指令表保持完整且契约不变。"""
    assert len(DEFAULT_DANCE_GROUPS) == 3
    total_items = sum(len(grp.get("items", [])) for grp in DEFAULT_DANCE_GROUPS)
    assert total_items == 33

    for grp in DEFAULT_DANCE_GROUPS:
        assert "group_id" in grp
        assert "items" in grp
        for item in grp.get("items", []):
            assert "alias" in item
            assert "name" in item
            assert "cmd" in item
            assert "keys" in item


def test_legacy_serial_dance_parser():
    """验证串口舞蹈指令解析器能正确解析 YAML 格式映射表。"""
    sample_yaml = """
dance_map:
  G1_TURN_JUMP:    [L1, DOWN]     # 转身跳跃
  G2_SPIN_KICK:    [R1, DOWN]     # 旋转飞踢
"""
    groups = parse_dance_map_yaml(sample_yaml)
    assert len(groups) >= 2
    aliases = [item["alias"] for g in groups for item in g["items"]]
    assert "G1_TURN_JUMP" in aliases
    assert "G2_SPIN_KICK" in aliases


def test_legacy_dance_zip_update_no_file(client):
    """验证 2026-10-01 前 /api/dance/update 接口未传文件时的安全拦截契约。"""
    resp = client.post("/api/dance/update", data={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is False
    assert "未检测到" in data["msg"]


def test_legacy_dance_zip_update_valid_zip(client, tmp_path):
    """验证上传有效 zip 压缩包时正常生成 dance_update_ 任务 ID。"""
    zip_path = tmp_path / "test_dances.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("model_a.vsis", "dummy vsis content A")
        zf.writestr("config.yaml", "dummy: true\n")

    with open(zip_path, "rb") as fp:
        data = {
            "zip_file": (fp, "test_dances.zip"),
            "dest_path": "/secure/config_vsis",
        }
        resp = client.post("/api/dance/update", data=data, content_type="multipart/form-data")
        assert resp.status_code == 200
        res_json = resp.get_json()
        assert res_json["success"] is True
        assert res_json["task_id"].startswith("dance_update_")
        assert res_json["filename"] == "test_dances.zip"


def test_legacy_g1_urdf_models_exist():
    """验证 2026-10-01 引入的 Unitree G1 23/29DOF URDF 资产完好无损。"""
    g1_dir = os.path.join("assets", "models", "g1_avatar", "g1_description")
    assert os.path.isdir(g1_dir)
    urdf_23 = os.path.join(g1_dir, "g1_23dof.urdf")
    urdf_29 = os.path.join(g1_dir, "g1_29dof.urdf")
    urdf_29_hand = os.path.join(g1_dir, "g1_29dof_with_hand.urdf")
    assert os.path.isfile(urdf_23)
    assert os.path.isfile(urdf_29)
    assert os.path.isfile(urdf_29_hand)


def test_legacy_preview_manager_loaded():
    """验证 2026-10-01 前 3D 舞蹈预览管理器单例正常加载并具备基础服务契约。"""
    assert preview_manager is not None
    models_dir = preview_manager.get_builtin_models_dir()
    assert os.path.exists(models_dir)
    assert hasattr(preview_manager, "list_all_dances")
    assert hasattr(preview_manager, "import_zip")
