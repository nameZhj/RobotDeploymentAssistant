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
    import sys
    get_paths(reset=True)

    # Offline SLAM must refuse to fabricate fake .pcd maps
    offline_slam = SlamMappingClient()
    ok_off, _ = offline_slam.start_mapping("A", "")
    assert not ok_off
    with pytest.raises(RuntimeError):
        offline_slam.save_live_map("should_fail")

    # Connected to real LowerComputerHttpServer over Wi-Fi LAN HTTP
    lower_root = pathlib.Path(__file__).resolve().parents[2] / "lower_computer"
    orig_path = list(sys.path)
    saved_src = {k: v for k, v in sys.modules.items() if k == "src" or k.startswith("src.")}
    for k in list(saved_src):
        del sys.modules[k]
    sys.path.insert(0, str(lower_root))
    from src.api.http_server import LowerComputerHttpServer
    from src.api.routes import LowerComputerContext
    from src.config.ros_env_config import RosEnvConfig
    from src.ros_bridge.navctl_runner import NavctlRunner
    from src.ros_bridge.ros_topic_service_bridge import RosTopicServiceBridge
    import subprocess
    for k in list(sys.modules):
        if k == "src" or k.startswith("src."):
            del sys.modules[k]
    sys.modules.update(saved_src)
    sys.path[:] = orig_path

    maps_dir = tmp_path / "robot_maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    (maps_dir / "real_scan.pcd").write_text("# .PCD v0.7\nVERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\nWIDTH 2\nHEIGHT 1\nPOINTS 2\nDATA ascii\n0 0 0.5\n1 0 0.5\n", encoding="utf-8")
    l_cfg = RosEnvConfig(maps_dir=maps_dir, cache_dir=tmp_path / "lcache")
    l_nav = NavctlRunner(cmd_runner=lambda a, _t: subprocess.CompletedProcess(a, 0, "ok", ""), exists_checker=lambda _p: True)
    l_ros = RosTopicServiceBridge(cfg=l_cfg, master_checker=lambda: True, shell_runner=lambda _c, _t: (0, "ok", ""))
    l_ctx = LowerComputerContext(cfg=l_cfg, navctl=l_nav, ros_bridge=l_ros)
    l_ctx.slam_tap.push_points_list([(0.0, 0.0, 0.5), (1.0, 0.0, 0.5)])
    l_srv = LowerComputerHttpServer(l_ctx, host="127.0.0.1", port=0)
    l_port = l_srv.start()
    try:
        from src.protocol.robot_http_client import RobotHttpClient
        sent = []
        slam = SlamMappingClient(
            frame_sender=lambda b: sent.append(b) or True,
            http_client=RobotHttpClient(timeout_s=2.0),
        )
        from src.core.settings import get_settings, save_settings
        cfg_u = get_settings(reload=True)
        cfg_u.virtual_interfaces.http_default_port = l_port
        save_settings(cfg_u)

        ok, _ = slam.start_mapping("A", "127.0.0.1")
        assert ok
        ok_mv, msg = slam.send_teleop_move(0.5, 0.0, 0.2, 0.4)
        assert ok_mv and msg.startswith("A|MOVE")
        pts, seq = slam.fetch_live_cloud(0)
        assert pts is not None and len(pts) == 2 and seq == 1
        pcd_file = slam.save_live_map("test_scan")
        assert pcd_file.exists() and "DATA ascii" in pcd_file.read_text(encoding="utf-8")
        ok_stop, _ = slam.stop_mapping()
        assert ok_stop
    finally:
        l_ros.stop_cmd_vel()
        l_srv.stop()
        get_paths(reset=True)
