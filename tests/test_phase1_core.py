# @file: tests/test_phase1_core.py
# @brief: Unit tests for Phase 1 core paths, settings, logger, event bus, undo stack, and hygiene checks.
# @exports: test_workspace_paths_isolation, test_settings_load_and_save, test_event_bus_pubsub, test_undo_stack_100_ops, test_hygiene_passes

from __future__ import annotations

import pathlib

from scripts.verify_hygiene import audit_directory
from src.core.event_bus import StudioEvent, StudioEventBus
from src.core.logger import get_studio_logger
from src.core.paths import build_workspace_paths
from src.core.settings import StageDefaults, StudioSettings, load_settings, save_settings
from src.core.undo_stack import CallableUndoCommand, StudioUndoStack


def test_workspace_paths_isolation(tmp_path: pathlib.Path) -> None:
    paths = build_workspace_paths(tmp_path)
    paths.ensure_runtime_dirs()
    assert paths.db_path == tmp_path / ".agent_workspace" / "runtime" / "uniuni_studio.db"
    assert paths.pcd_cache_dir.is_dir()
    assert paths.http_uploads_dir.is_dir()
    assert not (tmp_path / "runtime").exists()


def test_settings_load_and_save(tmp_path: pathlib.Path) -> None:
    cfg_file = tmp_path / "app_settings.yaml"
    settings = StudioSettings(stage_defaults=StageDefaults(stage_width_m=15.0, stage_height_m=10.0))
    save_settings(settings, cfg_file)
    loaded = load_settings(cfg_file)
    assert loaded.stage_defaults.stage_width_m == 15.0
    assert loaded.stage_defaults.stage_height_m == 10.0
    assert loaded.ui_layout.right_lib_width_px == 330


def test_event_bus_pubsub() -> None:
    bus = StudioEventBus()
    received = []
    bus.subscribe(StudioEvent.SCENE_CHANGED, lambda payload: received.append(payload))
    count = bus.publish(StudioEvent.SCENE_CHANGED, {"sceneId": 42})
    assert count == 1
    assert received == [{"sceneId": 42}]


def test_undo_stack_100_ops() -> None:
    stack = StudioUndoStack(max_history=100)
    state = {"val": 0}
    for i in range(100):
        prev = state["val"]
        nxt = prev + 1
        stack.push(
            CallableUndoCommand(
                f"inc-{i}",
                redo_fn=lambda v=nxt: state.__setitem__("val", v),
                undo_fn=lambda v=prev: state.__setitem__("val", v),
            )
        )
    assert state["val"] == 100
    for _ in range(100):
        assert stack.undo() is not None
    assert state["val"] == 0
    for _ in range(100):
        assert stack.redo() is not None
    assert state["val"] == 100


def test_logger_and_hygiene_passes() -> None:
    logger = get_studio_logger("phase1_test")
    logger.info("Phase 1 verification initialized")
    root_dir = pathlib.Path(__file__).resolve().parents[1]
    errors, rows = audit_directory(root_dir)
    assert errors == []
    assert len(rows) >= 6
