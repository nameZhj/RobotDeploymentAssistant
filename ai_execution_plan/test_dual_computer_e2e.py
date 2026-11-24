# @file: ai_execution_plan/test_dual_computer_e2e.py
# @brief: Full real-HTTP dual-computer closed-loop test connecting upper_computer and lower_computer servers.
# @exports: test_dual_computer_full_http_closure

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time
from typing import List, Tuple

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[1]
UPPER_ROOT = REPO_ROOT / "upper_computer"
LOWER_ROOT = REPO_ROOT / "lower_computer"


def _load_lower_modules():
    """Import lower_computer server & bridge cleanly under a temporary sys.path swap."""
    orig = list(sys.path)
    saved_src = {k: v for k, v in sys.modules.items() if k == "src" or k.startswith("src.")}
    for k in list(saved_src):
        del sys.modules[k]
    sys.path.insert(0, str(LOWER_ROOT))
    try:
        from src.api.http_server import LowerComputerHttpServer
        from src.api.routes import LowerComputerContext
        from src.commands.lora_serial_daemon import LoraSerialWifiDaemon
        from src.config.ros_env_config import RosEnvConfig
        from src.ros_bridge.navctl_runner import NavctlRunner
        from src.ros_bridge.ros_topic_service_bridge import RosTopicServiceBridge
        return LowerComputerHttpServer, LowerComputerContext, RosEnvConfig, NavctlRunner, RosTopicServiceBridge, LoraSerialWifiDaemon
    finally:
        for k in list(sys.modules):
            if k == "src" or k.startswith("src."):
                del sys.modules[k]
        sys.modules.update(saved_src)
        sys.path[:] = orig


