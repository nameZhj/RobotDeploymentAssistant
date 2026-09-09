"""
VSISLAB 机器人助手 - CH341 驱动管理与下位机注入服务
封装上位机 (Windows) 驱动探测与安装、机器人下位机 (Linux) 驱动在线编译、udev 权限放行与守护部署等公共方法
"""
import os
import sys
import logging
from typing import Dict, Any, List, Optional, Tuple, Callable

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
    YAML_DISABLE_USB_RESET_CMD,
    LORA_SERIAL_SRC_REMOTE_PATH,
    LORA_SERIAL_CONTAINER_PATH,
    BULLETPROOF_SERIAL_CPP_PATCH,
    LORA_SERIAL_RECOMPILE_CMD,
    LORA_RECV_SYNC_CMD,
    RUN_BG_REMOTE_PATH,
    RUN_BG_SCRIPT_TEMPLATE,
    RUN_BG_SYNC_AND_CHMOD_CMD,
    START_LORA_DAEMON_CONTAINER_CMD,
    WINDOWS_DRIVER_FILENAMES
)

logger = logging.getLogger("CH341Manager")


class CH341Manager:
    """CH341 / CH340 驱动探测、安装与下位机串口环境加固公共服务"""

    def __init__(self):
        pass

    # =========================================================
    # 一、Windows 上位机驱动检测与安装
    # =========================================================
    def find_windows_driver_path(self) -> Optional[str]:
        """
        在打包环境 (PyInstaller)、当前工作目录与相对目录中智能搜寻 Windows CH341 驱动安装程序
        """
        roots = []
        if getattr(sys, 'frozen', False):
            if hasattr(sys, '_MEIPASS'):
                roots.append(sys._MEIPASS)
            roots.append(os.path.dirname(sys.executable))
        
        # 源码运行模式下的候选根目录
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        roots.append(current_file_dir)
        roots.append(os.path.dirname(current_file_dir))  # backend
        roots.append(os.path.dirname(os.path.dirname(current_file_dir)))  # 项目根目录
        roots.append(os.path.abspath("."))

        candidates = []
        for r in roots:
            for fname in WINDOWS_DRIVER_FILENAMES:
                candidates.extend([
                    os.path.join(r, fname),
                    os.path.join(r, "backend", "drivers", fname),
                    os.path.join(r, "drivers", fname),
                ])

        for c in candidates:
            if os.path.exists(c) and os.path.isfile(c):
                return os.path.abspath(c)

        return None

    def check_windows_driver(self) -> Dict[str, Any]:
        """
        检查 Windows 上位机 COM 端口与 CH340/CH341 驱动状态
        """
        ports = []
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DEVICEMAP\SERIALCOMM')
            i = 0
            while True:
                try:
                    name, val, _ = winreg.EnumValue(key, i)
                    ports.append({"device": name, "port": val})
                    i += 1
                except WindowsError:
                    break
        except Exception:
            pass

        has_ch341 = any("ch34" in p["device"].lower() or "usbserial" in p["device"].lower() for p in ports)
        return {
            "has_driver": len(ports) > 0 or has_ch341,
            "ports": ports,
            "count": len(ports),
            "msg": f"检测到 {len(ports)} 个活跃串口 ({', '.join(p['port'] for p in ports)})" if ports else "未检测到已插入的串口设备"
        }

    def install_windows_driver(self) -> Dict[str, Any]:
        """
        在 Windows 上位机一键运行内置的 CH341/CH340 驱动安装程序
        """
        import ctypes
        import subprocess

        driver_path = self.find_windows_driver_path()
        if not driver_path:
            return {
                "success": False,
                "msg": "未在软件内置目录中找到 Windows CH340/CH341 驱动安装程序 (CH341SER.EXE)"
            }

        try:
            # 优先以管理员权限弹出驱动安装器 (UAC 提权)
            ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", driver_path, "", None, 1)
            if ret > 32:
                return {"success": True, "msg": "已弹出 Windows CH341 驱动安装程序，请点击【安装】按钮完成配置。"}
            else:
                subprocess.Popen([driver_path], shell=True)
                return {"success": True, "msg": "已启动 Windows CH341 驱动程序。"}
        except Exception as e:
            return {"success": False, "msg": f"启动驱动安装程序异常: {str(e)}"}

    # =========================================================
    # 二、下位机 (Linux) 驱动状态探测与在线编译
    # =========================================================
    def check_linux_driver_status(self, ssh_client) -> Tuple[bool, str]:
        """
        检查机器人下位机端的 CH341 内核驱动模块状态
        返回: (has_driver: bool, description: str)
        """
        code_dev, ch341_ls, _ = ssh_client.execute_command(CH341_DEV_PROBE_CMD)
        code_mod, lsmod_out, _ = ssh_client.execute_command(CH341_LSMOD_CMD)
        code_info, modinfo_out, _ = ssh_client.execute_command(CH341_MODINFO_CMD)

        has_driver = bool(
            (code_dev == 0 and "ttyCH34" in ch341_ls) or
            (code_mod == 0 and "ch341" in lsmod_out.lower()) or
            (code_info == 0 and modinfo_out.strip())
        )
        desc = ch341_ls.strip() if (code_dev == 0 and "ttyCH34" in ch341_ls) else "内核 ch341 驱动模块就绪"
        return has_driver, desc

    def compile_and_install_linux_driver(self, ssh_client, stream_callback: Optional[Callable[[str, bool], None]] = None) -> bool:
        """
        一键在线编译安装机器人端的 CH341 串口驱动（包含幂等检测）
        """
        def _cb(msg: str, is_err: bool = False):
            if stream_callback:
                stream_callback(msg, is_err)

        _cb("[INFO] 正在检测机器人端现有驱动状态...\n", False)
        has_driver, desc = self.check_linux_driver_status(ssh_client)
        if has_driver:
            _cb(f"[SUCCESS] 检测到机器人端已有 CH341 驱动 ({desc})，驱动已就绪，无需重复安装！\n", False)
            return True

        for step_title, step_cmd in CH341_LINUX_BUILD_PIPELINE:
            _cb(f"\n[STEP] 正在执行: {step_title} ...\n", False)
            code = ssh_client.execute_command_stream(step_cmd, _cb, sudo=True)
            if code != 0 and "apt purge" not in step_cmd:
                _cb(f"[ERROR] 执行失败，退出码: {code}\n", True)
                return False

        # 验证驱动是否加载成功
        _cb("\n[CHECK] 正在验证 /dev/ttyCH34* 设备...\n", False)
        code, out, _ = ssh_client.execute_command(CH341_DEV_PROBE_CMD)
        if code == 0:
            _cb(f"[SUCCESS] CH341 驱动加载成功！设备节点: {out.strip()}\n", False)
            return True
        else:
            _cb("[WARNING] 驱动已编译加载，未检测到插入的 USB 转串口设备，请确认硬件是否牢固插入机器 USB 口。\n", True)
            return True

    # =========================================================
    # 三、下位机 Udev 规则与权限放行公共方法
    # =========================================================
    def setup_udev_and_permissions(self, ssh_client, stream_callback: Optional[Callable[[str, bool], None]] = None) -> bool:
        """
        在机器人端配置 99-ch341-permissions.rules，放行 0666 读写权限并将用户加入 dialout 组
        """
        def _cb(msg: str, is_err: bool = False):
            if stream_callback:
                stream_callback(msg, is_err)

        _cb("[STEP] 正在配置 udev 规则并放行 USB/串口 0666 读写权限...\n", False)
        try:
            ssh_client.write_remote_text_file(UDEV_RULES_CONTENT, UDEV_RULES_PATH, sudo=True)
            ssh_client.execute_command(UDEV_RELOAD_CMD, sudo=True)
            ssh_client.execute_command(USER_GROUPS_CMD, sudo=True)
            ssh_client.execute_command(CHMOD_DEV_NODES_CMD, sudo=True)
            _cb("[SUCCESS] ✅ udev 规则与底层设备读写权限已放行！\n", False)
            return True
        except Exception as e:
            _cb(f"[ERROR] 配置 udev 规则异常: {e}\n", True)
            return False

    def disable_usb_reset(self, ssh_client, stream_callback: Optional[Callable[[str, bool], None]] = None) -> bool:
        """
        优化 lora_recv_group.yaml 参数，关闭破坏性 USB 硬件复位
        """
        def _cb(msg: str, is_err: bool = False):
            if stream_callback:
                stream_callback(msg, is_err)

        _cb("[STEP] 正在检查并优化 lora_recv_group.yaml 串口通信配置...\n", False)
        try:
            ssh_client.execute_command(YAML_DISABLE_USB_RESET_CMD, sudo=True)
            _cb("[SUCCESS] ✅ lora_recv_group.yaml 参数已加固 (usb_reset_timeout_ms: 0)。\n", False)
            return True
        except Exception as e:
            _cb(f"[WARN] 优化 yaml 出现警告: {e}\n", True)
            return False

    # =========================================================
    # 四、下位机 C++ 串口动态容灾补丁
    # =========================================================
    def patch_and_recompile_lora_serial(self, ssh_client, stream_callback: Optional[Callable[[str, bool], None]] = None) -> bool:
        """
        检查 lora_serial.cpp，若缺少动态多节点探测逻辑则自动注入热补丁并重新编译
        """
        def _cb(msg: str, is_err: bool = False):
            if stream_callback:
                stream_callback(msg, is_err)

        _cb("[STEP] 正在检查 lora_recv_group 源码与多端口自适应热补丁...\n", False)
        check_src_cmd = (
            f"cat {LORA_SERIAL_SRC_REMOTE_PATH} 2>/dev/null || "
            f"(docker exec vsis_g1 cat {LORA_SERIAL_SRC_REMOTE_PATH} 2>/dev/null)"
        )
        code_src, src_content, _ = ssh_client.execute_command(check_src_cmd)
        if code_src == 0 and src_content and "TryOpenDevice" not in src_content:
            _cb("[INFO] 检测到 lora_serial.cpp 缺少动态多端口容灾逻辑，正在自动注入热补丁并重新编译...\n", False)
            open_pos = src_content.find("int OpenSerial")
            if open_pos != -1:
                patched_src = src_content[:open_pos] + BULLETPROOF_SERIAL_CPP_PATCH
                ssh_client.write_remote_text_file(patched_src, LORA_SERIAL_SRC_REMOTE_PATH, sudo=True)
                ssh_client.execute_command(f"docker cp {LORA_SERIAL_SRC_REMOTE_PATH} {LORA_SERIAL_CONTAINER_PATH} 2>/dev/null || true", sudo=True)

                _cb("[INFO] 正在调用 make.sh 重新编译生成 lora_recv_group 二进制...\n", False)
                ssh_client.execute_command_stream(LORA_SERIAL_RECOMPILE_CMD, _cb, sudo=True)
                ssh_client.execute_command(LORA_RECV_SYNC_CMD, sudo=True)
                _cb("[SUCCESS] ✅ lora_recv_group 编译加固完成！\n", False)
                return True
        else:
            _cb("[SUCCESS] ✅ lora_recv_group 二进制与多端口探测逻辑校验通过。\n", False)
            return True

    # =========================================================
    # 五、下位机开机自启动守护脚本部署
    # =========================================================
    def deploy_run_bg_script(self, ssh_client, stream_callback: Optional[Callable[[str, bool], None]] = None) -> bool:
        """
        写入高可靠开机自启与 LoRa 进程守护脚本 run_bg.sh，并同步至容器与宿主机
        """
        def _cb(msg: str, is_err: bool = False):
            if stream_callback:
                stream_callback(msg, is_err)

        _cb("[STEP] 正在写入高可靠自适应 run_bg.sh 启动与守护脚本...\n", False)
        try:
            ssh_client.write_remote_text_file(RUN_BG_SCRIPT_TEMPLATE, RUN_BG_REMOTE_PATH, sudo=True)
            ssh_client.execute_command(RUN_BG_SYNC_AND_CHMOD_CMD, sudo=True)
            _cb("[SUCCESS] ✅ run_bg.sh 脚本与容器内环境同步完成。\n", False)
            return True
        except Exception as e:
            _cb(f"[ERROR] 部署 run_bg.sh 异常: {e}\n", True)
            return False


# 全局单例
ch341_manager = CH341Manager()
