import time
import re
from typing import Any, Dict, Tuple
from backend.ssh_client import ssh_manager
from backend.drivers.commands import (
    CUSTOM_STARTUP_SCRIPT_TEMPLATE,
    CUSTOM_STARTUP_REMOTE_PATH,
    RUN_BG_SYNC_AND_CHMOD_CMD
)


class DeploymentProcessHelper:
    """机载运控与 LoRa 进程拉起、日志流监听与机器码读取"""

    @staticmethod
    def read_machine_id() -> Dict[str, Any]:
        if not ssh_manager.is_connected():
            return {"success": False, "machine_id": "", "msg": "未连接至机器人"}

        code, out, _ = ssh_manager.execute_command(
            "docker exec vsis_g1 /home/ubuntu/vsis_mimic_deploy/g1_ctrl_vsis --print-machine-id 2>/dev/null "
            "|| /home/ubuntu/vsis_mimic_deploy/g1_ctrl_vsis --print-machine-id 2>/dev/null",
            sudo=True
        )
        if code == 0 and out.strip():
            mid = out.strip().split()[-1]
            return {"success": True, "machine_id": mid, "msg": "获取机器码成功"}

        code_cat, out_cat, _ = ssh_manager.execute_command("cat /etc/machine-id 2>/dev/null")
        if code_cat == 0 and out_cat.strip():
            return {"success": True, "machine_id": out_cat.strip(), "msg": "读取系统机器码成功"}

        return {"success": False, "machine_id": "", "msg": "未能获取有效机器码"}

    @staticmethod
    def configure_autostart_and_robot_id(robot_id: str = "A") -> Dict[str, Any]:
        from backend.deployment_core import validate_robot_id
        is_valid, clean_id, err_msg = validate_robot_id(robot_id)
        if not is_valid:
            return {"success": False, "msg": err_msg}

        ssh_manager.write_remote_text_file(CUSTOM_STARTUP_SCRIPT_TEMPLATE, CUSTOM_STARTUP_REMOTE_PATH, sudo=True)
        ssh_manager.execute_command("chmod +x /docker_config/custom_startup.sh", sudo=True)
        ssh_manager.execute_command(RUN_BG_SYNC_AND_CHMOD_CMD, sudo=True)

        id_path = "/home/ubuntu/vsis_mimic_deploy/group/lora_robot_id.txt"
        ssh_manager.write_remote_text_file(f"{clean_id}\n", id_path, sudo=True)
        ssh_manager.execute_command(f"docker exec vsis_g1 bash -c \"mkdir -p /home/ubuntu/vsis_mimic_deploy/group && echo '{clean_id}' > {id_path}\" || true", sudo=True)

        return {"success": True, "robot_id": clean_id, "msg": f"开机自启已配置，Robot ID 设为 [{clean_id}]"}

    @staticmethod
    def get_robot_process_status() -> Dict[str, Any]:
        if not ssh_manager.is_connected():
            return {"connected": False, "g1_ctrl_running": False, "lora_recv_running": False, "all_running": False}

        code_c, out_c, _ = ssh_manager.execute_command("pgrep -f g1_ctrl_vsis", sudo=True)
        code_l, out_l, _ = ssh_manager.execute_command("pgrep -f lora_recv_group", sudo=True)
        g1_ok = (code_c == 0 and bool(out_c.strip()))
        lora_ok = (code_l == 0 and bool(out_l.strip()))

        return {
            "connected": True,
            "g1_ctrl_running": g1_ok,
            "lora_recv_running": lora_ok,
            "all_running": g1_ok and lora_ok,
        }

    @staticmethod
    def stop_robot_processes() -> Tuple[bool, str]:
        if not ssh_manager.is_connected():
            return False, "未连接至机器人"
        ssh_manager.execute_command("pkill -9 -f g1_ctrl_vsis ; pkill -9 -f lora_recv_group", sudo=True)
        return True, "机载进程已停止"


deployment_process_helper = DeploymentProcessHelper()
