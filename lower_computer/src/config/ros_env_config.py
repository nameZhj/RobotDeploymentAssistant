# @file: src/config/ros_env_config.py
# @brief: Authoritative ROS 1.17.4, navctl, topic/service, and G1 deploy path definitions from 下位机ros信息.
# @exports: ROS_COMPONENTS, ROS_LAUNCH_COMMANDS, NAVCTL_BIN, NAVCTL_ACTIONS, ROS_TOPICS, ROS_SERVICES, RosEnvConfig

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Tuple

ROS_COMPONENTS: Dict[str, str] = {
    "ros_core": "1.17.4",
    "catkin": "0.8.12",
    "tf": "1.13.4",
    "tf2": "0.7.10",
    "rviz": "1.14.26",
    "livox_ros_driver2": "1.0.0",
    "fast_lio": "0.0.0",
    "open3d_loc": "0.0.0",
    "open3d_cpp": "0.14.1",
    "mid360_to_velodyne": "0.0.0",
    "teb_polar": "0.0.0",
}

ROS_LAUNCH_COMMANDS: Dict[str, str] = {
    "ros_master": "roscore -p 11311",
    "livox_driver": "roslaunch livox_ros_driver2 msg_MID360.launch",
    "localization": "roslaunch open3d_loc localization_3d_g1.launch",
    "pointcloud_conv": "roslaunch mid360_to_velodyne mid360_to_velodyne.launch",
    "teb_planner": "roslaunch teb_polar controller_planning.launch",
    "fast_lio_mapping": "roslaunch fast_lio mapping_mid360_g1.launch rviz:=false",
    "rosbag_record": "rosbag record -a",
    "cad_scan_pub": "python3 main.py single",
    "nav_web_server": "python3 nav_web_server.py",
    "dds_bridge": "nav_gait_bridge -> rt/navvelocity",
}

NAVCTL_BIN = "/opt/vsis_nav/navctl"

NAVCTL_ACTIONS: Tuple[str, ...] = (
    "status",
    "start localization",
    "restart localization",
    "start mapping",
    "restart mapping",
    "finish-mapping",
    "stop",
)

ROS_TOPICS: Dict[str, Dict[str, str]] = {
    "lidar": {"topic": "/livox/lidar", "type": "livox_ros_driver2/CustomMsg"},
    "odometry_loc": {"topic": "/Odometry_loc", "type": "nav_msgs/Odometry"},
    "loc_confidence": {"topic": "/localization_3d_confidence", "type": "std_msgs/Float32"},
    "loc_delay_ms": {"topic": "/localization_3d_delay_ms", "type": "std_msgs/Float32"},
    "cad_scan": {"topic": "/cad_scan", "type": "sensor_msgs/LaserScan"},
    "global_path": {"topic": "/global_planner/path", "type": "nav_msgs/Path"},
    "cmd_vel": {"topic": "/teb_polar_node/cmd_vel", "type": "geometry_msgs/Twist"},
    "local_nav_status": {"topic": "/local_nav_status", "type": "std_msgs/String"},
    "move_base_goal": {"topic": "/move_base_simple/goal", "type": "geometry_msgs/PoseStamped"},
    "initialpose": {"topic": "/initialpose", "type": "geometry_msgs/PoseWithCovarianceStamped"},
}

ROS_SERVICES: Dict[str, str] = {
    "cancel_planning": "/teb_polar_node/cancel_planning",
    "set_parameters": "/teb_polar_node/set_parameters",
    "tf_map_to_base": "map -> base_link",
}


@dataclass
class RosEnvConfig:
    """Runtime path and endpoint settings for the G1 onboard HTTP/ROS agent."""

    listen_host: str = "0.0.0.0"
    listen_port: int = 8090
    ros_master_uri: str = "http://127.0.0.1:11311"
    navctl_bin: str = NAVCTL_BIN
    deploy_root: Path = field(default_factory=lambda: Path("/home/ubuntu/vsis_mimic_deploy"))
    robot_id_file: Path = field(default_factory=lambda: Path("/home/ubuntu/vsis_mimic_deploy/group/lora_robot_id.txt"))
    lora_yaml_file: Path = field(default_factory=lambda: Path("/home/ubuntu/vsis_mimic_deploy/group/lora_recv_group.yaml"))
    license_file: Path = field(default_factory=lambda: Path("/home/ubuntu/vsis_mimic_deploy/license.json"))
    g1_ctrl_bin: Path = field(default_factory=lambda: Path("/home/ubuntu/vsis_mimic_deploy/g1_ctrl_vsis"))
    maps_dir: Path = field(default_factory=lambda: Path("/home/ubuntu/vsis_nav_maps"))
    cache_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2] / "runtime_cache")
    arrival_xy_tolerance_m: float = 0.25
    arrival_yaw_tolerance_rad: float = 0.35
    nav_poll_interval_s: float = 0.2
    nav_goal_timeout_s: float = 180.0
    motion_udp_enabled: bool = False
    motion_udp_host: str = "127.0.0.1"
    motion_udp_port: int = 8899
    motion_udp_source_ip: str = "127.0.0.1"
    motion_udp_source_port: int = 0
    motion_udp_probe_timeout_s: float = 2.0
    motion_udp_ack_timeout_s: float = 0.5
    motion_udp_dance_grace_s: float = 10.0
    motion_udp_default_dance_timeout_s: float = 60.0
    motion_udp_transition_timeout_s: float = 6.0
