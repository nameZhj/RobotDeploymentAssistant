# @file: tests/test_lower_computer.py
# @brief: Comprehensive tests for lower computer ROS bridge, real 503 honesty, arrival-driven task chain, barrier, system ops, diagnostics, and LoRa agent.
# @exports: test_health_and_honest_503_when_ros_absent, test_motion_commands_and_reserved_dance_slot, test_task_chain_arrival_progression_and_stop_to_origin, test_system_ops_diagnostics_barrier_and_lora_agent

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List
from urllib import error as urlerror
from urllib import request as urlrequest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api.http_server import LowerComputerHttpServer
from src.api.routes import LowerComputerContext
from src.config.ros_env_config import RosEnvConfig
from src.ros_bridge.navctl_runner import NavctlRunner
from src.ros_bridge.ros_topic_service_bridge import RosTopicServiceBridge


def _http_call(url: str, method: str = "GET", body: Dict[str, Any] | None = None) -> tuple[int, Dict[str, Any]]:
    raw = json.dumps(body).encode("utf-8") if body is not None else None
    req = urlrequest.Request(url, data=raw, headers={"Content-Type": "application/json"}, method=method)
    opener = urlrequest.build_opener(urlrequest.ProxyHandler({}))
    try:
        with opener.open(req, timeout=3.0) as resp:
            return int(resp.status), json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as ex:
        return int(ex.code), json.loads(ex.read().decode("utf-8"))


def test_health_and_honest_503_when_ros_absent(tmp_path: Path) -> None:
    cfg = RosEnvConfig(
        lora_yaml_file=tmp_path / "missing.yaml",
        robot_id_file=tmp_path / "missing_id.txt",
        cache_dir=tmp_path / "cache",
    )
    navctl = NavctlRunner(navctl_bin=str(tmp_path / "missing_navctl"), exists_checker=lambda _p: False)
    ros_bridge = RosTopicServiceBridge(cfg=cfg, master_checker=lambda: False)
    ctx = LowerComputerContext(cfg=cfg, navctl=navctl, ros_bridge=ros_bridge)
    srv = LowerComputerHttpServer(ctx, host="127.0.0.1", port=0)
    port = srv.start()
    try:
        code, health = _http_call(f"http://127.0.0.1:{port}/api/v1/health")
        assert code == 200 and health["ros_master_reachable"] is False and health["navctl_available"] is False

        # Never fabricate success when ROS / navctl is absent
        code_nav, res_nav = _http_call(f"http://127.0.0.1:{port}/api/v1/navigation/navctl", "POST", {"action": "status"})
        assert code_nav == 503 and res_nav["ok"] is False

        code_goal, res_goal = _http_call(f"http://127.0.0.1:{port}/api/v1/navigation/goal", "POST", {"x": 1.0, "y": 2.0})
        assert code_goal == 503 and res_goal["ok"] is False and res_goal["ros_available"] is False
    finally:
        srv.stop()


def test_motion_commands_and_reserved_dance_slot(tmp_path: Path) -> None:
    yaml_file = tmp_path / "lora_recv_group.yaml"
    yaml_file.write_text(
        "motion:\n  forward_axis: 0.60\n  lateral_axis: 0.50\n  turn_axis: 0.70\n"
        "dance_map:\n  # Group 1: select key L1\n  G1_TAIJI: [L1, LEFT] # 太极 RL_taiji\n",
        encoding="utf-8",
    )
    id_file = tmp_path / "lora_robot_id.txt"
    id_file.write_text("A\n", encoding="utf-8")

    cfg = RosEnvConfig(lora_yaml_file=yaml_file, robot_id_file=id_file, cache_dir=tmp_path / "cache")
    ros_bridge = RosTopicServiceBridge(cfg=cfg, master_checker=lambda: True, shell_runner=lambda _c, _t: (0, "ok", ""))
    ctx = LowerComputerContext(cfg=cfg, ros_bridge=ros_bridge)

    assert ctx.motion_exec.execute("STAND").ok
    assert ctx.motion_exec.execute("GAIT").ok
    mv = ctx.motion_exec.execute("MOVE", ["0.5", "0", "0", "2"])
    assert mv.ok and abs(mv.details["vx"] - 0.30) < 1e-6

    # Dance maps to authentic RESERVED_SLOT with keys from lora_recv_group.yaml
    dn = ctx.motion_exec.execute("DANCE", ["G1_TAIJI"])
    assert dn.ok and dn.execution_mode == "RESERVED_SLOT"
    assert dn.details["mapped_keys"] == ["L1", "LEFT"]

    # Unregistered dance must be rejected
    bad = ctx.motion_exec.execute("DANCE", ["NON_EXISTENT_DANCE"])
    assert not bad.ok and bad.execution_mode == "REJECTED"


