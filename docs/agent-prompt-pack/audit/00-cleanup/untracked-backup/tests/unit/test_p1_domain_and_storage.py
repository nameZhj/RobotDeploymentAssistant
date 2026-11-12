"""
@file: tests/unit/test_p1_domain_and_storage.py
@brief: P1 统一领域实体、时空几何变换与工程项目持久化仓储单元测试集
@exports: 测试用例集合
"""
import math
import os
import pytest
from src.domain.project.show_project import (
    Formation, MotionAsset, Robot, RobotGroup, ShowProject
)
from src.domain.transform.stage_coordinate_transform import (
    CanvasTransformConfig, StageCoordinateTransform, deg_to_rad,
    normalize_yaw_deg, normalize_yaw_rad, rad_to_deg
)
from src.infrastructure.storage.show_project_repository import ShowProjectRepository


@pytest.fixture
def temp_project_repo(tmp_path):
    db_file = str(tmp_path / "test_show_project.db")
    return ShowProjectRepository(db_path=db_file)


def test_01_domain_entities_validation():
    p = ShowProject(project_id="proj_01", name="开场大秀", current_map_id="map_stage_01")
    assert p.project_id == "proj_01"
    d = p.to_dict()
    assert d["name"] == "开场大秀"
    restored = ShowProject.from_dict(d)
    assert restored.project_id == "proj_01"

    with pytest.raises(ValueError):
        ShowProject(project_id="", name="非法空项目")

    r = Robot(robot_id="1", display_name="G1_领舞")
    assert r.status == "AVAILABLE"
    assert Robot.from_dict(r.to_dict()).robot_id == "1"

    grp = RobotGroup(group_id="G1", name="先锋编队", member_robot_ids=["1", "2"])
    assert len(grp.member_robot_ids) == 2
    assert RobotGroup.from_dict(grp.to_dict()).group_id == "G1"

    fmt = Formation(formation_id="fmt_01", name="直线阵型", spacing_m=1.5)
    assert fmt.spacing_m == 1.5
    assert Formation.from_dict(fmt.to_dict()).formation_id == "fmt_01"

    motion = MotionAsset(motion_id="m_01", name="Popping", file_path="preview/G1_TIKTOK.npz", frame_count=120)
    assert motion.frame_count == 120
    assert MotionAsset.from_dict(motion.to_dict()).file_path == "preview/G1_TIKTOK.npz"


def test_02_coordinate_transform_canvas_world_roundtrip():
    cfg = CanvasTransformConfig(width=1000.0, height=800.0, scale_px_per_m=50.0, offset_x_px=0.0, offset_y_px=0.0)

    # 屏幕中心 (500, 400) 对应世界原点 (0, 0)
    wx, wy = StageCoordinateTransform.canvas_px_to_world_m(500.0, 400.0, cfg)
    assert wx == 0.0 and wy == 0.0

    # 屏幕上方 50px (500, 350) 对应世界 Y 轴正方向 1.0m (屏幕 Y 轴向下，舞台 Y 轴向上)
    wx2, wy2 = StageCoordinateTransform.canvas_px_to_world_m(500.0, 350.0, cfg)
    assert wx2 == 0.0 and wy2 == 1.0

    # 逆向变换往返一致
    px, py = StageCoordinateTransform.world_m_to_canvas_px(wx2, wy2, cfg)
    assert pytest.approx(px, abs=1e-2) == 500.0
    assert pytest.approx(py, abs=1e-2) == 350.0


def test_03_coordinate_transform_angles_and_pcd():
    assert pytest.approx(deg_to_rad(180.0), abs=1e-4) == math.pi
    assert pytest.approx(rad_to_deg(math.pi), abs=1e-4) == 180.0
    assert pytest.approx(normalize_yaw_deg(270.0), abs=1e-4) == -90.0
    assert pytest.approx(normalize_yaw_rad(3.0 * math.pi), abs=1e-4) == -math.pi

    # PCD 局部转世界原点
    wx, wy, wz = StageCoordinateTransform.pcd_to_world_m(5.0, 3.0, 0.5, origin_x=2.0, origin_y=1.0)
    assert wx == 3.0 and wy == 2.0 and wz == 0.5

    # 反算 PCD
    px, py, pz = StageCoordinateTransform.world_m_to_pcd(wx, wy, wz, origin_x=2.0, origin_y=1.0)
    assert px == 5.0 and py == 3.0 and pz == 0.5

    # 毫秒与秒
    assert StageCoordinateTransform.seconds_to_ms(2.5) == 2500
    assert StageCoordinateTransform.ms_to_seconds(2500) == 2.5


def test_04_project_repository_crud_and_atomic_transactions(temp_project_repo):
    repo = temp_project_repo
    p = ShowProject(project_id="p_test_01", name="测试工程A", current_map_id="map_001")
    robots = [Robot(robot_id="1", display_name="主机"), Robot(robot_id="2", display_name="从机")]
    groups = [RobotGroup(group_id="G1", name="主从组", member_robot_ids=["1", "2"])]

    ok, msg = repo.save_project(p, robots, groups)
    assert ok is True

    # 验证重读
    retrieved = repo.get_project("p_test_01")
    assert retrieved is not None
    assert retrieved.name == "测试工程A"
    assert retrieved.current_map_id == "map_001"

    r_list = repo.list_project_robots("p_test_01")
    assert len(r_list) == 2
    assert r_list[0].robot_id == "1"

    g_list = repo.list_project_groups("p_test_01")
    assert len(g_list) == 1
    assert g_list[0].member_robot_ids == ["1", "2"]

    # 阵型 CRUD
    fmt = Formation(formation_id="fmt_01", name="横队", spacing_m=1.0)
    assert repo.save_formation(fmt)[0] is True
    assert repo.get_formation("fmt_01").name == "横队"
    assert len(repo.list_formations()) >= 1

    # 动作素材 CRUD
    m = MotionAsset(motion_id="m_01", name="Popping1", file_path="preview/G1_KUNG_FU.npz")
    assert repo.save_motion_asset(m)[0] is True
    assert repo.get_motion_asset("m_01").name == "Popping1"
    assert len(repo.list_motion_assets()) >= 1
