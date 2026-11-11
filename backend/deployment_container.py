import time
from typing import Any, Dict, Tuple
from backend.ssh_client import ssh_manager
from backend.drivers import ch341_manager
from backend.drivers.commands import RUN_BG_SYNC_AND_CHMOD_CMD


class DeploymentContainerHelper:
    """Docker 容器生命周期管理与固化自启动"""

    @staticmethod
    def start_container(image_tag: str = "rl_cu118:2.0", stream_callback=None) -> Tuple[bool, str]:
        def _cb(msg, is_err=False):
            if stream_callback:
                stream_callback(msg, is_err)

        if not ssh_manager.is_connected():
            return False, "未连接至机器人"

        run_cmd = (
            "docker run -d --restart=on-failure "
            "--name vsis_g1 "
            "--cap-add=SYS_PTRACE "
            "--gpus all "
            "--shm-size=1024m "
            "--privileged "
            "--cap-add=NET_ADMIN "
            "--network=host "
            "--device /dev/:/dev/ "
            "-v /tmp/.X11-unix:/tmp/.X11-unix:rw "
            "-v /tmp:/tmp/ "
            "-v /run/udev/:/run/udev/ "
            f"{image_tag} 2>/dev/null || docker start vsis_g1"
        )
        ssh_manager.execute_command(run_cmd, sudo=True)
        time.sleep(2.0)
        code_ps, ps_out, _ = ssh_manager.execute_command("docker ps --filter name=vsis_g1 --format '{{.Names}}'", sudo=True)
        if code_ps == 0 and "vsis_g1" in ps_out:
            ch341_manager.deploy_run_bg_script(ssh_manager, stream_callback)
            return True, "容器启动成功"
        return False, "容器未能正常启动"

    @staticmethod
    def compile_robot_code(stream_callback=None, force: bool = False) -> Tuple[bool, str]:
        cb = stream_callback or (lambda m, e: None)
        cb("[INFO] 正在容器内执行自动编译 (make.sh) ...\n", False)
        cmd = "docker exec vsis_g1 bash -c 'cd /home/ubuntu/vsis_mimic_deploy && rm -rf build && mkdir -p build && cd build && cmake .. && make -j$(nproc)'"
        code = ssh_manager.execute_command_stream(cmd, cb, sudo=True)
        return code == 0, "编译成功" if code == 0 else "编译失败"

    @staticmethod
    def load_docker_image(remote_tar_path: str, stream_callback=None) -> Tuple[bool, str]:
        def _cb(msg, is_err=False):
            if stream_callback:
                stream_callback(msg, is_err)

        if not ssh_manager.is_connected():
            _cb("[ERROR] 未连接至机器人！请先连接机器人。\n", True)
            return False, "未连接至机器人"

        code_chk, out_chk, _ = ssh_manager.execute_command(f"ls -lh '{remote_tar_path}' 2>/dev/null", sudo=True)
        if code_chk != 0 or not out_chk.strip():
            _cb(f"[ERROR] 远端镜像包不存在: {remote_tar_path}\n", True)
            return False, f"远端文件不存在: {remote_tar_path}"

        _cb(f"[INFO] 确认远端镜像文件: {out_chk.strip()}\n", False)
        cmd = f"docker load -i '{remote_tar_path}'"
        code = ssh_manager.execute_command_stream(cmd, _cb, sudo=True, timeout=1200.0)
        if code == 0:
            from backend.deployment_core import deployment_core
            ssh_manager.execute_command(
                "docker images --format 'table {{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}' | head -n 5",
                sudo=True
            )
            _cb("\n[SUCCESS] Docker 镜像成功导入完成！\n", False)

            latest_image = "rl_cu118:2.0"
            code_latest, latest_out, _ = ssh_manager.execute_command(
                "docker images --format '{{.Repository}}:{{.Tag}}' | head -n 1", sudo=True
            )
            if code_latest == 0 and latest_out.strip() and "<none>" not in latest_out:
                latest_image = latest_out.strip()

            deployment_core.start_container(latest_image, stream_callback)
            deployment_core.compile_robot_code(stream_callback, force=True)
            deployment_core.check_and_fix_robot_environment(stream_callback)
            return True, "镜像导入成功"
        else:
            _cb(f"[ERROR] 镜像导入失败，退出码: {code}\n", True)
            return False, f"镜像导入失败 (code {code})"


deployment_container_helper = DeploymentContainerHelper()