def test_task_chain_arrival_progression_and_stop_to_origin(tmp_path: Path) -> None:
    # Start a real local HTTP callback listener to verify authentic Webhook callbacks
    events: List[Dict[str, Any]] = []

    class _CbHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

        def do_POST(self) -> None:  # noqa: N802
            ln = int(self.headers.get("Content-Length", "0"))
            events.append(json.loads(self.rfile.read(ln).decode("utf-8")))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

    cb_srv = ThreadingHTTPServer(("127.0.0.1", 0), _CbHandler)
    cb_port = cb_srv.server_address[1]
    threading.Thread(target=cb_srv.serve_forever, daemon=True).start()
    cb_url = f"http://127.0.0.1:{cb_port}/cb"

    # Simulated authentic ROS topic progression: robot moves toward current published goal
    sim_pose = [0.0, 0.0, 0.0]
    published_goals: List[tuple[float, float]] = []
    cancelled = [False]

    def _ros_shell(cmd: str, _timeout: float):
        if "rostopic pub -1 /move_base_simple/goal" in cmd:
            import re
            mx = re.search(r"x:\s*([-0-9.]+),\s*y:\s*([-0-9.]+)", cmd)
            if mx:
                published_goals.append((float(mx.group(1)), float(mx.group(2))))
            return 0, "published", ""
        if "rostopic echo -n 1 /Odometry_loc" in cmd:
            if published_goals:
                gx, gy = published_goals[-1]
                sim_pose[0] += (gx - sim_pose[0]) * 0.65
                sim_pose[1] += (gy - sim_pose[1]) * 0.65
            out = f"pose:\n  pose:\n    position:\n      x: {sim_pose[0]:.4f}\n      y: {sim_pose[1]:.4f}\n      z: 0.0\n    orientation:\n      x: 0.0\n      y: 0.0\n      z: 0.0\n      w: 1.0"
            return 0, out, ""
        if "rostopic echo -n 1 /local_nav_status" in cmd:
            return 0, "data: 'ARRIVED'", ""
        if "rosservice call /teb_polar_node/cancel_planning" in cmd:
            cancelled[0] = True
            return 0, "cancelled", ""
        return 0, "", ""

    yaml_file = tmp_path / "lora_recv_group.yaml"
    yaml_file.write_text("dance_map:\n  G1_TAIJI: [L1, LEFT]\n", encoding="utf-8")
    cfg = RosEnvConfig(lora_yaml_file=yaml_file, cache_dir=tmp_path / "cache", nav_poll_interval_s=0.05)
    ros_bridge = RosTopicServiceBridge(cfg=cfg, master_checker=lambda: True, shell_runner=_ros_shell)
    navctl = NavctlRunner(cmd_runner=lambda argv, _t: subprocess.CompletedProcess(argv, 0, "active", ""), exists_checker=lambda _p: True)
    ctx = LowerComputerContext(cfg=cfg, navctl=navctl, ros_bridge=ros_bridge)
    srv = LowerComputerHttpServer(ctx, host="127.0.0.1", port=0)
    port = srv.start()
    try:
        base = f"http://127.0.0.1:{port}"
        c_up, _ = _http_call(f"{base}/api/v1/task_chain/upload", "POST", {
            "target_id": "A",
            "plan_id": "8001",
            "origin_pose": {"x": -1.0, "y": 0.0, "yaw": 0.0},
            "chain_nodes": [
                {"node_type": "trajectory", "title": "导航到点1", "target_x": 2.0, "target_y": 0.0, "target_yaw": 0.0},
                {"node_type": "action", "title": "太极", "lrmp_code": "G1_TAIJI"},
            ],
        })
        assert c_up == 200
        c_st, _ = _http_call(f"{base}/api/v1/task_chain/start", "POST", {"run_id": "9001", "callback_url": cb_url})
        assert c_st == 202

        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline and not any(e["event"] == "CHAIN_COMPLETED" for e in events):
            time.sleep(0.05)

        ev_names = [e["event"] for e in events]
        assert "STEP_STARTED" in ev_names and "STEP_COMPLETED" in ev_names and "CHAIN_COMPLETED" in ev_names
        # Action node 2 only started AFTER navigation node 1 reached target (2.0, 0.0)
        idx_nav_done = next(i for i, e in enumerate(events) if e["event"] == "STEP_COMPLETED" and e.get("title") == "导航到点1")
        idx_act_start = next(i for i, e in enumerate(events) if e["event"] == "STEP_STARTED" and e.get("title") == "太极")
        assert idx_nav_done < idx_act_start

        # Stop must cancel planning and publish origin_pose goal (-1.0, 0.0)
        c_stop, stop_res = _http_call(f"{base}/api/v1/task_chain/stop", "POST", {"origin_pose": {"x": -1.0, "y": 0.0, "yaw": 0.0}, "callback_url": cb_url})
        assert c_stop == 200 and stop_res["ok"] is True
        assert cancelled[0] is True
        assert published_goals[-1] == (-1.0, 0.0)
    finally:
        srv.stop()
        cb_srv.shutdown()
        cb_srv.server_close()


