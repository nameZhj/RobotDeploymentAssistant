# @file: tests/test_phase3_protocol.py
# @brief: Unit tests for Phase 3 LRMP V1.0-R3 codec, authority mutual exclusion, compiler, HTTP upload & SLAM stub.
# @exports: test_lrmp_codec_and_expansion, test_authority_mutual_exclusion, test_timeline_compiler_and_precheck, test_virtual_http_and_slam_mapping

from __future__ import annotations

import json
import pathlib
import pytest

from src.domain.timeline_entities import TimelineBlockEntity
from src.domain.track_entities import TrackEntity
from src.protocol import (
    AuthorityStateMachine,
    ControlAuthority,
    HttpTrajectoryClient,
    LrmpCodec,
    LrmpValidationError,
    SlamMappingClient,
    TimelineLrmpCompiler,
    VirtualRobotServer,
)


def test_lrmp_codec_and_expansion() -> None:
    assert LrmpCodec.encode("a", "stand") == b"A|STAND\n"
    assert LrmpCodec.encode_move("B", 0.5, -0.2, 0.1, 2.0) == b"B|MOVE,0.500,-0.200,0.100,2.00\n"
    expanded = LrmpCodec.expand_targets(["A", "B"], "DANCE", "G1_TIKTOK")
    assert expanded == [b"A|DANCE,G1_TIKTOK\n", b"B|DANCE,G1_TIKTOK\n"]
    with pytest.raises(LrmpValidationError):
        LrmpCodec.encode("A", "PREPARE_EPOCH", "1")
    with pytest.raises(LrmpValidationError):
        LrmpCodec.encode_move("A", 1.8, 0.0, 0.0, 1.0)


def test_authority_mutual_exclusion() -> None:
    sm = AuthorityStateMachine()
    assert sm.get_state("A") == ControlAuthority.FREE
    assert sm.apply_command("A", "STAND").allowed
    assert sm.get_state("A") == ControlAuthority.MANUAL
    assert not sm.apply_command("A", "PREP").allowed
    assert sm.apply_command("A", "RELEASE").allowed
    assert sm.apply_command("A", "PREP").allowed
    assert not sm.apply_command("A", "MOVE").allowed
    assert sm.apply_command("A", "EMERGENCY").allowed
    assert sm.get_state("A") == ControlAuthority.FREE


def test_timeline_compiler_and_precheck() -> None:
    tracks = [TrackEntity(id=1, track_no=1, target_id="A"), TrackEntity(id=2, track_no=2, target_id="B")]
    blocks = [
        TimelineBlockEntity(id=1, task_id=1, track_id=1, block_type="action", code_no="550005", title="G1_TIKTOK", start_time=4.0, duration=18.0, extra={"lrmpCode": "G1_TIKTOK"}),
        TimelineBlockEntity(id=2, task_id=1, track_id=2, block_type="action", code_no="550031", title="G3_KUNGFU", start_time=4.0, duration=20.0, extra={"lrmpCode": "G3_KUNGFU"}),
    ]
    report = TimelineLrmpCompiler.validate_before_launch(tracks, blocks)
    assert report.passed
    plan = TimelineLrmpCompiler.compile_plan(tracks, blocks, plan_id="8001", run_id="9001")
    assert plan.prep_frames == ["A|PREP,8001,9001", "B|PREP,8001,9001"]
    assert len(plan.play_frames) == 2
    assert plan.commands[0].ascii_frame == "A|DANCE,G1_TIKTOK"


def test_virtual_http_and_slam_mapping(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = HttpTrajectoryClient(virtual_server=VirtualRobotServer(uploads_dir=tmp_path))
    receipt = client.upload_payload("192.168.123.101", "A", {"trajectories": [{"no": 100001}]}, prefer_virtual=True)
    assert receipt.success
    assert receipt.mode == "VIRTUAL"
    saved = json.loads(pathlib.Path(receipt.saved_path).read_text(encoding="utf-8"))
    assert saved["trajectories"][0]["no"] == 100001

    monkeypatch.setenv("RDA_WORKSPACE_ROOT", str(tmp_path))
    from src.core.paths import get_paths
    get_paths(reset=True)
    sent = []
    slam = SlamMappingClient(frame_sender=lambda b: sent.append(b) or True)
    ok, _ = slam.start_mapping("A")
    assert ok
    ok_mv, msg = slam.send_teleop_move(0.5, 0.0, 0.2, 1.0)
    assert ok_mv and msg.startswith("A|MOVE")
    pcd_file = slam.save_live_map("test_scan")
    assert pcd_file.exists() and "DATA ascii" in pcd_file.read_text(encoding="utf-8")
    ok_stop, _ = slam.stop_mapping()
    assert ok_stop and any(b == b"A|RELEASE\n" for b in sent)
    get_paths(reset=True)
