"""
@file: src/application/services/auxiliary_tools_service.py
@brief: 动作测试评分报表、雷达IMU健康监控、运行日志偏差分析与动作商店部署服务
@exports: ActionTestService, RadarImuMonitorService, RunLogAnalyzerService, ActionStoreService
"""
import csv
import io
import math
import time
from typing import Any, Dict, List, Optional, Tuple
from backend.serial_manager import serial_manager
from backend.dance_updater import dance_updater


class ActionTestService:
    """动作测试触发、1~4分评级打分与 CSV 报表导出器"""

    def __init__(self) -> None:
        self.records: List[Dict[str, Any]] = []

    def trigger_action(self, robot_id: str, action_name: str) -> Tuple[bool, str]:
        res = serial_manager.send_command(robot_id, f"ACTION_TEST,{action_name}")
        return bool(res.get("success", False)), str(res.get("msg", ""))

    def record_rating(self, robot_id: str, action_name: str, score: int, comment: str = "") -> None:
        val = max(1, min(4, int(score)))
        self.records.append({
            "robot_id": robot_id,
            "action_name": action_name,
            "score": val,
            "comment": comment,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })

    def export_ratings_csv(self) -> str:
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["robot_id", "action_name", "score", "comment", "timestamp"])
        for r in self.records:
            writer.writerow([r["robot_id"], r["action_name"], r["score"], r["comment"], r["timestamp"]])
        return out.getvalue()


class RadarImuMonitorService:
    """雷达点云 60Hz 帧率统计与 IMU 加速度/角速度峰值差异常告警检测器"""

    def __init__(self) -> None:
        self.frame_records: Dict[str, List[float]] = {}
        self.imu_histories: Dict[str, List[Tuple[float, float]]] = {}

    def record_point_cloud_frame(self, sensor_id: str, timestamp_s: float, point_count: int) -> float:
        hist = self.frame_records.setdefault(sensor_id, [])
        hist.append(timestamp_s)
        cutoff = timestamp_s - 1.0
        self.frame_records[sensor_id] = [t for t in hist if t >= cutoff]
        return float(len(self.frame_records[sensor_id]))

    def record_imu_sample(
        self,
        sensor_id: str,
        accel: Tuple[float, float, float],
        gyro: Tuple[float, float, float],
        acc_threshold: float = 15.0,
        gyro_threshold: float = 5.0
    ) -> bool:
        a_norm = math.sqrt(accel[0]**2 + accel[1]**2 + accel[2]**2)
        g_norm = math.sqrt(gyro[0]**2 + gyro[1]**2 + gyro[2]**2)
        hist = self.imu_histories.setdefault(sensor_id, [])
        hist.append((a_norm, g_norm))
        if len(hist) > 50:
            hist.pop(0)

        min_a = min(item[0] for item in hist)
        max_a = max(item[0] for item in hist)
        min_g = min(item[1] for item in hist)
        max_g = max(item[1] for item in hist)

        is_alert = (max_a - min_a > acc_threshold) or (max_g - min_g > gyro_threshold)
        return is_alert


class RunLogAnalyzerService:
    """运行日志解析器：对比 SLAM/控制/参考三轨迹并识别突变异常区间"""

    @classmethod
    def parse_run_log(cls, log_lines: List[str], error_tolerance: float = 0.3) -> Dict[str, Any]:
        slam_traj: List[Tuple[float, float, float]] = []
        ref_traj: List[Tuple[float, float, float]] = []
        ctrl_traj: List[Tuple[float, float, float]] = []
        anomalies: List[Dict[str, Any]] = []

        for line in log_lines:
            tokens = [t.strip() for t in line.split(",") if t.strip()]
            if len(tokens) >= 5 and tokens[0] == "TRAJ_COMPARE":
                t_sec = float(tokens[1])
                slam_x, slam_y = float(tokens[2]), float(tokens[3])
                ref_x, ref_y = float(tokens[4]), float(tokens[5]) if len(tokens) >= 6 else (ref_x, 0.0)
                slam_traj.append((t_sec, slam_x, slam_y))
                ref_traj.append((t_sec, ref_x, ref_y))
                err = math.hypot(slam_x - ref_x, slam_y - ref_y)
                if err > error_tolerance:
                    anomalies.append({"time_sec": t_sec, "error": round(err, 4), "slam": (slam_x, slam_y), "ref": (ref_x, ref_y)})

        return {
            "slam_points_count": len(slam_traj),
            "ref_points_count": len(ref_traj),
            "anomalies_count": len(anomalies),
            "anomalies": anomalies
        }


class ActionStoreService:
    """动作包商店与右上角异步部署任务中心"""

    def __init__(self) -> None:
        self.tasks: Dict[str, Dict[str, Any]] = {}

    def list_action_packages(self) -> List[Dict[str, Any]]:
        return [
            {"id": "pkg_popping", "name": "机械Popping全动作包", "version": "1.2.0", "size_kb": 2048},
            {"id": "pkg_ballet", "name": "天鹅湖现代芭蕾动作包", "version": "1.0.1", "size_kb": 1820},
            {"id": "pkg_kungfu", "name": "中华武术套路动作包", "version": "2.0.0", "size_kb": 3100}
        ]

    def deploy_package_async(self, robot_ip: str, package_path: str) -> str:
        task_id = f"task_{int(time.time() * 1000)}"
        self.tasks[task_id] = {
            "task_id": task_id,
            "ip": robot_ip,
            "package": package_path,
            "status": "RUNNING",
            "progress": 20
        }
        try:
            ok, msg = dance_updater.deploy_zip_package(robot_ip, package_path)
            self.tasks[task_id]["status"] = "SUCCESS" if ok else "FAILED"
            self.tasks[task_id]["progress"] = 100 if ok else 50
            self.tasks[task_id]["message"] = msg
        except Exception as e:
            self.tasks[task_id]["status"] = "FAILED"
            self.tasks[task_id]["progress"] = 0
            self.tasks[task_id]["message"] = str(e)
        return task_id

    def get_task_progress(self, task_id: str) -> Dict[str, Any]:
        return self.tasks.get(task_id, {"status": "UNKNOWN", "progress": 0})

