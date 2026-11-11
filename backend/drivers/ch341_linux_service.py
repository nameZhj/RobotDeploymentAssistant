from typing import Callable, Optional, Tuple
from backend.drivers.commands import (
    CH341_DEV_PROBE_CMD,
    CH341_ALL_SERIAL_DEVS_CMD,
    CH341_LSMOD_CMD,
    CH341_MODINFO_CMD,
    CH341_MODPROBE_CMD,
    CH341_LINUX_BUILD_PIPELINE,
    UDEV_RULES_PATH,
    UDEV_RULES_CONTENT,
    UDEV_RELOAD_CMD,
    USER_GROUPS_CMD,
    CHMOD_DEV_NODES_CMD,
    DEFAULT_LORA_RECV_GROUP_YAML,
    YAML_DISABLE_USB_RESET_CMD,
    LORA_SERIAL_SRC_REMOTE_PATH,
    LORA_SERIAL_CONTAINER_PATH,
    BULLETPROOF_SERIAL_CPP_PATCH,
    LORA_SERIAL_RECOMPILE_CMD,
    LORA_RECV_SYNC_CMD,
    RUN_BG_REMOTE_PATH,
    RUN_BG_SYNC_AND_CHMOD_CMD,
    CUSTOM_STARTUP_REMOTE_PATH,
    CUSTOM_STARTUP_SCRIPT_TEMPLATE,
)


