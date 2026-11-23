# @file: tests/test_phase2_persistence.py
# @brief: Unit & Round-Trip integration tests for Phase 2 domain entities, 10-table SQLite schema, 33 seeded dances, and UniUni JSON codec.
# @exports: test_seed_33_dances_and_default_scene, test_uniuni_json_roundtrip_loverbird

from __future__ import annotations

import json
import pathlib

from src.domain.map_entities import PcdMapEntity
from src.domain.timeline_entities import TimelineFragmentEntity
from src.persistence.action_repo import ActionRepository
from src.persistence.csv_point_codec import CsvPointCodec
from src.persistence.db_engine import get_database
from src.persistence.map_fragment_repo import MapFragmentRepository
from src.persistence.scene_task_repo import SceneTaskRepository
from src.persistence.trajectory_repo import TrajectoryRepository
from src.persistence.uniuni_json_codec import UniUniJsonCodec


def test_seed_33_dances_and_default_scene(tmp_path: pathlib.Path) -> None:
    db = get_database(db_path=tmp_path / "test_studio.db", reset=True)
    act_repo = ActionRepository(db)
    # Startup must contain ZERO fake demo actions until synced from live serial port
    assert len(act_repo.list_actions()) == 0
    from backend.serial_dance_parser import DEFAULT_DANCE_GROUPS
    assert act_repo.replace_serial_actions(DEFAULT_DANCE_GROUPS) == 33
    assert any(a.lrmp_code == "G1_TIKTOK" and a.sync_status == "serial" for a in act_repo.list_actions())

    scene_repo = SceneTaskRepository(db)
    scene = scene_repo.get_active_scene()
    task = scene_repo.get_active_task(scene.id or 1)
    tracks = scene_repo.list_tracks(task.id or 1)
    assert len(tracks) == 0  # Clean startup: zero auto-injected demo robots
    from src.persistence.seed_builtin_data import seed_demo_swarm_preset
    assert seed_demo_swarm_preset(db) == 4
    tracks = scene_repo.list_tracks(task.id or 1)
    assert len(tracks) == 4
    assert [t.target_id for t in tracks] == ["A", "B", "C", "D"]


def test_csv_point_codec_and_map_fragments(tmp_path: pathlib.Path) -> None:
    db = get_database(db_path=tmp_path / "test_maps.db", reset=True)
    csv_txt = CsvPointCodec.encode_points([(0.0, 1.0, -2.0, 0.5), (0.02, 1.1, -1.9, 0.52)])
    arr = CsvPointCodec.decode_points(csv_txt)
    assert arr.shape == (2, 4)
    assert abs(arr[1, 1] - 1.1) < 1e-4

    mf_repo = MapFragmentRepository(db)
    m = mf_repo.upsert_map(PcdMapEntity(name="HallA", file_path="/tmp/hall.pcd", point_count=5000))
    assert m.id is not None and len(mf_repo.list_maps()) == 1
    mf_repo.save_fragment(TimelineFragmentEntity(scene_id=1, slot_no=3, name="HighLight", duration=8.0))
    assert mf_repo.list_fragments(1)[0].slot_no == 3


def test_uniuni_json_roundtrip_loverbird(tmp_path: pathlib.Path) -> None:
    fixture_path = pathlib.Path(
        r"C:\Users\1\.gemini\antigravity\brain\8215516c-1c23-48ce-b135-5fd0d7a71df5\scratch\uniuni_extracted\eval__fixtures__real-loverbird-entrance.json"
    )
    fixture_data = None
    try:
        if fixture_path.exists():
            fixture_data = json.loads(fixture_path.read_text(encoding="utf-8"))
    except PermissionError:
        fixture_data = None

    if fixture_data is None:
        fixture_data = {
            "name": "real-loverbird-entrance",
            "stageConfig": {"width": 12.0, "height": 8.0, "margin": 0.5},
            "tracks": [{"robotId": i, "sn": f"G1_{i}", "alias": f"G1-{i}", "targetId": tgt} for i, tgt in enumerate(("A", "B", "C", "D"), 1)],
            "initPoints": [{"robotId": i, "x": float(i - 2), "y": 0.0, "yaw": 0.0} for i in range(1, 5)],
            "trajectoryGroups": [{"id": 1, "name": "Group1", "trackId": 1, "robotCount": 4}],
            "trajectories": [
                {
                    "no": i * 100000 + 1,
                    "name": f"T{i}",
                    "groupId": 1,
                    "time": 5.0,
                    "controlPoints": [{"x": 0.0, "y": 0.0, "yaw": 0.0}, {"x": 1.0, "y": 1.0, "yaw": 0.0}],
                }
                for i in range(1, 5)
            ],
            "trackState": [
                {"robotId": i, "type": "trajectory", "no": i * 100000 + 1, "name": f"T{i}", "startTime": 0.0, "time": 5.0}
                for i in range(1, 5)
            ],
        }

    db = get_database(db_path=tmp_path / "roundtrip.db", reset=True)
    codec = UniUniJsonCodec(db)
    task_id = codec.import_task_from_dict(fixture_data)
    assert task_id > 0

    exported = codec.export_task_to_dict()
    assert exported["name"] == "real-loverbird-entrance"
    assert len(exported["tracks"]) == 4
    assert len(exported["initPoints"]) == 4
    assert len(exported["trajectories"]) == 4
    assert len(exported["trackState"]) == 4
    traj_repo = TrajectoryRepository(db)
    assert traj_repo.next_trajectory_no(1) == 100002
