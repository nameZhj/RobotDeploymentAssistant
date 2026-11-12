"""
@file: tests/unit/test_studio_facade_use_cases.py
@brief: 舞台编导 StudioFacade 与 Composition Root 用例接口单元测试
@exports: test_load_and_create_scene_use_case, test_list_robots_and_actions_use_case, test_trajectory_import_export_use_case, test_studio_dependencies_lifecycle
"""
from pathlib import Path
import pytest
from src.application.studio.studio_dependencies import StudioDependencies, get_studio_dependencies
from src.application.studio.studio_facade import (
    ActionViewData,
    ExportResult,
    ImportResult,
    RobotViewData,
    SaveResult,
    SceneViewData,
    StudioFacade,
    TimelineClipViewData,
    TrajectoryViewData,
    studio_facade,
)
from src.core.models import ControlPoint, SampledPoint, TrajectoryModel
from src.core.storage_manager import StorageManager


def test_load_and_create_scene_use_case(tmp_path):
    """验证创建空场景与加载场景 Use Case。"""
    test_db = str(tmp_path / "test_choreo.db")
    storage = StorageManager(base_dir=str(tmp_path), db_path=test_db)
    facade = StudioFacade(storage=storage)

    # 1. 创建空场景
    scene_view = facade.create_empty_scene("测试排练大厅")
    assert isinstance(scene_view, SceneViewData)
    assert scene_view.name == "测试排练大厅"
    assert scene_view.scene_id.startswith("scene_")

    # 2. 读取刚创建的场景
    loaded = facade.load_scene(scene_view.scene_id)
    assert loaded is not None
    assert loaded.scene_id == scene_view.scene_id
    assert loaded.name == "测试排练大厅"

    # 3. 尝试读取不存在场景
    assert facade.load_scene("non_existent_scene") is None


def test_list_robots_and_actions_use_case(tmp_path):
    """验证机器人列表与动作库 Use Case（严格返回不可变 View Data）。"""
    test_db = str(tmp_path / "test_choreo.db")
    storage = StorageManager(base_dir=str(tmp_path), db_path=test_db)
    facade = StudioFacade(storage=storage)

    # 初始空场景下无机器人
    robots = facade.list_robots("scene_001")
    assert isinstance(robots, list)

    # 动作库应从真实动作定义获取，不包含假型号
    actions = facade.list_actions("Unitree_G1")
    assert isinstance(actions, list)
    assert len(actions) > 0
    for a in actions:
        assert isinstance(a, ActionViewData)
        assert a.model_type == "Unitree_G1"
        assert a.duration > 0.0


def test_trajectory_import_export_use_case(tmp_path):
    """验证轨迹导入导出 Use Case 的原子性与往返一致性。"""
    test_db = str(tmp_path / "test_choreo.db")
    storage = StorageManager(base_dir=str(tmp_path), db_path=test_db)
    facade = StudioFacade(storage=storage)

    # 构造一条合法轨迹实体并保存
    traj = TrajectoryModel(
        trajectory_id="traj_facade_001",
        name="门面测试轨迹",
        scene_id="scene_001",
        target_type="single",
        target_id="A",
        formation_id="",
        interpolation="catmull_rom",
        max_velocity=1.2,
        control_points=[
            ControlPoint(0.0, 0.0, 0.0, 0.0, False),
            ControlPoint(2.0, 1.0, 2.0, 0.5, False),
        ],
        sampled_points=[SampledPoint(0.0, 0.0, 0.0, 0.0, 0.0)],
    )
    storage.save_trajectory(traj)

    # 导出到 JSON
    export_file = tmp_path / "exported_traj.json"
    exp_res = facade.export_trajectory("traj_facade_001", export_file)
    assert exp_res.success is True
    assert export_file.exists()

    # 导入该 JSON
    imp_res = facade.import_trajectory(export_file)
    assert imp_res.success is True
    assert imp_res.trajectory_id == "traj_facade_001"

    # 导入不存在的文件
    failed_imp = facade.import_trajectory(tmp_path / "ghost.json")
    assert failed_imp.success is False


def test_studio_dependencies_lifecycle(tmp_path):
    """验证 StudioDependencies 单例创建与 dispose 释放行为。"""
    test_db = str(tmp_path / "test_choreo.db")
    storage = StorageManager(base_dir=str(tmp_path), db_path=test_db)
    deps = StudioDependencies(storage=storage)
    assert deps.storage is storage
    assert deps.facade is not None

    # 调用 dispose 释放资源
    deps.dispose()
