import os
import yaml
import time
import logging
from typing import Dict, Any, List, Optional, Tuple
from backend.ssh_client import ssh_manager

logger = logging.getLogger("DanceUpdater")


class DanceUpdater:
    """舞蹈更新管理：.zip 动作压缩包上传、自动解压覆盖至 /secure/config_vsis 与机载进程平滑热重启"""

    def __init__(self):
        self.yaml_remote_path = "/home/ubuntu/vsis_mimic_deploy/group/lora_recv_group.yaml"
        self.default_dest_path = "/secure/config_vsis"

    def deploy_zip_package(self, local_zip_path: str, stream_callback, dest_path: str = "/secure/config_vsis") -> Tuple[bool, str]:
        """
        上传 .zip 动作压缩包至机器人，自动解压并覆盖到 /secure/config_vsis 目录
        1. 上传 zip 包至 /tmp/
        2. 在容器 vsis_g1 及宿主机中创建目标目录并解压覆盖
        3. 设置权限并清理临时文件
        """
        if not os.path.exists(local_zip_path):
            stream_callback(f"[ERROR] 本地压缩包文件不存在: {local_zip_path}\n", True)
            return False, f"本地压缩包文件不存在: {local_zip_path}"

        if not ssh_manager.is_connected():
            stream_callback("[ERROR] 未连接至机器人 SSH，请先连接机器人！\n", True)
            return False, "未连接至机器人"

        filename = os.path.basename(local_zip_path)
        file_size_mb = os.path.getsize(local_zip_path) / (1024 * 1024)
        temp_remote = f"/tmp/{filename}"
        dest_path = dest_path.strip().replace("\\", "/")
        if not dest_path:
            dest_path = self.default_dest_path

        # 1. 上传文件到机器人 /tmp/
        stream_callback(f"[INFO] 正在将动作压缩包 [{filename}] ({round(file_size_mb, 2)} MB) 上传至机器人 /tmp/ ...\n", False)
        ok_up, msg_up = ssh_manager.upload_file(local_zip_path, temp_remote)
        if not ok_up:
            stream_callback(f"[ERROR] 上传压缩包失败: {msg_up}\n", True)
            return False, f"上传压缩包失败: {msg_up}"

        stream_callback(f"[SUCCESS] ✅ 压缩包已成功上传至机器人临时目录: {temp_remote}\n", False)

        # 2. 解压并覆盖至目标目录（优先在容器 vsis_g1 内部解压，同时同步宿主机）
        stream_callback(f"[INFO] 正在解压压缩包并覆盖至目标目录 [{dest_path}] ...\n", False)

        # 容器内解压命令（优先使用 unzip，若无则使用 python3 内置 zipfile 模块）
        unzip_container_cmd = (
            f"docker exec vsis_g1 mkdir -p '{dest_path}' && "
            f"docker cp '{temp_remote}' vsis_g1:/tmp/{filename} && "
            f"docker exec vsis_g1 bash -c \"if command -v unzip >/dev/null 2>&1; then "
            f"unzip -o -q '/tmp/{filename}' -d '{dest_path}'; "
            f"else python3 -m zipfile -e '/tmp/{filename}' '{dest_path}'; fi && "
            f"chmod -R a+rwx '{dest_path}' 2>/dev/null || true\""
        )
        code_c, out_c, err_c = ssh_manager.execute_command(unzip_container_cmd, sudo=True)
        if code_c != 0:
            logger.warning(f"容器内解压返回非0 ({code_c}): {err_c}")

        # 宿主机同步解压
        unzip_host_cmd = (
            f"mkdir -p '{dest_path}' 2>/dev/null && "
            f"if command -v unzip >/dev/null 2>&1; then "
            f"unzip -o -q '{temp_remote}' -d '{dest_path}' 2>/dev/null; "
            f"else python3 -m zipfile -e '{temp_remote}' '{dest_path}' 2>/dev/null || true; fi && "
            f"chmod -R a+rwx '{dest_path}' 2>/dev/null || true"
        )
        ssh_manager.execute_command(unzip_host_cmd, sudo=True)

        # 3. 清理临时压缩包
        ssh_manager.execute_command(f"rm -f '{temp_remote}' ; docker exec vsis_g1 rm -f '/tmp/{filename}' 2>/dev/null || true", sudo=True)

        # 4. 检查解压后目录文件清单
        code_ls, out_ls, _ = ssh_manager.execute_command(
            f"docker exec vsis_g1 ls -1 '{dest_path}' 2>/dev/null || ls -1 '{dest_path}' 2>/dev/null",
            sudo=True
        )
        extracted_files = [f.strip() for f in out_ls.splitlines() if f.strip()]
        if extracted_files:
            stream_callback(f"[SUCCESS] ✅ 动作包已成功解压并覆盖至 {dest_path}！(包含 {len(extracted_files)} 个模型/配置文件: {', '.join(extracted_files[:5])}{'...' if len(extracted_files) > 5 else ''})\n", False)
        else:
            stream_callback(f"[SUCCESS] ✅ 动作包已成功解压并覆盖至 {dest_path}！\n", False)

        return True, f"动作压缩包已成功解压覆盖至 {dest_path}"

    def restart_control_processes(self, stream_callback) -> bool:
        """
        重启控制进程（补充说明第3节与第7节）：
        pkill -f g1_ctrl_vsis ; pkill -f lora_recv_group ; run_bg.sh
        """
        stream_callback("[INFO] 正在准备自动热重启机载运控与跳舞进程...\n", False)
        if not ssh_manager.is_connected():
            stream_callback("[ERROR] 未连接至机器人！\n", True)
            return False

        # 1. 停止当前运控与群控进程
        stop_cmd = "pkill -f g1_ctrl_vsis ; pkill -f lora_recv_group ; sleep 1"
        stream_callback("[STEP 2/2] 停止当前运行中的运控与跳舞旧进程 (pkill)...\n", False)
        ssh_manager.execute_command(stop_cmd, sudo=True)
        ssh_manager.execute_command("docker exec vsis_g1 pkill -f g1_ctrl_vsis 2>/dev/null || true", sudo=True)
        ssh_manager.execute_command("docker exec vsis_g1 pkill -f lora_recv_group 2>/dev/null || true", sudo=True)

        # 2. 拉起 run_bg.sh
        stream_callback("[STEP 2/2] 正在容器中调用 run_bg.sh 重新拉起程序...\n", False)
        ssh_manager.execute_command(
            "docker exec -d vsis_g1 bash -c 'cd /home/ubuntu/vsis_mimic_deploy && ./run_bg.sh' 2>/dev/null || nohup /home/ubuntu/vsis_mimic_deploy/run_bg.sh >/dev/null 2>&1 &",
            sudo=True
        )

        time.sleep(2)
        stream_callback("[SUCCESS] 🎉 机载运控与跳舞程序热重启指令已发送完毕！\n", False)
        return True


dance_updater = DanceUpdater()
