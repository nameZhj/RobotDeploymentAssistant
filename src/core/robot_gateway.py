"""
@file: src/core/robot_gateway.py
@brief: 机器人远程实时建图通信网关与 HTTP 轨迹上传预留接口
@exports: RemoteMappingGateway, remote_mapping_gateway, RobotTrajectoryHttpGateway, robot_trajectory_http_gateway
"""
import copy
import logging
from typing import Any, Dict, List, Optional
from src.core.storage_manager import storage_manager

logger = logging.getLogger("RobotGateway")

DEFAULT_RESERVED_MESSAGE = "[预留接口] 需机器人端建图节点配合实时上传建图数据，当前请通过【上传本地PCD】获取地图"


class RemoteMappingGateway:
    """机器人远程建图与遥控通信网关（功能5预留接口）"""

    def __init__(self, default_endpoint: str = "http://192.168.123.164:8090") -> None:
        self.default_endpoint = default_endpoint
        self._active_sessions: Dict[str, Dict[str, Any]] = {}

    def start_mapping_session(self, robot_id: str, endpoint: Optional[str] = None) -> Dict[str, Any]:
        target_ep = endpoint or self.default_endpoint
        clean_id = robot_id.strip().upper() if robot_id else "A"
        logger.info(f"[GATEWAY STUB] 尝试在机器人 {clean_id} 启动建图: {target_ep}")
        return {
            "ok": False,
            "code": "NOT_IMPLEMENTED",
            "robot_id": clean_id,
            "endpoint": target_ep,
            "session_id": f"sess_{clean_id}_stub",
            "message": DEFAULT_RESERVED_MESSAGE,
        }

    def send_teleop_velocity(self, robot_id: str, vx: float, vy: float, wz: float) -> Dict[str, Any]:
        clean_id = robot_id.strip().upper() if robot_id else "A"
        clamped_vx = round(max(-1.0, min(1.0, float(vx))), 3)
        clamped_vy = round(max(-0.8, min(0.8, float(vy))), 3)
        clamped_wz = round(max(-1.2, min(1.2, float(wz))), 3)
        logger.info(f"[GATEWAY STUB] 遥控速度: {clean_id} -> vx={clamped_vx}, vy={clamped_vy}, wz={clamped_wz}")
        return {
            "ok": False,
            "code": "NOT_IMPLEMENTED",
            "robot_id": clean_id,
            "command": f"MOVE,{clamped_vx},{clamped_vy},{clamped_wz}",
            "message": DEFAULT_RESERVED_MESSAGE,
        }

    def poll_realtime_pointcloud(self, session_id: str) -> Dict[str, Any]:
        return {
            "ok": False,
            "code": "NOT_IMPLEMENTED",
            "session_id": session_id,
            "point_count": 0,
            "points": [],
            "message": DEFAULT_RESERVED_MESSAGE,
        }

    def finish_and_save_pcd(self, session_id: str, target_pcd_path: str) -> Dict[str, Any]:
        logger.info(f"[GATEWAY STUB] 结束建图落盘: {session_id} -> {target_pcd_path}")
        return {
            "ok": False,
            "code": "NOT_IMPLEMENTED",
            "session_id": session_id,
            "target_pcd_path": target_pcd_path,
            "message": DEFAULT_RESERVED_MESSAGE,
        }


class RobotTrajectoryHttpGateway:
    """预留 HTTP 协议上传单机与群体轨迹到机器人通信网关"""

    def upload_trajectory(self, robot_ip: str, port: int, trajectory_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        校验轨迹数据完整性并构造标准 HTTP 请求报文载荷
        @param robot_ip: 目标机器人 IP
        @param port: 目标机器人 HTTP 端口
        @param trajectory_data: 包含完整轨迹与控制点的字典
        """
        required = ["trajectory_id", "target_type", "target_id", "control_points", "sampled_points"]
        for key in required:
            if key not in trajectory_data:
                return {
                    "ok": False,
                    "code": "INVALID_PAYLOAD",
                    "message": f"轨迹数据缺少必填字段: {key}",
                }

        clean_ip = robot_ip.strip() if robot_ip else "192.168.123.164"
        clean_port = int(port) if port else 8090
        endpoint = f"http://{clean_ip}:{clean_port}/api/v1/trajectory/upload"

        payload = copy.deepcopy(trajectory_data)
        if payload.get("target_type") == "swarm" and payload.get("formation_id"):
            payload["swarm_sub_trajectories"] = self._resolve_swarm_payloads(payload)

        return {
            "ok": True,
            "simulated": True,
            "endpoint": endpoint,
            "method": "POST",
            "headers": {"Content-Type": "application/json", "X-Protocol-Version": "LRMP-1.0-R3"},
            "payload": payload,
            "message": "HTTP虚拟接口预留调用成功（未连接真实机器人HTTP服务），已生成标准JSON报文",
        }

    def _resolve_swarm_payloads(self, swarm_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """基于阵型局部偏移展开多机成员独立子轨迹"""
        form_id = swarm_data.get("formation_id", "")
        formation = storage_manager.load_formation(form_id)
        if not formation:
            return []

        sub_trajs: List[Dict[str, Any]] = []
        cps = swarm_data.get("control_points", [])
        for m in formation.members:
            mem_cps = []
            for p in cps:
                mem_cps.append({
                    "seq": p.get("seq", 0),
                    "x": round(float(p.get("x", 0.0)) + m.offset_x, 4),
                    "y": round(float(p.get("y", 0.0)) + m.offset_y, 4),
                    "yaw": round(float(p.get("yaw", 0.0)) + m.offset_yaw, 4),
                    "t": p.get("t", 0.0),
                })
            sub_trajs.append({
                "robot_id": m.robot_id,
                "seq": m.seq,
                "offset": {"x": m.offset_x, "y": m.offset_y, "yaw": m.offset_yaw},
                "control_points": mem_cps,
            })
        return sub_trajs


remote_mapping_gateway = RemoteMappingGateway()
robot_trajectory_http_gateway = RobotTrajectoryHttpGateway()
