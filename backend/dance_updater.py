import os
import yaml
import time
import logging
from typing import Dict, Any, List, Optional, Tuple
from backend.ssh_client import ssh_manager
from backend.license_service import license_service

logger = logging.getLogger("DanceUpdater")


class DanceUpdater:
    """舞蹈更新管理：.vsis 动作包导入、YAML 舞蹈映射更新、进程平滑热重启与授权验证"""

    def __init__(self):
        self.yaml_remote_path = "/home/ubuntu/vsis_mimic_deploy/group/lora_recv_group.yaml"

    def parse_remote_yaml(self) -> Dict[str, Any]:
        """读取远端的 lora_recv_group.yaml"""
        if not ssh_manager.is_connected():
            return {}

        ok, content = ssh_manager.read_remote_text_file(self.yaml_remote_path)
        if not ok or not content.strip():
            # 尝试在容器内读取
            code, out, _ = ssh_manager.execute_command(f"docker exec vsis_g1 cat {self.yaml_remote_path} 2>/dev/null", sudo=True)
            if code == 0 and out.strip():
                content = out
            else:
                return {}

        try:
            return yaml.safe_load(content) or {}
        except Exception as e:
            logger.error(f"解析 YAML 失败: {e}")
            return {}

    def update_dance_map(self, dance_alias: str, button_group: str = "R1", button_action: str = "SELECT") -> Tuple[bool, str]:
        """
        在 lora_recv_group.yaml 的 dance_map 中添加或更新舞蹈映射
        例如: G2_NEW_DANCE: [R1, SELECT]
        """
        dance_alias = dance_alias.strip().upper()
        current_data = self.parse_remote_yaml()

        if "dance_map" not in current_data:
            current_data["dance_map"] = {}

        current_data["dance_map"][dance_alias] = [button_group.upper(), button_action.upper()]
        
        # 序列化为 YAML
        new_yaml_str = yaml.dump(current_data, allow_unicode=True, default_flow_style=False, sort_keys=False)
        
        # 写入远程文件
        ok, msg = ssh_manager.write_remote_text_file(new_yaml_str, self.yaml_remote_path, sudo=True)
        if not ok:
            return False, f"写入 YAML 失败: {msg}"

        # 同步写入容器内部
        ssh_manager.execute_command(
            f"docker exec vsis_g1 bash -c \"cat << 'EOF' > {self.yaml_remote_path}\n{new_yaml_str}\nEOF\" || true",
            sudo=True
        )

        return True, f"舞蹈映射已成功更新: {dance_alias} -> [{button_group}, {button_action}]"

    def deploy_vsis_file(self, local_vsis_path: str, remote_dest_path: str = "/secure/config_vsis/mimic_exp2") -> Tuple[bool, str]:
        """上传 .vsis 动作权重文件并替换旧配置"""
        if not os.path.exists(local_vsis_path):
            return False, f"本地 .vsis 文件不存在: {local_vsis_path}"

        temp_remote = f"/tmp/{os.path.basename(local_vsis_path)}"
        ok_up, msg_up = ssh_manager.upload_file(local_vsis_path, temp_remote)
        if not ok_up:
            return False, f"上传 .vsis 动作文件失败: {msg_up}"

        # 拷贝到宿主机或容器对应路径
        dest_dir = os.path.dirname(remote_dest_path).replace("\\", "/")
        ssh_manager.execute_command(f"mkdir -p {dest_dir} && cp {temp_remote} {remote_dest_path} && rm -f {temp_remote}", sudo=True)

        # 同时也拷贝进容器内部
        ssh_manager.execute_command(
            f"docker exec vsis_g1 mkdir -p {dest_dir} && docker cp {remote_dest_path} vsis_g1:{remote_dest_path} || true",
            sudo=True
        )

        return True, f"动作文件已部署至 {remote_dest_path}"

    def restart_control_processes(self, stream_callback) -> bool:
        """
        重启控制进程（补充说明第3节与第7节）：
        pkill -f g1_ctrl_vsis ; pkill -f lora_recv_group ; run_bg.sh
        """
        stream_callback("[INFO] 准备重启运控与群控进程...\n", False)
        if not ssh_manager.is_connected():
            stream_callback("[ERROR] 未连接至机器人！\n", True)
            return False

        # 1. 停止当前运控与群控进程
        stop_cmd = "pkill -f g1_ctrl_vsis ; pkill -f lora_recv_group ; sleep 1"
        stream_callback("[STEP 1/2] 停止当前旧进程...\n", False)
        ssh_manager.execute_command(stop_cmd, sudo=True)
        # 在容器中也执行 pkill
        ssh_manager.execute_command("docker exec vsis_g1 pkill -f g1_ctrl_vsis || true", sudo=True)
        ssh_manager.execute_command("docker exec vsis_g1 pkill -f lora_recv_group || true", sudo=True)

        # 2. 拉起 run_bg.sh
        stream_callback("[STEP 2/2] 启动 run_bg.sh 重新拉起程序...\n", False)
        restart_cmd = "nohup /home/ubuntu/vsis_mimic_deploy/run_bg.sh >/dev/null 2>&1 &"
        ssh_manager.execute_command(restart_cmd, sudo=True)
        ssh_manager.execute_command(f"docker exec -d vsis_g1 /home/ubuntu/vsis_mimic_deploy/run_bg.sh || true", sudo=True)

        time.sleep(2)
        stream_callback("[SUCCESS] 控制进程热重启指令已发送完毕！\n", False)
        return True


dance_updater = DanceUpdater()
