# @file: main.py
# @brief: Lower computer onboard HTTP & ROS agent entrypoint.
# @exports: main

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api.http_server import LowerComputerHttpServer
from src.api.routes import LowerComputerContext
from src.commands.lora_serial_daemon import LoraSerialWifiDaemon
from src.config.ros_env_config import RosEnvConfig
from src.ros_bridge.ros_topic_service_bridge import RosTopicServiceBridge


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unitree G1 Lower Computer HTTP/ROS Agent")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP bind address")
    parser.add_argument("--port", type=int, default=8090, help="HTTP listen port (default: 8090)")
    parser.add_argument("--lora-yaml", default="/home/ubuntu/vsis_mimic_deploy/group/lora_recv_group.yaml")
    parser.add_argument("--robot-id-file", default="/home/ubuntu/vsis_mimic_deploy/group/lora_robot_id.txt")
    parser.add_argument("--use-navctl-shell", action="store_true", help="Execute ROS CLI inside sudo /opt/vsis_nav/navctl shell")
    parser.add_argument("--lora-serial-port", default="", help="Optional LoRa serial device for pure-LoRa Wi-Fi provisioning")
    parser.add_argument("--lora-baud", type=int, default=9600, help="LoRa serial baudrate")
    args = parser.parse_args(argv)

    cfg = RosEnvConfig(
        listen_host=args.host,
        listen_port=args.port,
        lora_yaml_file=Path(args.lora_yaml),
        robot_id_file=Path(args.robot_id_file),
    )
    auto_navctl = args.use_navctl_shell or (shutil.which("rostopic") is None and Path(cfg.navctl_bin).exists())
    ros_bridge = RosTopicServiceBridge(cfg=cfg, use_navctl_shell=auto_navctl)
    ctx = LowerComputerContext(cfg=cfg, ros_bridge=ros_bridge)
    if ctx.ros_bridge.is_ros_master_reachable():
        ctx.discovery.discover_topics(force=True)
        ctx.slam_tap.start()
    lora_daemon = None
    if args.lora_serial_port:
        lora_daemon = LoraSerialWifiDaemon(ctx.lora_wifi, ctx.config_reader, args.lora_serial_port, args.lora_baud)
        if lora_daemon.start():
            print(f"[LowerComputer] LoRa Wi-Fi provisioning listener active on {args.lora_serial_port}@{args.lora_baud}")
    srv = LowerComputerHttpServer(ctx, host=args.host, port=args.port)
    print(f"[LowerComputer] Listening on http://{args.host}:{args.port} (ROS Master: {cfg.ros_master_uri}, navctl_shell={auto_navctl})")
    try:
        srv.start(blocking=True)
    except KeyboardInterrupt:
        if lora_daemon is not None:
            lora_daemon.stop()
        srv.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
