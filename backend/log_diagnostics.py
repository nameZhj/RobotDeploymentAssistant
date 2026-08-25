import re
import time
import logging
from typing import Dict, Any, List, Optional
from backend.ssh_client import ssh_manager

logger = logging.getLogger("LogDiagnostics")


DIAGNOSTIC_RULES = [
    {
        "id": "missing_ch341",
        "regex": r"(/dev/ttyCH341USB0.*(?:No such file|not found|cannot open)|open serial error|CH341.*failed)",
        "title": "CH341 串口驱动缺失或硬件未插",
        "severity": "danger",
        "description": "系统未能找到 /dev/ttyCH341USB0 串口设备。驱动装在宿主机上，如果缺失将导致 LoRa 群控接收端无法接收无线指令。",
        "fix_title": "一键修复 CH341 驱动",
        "fix_action": "fix_ch341"
    },
    {
        "id": "not_licensed",
        "regex": r"(\[SKIP\]\s*not licensed|license\.json.*(?:not found|invalid|mismatch)|Hardware ID mismatch)",
        "title": "License 授权无效或机器码不匹配",
        "severity": "danger",
        "description": "当前 license.json 与机器人的 64 位硬件机器码不一致，或未授权对应舞蹈，控制程序已跳过加载。",
        "fix_title": "前往导入匹配 License",
        "fix_action": "goto_license"
    },
    {
        "id": "dds_conflict",
        "regex": r"(Address already in use|bind failed|DDS.*conflict|domain.*conflict)",
        "title": "DDS 通信或端口冲突",
        "severity": "warning",
        "description": "DDS 运控话题 rt/groupcontroller 或端口被旧的残留进程占用。",
        "fix_title": "一键重启运控与群控进程",
        "fix_action": "restart_processes"
    },
    {
        "id": "cuda_error",
        "regex": r"(CUDA error|cudaGetDeviceCount failed|CUDA driver version is insufficient|NVIDIA-SMI has failed)",
        "title": "CUDA / GPU 运行时异常",
        "severity": "danger",
        "description": "Docker 容器内无法调用 GPU 硬件加速，请确认宿主机 NVIDIA 驱动及 docker run --gpus all 参数。",
        "fix_title": "查看环境预检",
        "fix_action": "goto_precheck"
    },
    {
        "id": "port_allocated",
        "regex": r"(port is already allocated|Bind for 0\.0\.0\.0:400 failed|driver failed programming external connectivity)",
        "title": "Docker 端口冲突 (400/4001/4002 已被占用)",
        "severity": "danger",
        "description": "端口 400 (SSH)、4001 或 4002 被机器人上的旧容器或残留进程占用，导致 vsis_g1 容器无法绑定端口启动。",
        "fix_title": "一键释放端口并重启容器",
        "fix_action": "fix_port_conflict"
    },
    {
        "id": "robot_id_error",
        "regex": r"(robot_id.*empty|robot_id cannot be ALL|invalid robot_id)",
        "title": "Robot ID 格式错误",
        "severity": "warning",
        "description": "lora_robot_id.txt 中的 ID 必须为 A/B/C/D 中的一个，且不可为 ALL 或为空。",
        "fix_title": "一键重置 Robot ID 为 A",
        "fix_action": "fix_robot_id"
    }
]


class LogDiagnostics:
    """日志拉取、实时监控与智能故障诊断规则引擎"""

    def __init__(self):
        pass

    def fetch_logs(self, log_type: str = "container", tail_lines: int = 150) -> Dict[str, Any]:
        """
        拉取指定来源的日志
        log_type: container (docker logs), sec_run (主控日志), lora_recv (群控日志), dmesg (内核硬件)
        """
        if not ssh_manager.is_connected():
            return {
                "success": False,
                "log_type": log_type,
                "raw_text": "未连接至机器人，请先建立 SSH 连接。",
                "lines_count": 0,
                "diagnostics": []
            }

        cmd_map = {
            "container": f"docker logs --tail {tail_lines} vsis_g1 2>&1",
            "sec_run": f"tail -n {tail_lines} /home/ubuntu/vsis_mimic_deploy/log/sec_run.log 2>&1 || docker exec vsis_g1 tail -n {tail_lines} /home/ubuntu/vsis_mimic_deploy/log/sec_run.log 2>&1",
            "lora_recv": f"tail -n {tail_lines} /home/ubuntu/vsis_mimic_deploy/log/lora_recv.log 2>&1 || docker exec vsis_g1 tail -n {tail_lines} /home/ubuntu/vsis_mimic_deploy/log/lora_recv.log 2>&1",
            "dmesg": "dmesg | grep -iE 'ch341|ttyCH|nvidia|docker' | tail -n 80"
        }

        cmd = cmd_map.get(log_type, cmd_map["container"])
        code, out, err = ssh_manager.execute_command(cmd, sudo=True)
        raw_text = out if code == 0 else (out or err or "暂无日志或文件未生成")
        
        diagnostics = self.analyze_log(raw_text)
        return {
            "success": True,
            "log_type": log_type,
            "raw_text": raw_text,
            "lines_count": len(raw_text.strip().split("\n")),
            "diagnostics": diagnostics
        }

    def analyze_log(self, log_content: str) -> List[Dict[str, Any]]:
        """分析日志文本，匹配已知故障模式并生成人话解释与修复入口"""
        detected = []
        for rule in DIAGNOSTIC_RULES:
            match = re.search(rule["regex"], log_content, re.IGNORECASE)
            if match:
                detected.append({
                    "id": rule["id"],
                    "title": rule["title"],
                    "severity": rule["severity"],
                    "description": rule["description"],
                    "matched_text": match.group(0),
                    "fix_title": rule["fix_title"],
                    "fix_action": rule["fix_action"]
                })
        return detected


log_diagnostics = LogDiagnostics()