class CH341LinuxService:
    """Linux 机器人端驱动编译、udev 规则与环境配置"""

    def check_linux_driver_status(self, ssh_client) -> Tuple[bool, str]:
        code_dev, ch341_ls, _ = ssh_client.execute_command(CH341_DEV_PROBE_CMD)
        code_lsmod, lsmod_out, _ = ssh_client.execute_command(CH341_LSMOD_CMD)
        code_info, modinfo_out, _ = ssh_client.execute_command(CH341_MODINFO_CMD)
        has_driver = (code_dev == 0 and "ttyCH34" in ch341_ls) or (code_lsmod == 0 and "ch341" in lsmod_out) or (code_info == 0 and bool(modinfo_out.strip()))
        desc = ch341_ls.strip() if (code_dev == 0 and "ttyCH34" in ch341_ls) else "内核 ch341 驱动模块就绪"
        return has_driver, desc

    def compile_and_install_linux_driver(self, ssh_client, stream_callback: Optional[Callable[[str, bool], None]] = None) -> bool:
        def _cb(msg: str, is_err: bool = False):
            if stream_callback:
                stream_callback(msg, is_err)

        has_driver, desc = self.check_linux_driver_status(ssh_client)
        if has_driver:
            _cb(f"[SUCCESS] 检测到机器人端已有 CH341 驱动 ({desc})，无需重复安装！\n", False)
            return True

        for step_title, step_cmd in CH341_LINUX_BUILD_PIPELINE:
            _cb(f"\n[STEP] 正在执行: {step_title} ...\n", False)
            code = ssh_client.execute_command_stream(step_cmd, _cb, sudo=True)
            if code != 0 and "apt purge" not in step_cmd:
                _cb(f"[ERROR] 执行失败，退出码: {code}\n", True)
                return False

        code, out, _ = ssh_client.execute_command(CH341_DEV_PROBE_CMD)
        return True

    def setup_udev_and_permissions(self, ssh_client, stream_callback: Optional[Callable[[str, bool], None]] = None) -> bool:
        try:
            ssh_client.write_remote_text_file(UDEV_RULES_CONTENT, UDEV_RULES_PATH, sudo=True)
            ssh_client.execute_command(UDEV_RELOAD_CMD, sudo=True)
            ssh_client.execute_command(USER_GROUPS_CMD, sudo=True)
            ssh_client.execute_command(CHMOD_DEV_NODES_CMD, sudo=True)
            return True
        except Exception:
            return False

    def ensure_lora_recv_yaml(self, ssh_client, stream_callback: Optional[Callable[[str, bool], None]] = None) -> bool:
        yaml_host_path = "/home/ubuntu/vsis_mimic_deploy/group/lora_recv_group.yaml"
        yaml_cont_path = "vsis_g1:/home/ubuntu/vsis_mimic_deploy/group/lora_recv_group.yaml"
        try:
            ssh_client.execute_command("mkdir -p /home/ubuntu/vsis_mimic_deploy/group", sudo=True)
            ssh_client.execute_command("docker exec vsis_g1 mkdir -p /home/ubuntu/vsis_mimic_deploy/group 2>/dev/null || true", sudo=True)
            code_host, out_sz, _ = ssh_client.execute_command(
                f"[ -s {yaml_host_path} ] && [ $(wc -c < {yaml_host_path} 2>/dev/null || echo 0) -gt 100 ] && echo 'OK' || echo 'INVALID'",
                sudo=True
            )
            host_valid = (code_host == 0 and "OK" in out_sz)
            code_cont, out_csz, _ = ssh_client.execute_command(
                f"docker exec vsis_g1 bash -c '[ -s {yaml_host_path} ] && [ $(wc -c < {yaml_host_path} 2>/dev/null || echo 0) -gt 100 ] && echo \"OK\" || echo \"INVALID\"' 2>/dev/null || echo 'INVALID'",
                sudo=True
            )
            cont_valid = (code_cont == 0 and "OK" in out_csz)
            if not host_valid and cont_valid:
                ssh_client.execute_command(f"docker cp {yaml_cont_path} {yaml_host_path} 2>/dev/null || true", sudo=True)
                host_valid = True
            if not host_valid:
                ssh_client.write_remote_text_file(DEFAULT_LORA_RECV_GROUP_YAML, yaml_host_path, sudo=True)
            ssh_client.execute_command(f"docker cp {yaml_host_path} {yaml_cont_path} 2>/dev/null || true", sudo=True)
            ssh_client.execute_command(f"chmod 666 {yaml_host_path} 2>/dev/null || true", sudo=True)
            ssh_client.execute_command(f"docker exec vsis_g1 chmod 666 {yaml_host_path} 2>/dev/null || true", sudo=True)
            ssh_client.execute_command(YAML_DISABLE_USB_RESET_CMD, sudo=True)
            return True
        except Exception:
            return False

    def disable_usb_reset(self, ssh_client, stream_callback: Optional[Callable[[str, bool], None]] = None) -> bool:
        try:
            ssh_client.execute_command(YAML_DISABLE_USB_RESET_CMD, sudo=True)
            return True
        except Exception:
            return False

    def patch_and_recompile_lora_serial(self, ssh_client, stream_callback: Optional[Callable[[str, bool], None]] = None) -> bool:
        try:
            code_cat, cpp_content, _ = ssh_client.execute_command(f"cat {LORA_SERIAL_SRC_REMOTE_PATH} 2>/dev/null")
            if code_cat != 0 or not cpp_content:
                ssh_client.execute_command(f"docker cp {LORA_SERIAL_CONTAINER_PATH} {LORA_SERIAL_SRC_REMOTE_PATH} 2>/dev/null || true")
                code_cat, cpp_content, _ = ssh_client.execute_command(f"cat {LORA_SERIAL_SRC_REMOTE_PATH} 2>/dev/null")
            if "TryOpenDevice" not in cpp_content:
                patched_content = cpp_content + "\n" + BULLETPROOF_SERIAL_CPP_PATCH
                ssh_client.write_remote_text_file(patched_content, LORA_SERIAL_SRC_REMOTE_PATH, sudo=True)
                ssh_client.execute_command(f"docker cp {LORA_SERIAL_SRC_REMOTE_PATH} {LORA_SERIAL_CONTAINER_PATH} 2>/dev/null || true")
            ssh_client.execute_command_stream(LORA_SERIAL_RECOMPILE_CMD, stream_callback, sudo=True)
            ssh_client.execute_command(LORA_RECV_SYNC_CMD, sudo=True)
            return True
        except Exception:
            return False

    def deploy_run_bg_script(self, ssh_client, stream_callback: Optional[Callable[[str, bool], None]] = None) -> bool:
        try:
            self.ensure_lora_recv_yaml(ssh_client, stream_callback)
            ssh_client.write_remote_text_file(CUSTOM_STARTUP_SCRIPT_TEMPLATE, CUSTOM_STARTUP_REMOTE_PATH, sudo=True)
            ssh_client.execute_command(RUN_BG_SYNC_AND_CHMOD_CMD, sudo=True)
            return True
        except Exception:
            return False