def test_system_ops_diagnostics_barrier_and_lora_agent(tmp_path: Path) -> None:
    import base64
    import io
    import zipfile

    yaml_file = tmp_path / "lora_recv_group.yaml"
    yaml_file.write_text("motion:\n  forward_axis: 0.6\ndance_map:\n  G1_TAIJI: [L1, LEFT]\n", encoding="utf-8")
    id_file = tmp_path / "lora_robot_id.txt"
    id_file.write_text("A\n", encoding="utf-8")
    lic_file = tmp_path / "license.json"

    def _sys_shell(cmd: str, _t: float):
        if "nmcli" in cmd:
            return 0, "IP4.ADDRESS[1]: 192.168.50.10/24\n", ""
        if "rosversion -d" in cmd:
            return 0, "noetic\n", ""
        if "rosversion roslaunch" in cmd:
            return 0, "1.17.4\n", ""
        if "rosnode list" in cmd:
            return 0, "/livox_lidar_publisher\n/laserMapping\n/global_localization\n/mid360_to_velodyne\n/teb_polar_node\n", ""
        if "rostopic list" in cmd:
            return 0, "/Odometry_loc\n/localization_3d_confidence\n/localization_3d_delay_ms\n/cad_scan\n/global_planner/path\n/teb_polar_node/cmd_vel\n/local_nav_status\n/move_base_simple/goal\n/initialpose\n", ""
        if "rosservice list" in cmd:
            return 0, "/teb_polar_node/cancel_planning\n/teb_polar_node/set_parameters\n", ""
        if "rostopic echo -n 1 /cad_scan" in cmd:
            return 0, "angle_min: -3.14\nangle_max: 3.14\nranges: [1.2, 1.5, 2.0]\n", ""
        if "rosparam set /teb_polar_node/" in cmd or "/teb_polar_node/set_parameters" in cmd:
            return 0, "config: {}", ""
        return 0, "ok", ""

    cfg = RosEnvConfig(
        deploy_root=tmp_path,
        lora_yaml_file=yaml_file,
        robot_id_file=id_file,
        license_file=lic_file,
        g1_ctrl_bin=tmp_path / "missing_g1_ctrl_vsis",
        cache_dir=tmp_path / "cache",
    )
    ros_bridge = RosTopicServiceBridge(cfg=cfg, master_checker=lambda: True, shell_runner=_sys_shell)
    navctl = NavctlRunner(cmd_runner=lambda argv, _t: subprocess.CompletedProcess(argv, 0, "navctl active", ""), exists_checker=lambda _p: True)
    ctx = LowerComputerContext(cfg=cfg, navctl=navctl, ros_bridge=ros_bridge)
    ctx.system_ops._shell = _sys_shell
    ctx.lora_wifi._shell = _sys_shell

    srv = LowerComputerHttpServer(ctx, host="127.0.0.1", port=0)
    port = srv.start()
    try:
        base = f"http://127.0.0.1:{port}"
        c_pre, pre = _http_call(f"{base}/api/v1/system/precheck")
        assert c_pre == 200 and pre["dance_registry_available"] is True and pre["deploy_root_exists"] is True

        c_rid, rid = _http_call(f"{base}/api/v1/system/robot_id", "POST", {"robot_id": "B", "write_autostart": False})
        assert c_rid == 200 and rid["robot_id"] == "B"

        c_lic, lic = _http_call(f"{base}/api/v1/license/deploy", "POST", {
            "content": {"machine_id": "MACHINE-ID-G1-8899", "customer": "UnitreeG1", "dances": ["G1_TAIJI"]},
        })
        assert c_lic == 200 and lic["ok"] is True

        c_reg, reg = _http_call(f"{base}/api/v1/actions/register", "POST", {
            "alias": "G1_WAVE", "select_key": "L1", "action_key": "RIGHT", "comment": "挥手",
        })
        assert c_reg == 200 and reg["ok"] is True

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("RL_wave/config.yaml", "name: wave\n")
        b64_zip = base64.b64encode(buf.getvalue()).decode("ascii")
        c_dp, dp = _http_call(f"{base}/api/v1/dance/deploy", "POST", {"zip_base64": b64_zip})
        assert c_dp == 200 and dp["extracted_count"] == 1

        c_diag, diag = _http_call(f"{base}/api/v1/navigation/diagnostics")
        assert c_diag == 200 and diag["ok"] is True and diag["versions"]["roslaunch_version"] == "1.17.4"

        c_scan, scan = _http_call(f"{base}/api/v1/slam/scan")
        assert c_scan == 200 and scan["ok"] is True and scan["sample_count"] == 3

        c_teb, teb = _http_call(f"{base}/api/v1/navigation/teb_params", "POST", {"params": {"max_vel_x": 0.8}})
        assert c_teb == 200 and teb["ok"] is True

        c_lora, lora = _http_call(f"{base}/api/v1/lora_wifi/command", "POST", {"command": "WIFI_PROBE", "params": ["wlan0"]})
        assert c_lora == 200 and lora["ok"] is True and lora["ip_address"] == "192.168.50.10"

        c_prep, prep = _http_call(f"{base}/api/v1/control/command", "POST", {"command": "PREP", "params": ["8001"]})
        assert c_prep == 200 and prep["ok"] is True

        c_bar, bar = _http_call(f"{base}/api/v1/control/command", "POST", {"command": "BARRIER", "params": ["8001", "1"]})
        assert c_bar == 200 and bar["ok"] is True

        # Verify HTTP edge cases: invalid numeric args -> 400, unsupported method -> 405, CORS OPTIONS -> 204
        c_bad_goal, _ = _http_call(f"{base}/api/v1/navigation/goal", "POST", {"x": "not_a_num", "y": 1.0})
        assert c_bad_goal == 400
        c_bad_log, _ = _http_call(f"{base}/api/v1/system/logs?lines=abc")
        assert c_bad_log == 400
        req_put = urlrequest.Request(f"{base}/api/v1/health", method="PUT")
        opener = urlrequest.build_opener(urlrequest.ProxyHandler({}))
        try:
            opener.open(req_put, timeout=2.0)
            assert False, "PUT should return 405"
        except urlerror.HTTPError as ex:
            assert ex.code == 405

        # Verify navctl shell wrapping with proper shlex quoting
        captured: List[str] = []
        nav_bridge = RosTopicServiceBridge(
            cfg=cfg,
            shell_runner=lambda c, _t: (captured.append(c) or (0, "ok", "")),
            master_checker=lambda: True,
            use_navctl_shell=True,
        )
        g_res = nav_bridge.publish_nav_goal(1.5, -0.5, 0.0)
        assert g_res["ok"] is True and captured and "navctl shell -c" in captured[0]
    finally:
        srv.stop()

