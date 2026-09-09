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

    def fetch_logs(self, log_type: str = "container", container_name: str = "", tail_lines: int = 200) -> Dict[str, Any]:
        """
        拉取指定来源的日志
        log_type: container (已启动容器日志), lora (LoRa群控日志), g1_ctrl (运控主程序日志), dmesg (内核硬件)
        """
        if not ssh_manager.is_connected():
            return {
                "success": False,
                "log_type": log_type,
                "target_container": "",
                "available_containers": [],
                "raw_text": "【未连接至机器人】请先点击顶部的【连接机器人】(192.168.123.164)。",
                "lines_count": 0,
                "diagnostics": []
            }

        # 1. 动态探测机器人上正在运行及所有 Docker 容器
        code_ps, ps_out, _ = ssh_manager.execute_command(
            "docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}'", sudo=True
        )
        available_containers = []
        running_names = []
        all_names = []

        if code_ps == 0 and ps_out.strip():
            for line in ps_out.strip().split("\n"):
                if line.strip():
                    parts = line.split("\t")
                    if len(parts) >= 3:
                        c_name_item, img_item, status_item = parts[0], parts[1], parts[2]
                        is_up = status_item.lower().startswith("up")
                        all_names.append(c_name_item)
                        if is_up:
                            running_names.append(c_name_item)
                        available_containers.append({
                            "name": c_name_item,
                            "image": img_item,
                            "is_running": is_up,
                            "status": "运行中" if is_up else "已停止"
                        })

        # 确定选定容器名称
        c_name = container_name.strip() if container_name else ""
        if not c_name or c_name not in all_names:
            if "vsis_g1" in running_names:
                c_name = "vsis_g1"
            elif running_names:
                c_name = running_names[0]
            elif "vsis_g1" in all_names:
                c_name = "vsis_g1"
            elif all_names:
                c_name = all_names[0]
            else:
                c_name = "vsis_g1"

        # 2. 根据类型组装执行指令 (优先直接从运行中的 Docker 容器内提取完整日志)
        if log_type == "dmesg":
            cmd = f"dmesg -T 2>/dev/null | grep -iE 'ch341|ttyCH|nvidia|docker|usb' | tail -n {tail_lines} || dmesg | tail -n {tail_lines}"

        elif log_type in ("g1_ctrl", "sec_run"):
            # 主控运控日志：优先直接从 vsis_g1 容器内读取完整日志与实时进程
            cmd = (
                "echo '=========================================' && "
                "echo '🤖 [1. 运控进程运行状态 (g1_ctrl_vsis / sec_run)]' && "
                "echo '=========================================' && "
                "docker exec {c_name} ps aux 2>/dev/null | grep -E 'g1_ctrl_vsis|sec_run' | grep -v grep "
                "|| ps aux | grep -E 'g1_ctrl_vsis|sec_run' | grep -v grep "
                "|| echo '[OFFLINE] 容器与宿主机均未检测到 g1_ctrl_vsis 运行进程' && "
                "echo '' && "
                "echo '=========================================' && "
                "echo '📋 [2. 运控核心实时日志 (最新 {lines} 行)]' && "
                "echo '=========================================' && "
                "docker exec {c_name} tail -n {lines} /home/ubuntu/vsis_mimic_deploy/log/sec_run.log 2>/dev/null "
                "|| ( [ -f /home/ubuntu/vsis_mimic_deploy/log/sec_run.log ] && tail -n {lines} /home/ubuntu/vsis_mimic_deploy/log/sec_run.log ) "
                "|| echo '[提示] 暂未生成独立 sec_run.log 日志文件'"
            ).format(lines=tail_lines, c_name=c_name)

        elif log_type in ("lora_recv", "lora"):
            # LoRa 群控通信与接收日志
            cmd = (
                "echo '=========================================' && "
                "echo '📡 [1. 硬件 USB 串口设备检测 (/dev/ttyCH341* /dev/ttyUSB*)]' && "
                "echo '=========================================' && "
                "docker exec {c_name} ls -l /dev/ttyCH341* /dev/ttyUSB* 2>/dev/null "
                "|| ls -l /dev/ttyCH341* /dev/ttyUSB* 2>/dev/null "
                "|| echo '[WARN] 未检测到 /dev/ttyCH341USB0 串口（请确认 USB 模块已插入）' && "
                "echo '' && "
                "echo '=========================================' && "
                "echo '🆔 [2. 本机分配的 Robot ID (群控寻址唯一标识)]' && "
                "echo '=========================================' && "
                "docker exec {c_name} cat /home/ubuntu/vsis_mimic_deploy/group/lora_robot_id.txt 2>/dev/null "
                "|| cat /home/ubuntu/vsis_mimic_deploy/group/lora_robot_id.txt 2>/dev/null "
                "|| echo '[提示] 尚未分配 Robot ID' && "
                "echo '' && "
                "echo '=========================================' && "
                "echo '⚡ [3. LoRa 群控接收进程状态 (lora_recv_group)]' && "
                "echo '=========================================' && "
                "docker exec {c_name} ps aux 2>/dev/null | grep -E 'lora_recv_group|lora_send' | grep -v grep "
                "|| ps aux | grep -E 'lora_recv_group|lora_send' | grep -v grep "
                "|| echo '[OFFLINE] 容器与宿主机均未运行 lora_recv_group 接收进程' && "
                "echo '' && "
                "echo '=========================================' && "
                "echo '📋 [4. LoRa 无线通信接收实时日志 (最新 {lines} 行)]' && "
                "echo '=========================================' && "
                "docker exec {c_name} tail -n {lines} /home/ubuntu/vsis_mimic_deploy/log/lora_recv.log 2>/dev/null "
                "|| ( [ -f /home/ubuntu/vsis_mimic_deploy/log/lora_recv.log ] && tail -n {lines} /home/ubuntu/vsis_mimic_deploy/log/lora_recv.log ) "
                "|| docker logs --timestamps --tail {lines} {c_name} 2>&1 | grep -iE 'lora|recv|robot_id|radio|serial|rx' "
                "|| echo '[INFO] 暂未生成独立 lora_recv.log 日志文件。'"
            ).format(lines=tail_lines, c_name=c_name)

        else:
            # 默认直接输出 Docker 容器日志 (针对选定的容器，附带时间戳)
            cmd = f"docker logs --timestamps --tail {tail_lines} {c_name} 2>&1"

        code, out, err = ssh_manager.execute_command(cmd, sudo=True)
        raw_text = out if (code == 0 or out.strip()) else (out or err or "【暂无日志输出】请确保机器人已连接且对应容器已启动。")

        diagnostics = self.analyze_log(raw_text)
        return {
            "success": True,
            "log_type": log_type,
            "target_container": c_name,
            "available_containers": available_containers,
            "raw_text": raw_text.strip(),
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
