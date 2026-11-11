"""
@file: tests/unit/test_f06_execution_and_swarm.py
@brief: Plan F-06 真机执行调度、三链路同步与附属工具后台单元测试
@exports: test_execution_engine_and_authority, test_swarm_monitor_three_links, test_auxiliary_services
"""
import numpy as np
import pytest
from src.application.services.choreo_execution_engine import (
    ChoreoExecutionEngine,
    ms_to_timecode,
    timecode_to_ms
)
from src.application.services.swarm_monitor_service import SwarmMonitorService
from src.application.services.auxiliary_tools_service import (
    ActionTestService,
    RadarImuMonitorService,
    RunLogAnalyzerService,
    ActionStoreService
)


def test_execution_engine_and_authority():
    engine = ChoreoExecutionEngine()
    assert ms_to_timecode(1000, fps=60) == "00:00:01-00"
    assert timecode_to_ms("00:00:01-00", fps=60) == 1000

    ok, _ = engine.request_authority("A", "CHOREO")
    assert ok is True
    ok_release, msg = engine.request_authority("A", "RELEASE")
    assert ok_release is False
    assert "严禁" in msg

    engine.trigger_emergency_stop(["A", "B"])
    assert engine.authorities["A"] == "FREE"
    assert engine.authorities["B"] == "FREE"

    wait_called = []
    gait_ok = engine.stand_to_gait_sequence("A", wait_callback=lambda s: wait_called.append(s))
    assert gait_ok is True
    assert len(wait_called) == 1 and wait_called[0] == 3.0

    track_state = [
        {"robot_id": 1, "no": 101, "name": "POPPING", "type": "active", "start_time": 1.0, "end_time": 3.0}
    ]
    res = engine.dispatch_timeline_tick(time_ms=1500, track_state=track_state)
    assert len(res["dispatched"]) == 1
    assert res["dispatched"][0]["cmd"] == "DANCE,POPPING"


def test_swarm_monitor_three_links():
    service = SwarmMonitorService()

    ok_all, _ = service.assign_robot_lora_id("192.168.1.101", "ALL")
    assert ok_all is False
    ok_invalid, _ = service.assign_robot_lora_id("192.168.1.101", "E")
    assert ok_invalid is False
    ok_valid, _ = service.assign_robot_lora_id("192.168.1.101", "a")
    assert ok_valid is True

    health = service.check_swarm_health(["A", "B"])
    assert "A" in health and "B" in health
    assert "healthy" in health["A"]

    task_res = service.sync_tasks({"name": "巡演编排1"}, targets=["A", "B"])
    assert task_res["A"] is True and task_res["B"] is True

    r_mat = np.array([[-1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
    t_vec = np.array([5.0, 5.0, 0.0], dtype=np.float32)
    raw_traj = {101: "0.00,0.0000,0.0000,0.00\n1.00,1.0000,1.0000,0.00"}
    traj_res = service.sync_trajectories(raw_traj, targets=["A"], use_rt=True, r_mat=r_mat, t_vec=t_vec)
    assert traj_res["A"] is True

    prog_list = []
    map_res = service.sync_maps("dummy.pcd", targets=["A"], progress_cb=lambda tg, p: prog_list.append((tg, p)))
    assert map_res["A"] is True
    assert len(prog_list) >= 2

    service.cancel_map_transfer("A")
    map_cancel = service.sync_maps("dummy.pcd", targets=["A"])
    assert map_cancel["A"] is False


def test_auxiliary_services():
    action_test = ActionTestService()
    ok, msg = action_test.trigger_action("A", "POPPING")
    assert isinstance(ok, bool)
    assert isinstance(msg, str)
    action_test.record_rating("A", "POPPING", score=4, comment="节奏完美")
    action_test.record_rating("A", "芭蕾", score=5)  # 5分应被截断为 4分
    csv_text = action_test.export_ratings_csv()
    assert "POPPING,4,节奏完美" in csv_text
    assert "芭蕾,4" in csv_text

    radar_imu = RadarImuMonitorService()
    for t in [0.1, 0.3, 0.5, 0.7, 0.9]:
        fps = radar_imu.record_point_cloud_frame("lidar_1", timestamp_s=t, point_count=1000)
    assert fps == 5.0

    radar_imu.record_imu_sample("imu_1", (0.0, 0.0, 9.8), (0.0, 0.0, 0.0))
    is_alert = radar_imu.record_imu_sample("imu_1", (0.0, 0.0, 30.0), (0.0, 0.0, 0.0), acc_threshold=15.0)
    assert is_alert is True

    log_lines = [
        "HEADER,VERSION=1",
        "TRAJ_COMPARE,0.1,1.0,2.0,1.0,2.0",
        "TRAJ_COMPARE,0.2,1.5,2.5,1.0,2.0",  # 偏差 ~0.7 > 0.3
        "FOOTER,END"
    ]
    log_res = RunLogAnalyzerService.parse_run_log(log_lines, error_tolerance=0.3)
    assert log_res["slam_points_count"] == 2
    assert log_res["anomalies_count"] == 1
    assert log_res["anomalies"][0]["time_sec"] == 0.2

    store = ActionStoreService()
    pkgs = store.list_action_packages()
    assert len(pkgs) >= 3
    t_id = store.deploy_package_async("192.168.1.101", "dummy.zip")
    prog = store.get_task_progress(t_id)
    assert "status" in prog
