# @file: tests/test_lower_computer.py
# @brief: Comprehensive tests for lower computer ROS bridge, 503 honesty, task chain, UDP closed-loop safety/nav/relocalize, and regression guards.
# @exports: test_health_and_honest_503_when_ros_absent, test_motion_commands_and_reserved_dance_slot, test_task_chain_arrival_progression_and_stop_to_origin, test_system_ops_diagnostics_barrier_and_lora_agent, test_dynamic_ros_discovery_sse_stream_binary_cloud_and_maps, test_udp_motion_bridge_probe_commands_and_dance_done, test_g1_full_closure_state_faults_nav_and_relocalize, test_regression_fixes_d1_d2_d3_d4_d7

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

    # Dance maps to authentic RESERVED_SLOT with case-insensitive lookup from lora_recv_group.yaml
    dn = ctx.motion_exec.execute("DANCE", ["g1_taiji"])
    assert dn.ok and dn.execution_mode == "RESERVED_SLOT"
    assert dn.details["mapped_keys"] == ["L1", "LEFT"]

    # Comma-separated command string & DISCOVER work seamlessly
    dn2 = ctx.motion_exec.execute("DANCE,G1_TAIJI")
    assert dn2.ok and dn2.params == ["G1_TAIJI"]
    disc = ctx.motion_exec.execute("DISCOVER")
    assert disc.ok and disc.details["robot_id"]["robot_id"] == "A"
    assert ctx.motion_exec.get_state()["motion"]["active_dance"] == "G1_TAIJI"

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
                {
                    "node_type": "trajectory", "title": "导航到点1",
                    "target_x": 2.0, "target_y": 0.0, "target_yaw": 0.0,
                    "waypoints": [{"x": 1.0, "y": 0.5, "yaw": 0.0}, {"x": 2.0, "y": 0.0, "yaw": 0.0}],
                },
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
        # Multi-waypoint sequential dispatch: intermediate (1.0, 0.5) published before final (2.0, 0.0)
        assert (1.0, 0.5) in published_goals and (2.0, 0.0) in published_goals
        assert published_goals.index((1.0, 0.5)) < published_goals.index((2.0, 0.0))
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
        assert "items" in pre and "robot_id" in pre["items"]

        c_post, post_res = _http_call(f"{base}/api/v1/control/posture", "POST", {"posture": "STAND"})
        assert c_post == 200 and post_res["ok"] is True
        c_vel, vel_res = _http_call(f"{base}/api/v1/control/velocity", "POST", {"direction": "FORWARD", "duration": 1.5})
        assert c_vel == 200 and vel_res["ok"] is True
        c_dan, dan_res = _http_call(f"{base}/api/v1/control/dance", "POST", {"alias": "G1_TAIJI"})
        assert c_dan == 200 and dan_res["ok"] is True
        c_st, st_res = _http_call(f"{base}/api/v1/control/state")
        assert c_st == 200 and st_res["motion"]["active_dance"] == "G1_TAIJI"
        c_stp, stp_res = _http_call(f"{base}/api/v1/control/stop", "POST", {"emergency": False})
        assert c_stp == 200 and stp_res["ok"] is True
        assert _http_call(f"{base}/api/v1/control/posture", "POST", {"posture": "RELEASE"})[0] == 200
        c_dk, dk_res = _http_call(f"{base}/api/v1/system/docker")
        assert c_dk == 200 and "containers" in dk_res
        c_ct, ct_res = _http_call(f"{base}/api/v1/system/container", "POST", {"action": "restart", "container_name": "vsis_g1"})
        assert c_ct == 200 and ct_res["ok"] is True

        c_rid, rid = _http_call(f"{base}/api/v1/system/robot_id", "POST", {"robot_id": "B", "write_autostart": False})
        assert c_rid == 200 and rid["robot_id"] == "B"

        c_lic, lic = _http_call(f"{base}/api/v1/license/deploy", "POST", {
            "content": {"machine_id": "MACHINE-ID-G1-8899", "customer": "StageG1", "dances": ["G1_TAIJI"]},
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

        c_rlog, rlog = _http_call(f"{base}/api/v1/system/logs?type=ros_nav")
        assert c_rlog == 200 and rlog["ok"] is True and "navctl status" in rlog["raw_text"]

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


def test_dynamic_ros_discovery_sse_stream_binary_cloud_and_maps(tmp_path: Path) -> None:
    map_dir = tmp_path / "dynamic_maps"
    map_dir.mkdir(parents=True, exist_ok=True)
    real_pcd = map_dir / "scans_live.pcd"
    real_pcd.write_text("# .PCD v0.7\nVERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\nWIDTH 2\nHEIGHT 1\nPOINTS 2\nDATA ascii\n0.0 0.0 0.5\n1.0 1.0 0.8\n", encoding="utf-8")
    vel_cmds: List[str] = []

    def _dyn_shell(cmd: str, _t: float):
        if "rostopic list -v" in cmd:
            return 0, (
                "Published topics:\n"
                " * /Odometry [nav_msgs/Odometry] 1 publisher\n"
                " * /cloud_registered [sensor_msgs/PointCloud2] 1 publisher\n"
                " * /global_planner/path [nav_msgs/Path] 1 publisher\n"
                " * /cad_scan [sensor_msgs/LaserScan] 1 publisher\n"
                " * /local_nav_status [std_msgs/String] 1 publisher\n\n"
                "Subscribed topics:\n"
                " * /cmd_vel [geometry_msgs/Twist] 1 subscriber\n"
            ), ""
        if "rosparam list" in cmd:
            return 0, "/fast_lio/map_save_dir\n", ""
        if "rosparam get /fast_lio/map_save_dir" in cmd:
            return 0, str(map_dir), ""
        if "rostopic echo -n 1 /Odometry" in cmd:
            return 0, "position:\n  x: 1.25\n  y: -0.75\norientation:\n  x: 0.0\n  y: 0.0\n  z: 0.0\n  w: 1.0", ""
        if "rostopic echo -n 1 /cad_scan" in cmd:
            return 0, "angle_min: 0.0\nangle_increment: 1.5708\nranges: [1.5, 2.0]", ""
        if "rostopic pub -1 /cmd_vel" in cmd:
            vel_cmds.append(cmd)
            return 0, "ok", ""
        return 0, "", ""

    cfg = RosEnvConfig(cache_dir=tmp_path / "cache", maps_dir=tmp_path / "unused_maps")
    ros_bridge = RosTopicServiceBridge(cfg=cfg, master_checker=lambda: True, shell_runner=_dyn_shell)
    ctx = LowerComputerContext(cfg=cfg, ros_bridge=ros_bridge)
    srv = LowerComputerHttpServer(ctx, host="127.0.0.1", port=0)
    port = srv.start()
    try:
        base = f"http://127.0.0.1:{port}"
        c_d, disc = _http_call(f"{base}/api/v1/navigation/discovery")
        assert c_d == 200 and disc["endpoints"]["odom_topic"] == "/Odometry"
        assert disc["endpoints"]["cloud_topic"] == "/cloud_registered"
        assert disc["endpoints"]["cmd_vel_topic"] == "/cmd_vel"
        assert disc["maps"]["count"] == 1 and str(real_pcd) in disc["maps"]["maps"][0]["path"]

        vel_res = ros_bridge.publish_cmd_vel(0.4, 0.0, 0.0, duration_s=0.35)
        assert vel_res["ok"] is True and vel_res["topic"] == "/cmd_vel"
        time.sleep(0.55)
        assert len(vel_cmds) >= 3 and "x: 0.0000" in vel_cmds[-1]

        ctx.slam_tap.push_points_list([(0.1, 0.2, 0.3), (1.1, 1.2, 0.5)])
        opener = urlrequest.build_opener(urlrequest.ProxyHandler({}))
        with opener.open(f"{base}/api/v1/slam/stream", timeout=2.5) as sse_resp:
            line = sse_resp.readline().decode("utf-8").strip()
            assert line.startswith("data:")
            ev = json.loads(line[5:].strip())
            assert ev["cloud_seq"] == 1 and ev["point_count"] == 2
        with opener.open(f"{base}/api/v1/slam/live_cloud?since_seq=0", timeout=2.5) as bin_resp:
            assert bin_resp.status == 200 and len(bin_resp.read()) == 24
        with opener.open(f"{base}/api/v1/slam/map.pcd", timeout=2.5) as pcd_resp:
            assert b"1.0 1.0 0.8" in pcd_resp.read()

        # Verify local .pcd push to robot map directory + bad-header rejection
        up_bytes = b"# .PCD v0.7\nVERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\nWIDTH 1\nHEIGHT 1\nPOINTS 1\nDATA ascii\n2.5 3.5 0.4\n"
        req_up = urlrequest.Request(
            f"{base}/api/v1/slam/map/upload?filename=user_stage.pcd&restart_localization=0",
            data=up_bytes, headers={"Content-Type": "application/octet-stream"}, method="POST",
        )
        with opener.open(req_up, timeout=2.5) as up_resp:
            up_data = json.loads(up_resp.read().decode("utf-8"))
            assert up_resp.status == 200 and up_data["ok"] is True
            assert (map_dir / "user_stage.pcd").exists()
        bad_req = urlrequest.Request(
            f"{base}/api/v1/slam/map/upload?filename=bad.pcd",
            data=b"not a pcd file", headers={"Content-Type": "application/octet-stream"}, method="POST",
        )
        try:
            opener.open(bad_req, timeout=2.0)
            assert False, "invalid PCD header must return 400"
        except urlerror.HTTPError as ex:
            assert ex.code == 400
    finally:
        ros_bridge.stop_cmd_vel()
        srv.stop()


def test_udp_motion_bridge_probe_commands_and_dance_done(tmp_path: Path) -> None:
    import socket
    from src.commands.g1_udp_motion_bridge import build_motion_udp_packet

    # Frame validation matches g1_motion.py rules
    assert build_motion_udp_packet("a", "stand") == b"A|STAND\n"
    for bad in ("GETDANCELIST", "STAND|EXTRA", "X" * 200):
        try:
            build_motion_udp_packet("A", bad)
            assert False, f"expected ValueError for {bad}"
        except ValueError:
            pass

    rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx_sock.bind(("127.0.0.1", 0))
    rx_sock.settimeout(0.1)
    udp_port = rx_sock.getsockname()[1]

    received: List[str] = []
    pong_enabled = [True]
    ack_enabled = [True]
    dance_done_mode = ["OK"]  # "OK" | "ABORTED" | "NONE"
    stop_rx = threading.Event()

    def _fake_g1_rx() -> None:
        while not stop_rx.is_set():
            try:
                data, addr = rx_sock.recvfrom(512)
            except socket.timeout:
                continue
            except OSError:
                break
            for raw_line in data.decode("ascii", errors="ignore").splitlines():
                received.append(raw_line)
                _, _, cmd_part = raw_line.partition("|")
                cmd_head = cmd_part.split(",", 1)[0]
                if raw_line == "A|PING" and pong_enabled[0]:
                    rx_sock.sendto(b"A|PONG\n", addr)
                elif raw_line == "A|QUERY_STATE":
                    rx_sock.sendto(b"A|STATE,STAND,NONE\n", addr)
                elif raw_line == "A|DANCE,G1_FORBIDDEN":
                    rx_sock.sendto(b"A|ERR,DANCE,UNLICENSED\n", addr)
                elif raw_line == "A|DANCE,G1_TAIJI" and ack_enabled[0]:
                    rx_sock.sendto(b"A|ACK,DANCE\n", addr)
                    if dance_done_mode[0] in ("OK", "ABORTED"):
                        rx_sock.sendto(f"A|DANCE_DONE,G1_TAIJI,{dance_done_mode[0]}\n".encode("ascii"), addr)
                elif cmd_head not in ("PING", "QUERY_STATE") and ack_enabled[0]:
                    rx_sock.sendto(f"A|ACK,{cmd_head}\n".encode("ascii"), addr)

    rx_thread = threading.Thread(target=_fake_g1_rx, daemon=True)
    rx_thread.start()

    yaml_file = tmp_path / "lora_recv_group.yaml"
    yaml_file.write_text(
        "motion:\n  forward_axis: 0.60\n  lateral_axis: 0.50\n  turn_axis: 0.70\n"
        "dance_map:\n  G1_TAIJI: [L1, LEFT] # 太极\n  G1_FORBIDDEN: [L1, RIGHT] # 未授权\n",
        encoding="utf-8",
    )
    id_file = tmp_path / "lora_robot_id.txt"
    id_file.write_text("A\n", encoding="utf-8")

    def _ros_shell(cmd: str, _t: float):
        if "rostopic echo -n 1 /Odometry_loc" in cmd:
            return 0, "position:\n  x: 1.0\n  y: 0.0\norientation:\n  x: 0.0\n  y: 0.0\n  z: 0.0\n  w: 1.0", ""
        if "rostopic echo -n 1 /local_nav_status" in cmd:
            return 0, "data: 'ARRIVED'", ""
        return 0, "ok", ""

    cfg = RosEnvConfig(
        lora_yaml_file=yaml_file, robot_id_file=id_file, cache_dir=tmp_path / "cache",
        nav_poll_interval_s=0.03, motion_udp_enabled=True,
        motion_udp_host="127.0.0.1", motion_udp_port=udp_port,
        motion_udp_probe_timeout_s=0.35, motion_udp_ack_timeout_s=0.25, motion_udp_dance_grace_s=0.0,
    )
    ros_bridge = RosTopicServiceBridge(cfg=cfg, master_checker=lambda: True, shell_runner=_ros_shell)
    ctx = LowerComputerContext(cfg=cfg, ros_bridge=ros_bridge)
    srv = LowerComputerHttpServer(ctx, host="127.0.0.1", port=0)
    http_port = srv.start()
    try:
        base = f"http://127.0.0.1:{http_port}"
        c_p, res_p = _http_call(f"{base}/api/v1/control/probe")
        assert c_p == 200 and res_p["reachable"] is True
        c_h, res_h = _http_call(f"{base}/api/v1/health")
        assert c_h == 200 and res_h["motion_udp_enabled"] is True and res_h["motion_udp"]["reachable"] is True

        pong_enabled[0] = False
        c_p2, res_p2 = _http_call(f"{base}/api/v1/control/probe")
        assert c_p2 == 503 and res_p2["reachable"] is False
        pong_enabled[0] = True

        for body in (
            {"command": "STAND"}, {"command": "GAIT"}, {"command": "PASSIVE"},
            {"command": "FORWARD", "params": ["0.2"]}, {"command": "BACK", "params": ["0.3"]},
            {"command": "MOVE_LEFT", "params": ["0.2"]}, {"command": "TURN_LEFT", "params": ["0.2"]},
            {"command": "MOVE", "params": ["0.5", "0", "0", "0.4"]},
        ):
            code, d = _http_call(f"{base}/api/v1/control/command", "POST", body)
            assert code == 200 and d["ok"] is True and d["details"]["udp"]["ack_received"] is True

        # ERR,DANCE,UNLICENSED -> 409 REJECTED with error_code
        c_err, r_err = _http_call(f"{base}/api/v1/control/dance", "POST", {"alias": "G1_FORBIDDEN"})
        assert c_err == 409 and not r_err["ok"] and r_err["details"]["udp"]["error_code"] == "UNLICENSED"

        # ACK_TIMEOUT -> honest 503 UNAVAILABLE
        ack_enabled[0] = False
        c_tmo, r_tmo = _http_call(f"{base}/api/v1/control/posture", "POST", {"posture": "STAND"})
        assert c_tmo == 503 and not r_tmo["ok"] and r_tmo["details"]["udp"]["error_code"] == "ACK_TIMEOUT"
        ack_enabled[0] = True

        # DANCE -> ACK + DANCE_DONE clears active_dance; QUERY_STATE syncs STATE,STAND,NONE
        c_d, r_d = _http_call(f"{base}/api/v1/control/dance", "POST", {"alias": "G1_TAIJI"})
        assert c_d == 200 and r_d["execution_mode"] == "REAL" and r_d["details"]["udp"]["ack_received"] is True
        time.sleep(0.05)
        c_st, st_after = _http_call(f"{base}/api/v1/control/state?sync=1")
        assert c_st == 200 and st_after["motion"]["active_dance"] == "" and st_after["motion"]["state"] == "STAND"

        c_s, _ = _http_call(f"{base}/api/v1/control/stop", "POST", {"emergency": False})
        assert c_s == 200
        pre_emg_len = len(received)
        c_e, r_e = _http_call(f"{base}/api/v1/control/stop", "POST", {"emergency": True})
        assert c_e == 200 and r_e["command"] == "EMERGENCY"
        assert received[pre_emg_len:] == ["A|STOP"]

        for expect_pkt in (
            "A|STAND", "A|GAIT", "A|PASSIVE", "A|FORWARD,0.20", "A|BACKWARD,0.30",
            "A|MOVE_LEFT,0.20", "A|TURN_LEFT,0.20", "A|MOVE,0.500,0.000,0.000,0.40", "A|DANCE,G1_TAIJI",
        ):
            assert expect_pkt in received

        # TaskChain nav->dance waits for DANCE_DONE:OK even with duration=0.0, switching to GAIT before nav
        _http_call(f"{base}/api/v1/control/posture", "POST", {"posture": "RELEASE"})
        received.clear()
        assert _http_call(f"{base}/api/v1/task_chain/upload", "POST", {
            "target_id": "A", "plan_id": "9101",
            "chain_nodes": [
                {"node_type": "trajectory", "title": "到点", "target_x": 1.0, "target_y": 0.0, "target_yaw": 0.0},
                {"node_type": "action", "title": "太极", "lrmp_code": "G1_TAIJI", "duration": 0.0},
            ],
        })[0] == 200
        t0 = time.monotonic()
        assert _http_call(f"{base}/api/v1/task_chain/start", "POST", {"run_id": "9101"})[0] == 202
        while time.monotonic() - t0 < 2.0 and ctx.task_chain.state.status != "COMPLETED":
            time.sleep(0.03)
        assert ctx.task_chain.state.status == "COMPLETED" and (time.monotonic() - t0) < 1.0
        assert received.index("A|GAIT") < received.index("A|DANCE,G1_TAIJI")

        # DANCE_DONE:ABORTED marks TaskChain ERROR
        dance_done_mode[0] = "ABORTED"
        assert _http_call(f"{base}/api/v1/task_chain/upload", "POST", {
            "target_id": "A", "plan_id": "9102",
            "chain_nodes": [{"node_type": "action", "title": "太极", "lrmp_code": "G1_TAIJI", "duration": 2.0}],
        })[0] == 200
        assert _http_call(f"{base}/api/v1/task_chain/start", "POST", {"run_id": "9102"})[0] == 202
        t_ab = time.monotonic()
        while time.monotonic() - t_ab < 2.0 and ctx.task_chain.state.status not in ("ERROR", "COMPLETED"):
            time.sleep(0.03)
        assert ctx.task_chain.state.status == "ERROR"

        # Fallback to node duration when DANCE_DONE is absent
        dance_done_mode[0] = "NONE"
        assert _http_call(f"{base}/api/v1/task_chain/upload", "POST", {
            "target_id": "A", "plan_id": "9103",
            "chain_nodes": [{"node_type": "action", "title": "太极", "lrmp_code": "G1_TAIJI", "duration": 0.25}],
        })[0] == 200
        t1 = time.monotonic()
        assert _http_call(f"{base}/api/v1/task_chain/start", "POST", {"run_id": "9103"})[0] == 202
        while time.monotonic() - t1 < 2.0 and ctx.task_chain.state.status != "COMPLETED":
            time.sleep(0.03)
        assert ctx.task_chain.state.status == "COMPLETED" and (time.monotonic() - t1) >= 0.2
    finally:
        stop_rx.set()
        rx_sock.close()
        ros_bridge.stop_cmd_vel()
        srv.stop()


def test_g1_full_closure_state_faults_nav_and_relocalize(tmp_path: Path) -> None:
    import socket

    cb_events: List[Dict[str, Any]] = []

    class _CbHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

        def do_POST(self) -> None:  # noqa: N802
            ln = int(self.headers.get("Content-Length", "0"))
            cb_events.append(json.loads(self.rfile.read(ln).decode("utf-8")))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

    cb_srv = ThreadingHTTPServer(("127.0.0.1", 0), _CbHandler)
    cb_port = cb_srv.server_address[1]
    threading.Thread(target=cb_srv.serve_forever, daemon=True).start()
    cb_url = f"http://127.0.0.1:{cb_port}/cb"

    rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx_sock.bind(("127.0.0.1", 0))
    rx_sock.settimeout(0.1)
    udp_port = rx_sock.getsockname()[1]

    received: List[str] = []
    client_addr: List[Any] = [None]
    g1_mode = ["PASSIVE", "NONE", "BLOCKED"]  # MODE, ACTIVE_DANCE, NAV_INPUT
    g1_nav = ["IDLE", ""]
    stop_rx = threading.Event()

    def _emit_rx(line: str) -> None:
        if client_addr[0] is not None and not stop_rx.is_set():
            try:
                rx_sock.sendto((line + "\n").encode("ascii"), client_addr[0])
            except OSError:
                pass

    def _fake_g1_live() -> None:
        while not stop_rx.is_set():
            try:
                data, addr = rx_sock.recvfrom(512)
            except socket.timeout:
                continue
            except OSError:
                break
            client_addr[0] = addr
            for raw in data.decode("ascii", errors="ignore").splitlines():
                received.append(raw)
                _, _, cmd_part = raw.partition("|")
                head = cmd_part.split(",", 1)[0]
                if raw == "A|PING":
                    _emit_rx("A|PONG")
                elif raw == "A|QUERY_STATE":
                    _emit_rx(f"A|STATE,{g1_mode[0]},{g1_mode[1]},{g1_mode[2]}")
                elif raw == "A|QUERY_NAV":
                    _emit_rx(f"A|NAV_STATUS,{g1_nav[0]}" + (f",{g1_nav[1]}" if g1_nav[1] else ""))
                elif raw == "A|STAND":
                    _emit_rx("A|STATE,PASSIVE,NONE,BLOCKED")
                    _emit_rx("A|ACK,STAND")
                    def _finish_stand():
                        time.sleep(0.03)
                        _emit_rx("A|STATE,STANDING,NONE,BLOCKED")
                        time.sleep(0.04)
                        g1_mode[:] = ["STAND", "NONE", "BLOCKED"]
                        _emit_rx("A|STATE,STAND,NONE,BLOCKED")
                    threading.Thread(target=_finish_stand, daemon=True).start()
                elif raw == "A|GAIT":
                    _emit_rx("A|ACK,GAIT")
                    def _finish_gait():
                        time.sleep(0.04)
                        g1_mode[:] = ["GAIT", "NONE", "READY"]
                        _emit_rx("A|STATE,GAIT,NONE,READY")
                    threading.Thread(target=_finish_gait, daemon=True).start()
                elif raw == "A|DANCE,G1_TAIJI":
                    _emit_rx("A|ACK,DANCE")
                    _emit_rx("A|DANCE_START,G1_TAIJI")
                    def _abort_dance():
                        time.sleep(0.06)
                        _emit_rx("A|DANCE_DONE,G1_TAIJI,ABORTED,USER_STOP")
                        g1_mode[:] = ["STAND", "NONE", "BLOCKED"]
                        _emit_rx("A|STATE,STAND,NONE,BLOCKED")
                    threading.Thread(target=_abort_dance, daemon=True).start()
                elif head not in ("PING", "QUERY_STATE", "QUERY_NAV"):
                    _emit_rx(f"A|ACK,{head}")

    threading.Thread(target=_fake_g1_live, daemon=True).start()

    yaml_file = tmp_path / "lora_recv_group.yaml"
    yaml_file.write_text("dance_map:\n  G1_TAIJI: [L1, LEFT]\n", encoding="utf-8")
    id_file = tmp_path / "lora_robot_id.txt"
    id_file.write_text("A\n", encoding="utf-8")

    ros_master_up = [True]
    reloc_services = ["/open3d_loc/relocalize"]
    sim_confidence = [0.88]
    ros_calls: List[str] = []

    def _ros_shell(cmd: str, _t: float):
        ros_calls.append(cmd)
        if "rostopic list -v" in cmd:
            return 0, "Published topics:\n * /Odometry_loc [nav_msgs/Odometry] 1 publisher\n * /localization_3d_confidence [std_msgs/Float32] 1 publisher\n", ""
        if "rosservice list" in cmd:
            return 0, "\n".join(reloc_services), ""
        if "rosservice call /open3d_loc/relocalize" in cmd:
            return 0, "success: True", ""
        if "rostopic echo -n 1 /Odometry_loc" in cmd:
            return 0, "position:\n  x: 0.0\n  y: 0.0\norientation:\n  x: 0.0\n  y: 0.0\n  z: 0.0\n  w: 1.0", ""
        if "rostopic echo -n 1 /localization_3d_confidence" in cmd:
            return 0, f"data: {sim_confidence[0]}", ""
        if "rostopic echo -n 1 /local_nav_status" in cmd:
            return 0, "data: 'MOVING'", ""
        return 0, "ok", ""

    cfg = RosEnvConfig(
        lora_yaml_file=yaml_file, robot_id_file=id_file, cache_dir=tmp_path / "cache",
        nav_poll_interval_s=0.04, motion_udp_enabled=True, motion_udp_host="127.0.0.1",
        motion_udp_port=udp_port, motion_udp_probe_timeout_s=0.5, motion_udp_ack_timeout_s=0.3,
        motion_udp_transition_timeout_s=1.5, motion_udp_dance_grace_s=0.0,
    )
    ros_bridge = RosTopicServiceBridge(cfg=cfg, master_checker=lambda: ros_master_up[0], shell_runner=_ros_shell)
    navctl = NavctlRunner(cmd_runner=lambda argv, _t: subprocess.CompletedProcess(argv, 0, "ok", ""), exists_checker=lambda _p: True)
    ctx = LowerComputerContext(cfg=cfg, navctl=navctl, ros_bridge=ros_bridge)
    srv = LowerComputerHttpServer(ctx, host="127.0.0.1", port=0)
    http_port = srv.start()
    try:
        base = f"http://127.0.0.1:{http_port}"
        # 1. Probe syncs 3-field STATE (PASSIVE/BLOCKED); PASSIVE rejects direct nav goal with 409
        c_pr, r_pr = _http_call(f"{base}/api/v1/control/probe")
        assert c_pr == 200 and r_pr["state"]["nav_input"] == "BLOCKED"
        c_ng0, r_ng0 = _http_call(f"{base}/api/v1/navigation/goal", "POST", {"x": 1.0, "y": 0.0})
        assert c_ng0 == 409 and "PASSIVE" in r_ng0["message"]

        # 2. STAND with wait_ready awaits STANDING -> STAND; then nav goal auto-switches GAIT -> READY
        c_st, r_st = _http_call(f"{base}/api/v1/control/posture", "POST", {"posture": "STAND", "wait_ready": True})
        assert c_st == 200 and r_st["details"]["motion"]["state"] == "STAND"
        c_ng1, _ = _http_call(f"{base}/api/v1/navigation/goal", "POST", {"x": 2.0, "y": 1.0})
        assert c_ng1 == 202 and ctx.motion_udp.tracker.is_nav_ready() is True
        c_can, r_can = _http_call(f"{base}/api/v1/navigation/cancel", "POST", {})
        assert c_can == 200 and r_can["cmd_vel_stop"]["ok"] is True and "A|STOP" in received

        # 3. FAULT,WARN does NOT lock commands
        _emit_rx("A|FAULT,WARN,LOW_BATTERY")
        time.sleep(0.08)
        _, hl = _http_call(f"{base}/api/v1/health")
        assert hl["safety_locked"] is False and any(f["code"] == "LOW_BATTERY" for f in hl["active_faults"])
        assert _http_call(f"{base}/api/v1/control/posture", "POST", {"posture": "GAIT"})[0] == 200

        # 4. Release MANUAL lease first, then FAULT,FATAL,ESTOP_TRIGGERED + ESTOP locks arbiter and aborts running TaskChain
        assert _http_call(f"{base}/api/v1/control/posture", "POST", {"posture": "RELEASE"})[0] == 200
        _http_call(f"{base}/api/v1/task_chain/upload", "POST", {
            "target_id": "A", "plan_id": "9201",
            "chain_nodes": [{"node_type": "trajectory", "title": "长距离导航", "target_x": 8.0, "target_y": 0.0}],
        })
        assert _http_call(f"{base}/api/v1/task_chain/start", "POST", {"run_id": "9201", "callback_url": cb_url})[0] == 202
        time.sleep(0.08)
        _emit_rx("A|FAULT,FATAL,ESTOP_TRIGGERED")
        _emit_rx("A|STATE,ESTOP,NONE,BLOCKED")
        _emit_rx("A|NAV_STATUS,FAILED,FAULT")
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and (not ctx.arbiter.is_safety_locked or ctx.task_chain.state.status == "RUNNING"):
            time.sleep(0.03)
        assert ctx.arbiter.is_safety_locked is True and ctx.task_chain.state.status == "STOPPED"
        assert _http_call(f"{base}/api/v1/control/posture", "POST", {"posture": "GAIT"})[0] == 409
        assert _http_call(f"{base}/api/v1/navigation/goal", "POST", {"x": 1.0, "y": 1.0})[0] == 409
        _, stop_locked = _http_call(f"{base}/api/v1/task_chain/stop", "POST", {"callback_url": cb_url})
        assert stop_locked["return_goal_result"].get("skipped") is True
        assert any(e.get("event") == "ROBOT_FAULT" for e in cb_events)

        # SSE delivers real-time robot_state with active faults & lock
        opener = urlrequest.build_opener(urlrequest.ProxyHandler({}))
        with opener.open(f"{base}/api/v1/slam/stream", timeout=2.5) as sse_resp:
            ev = json.loads(sse_resp.readline().decode("utf-8").strip()[5:].strip())
            assert ev["robot_state"]["safety_locked"] is True and ev["robot_state"]["motion_state"] == "ESTOP"

        # 5. Live recovery: FAULT,CLEAR,CLEAR,ESTOP_TRIGGERED stays locked during ESTOP, unlocks upon STATE,STANDING
        _emit_rx("A|FAULT,CLEAR,CLEAR,ESTOP_TRIGGERED")
        time.sleep(0.08)
        assert ctx.arbiter.is_safety_locked is True
        _emit_rx("A|STATE,STANDING,NONE,BLOCKED")
        time.sleep(0.08)
        assert ctx.arbiter.is_safety_locked is False

        # 6. DANCE_START + DANCE_DONE,ABORTED,USER_STOP fails chain cleanly
        assert _http_call(f"{base}/api/v1/task_chain/upload", "POST", {
            "target_id": "A", "plan_id": "9202",
            "chain_nodes": [{"node_type": "action", "title": "太极", "lrmp_code": "G1_TAIJI", "duration": 3.0}],
        })[0] == 200
        assert _http_call(f"{base}/api/v1/task_chain/start", "POST", {"run_id": "9202", "callback_url": cb_url})[0] == 202
        t_dn = time.monotonic()
        while time.monotonic() - t_dn < 2.0 and ctx.task_chain.state.status not in ("ERROR", "COMPLETED"):
            time.sleep(0.03)
        assert ctx.task_chain.state.status == "ERROR" and "USER_STOP" in ctx.task_chain.state.last_error

        # 7. LOC_LOST fails nav node rapidly without locking manual authority
        assert _http_call(f"{base}/api/v1/task_chain/upload", "POST", {
            "target_id": "A", "plan_id": "9203",
            "chain_nodes": [{"node_type": "trajectory", "title": "导航重定位测试", "target_x": 6.0, "target_y": 0.0}],
        })[0] == 200
        assert _http_call(f"{base}/api/v1/task_chain/start", "POST", {"run_id": "9203", "callback_url": cb_url})[0] == 202
        time.sleep(0.12)
        _emit_rx("A|NAV_STATUS,FAILED,LOC_LOST")
        t_lc = time.monotonic()
        while time.monotonic() - t_lc < 2.0 and ctx.task_chain.state.status not in ("ERROR", "COMPLETED"):
            time.sleep(0.03)
        assert ctx.task_chain.state.status == "ERROR" and "LOC_LOST" in ctx.task_chain.state.last_error
        assert ctx.arbiter.is_safety_locked is False

        # 8. Relocalization endpoint: auto service -> low conf fallback -> manual initialpose with covariance -> ROS off 503
        c_r1, r_r1 = _http_call(f"{base}/api/v1/navigation/relocalize", "POST", {"mode": "auto", "timeout_s": 0.8})
        assert c_r1 == 200 and r_r1["converged"] is True and r_r1["strategy_used"] == "ros_service:/open3d_loc/relocalize"

        reloc_services.clear()
        sim_confidence[0] = 0.25
        c_r2, r_r2 = _http_call(f"{base}/api/v1/navigation/relocalize", "POST", {"mode": "auto", "timeout_s": 0.4, "allow_restart": True})
        assert c_r2 == 200 and r_r2["converged"] is False and r_r2["needs_manual"] is True and r_r2["ok"] is False

        sim_confidence[0] = 0.91
        c_r3, r_r3 = _http_call(f"{base}/api/v1/navigation/relocalize", "POST", {"mode": "manual", "x": 1.2, "y": -0.5, "yaw": 0.3, "timeout_s": 0.8})
        assert c_r3 == 200 and r_r3["converged"] is True and r_r3["strategy_used"] == "manual_initialpose"
        assert any("rostopic pub -1 /initialpose" in c and "covariance:" in c for c in ros_calls)

        ros_master_up[0] = False
        c_r4, r_r4 = _http_call(f"{base}/api/v1/navigation/relocalize", "POST", {"mode": "auto"})
        assert c_r4 == 503 and r_r4["ros_available"] is False and r_r4["ok"] is False
    finally:
        stop_rx.set()
        rx_sock.close()
        ros_bridge.stop_cmd_vel()
        srv.stop()
        cb_srv.shutdown()
        cb_srv.server_close()


def test_regression_fixes_d1_d2_d3_d4_d7(tmp_path: Path) -> None:
    """Verify fixes for D1 (None conf/stale cache), D2 (READY->ESTOP->CLEAR release), D3 (concurrent ACKs), D4 (edge cancel), D7 (rejected state)."""
    import socket

    rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx_sock.bind(("127.0.0.1", 0))
    rx_sock.settimeout(0.1)
    udp_port = rx_sock.getsockname()[1]

    peer_addr: List[Any] = [None]
    stop_rx = threading.Event()
    cancel_calls = [0]
    conf_reply: List[Any] = [0.90]

    def _emit_rx(line: str) -> None:
        if peer_addr[0] is not None and not stop_rx.is_set():
            try:
                rx_sock.sendto((line + "\n").encode("ascii"), peer_addr[0])
            except OSError:
                pass

    def _mock_rx() -> None:
        while not stop_rx.is_set():
            try:
                data, addr = rx_sock.recvfrom(512)
            except socket.timeout:
                continue
            except OSError:
                break
            peer_addr[0] = addr
            for raw in data.decode("ascii", errors="ignore").splitlines():
                _, _, cmd_part = raw.partition("|")
                head = cmd_part.split(",", 1)[0]
                if head == "PING":
                    _emit_rx("A|PONG")
                elif head == "DANCE":
                    _emit_rx("A|ERR,DANCE,UNLICENSED")
                elif head in ("MOVE",):
                    _emit_rx("A|ERR,MOVE,BLOCKED")
                elif head in ("FORWARD", "TURN_LEFT"):
                    def _delayed_ack(h: str = head) -> None:
                        time.sleep(0.05)
                        _emit_rx(f"A|ACK,{h}")
                    threading.Thread(target=_delayed_ack, daemon=True).start()
                elif head not in ("QUERY_STATE", "QUERY_NAV"):
                    _emit_rx(f"A|ACK,{head}")

    threading.Thread(target=_mock_rx, daemon=True).start()

    def _ros_shell(cmd: str, _t: float):
        if "cancel_planning" in cmd:
            cancel_calls[0] += 1
            return 0, "ok", ""
        if "rostopic list -v" in cmd:
            return 0, "Published topics:\n * /Odometry_loc [nav_msgs/Odometry] 1 publisher\n * /localization_3d_confidence [std_msgs/Float32] 1 publisher\n", ""
        if "rostopic echo -n 1 /Odometry_loc" in cmd:
            return 0, "position:\n  x: 0.0\n  y: 0.0\norientation:\n  x: 0.0\n  y: 0.0\n  z: 0.0\n  w: 1.0", ""
        if "rostopic echo -n 1 /localization_3d_confidence" in cmd:
            return (0, f"data: {conf_reply[0]}", "") if conf_reply[0] is not None else (1, "", "no msg")
        return 0, "ok", ""

    yaml_file = tmp_path / "lora_recv_group.yaml"
    yaml_file.write_text("dance_map:\n  G1_TAIJI: [L1, LEFT]\n", encoding="utf-8")
    id_file = tmp_path / "lora_robot_id.txt"
    id_file.write_text("A\n", encoding="utf-8")
    cfg = RosEnvConfig(
        lora_yaml_file=yaml_file, robot_id_file=id_file, cache_dir=tmp_path / "cache",
        motion_udp_enabled=True, motion_udp_host="127.0.0.1", motion_udp_port=udp_port,
        motion_udp_probe_timeout_s=0.4, motion_udp_ack_timeout_s=0.35,
    )
    ros_bridge = RosTopicServiceBridge(cfg=cfg, master_checker=lambda: True, shell_runner=_ros_shell)
    ctx = LowerComputerContext(cfg=cfg, ros_bridge=ros_bridge)
    srv = LowerComputerHttpServer(ctx, host="127.0.0.1", port=0)
    srv.start()
    try:
        # D1: prior confidence in slam_tap must not falsely converge or crash with NoneType format when ROS returns no confidence
        ctx.slam_tap.push_external_frame(pose={"x": 0.0, "y": 0.0, "yaw": 0.0}, confidence=0.90)
        conf_reply[0] = None
        rel_res = ctx.relocalizer.relocalize(mode="manual", pose=(1.0, 2.0, 0.0), timeout_s=0.3)
        assert rel_res["ok"] is False and rel_res["converged"] is False and rel_res["needs_manual"] is True
        assert "未收到新置信度反馈" in rel_res["message"]

        # D7: rejected MOVE / DANCE must not mutate local _active_motion["state"]
        assert ctx.motion_exec.execute("STAND").ok
        bad_mv = ctx.motion_exec.execute("MOVE", ["0.5", "0", "0", "0.2"])
        assert not bad_mv.ok and ctx.motion_exec._active_motion["state"] == "STAND"
        bad_dn = ctx.motion_exec.execute("DANCE", ["G1_TAIJI"])
        assert not bad_dn.ok and ctx.motion_exec._active_motion["state"] == "STAND" and ctx.motion_exec._active_motion["active_dance"] == ""

        # D3: concurrent ACK waits must not race and time out each other
        results: List[Any] = []
        t1 = threading.Thread(target=lambda: results.append(ctx.motion_udp.send_command("A", "FORWARD,0.2")))
        t2 = threading.Thread(target=lambda: results.append(ctx.motion_udp.send_command("A", "TURN_LEFT,0.2")))
        t1.start(); t2.start(); t1.join(); t2.join()
        assert len(results) == 2 and all(r.ok and r.ack_received for r in results)

        # D2 & D4: ESTOP during READY releases CHOREO, and repeated ESTOP heartbeats only cancel ROS once
        assert ctx.motion_exec.execute("RELEASE").ok
        assert ctx.task_chain.upload_chain({"target_id": "A", "plan_id": "9301", "chain_nodes": [{"node_type": "action", "title": "t", "lrmp_code": "STAND"}]})["status"] == "UPLOADED"
        assert ctx.task_chain.prep_chain("9301")["ok"] is True
        assert ctx.task_chain.state.status == "READY" and ctx.arbiter.state.value == "CHOREO"

        cancel_calls[0] = 0
        for _ in range(4):
            _emit_rx("A|STATE,ESTOP,NONE,BLOCKED")
            time.sleep(0.03)
        time.sleep(0.1)
        assert cancel_calls[0] == 1
        assert ctx.arbiter.is_safety_locked is True and ctx.arbiter.state.value == "FREE"

        _emit_rx("A|STATE,STANDING,NONE,BLOCKED")
        time.sleep(0.08)
        assert ctx.arbiter.is_safety_locked is False
        assert ctx.motion_exec.execute("STAND").ok

        # WebhookDispatcher & SystemOpsService audit regression checks (C-6 / W-3)
        from src.commands.system_ops_service import SystemOpsService
        from src.task_chain.webhook_dispatcher import WebhookDispatcher

        wd = WebhookDispatcher(async_backoff_s=0.0)
        assert wd.emit_async("", "STEP_PROGRESS", {"x": 1}).ok is False and wd._async_worker is None
        wd._ensure_async_worker = lambda: None
        wd.emit_async("http://127.0.0.1:1/cb", "STEP_PROGRESS", {"idx": 1})
        wd.emit_async("http://127.0.0.1:1/cb", "CHAIN_ABORTED", {"target_id": "A"}, urgent=True)
        assert [it[1] for it in wd._pending] == ["CHAIN_ABORTED"]

        sys_ops = SystemOpsService(
            cfg, ctx.config_reader,
            shell_fn=lambda cmd, _t: (0, "vsis_g1|rl:2.0|Up 2 hours" if "docker ps" in cmd else "", ""),
        )
        dk = sys_ops.get_docker_status()
        assert dk["running"] is True and dk["container_exists"] is True and dk["is_container_running"] is True and dk["robot_id"] == "A"
    finally:
        stop_rx.set()
        rx_sock.close()
        ros_bridge.stop_cmd_vel()
        srv.stop()