def test_dual_computer_full_http_closure(tmp_path: Path, monkeypatch) -> None:
    # 1. Start real lower_computer HTTP Server with real ROS shell progression
    LowerHttpServer, LowerCtx, RosEnvCfg, NavctlRunner, RosBridge, LoraSerialDaemon = _load_lower_modules()

    yaml_file = tmp_path / "lora_recv_group.yaml"
    yaml_file.write_text(
        "dance_map:\n  # Group 1: select key L1\n  G1_TAIJI: [L1, LEFT] # 太极 RL_taiji\n  G1_TIKTOK: [L1, UP] # 街舞 RL_tiktok\n",
        encoding="utf-8",
    )
    id_file = tmp_path / "lora_robot_id.txt"
    id_file.write_text("A\n", encoding="utf-8")

    sim_pose = [-1.0, 0.0, 0.0]
    goals: List[Tuple[float, float]] = []
    cancelled = [False]

    def _ros_shell(cmd: str, _t: float):
        if "rostopic pub -1 /move_base_simple/goal" in cmd:
            import re
            m = re.search(r"x:\s*([-0-9.]+),\s*y:\s*([-0-9.]+)", cmd)
            if m:
                goals.append((float(m.group(1)), float(m.group(2))))
            return 0, "ok", ""
        if "rostopic echo -n 1 /Odometry_loc" in cmd:
            if goals:
                gx, gy = goals[-1]
                sim_pose[0] += (gx - sim_pose[0]) * 0.7
                sim_pose[1] += (gy - sim_pose[1]) * 0.7
            return 0, f"position:\n  x: {sim_pose[0]:.4f}\n  y: {sim_pose[1]:.4f}\norientation:\n  x: 0.0\n  y: 0.0\n  z: 0.0\n  w: 1.0", ""
        if "rostopic echo -n 1 /local_nav_status" in cmd:
            return 0, "data: 'ARRIVED'", ""
        if "rosservice call /teb_polar_node/cancel_planning" in cmd:
            cancelled[0] = True
            return 0, "ok", ""
        return 0, "", ""

    l_cfg = RosEnvCfg(
        deploy_root=tmp_path / "lower_deploy",
        lora_yaml_file=yaml_file,
        robot_id_file=id_file,
        cache_dir=tmp_path / "lower_cache",
        nav_poll_interval_s=0.04,
    )
    l_bridge = RosBridge(cfg=l_cfg, master_checker=lambda: True, shell_runner=_ros_shell)
    l_navctl = NavctlRunner(cmd_runner=lambda argv, _t: subprocess.CompletedProcess(argv, 0, "navctl ok", ""), exists_checker=lambda _p: True)
    l_ctx = LowerCtx(cfg=l_cfg, navctl=l_navctl, ros_bridge=l_bridge)
    l_srv = LowerHttpServer(l_ctx, host="127.0.0.1", port=0)
    lower_port = l_srv.start()

    # 2. Boot upper_computer StudioStateService pointed at lower_computer HTTP port
    if str(UPPER_ROOT) not in sys.path:
        sys.path.insert(0, str(UPPER_ROOT))
    monkeypatch.setenv("RDA_WORKSPACE_ROOT", str(tmp_path / "upper_ws"))
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from src.core.paths import get_paths
    from src.core.settings import get_settings, save_settings
    from src.domain.timeline_entities import TimelineBlockEntity
    from src.domain.track_entities import TrackEntity
    from src.domain.trajectory_entities import ControlPoint2D, TrajectoryEntity
    from src.persistence import StudioDatabase
    from src.persistence.seed_builtin_data import ensure_seeded
    from src.services.playback_coordinator import PlaybackCoordinator
    from src.services.studio_state_service import StudioStateService

    get_paths(reset=True)
    cfg = get_settings(reload=True)
    cfg.virtual_interfaces.http_default_port = lower_port
    cfg.virtual_interfaces.http_upload_virtual_fallback = False
    save_settings(cfg)

    db = StudioDatabase(tmp_path / "upper_e2e.db")
    ensure_seeded(db)
    state = StudioStateService(db=db)
    playback = PlaybackCoordinator(state)

    try:
        tr = state.upsert_track_validated(TrackEntity(
            task_id=state.task.id or 1, track_no=1, name="G1-A", target_id="A",
            robot_ip="127.0.0.1", init_x=-1.0, init_y=0.0, init_yaw=0.0,
        ))
        # Sync actions over real Wi-Fi HTTP
        ok_act, cnt_act, _ = state.sync_actions_from_http()
        assert ok_act and cnt_act == 2

        # Build Task Chain: "导航到点1" - "太极"
        grp = state.list_groups()[0]
        traj = state.traj_repo.upsert_trajectory(TrajectoryEntity(
            group_id=grp.id or 1, no=100001, name="导航到点1", duration=4.0,
            control_points=[ControlPoint2D(-1.0, 0.0), ControlPoint2D(2.0, 0.0)],
        ))
        act_taiji = state.action_repo.find_by_code_or_no("G1_TAIJI")
        assert act_taiji is not None
        state.commit_block_change(None, TimelineBlockEntity(
            task_id=state.task.id or 1, track_id=tr.id or 1, block_type="trajectory",
            ref_id=traj.id or 0, title="导航到点1", start_time=0.0, duration=4.0,
        ), "添加导航到点1")
        state.commit_block_change(None, TimelineBlockEntity(
            task_id=state.task.id or 1, track_id=tr.id or 1, block_type="action",
            ref_id=act_taiji.id or 0, code_no="G1_TAIJI", title="太极", start_time=4.0, duration=5.0,
        ), "添加太极")

        # Upload & Prep & Start via Wi-Fi HTTP
        up_res = state.compile_and_upload_chains_http(prep=True)
        assert up_res[0]["upload_ok"] and up_res[0]["prep_ok"]
        st_res = state.start_task_chains_http(run_id="9001")
        assert st_res[0]["ok"]

        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            evs = [e.get("event") for e in state.callback_listener.events]
            if "CHAIN_COMPLETED" in evs:
                break
            time.sleep(0.05)

        ev_list = [e.get("event") for e in state.callback_listener.events]
        assert "STEP_STARTED" in ev_list and "STEP_COMPLETED" in ev_list and "CHAIN_COMPLETED" in ev_list

        # Trigger stop-to-origin -> must cancel planning and send goal (-1.0, 0.0) over HTTP
        playback.stop_and_return_origin()
        assert cancelled[0] is True
        assert goals[-1] == (-1.0, 0.0)
        assert abs(state.playhead_s) < 1e-6

        # 3. Verify Upper Computer HttpLowerBridge & Pure-LoRa Wi-Fi Provisioning against Lower Computer
        from backend.http_lower_bridge import HttpLowerBridge
        from backend.lora_wifi_tunnel import LoraWifiTunnel
        from src.services.task_chain_normalizer import format_track_chain_summary
        from src.ui.choreography.timeline_context_menus import reorder_block_in_chain

        bridge = HttpLowerBridge(default_port=lower_port)
        cmd_res = bridge.send_command("A", "STAND", robot_ip="127.0.0.1")
        assert cmd_res["ok"] is True and cmd_res["http_used"] is True
        dances_res = bridge.fetch_dance_list("127.0.0.1")
        assert dances_res["ok"] is True and dances_res["total_count"] == 2
        pre_res = bridge.precheck("127.0.0.1")
        assert pre_res["ok"] is True and pre_res["http_used"] is True
        disc_res = state.http_rpc.fetch_nav_discovery("127.0.0.1")
        assert disc_res.ok is True and disc_res.data["endpoints"]["odom_topic"] == "/Odometry_loc"

        # Verify Flask Web Console pure Wi-Fi HTTP APIs (fleet, health, command, posture, velocity, dance, stop, state, precheck, logs)
        from app import app as flask_app
        from backend.http_lower_bridge import http_lower_bridge
        orig_storage = http_lower_bridge._storage_file
        http_lower_bridge._storage_file = tmp_path / "test_http_fleet.json"
        log_dir = l_cfg.deploy_root / "log"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "sec_run.log").write_text("[INFO] g1_ctrl_vsis ready\n", encoding="utf-8")
        try:
            flask_client = flask_app.test_client()
            r_fl = flask_client.post("/api/fleet", json={"robots": [{"id": "A", "ip": "127.0.0.1", "port": lower_port}], "selected": ["A"]})
            assert r_fl.status_code == 200 and r_fl.get_json()["success"] is True
            r_hl = flask_client.post("/api/http/health", json={"robots": [{"id": "A", "ip": "127.0.0.1", "port": lower_port}]})
            assert r_hl.status_code == 200 and r_hl.get_json()["online_count"] == 1
            r_cm = flask_client.post("/api/http/command", json={"target": "A", "command": "STAND", "targets_map": {"A": {"ip": "127.0.0.1", "port": lower_port}}})
            assert r_cm.status_code == 200 and r_cm.get_json()["success"] is True and r_cm.get_json()["http_used"] is True
            r_po = flask_client.post("/api/http/posture", json={"target": "A", "posture": "GAIT", "robot_ip": "127.0.0.1", "port": lower_port})
            assert r_po.status_code == 200 and r_po.get_json()["success"] is True
            r_ve = flask_client.post("/api/http/velocity", json={"target": "A", "direction": "FORWARD", "duration": 1.0, "robot_ip": "127.0.0.1", "port": lower_port})
            assert r_ve.status_code == 200 and r_ve.get_json()["success"] is True
            r_da = flask_client.post("/api/http/dance", json={"target": "A", "alias": "G1_TAIJI", "robot_ip": "127.0.0.1", "port": lower_port})
            assert r_da.status_code == 200 and r_da.get_json()["success"] is True
            r_st = flask_client.get(f"/api/http/state?target=A&robot_ip=127.0.0.1&port={lower_port}")
            assert r_st.status_code == 200 and r_st.get_json()["data"]["motion"]["active_dance"] == "G1_TAIJI"
            r_sp = flask_client.post("/api/http/stop", json={"target": "A", "emergency": False, "robot_ip": "127.0.0.1", "port": lower_port})
            assert r_sp.status_code == 200 and r_sp.get_json()["success"] is True
            r_dn = flask_client.post("/api/http/dance_list", json={"target": "A", "targets_map": {"A": {"ip": "127.0.0.1", "port": lower_port}}})
            assert r_dn.status_code == 200 and r_dn.get_json()["total_count"] == 2
            r_lg = flask_client.get("/api/logs?type=g1_ctrl&lines=50&robot_ip=127.0.0.1")
            assert r_lg.status_code == 200 and "g1_ctrl_vsis ready" in r_lg.get_json().get("raw_text", "")
            r_pc = flask_client.get("/api/precheck?robot_ip=127.0.0.1")
            assert r_pc.status_code == 200 and "items" in r_pc.get_json().get("data", {})
        finally:
            http_lower_bridge._storage_file = orig_storage

        # Pure-LoRa Wi-Fi probe handshake without SSH: Upper LoraWifiTunnel <-> Lower LoraSerialWifiDaemon
        l_ctx.lora_wifi._shell = lambda _c, _t: (0, "GENERAL.STATE:100 (connected)\nIP4.ADDRESS[1]:192.168.50.108/24\n", "")
        lora_daemon = LoraSerialDaemon(l_ctx.lora_wifi, l_ctx.config_reader)
        rx_buf = []

        class _LoopbackLoRaSerial:
            def is_connected(self) -> bool:
                return True

            def send_command(self, target: str, body: str):
                ack_line = lora_daemon.process_frame_line(f"{target}|{body}")
                if ack_line:
                    rx_buf.append({"ts": time.time(), "text": ack_line})
                return {"success": True}

            def get_recent_messages(self, since_ts: float = 0.0):
                return [m for m in rx_buf if m["ts"] >= since_ts]

        tunnel = LoraWifiTunnel()
        assert "ProxyCommand=" in " ".join(tunnel.build_lora_ssh_argv("echo ok"))
        ack = tunnel.emit_and_wait_lora_ack("WIFI_PROBE", "wlan0", serial_mgr=_LoopbackLoRaSerial(), timeout_s=2.0)
        assert ack["ok"] is True and ack["ack_received"] is True
        assert ack["ack_data"]["ip_address"] == "192.168.50.108"

        # 4. Verify Task-Chain Node Reordering + Undo
        assert format_track_chain_summary(state.blocks, tr.id) == "导航到点1 - 太极"
        first_blk = next(b for b in state.blocks if b.title == "导航到点1")
        assert reorder_block_in_chain(state, first_blk, +1) is True
        assert format_track_chain_summary(state.blocks, tr.id) == "太极 - 导航到点1"
        assert state.undo_stack.undo() is not None
        assert format_track_chain_summary(state.blocks, tr.id) == "导航到点1 - 太极"
    finally:
        state.callback_listener.stop()
        l_srv.stop()
        get_paths(reset=True)
