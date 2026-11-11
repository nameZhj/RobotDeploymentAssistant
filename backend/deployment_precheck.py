import time
from typing import Any, Dict
from backend.ssh_client import ssh_manager
from backend.drivers import ch341_manager
from backend.drivers.commands import (
    CH341_MODPROBE_CMD,
    CH341_ALL_SERIAL_DEVS_CMD,
    CH341_LSMOD_CMD,
    CH341_MODINFO_CMD,
    START_LORA_DAEMON_CONTAINER_CMD,
)


class DeploymentPrecheckHelper:
    """环境预检与底层通信硬件自愈"""

    @staticmethod
    def run_environment_precheck() -> Dict[str, Any]:
        if not ssh_manager.is_connected():
            return {"timestamp": time.time(), "all_passed": False, "items": {}, "error": "未连接至机器人"}

        items = {}
        code_arch, arch_out, _ = ssh_manager.execute_command("uname -m")
        items["arch"] = {"passed": "aarch64" in arch_out.lower(), "detail": arch_out.strip()}

        code_dk, dk_out, _ = ssh_manager.execute_command("docker --version")
        items["docker"] = {"passed": code_dk == 0, "detail": dk_out.strip()}

        code_gpu, gpu_out, _ = ssh_manager.execute_command("nvidia-smi -L 2>/dev/null || echo 'NO_GPU'")
        items["gpu"] = {"passed": "NO_GPU" not in gpu_out, "detail": gpu_out.strip()}

        code_dev, ch341_ls, _ = ssh_manager.execute_command(ch341_manager.check_linux_driver_status(ssh_manager)[1])
        has_drv, drv_desc = ch341_manager.check_linux_driver_status(ssh_manager)
        items["ch341"] = {"passed": has_drv, "detail": drv_desc}

        code_ps, ps_out, _ = ssh_manager.execute_command("docker ps --filter name=vsis_g1 --format '{{.Names}}|{{.Status}}'", sudo=True)
        items["container"] = {"passed": code_ps == 0 and "vsis_g1" in ps_out, "detail": ps_out.strip()}

        all_passed = all(it["passed"] for it in items.values() if it != items.get("container"))
        return {"timestamp": time.time(), "all_passed": all_passed, "items": items}

    @staticmethod
    def fix_lora_environment(stream_callback=None) -> bool:
        def _cb(msg, is_err=False):
            if stream_callback:
                stream_callback(msg, is_err)

        if not ssh_manager.is_connected():
            _cb("[ERROR] 未连接至机器人\n", True)
            return False

        ch341_manager.compile_and_install_linux_driver(ssh_manager, _cb)
        ssh_manager.execute_command(CH341_MODPROBE_CMD, sudo=True)
        ch341_manager.setup_udev_and_permissions(ssh_manager, _cb)
        ch341_manager.disable_usb_reset(ssh_manager, _cb)
        ch341_manager.patch_and_recompile_lora_serial(ssh_manager, _cb)
        ch341_manager.deploy_run_bg_script(ssh_manager, _cb)
        return True

    @staticmethod
    def check_and_fix_robot_environment(stream_callback=None) -> Dict[str, Any]:
        def _cb(msg, is_err=False):
            if stream_callback:
                stream_callback(msg, is_err)

        if not ssh_manager.is_connected():
            _cb("[ERROR] 未连接至机器人，跳过自动巡检。\n", True)
            return {"success": False, "msg": "未连接至机器人"}

        ch341_manager.setup_udev_and_permissions(ssh_manager, _cb)
        ch341_manager.deploy_run_bg_script(ssh_manager, _cb)

        code_id, id_out, _ = ssh_manager.execute_command(
            "cat /home/ubuntu/vsis_mimic_deploy/group/lora_robot_id.txt 2>/dev/null", sudo=True
        )
        raw_robot_id = id_out.strip() if code_id == 0 else ""
        from backend.deployment_core import validate_robot_id
        has_valid_id, robot_id, _ = validate_robot_id(raw_robot_id)
        if has_valid_id:
            _cb(f"[SUCCESS] 检测到已配置合法 Robot ID: [{robot_id}]\n", False)
        else:
            _cb(f"[WARN] 未检测到有效 Robot ID: [{raw_robot_id}]\n", True)

        return {"success": True, "has_valid_id": has_valid_id}


deployment_precheck_helper = DeploymentPrecheckHelper()
