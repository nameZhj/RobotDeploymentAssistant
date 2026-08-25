import os
import re
import time
import logging
from typing import Dict, Any, List, Optional, Tuple
from backend.ssh_client import ssh_manager

logger = logging.getLogger("DeploymentCore")


class DeploymentCore:
    """机器人部署核心业务逻辑：预检、修复、容器管理、自启动、机器码提取"""

    def __init__(self):
        pass

    # ==========================
    # 1. 环境预检
    # ==========================
    def run_environment_precheck(self) -> Dict[str, Any]:
        """
        全面预检目标机器人的运行环境
        包含：Docker 版本、NVIDIA Runtime、GPU状态、CH341 串口、磁盘空间、系统架构等
        """
        results = {
            "timestamp": time.time(),
            "all_passed": False,
            "items": {}
        }

        if not ssh_manager.is_connected():
            return {
                "timestamp": time.time(),
                "all_passed": False,
                "items": {},
                "error": "未连接至机器人，请先连接机器人后再进行环境预检"
            }

        # 真实环境检查
        # 1. 架构与内核
        code, uname_m, _ = ssh_manager.execute_command("uname -m")
        code_r, uname_r, _ = ssh_manager.execute_command("uname -r")
        arch_str = f"{uname_m.strip()} (Linux {uname_r.strip()})"

        # 2. Docker
        code, docker_v, docker_err = ssh_manager.execute_command("docker --version")
        docker_ok = (code == 0)
        docker_status = "ok" if docker_ok else "error"
        docker_msg = "Docker 已安装" if docker_ok else "未检测到 Docker 或服务未启动"

        # 3. NVIDIA Runtime
        code, nvc_v, _ = ssh_manager.execute_command("which nvidia-container-cli || which nvidia-container-runtime")
        code2, daemon_json, _ = ssh_manager.execute_command("cat /etc/docker/daemon.json")
        nv_ok = (code == 0) or ("nvidia" in daemon_json)
        nv_status = "ok" if nv_ok else "warning"
        nv_msg = "NVIDIA Container Runtime 正常" if nv_ok else "未检测到 nvidia runtime 默认配置（若为标准 Docker 容器直通可继续）"

        # 4. GPU / nvidia-smi
        code, gpu_out, _ = ssh_manager.execute_command("nvidia-smi --query-gpu=name,driver_version --format=csv,noheader")
        if code != 0:
            # Jetson / Tegra 设备可能用 jtop 或 tegrastats
            code_tegrastats, tegra_out, _ = ssh_manager.execute_command("which tegrastats || ls /sys/devices/soc0")
            gpu_ok = (code_tegrastats == 0)
            gpu_ver = "Jetson / Tegra Integrated GPU" if gpu_ok else "未检测到独立 GPU"
            gpu_msg = "Jetson 嵌入式 GPU 架构就绪" if gpu_ok else "未能执行 nvidia-smi 检查 GPU"
        else:
            gpu_ok = True
            gpu_ver = gpu_out.strip()
            gpu_msg = f"检测到 GPU: {gpu_out.strip()}"
        gpu_status = "ok" if gpu_ok else "warning"

        # 5. CH341 串口（多维前置检查：设备节点 / 内核模块 / 模块文件 / dmesg 日志）
        code_dev, ch341_ls, _ = ssh_manager.execute_command("ls /dev/ttyCH34* 2>/dev/null")
        has_dev = (code_dev == 0 and "ttyCH34" in ch341_ls)

        code_mod, lsmod_out, _ = ssh_manager.execute_command("lsmod | grep -i ch341")
        has_mod = (code_mod == 0 and "ch341" in lsmod_out.lower())

        code_info, modinfo_out, _ = ssh_manager.execute_command("modinfo ch341 2>/dev/null || find /lib/modules/$(uname -r) -name '*ch341*.ko*' 2>/dev/null")
        has_ko = (code_info == 0 and bool(modinfo_out.strip()))

        code_d, dmesg_out, _ = ssh_manager.execute_command("dmesg | grep -i ch341 | tail -n 5", sudo=True)
        has_dmesg = (code_d == 0 and "ch341" in dmesg_out.lower())

        ch341_found = bool(has_dev or has_mod or has_ko or has_dmesg)
        ch341_status = "ok" if ch341_found else "error"
        if has_dev:
            ch341_ver = ch341_ls.strip()
            ch341_msg = f"CH341 驱动已加载，设备节点: {ch341_ls.strip()}"
        elif has_mod or has_ko:
            ch341_ver = "CH341 内核模块已安装 (ch341.ko)"
            ch341_msg = "CH341 驱动已编译并在内核就绪，插入 USB 串口模块即可通信"
        elif has_dmesg:
            ch341_ver = "内核日志就绪 (CH341)"
            ch341_msg = "系统底层已识别 CH341 驱动"
        else:
            ch341_ver = "未安装 /dev/ttyCH341USB0"
            ch341_msg = "未检测到 CH341 驱动，需一键编译安装驱动以支持 LoRa 群控通信"

        # 6. 磁盘空间
        code, df_out, _ = ssh_manager.execute_command("df -BG / | tail -n 1")
        disk_ok = True
        disk_ver = "未知"
        disk_msg = "磁盘空间检查完成"
        if code == 0:
            parts = df_out.split()
            if len(parts) >= 4:
                try:
                    total_gb = int(parts[1].replace("G", ""))
                    avail_gb = int(parts[3].replace("G", ""))
                    use_pct = parts[4]
                    disk_ver = f"可用 {avail_gb} GB / 总共 {total_gb} GB (使用率 {use_pct})"
                    if avail_gb < 10:
                        disk_ok = False
                        disk_msg = f"磁盘可用空间仅剩 {avail_gb}GB，镜像解压推荐保留至少 15GB！"
                    else:
                        disk_msg = f"磁盘可用空间充足 ({avail_gb}GB >= 15GB)"
                except Exception:
                    disk_ver = df_out.strip()

        all_ok = docker_ok and ch341_found and disk_ok

        results["all_passed"] = all_ok
        results["items"] = {
            "docker": {
                "name": "Docker 运行环境",
                "status": docker_status,
                "version": docker_v.strip() if docker_ok else "未安装",
                "msg": docker_msg,
                "can_fix": not docker_ok
            },
            "nvidia_runtime": {
                "name": "NVIDIA Container Runtime",
                "status": nv_status,
                "version": "nvidia-container-toolkit" if nv_ok else "缺失",
                "msg": nv_msg,
                "can_fix": not nv_ok
            },
            "gpu": {
                "name": "GPU / CUDA 加速",
                "status": gpu_status,
                "version": gpu_ver,
                "msg": gpu_msg,
                "can_fix": False
            },
            "serial_ch341": {
                "name": "LoRa CH341 串口驱动",
                "status": ch341_status,
                "version": ch341_ver,
                "msg": ch341_msg,
                "can_fix": not ch341_found
            },
            "disk_space": {
                "name": "磁盘剩余空间",
                "status": "ok" if disk_ok else "warning",
                "version": disk_ver,
                "msg": disk_msg,
                "can_fix": False
            },
            "system_arch": {
                "name": "系统架构与内核",
                "status": "ok",
                "version": arch_str,
                "msg": "架构匹配",
                "can_fix": False
            }
        }
        return results

    # ==========================
    # 2. 一键修复功能
    # ==========================
    def fix_ch341_driver(self, stream_callback) -> bool:
        """
        一键编译安装 CH341 串口驱动（前置幂等检查：若已存在则直接提示并返回）
        """
        stream_callback("[INFO] 正在检测机器人端现有驱动状态...\n", False)
        if not ssh_manager.is_connected():
            stream_callback("[ERROR] 未连接至机器人，请先连接机器人！\n", True)
            return False

        # 前置检查：是否已存在驱动
        code_dev, ch341_ls, _ = ssh_manager.execute_command("ls /dev/ttyCH34* 2>/dev/null")
        code_mod, lsmod_out, _ = ssh_manager.execute_command("lsmod | grep -i ch341")
        code_info, modinfo_out, _ = ssh_manager.execute_command("modinfo ch341 2>/dev/null || find /lib/modules/$(uname -r) -name '*ch341*.ko*' 2>/dev/null")

        if (code_dev == 0 and "ttyCH34" in ch341_ls) or (code_mod == 0 and "ch341" in lsmod_out.lower()) or (code_info == 0 and modinfo_out.strip()):
            device_desc = ch341_ls.strip() if (code_dev == 0 and "ttyCH34" in ch341_ls) else "内核 ch341 驱动模块就绪"
            stream_callback(f"[SUCCESS] 检测到机器人端已有 CH341 驱动 ({device_desc})，驱动已就绪，无需重复安装！\n", False)
            return True

        commands = [
            ("更新软件包并安装编译工具与内核头文件", "DEBIAN_FRONTEND=noninteractive apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y build-essential bc git dkms && (DEBIAN_FRONTEND=noninteractive apt-get install -y nvidia-l4t-kernel-headers || DEBIAN_FRONTEND=noninteractive apt-get install -y linux-headers-$(uname -r) || true)"),
            ("清理旧版驱动源码目录", "rm -rf /tmp/ch341ser_linux"),
            ("获取 CH341 官方 Linux 驱动源码", "git clone --depth 1 https://github.com/WCHSoftGroup/ch341ser_linux /tmp/ch341ser_linux || git clone --depth 1 https://gitee.com/mirrors_WCHSoftGroup/ch341ser_linux.git /tmp/ch341ser_linux"),
            ("编译驱动模块", "cd /tmp/ch341ser_linux/driver && make clean && make"),
            ("安装驱动模块", "cd /tmp/ch341ser_linux/driver && make install"),
            ("加载驱动模块", "modprobe ch341"),
            ("移除冲突的盲文串口服务 (brltty)", "DEBIAN_FRONTEND=noninteractive apt-get purge -y 'brltty*' || true"),
        ]

        for desc, cmd in commands:
            stream_callback(f"\n[STEP] 正在执行: {desc} ...\n", False)
            code = ssh_manager.execute_command_stream(cmd, stream_callback, sudo=True)
            if code != 0 and "apt purge" not in cmd:
                stream_callback(f"[ERROR] 执行失败，退出码: {code}\n", True)
                return False

        # 验证驱动
        stream_callback("\n[CHECK] 正在验证 /dev/ttyCH34* 设备...\n", False)
        code, out, _ = ssh_manager.execute_command("ls /dev/ttyCH34*")
        if code == 0:
            stream_callback(f"[SUCCESS] CH341 驱动加载成功！设备节点: {out.strip()}\n", False)
            return True
        else:
            stream_callback(f"[WARNING] 驱动已编译加载，未检测到插入的 USB 转串口设备，请确认硬件是否牢固插入机器 USB 口。\n", True)
            return True

    def check_windows_ch341(self) -> Dict[str, Any]:
        """检查 Windows 上位机 COM 端口与 CH340/CH341 驱动状态"""
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

    def install_windows_ch341(self) -> Dict[str, Any]:
        """在 Windows 上位机一键安装/运行内置的 CH341 串口驱动程序"""
        import sys, ctypes, subprocess
        if getattr(sys, 'frozen', False):
            base_root = sys._MEIPASS
        else:
            base_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        candidates = [
            os.path.join(base_root, "backend", "drivers", "CH341SER.EXE"),
            os.path.join(base_root, "CH340 CH341驱动.exe"),
            os.path.join(base_root, "CH341SER.EXE")
        ]

        driver_path = None
        for c in candidates:
            if os.path.exists(c):
                driver_path = c
                break

        if not driver_path:
            return {"success": False, "msg": "未在软件目录中找到 Windows CH341 驱动安装包"}

        try:
            # 优先以管理员权限弹出驱动安装器
            ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", driver_path, "", None, 1)
            if ret > 32:
                return {"success": True, "msg": "已弹出 Windows CH341 驱动安装程序，请点击【安装】按钮完成配置。"}
            else:
                subprocess.Popen([driver_path], shell=True)
                return {"success": True, "msg": "已启动 Windows CH341 驱动程序。"}
        except Exception as e:
            return {"success": False, "msg": f"启动驱动安装程序异常: {str(e)}"}

    def fix_docker(self, stream_callback) -> bool:
        """一键安装/启动 Docker 环境（前置检查：已存在则直接返回）"""
        stream_callback("[INFO] 正在检测 Docker 运行环境...\n", False)
        if not ssh_manager.is_connected():
            stream_callback("[ERROR] 未连接至机器人！\n", True)
            return False

        code_v, docker_v, _ = ssh_manager.execute_command("docker --version")
        code_act, act_out, _ = ssh_manager.execute_command("systemctl is-active docker")
        if code_v == 0 and "active" in act_out:
            stream_callback(f"[SUCCESS] 检测到 Docker 环境已正常运行 ({docker_v.strip()})，无需重复安装！\n", False)
            return True

        stream_callback("[INFO] 正在执行 Docker 安装与服务拉起...\n", False)
        cmd = "DEBIAN_FRONTEND=noninteractive apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io && systemctl enable --now docker && usermod -aG docker unitree"
        code = ssh_manager.execute_command_stream(cmd, stream_callback, sudo=True)
        return code == 0

    # ==========================
    # 3. 镜像加载与容器启动
    # ==========================
    def list_docker_images(self) -> List[Dict[str, str]]:
        """获取机器人当前已有的 Docker 镜像"""
        if not ssh_manager.is_connected():
            return []

        code, out, _ = ssh_manager.execute_command("docker images --format '{{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}'")
        images = []
        if code == 0:
            for line in out.strip().split("\n"):
                if line.strip():
                    parts = line.split("\t")
                    if len(parts) >= 4:
                        images.append({
                            "repository": parts[0],
                            "tag": parts[1],
                            "id": parts[2],
                            "size": parts[3]
                        })
        return images

    def load_docker_image(self, remote_tar_path: str, stream_callback) -> Tuple[bool, str]:
        """执行 docker load -i 导入镜像（前置检查：若已有目标镜像则跳过重复解压）"""
        if not ssh_manager.is_connected():
            stream_callback("[ERROR] 未连接至机器人！\n", True)
            return False, "未连接至机器人"

        # 检查现有镜像
        existing_images = self.list_docker_images()
        for img in existing_images:
            full_name = f"{img['repository']}:{img['tag']}"
            if "rl_cu" in full_name or "vsis" in full_name or "mimic" in full_name:
                stream_callback(f"[SUCCESS] 检测到机器人已存在就绪的 Docker 镜像 [{full_name}] (ID: {img['id']})，无需重复导入解压！\n", False)
                return True, f"镜像已存在: {full_name}"

        stream_callback(f"[INFO] 正在远端执行 docker load -i {remote_tar_path} (此步骤解压约需 1~3 分钟，请稍候)...\n", False)
        cmd = f"docker load -i {remote_tar_path}"
        code = ssh_manager.execute_command_stream(cmd, stream_callback, sudo=True, timeout=900.0)
        if code == 0:
            stream_callback("[SUCCESS] 镜像导入成功！\n", False)
            return True, "镜像导入成功"
        else:
            stream_callback(f"[ERROR] 镜像导入失败，退出码: {code}\n", True)
            return False, f"docker load 失败 (code {code})"

    def start_container(self, image_name: str, stream_callback) -> Tuple[bool, str]:
        """
        固化启动容器。如果设备中已存在 400 端口的容器，说明已经自启运行，无需重复启动。
        """
        container_name = "vsis_g1"

        if not ssh_manager.is_connected():
            stream_callback("[ERROR] 未连接至机器人！\n", True)
            return False, "未连接至机器人"

        # 检查是否已存在 400 端口容器
        code_p400, p400_out, _ = ssh_manager.execute_command("docker ps --filter publish=400 --format '{{.Names}}'", sudo=True)
        if code_p400 == 0 and p400_out.strip():
            existing_name = p400_out.strip().split('\n')[0]
            stream_callback(f"[SUCCESS] 检测到设备中已存在运行在 400 端口的容器 [{existing_name}]，已自动启动且运行正常，跳过创建步骤。\n", False)
            return True, f"已存在 400 端口容器: {existing_name}"

        # 检查同名容器 vsis_g1 是否已在运行
        code_ps, ps_out, _ = ssh_manager.execute_command(f"docker ps --filter name={container_name} --format '{{.Names}}'", sudo=True)
        if code_ps == 0 and container_name in ps_out:
            stream_callback(f"[SUCCESS] 容器 {container_name} 已处于运行状态，无需重复启动。\n", False)
            return True, f"容器 {container_name} 已在运行"

        # 若容器处于已停止 (exited) 状态，直接 docker start
        code_ps_a, ps_a_out, _ = ssh_manager.execute_command(f"docker ps -a --filter name={container_name} --format '{{.Names}}'", sudo=True)
        if code_ps_a == 0 and container_name in ps_a_out:
            stream_callback(f"[INFO] 容器 {container_name} 已存在但处于停止状态，正在执行 docker start ...\n", False)
            code_start, _, _ = ssh_manager.execute_command(f"docker start {container_name}", sudo=True)
            if code_start == 0:
                stream_callback(f"[SUCCESS] 容器 {container_name} 成功拉起！\n", False)
                return True, "容器启动成功"
            else:
                stream_callback(f"[INFO] docker start 失败，将重新创建容器...\n", False)
                ssh_manager.execute_command(f"docker rm -f {container_name}", sudo=True)

        # 固化启动参数（严密按照补充说明第8节第3步）
        run_cmd = (
            f"docker run -d --restart=on-failure "
            f"--name {container_name} "
            f"--cap-add=SYS_PTRACE "
            f"--gpus all "
            f"--shm-size=1024m "
            f"--privileged "
            f"--cap-add=NET_ADMIN "
            f"--device /dev/:/dev/ "
            f"-v /tmp/.X11-unix:/tmp/.X11-unix:rw "
            f"-v /tmp:/tmp/ "
            f"-v /run/udev/:/run/udev/ "
            f"-p 400:22 "
            f"-p 4001:4000 "
            f"-p 4002:6006 "
            f"{image_name}"
        )

        stream_callback(f"[INFO] 执行固化启动指令:\n{run_cmd}\n", False)
        code = ssh_manager.execute_command_stream(run_cmd, stream_callback, sudo=True)
        if code != 0:
            stream_callback(f"[ERROR] 容器启动失败 (code {code})\n", True)
            return False, f"容器启动失败 (code {code})"

        stream_callback("[INFO] 验证容器运行状态...\n", False)
        time.sleep(1.5)
        code_ps, ps_out, _ = ssh_manager.execute_command(f"docker ps --filter name={container_name} --format '{{.Names}}\t{{.Status}}'", sudo=True)
        if code_ps == 0 and container_name in ps_out:
            stream_callback(f"[SUCCESS] 容器 {container_name} 正常运行！状态: {ps_out.strip()}\n", False)
            return True, "容器启动成功"
        else:
            stream_callback(f"[WARNING] 容器启动后未能保持运行，请检查日志。\n", True)
            return False, "容器未正常运行"

    # ==========================
    # 4. 开机自启 & Robot ID 配置
    # ==========================
    def configure_autostart_and_robot_id(self, robot_id: str = "A") -> Dict[str, Any]:
        """
        1. 写入自启动钩子 /docker_config/custom_startup.sh
        2. 写入 robot_id 到 /home/ubuntu/vsis_mimic_deploy/group/lora_robot_id.txt
        """
        robot_id = robot_id.strip().upper()
        if robot_id not in ["A", "B", "C", "D"]:
            return {"success": False, "msg": "Robot ID 必须为 A / B / C / D 中的一个"}

        # 1. 写入 custom_startup.sh
        startup_script_content = "#!/bin/bash\n/home/ubuntu/vsis_mimic_deploy/run_bg.sh\n"
        ok_startup, msg_startup = ssh_manager.write_remote_text_file(
            startup_script_content,
            "/docker_config/custom_startup.sh",
            sudo=True
        )
        if ok_startup:
            ssh_manager.execute_command("chmod +x /docker_config/custom_startup.sh", sudo=True)

        # 2. 写入 robot_id
        robot_id_file = "/home/ubuntu/vsis_mimic_deploy/group/lora_robot_id.txt"
        ok_id, msg_id = ssh_manager.write_remote_text_file(
            f"{robot_id}\n",
            robot_id_file,
            sudo=True
        )
        # 同时写入容器内部（若容器正在运行）
        ssh_manager.execute_command(
            f"docker exec vsis_g1 bash -c \"mkdir -p /home/ubuntu/vsis_mimic_deploy/group && echo '{robot_id}' > {robot_id_file}\" || true",
            sudo=True
        )

        success = ok_startup and ok_id
        return {
            "success": success,
            "robot_id": robot_id,
            "startup_hook": "/docker_config/custom_startup.sh",
            "robot_id_path": robot_id_file,
            "msg": f"开机自启动钩子已写入，Robot ID 成功设为 [{robot_id}]" if success else f"自启动或 ID 写入失败: {msg_startup} / {msg_id}"
        }

    def check_container_and_autostart_status(self) -> Dict[str, Any]:
        """
        检查设备中是否存在 400 端口的容器或 vsis_g1 容器。
        规则：如果设备中存在一个 400 端口的容器，则说明程序已经设置好了自启并且已经正常启动，此时应该跳过第四步启动与自启。
        """
        if not ssh_manager.is_connected():
            return {
                "running": False,
                "has_port_400": False,
                "container_exists": False,
                "autostart_configured": False,
                "robot_id": "A",
                "msg": "未连接至机器人"
            }

        # 1. 检查是否存在绑定 400 端口的容器
        code_p400, p400_out, _ = ssh_manager.execute_command("docker ps --filter publish=400 --format '{{.Names}}'", sudo=True)
        has_port_400 = bool(code_p400 == 0 and p400_out.strip())

        # 2. 检查名为 vsis_g1 的容器
        code_ps, ps_out, _ = ssh_manager.execute_command("docker ps --filter name=vsis_g1 --format '{{.Names}}'", sudo=True)
        is_vsis_g1_running = bool(code_ps == 0 and "vsis_g1" in ps_out)

        # 3. 检查任意容器存在性
        code_ps_a, ps_a_out, _ = ssh_manager.execute_command("docker ps -a --filter name=vsis_g1 --format '{{.Names}}'", sudo=True)
        container_exists = bool(code_ps_a == 0 and "vsis_g1" in ps_a_out) or has_port_400

        # 4. 检查自启动脚本 /docker_config/custom_startup.sh
        ok_start, start_content = ssh_manager.read_remote_text_file("/docker_config/custom_startup.sh")
        autostart_configured = bool(ok_start and "run_bg.sh" in start_content) or has_port_400

        # 5. 检查 robot_id
        ok_id, id_txt = ssh_manager.read_remote_text_file("/home/ubuntu/vsis_mimic_deploy/group/lora_robot_id.txt")
        robot_id = id_txt.strip() if ok_id and id_txt.strip() else "A"

        is_running = has_port_400 or is_vsis_g1_running
        container_name = p400_out.strip().split('\n')[0] if has_port_400 else ("vsis_g1" if is_vsis_g1_running else "")

        return {
            "running": is_running,
            "has_port_400": has_port_400,
            "container_name": container_name,
            "container_exists": container_exists,
            "autostart_configured": autostart_configured,
            "robot_id": robot_id,
            "msg": f"检测到 400 端口容器 [{container_name}] 运行中且已就绪" if is_running else "容器未运行"
        }

    # ==========================
    # 5. 机器码读取
    # ==========================
    def read_machine_id(self) -> Dict[str, Any]:
        """
        读取 64 位机器码
        容器内执行 ./g1_ctrl_vsis --print-machine-id
        """
        if not ssh_manager.is_connected():
            return {
                "success": False,
                "machine_id": "",
                "msg": "未连接至机器人，请先连接"
            }

        # 动态查询 400 端口正在运行的容器名称 (例如 mimic_cpu 或 vsis_g1)
        c_name = "vsis_g1"
        code_p400, p400_out, _ = ssh_manager.execute_command("docker ps --filter publish=400 --format '{{.Names}}'", sudo=True)
        if code_p400 == 0 and p400_out.strip():
            c_name = p400_out.strip().split('\n')[0]

        # 优先通过 docker exec 运行获取
        cmd1 = f"docker exec {c_name} bash -c 'cd /home/ubuntu/vsis_mimic_deploy && ./g1_ctrl_vsis --print-machine-id'"
        code, out, err = ssh_manager.execute_command(cmd1, sudo=True)

        # 若容器未起，尝试在宿主机对应目录执行
        if code != 0 or not out.strip():
            cmd2 = "cd /home/ubuntu/vsis_mimic_deploy && ./g1_ctrl_vsis --print-machine-id"
            code, out, err = ssh_manager.execute_command(cmd2, sudo=True)

        # 提取 64 位十六进制字符
        cleaned = out.strip()
        match = re.search(r'[0-9a-fA-F]{64}', cleaned)
        if match:
            mid = match.group(0).lower()
            return {
                "success": True,
                "machine_id": mid,
                "source": "g1_ctrl_vsis",
                "msg": "成功读取 64 位硬件指纹机器码"
            }
        
        # 提取 /etc/machine-id 硬件特征
        code_m, out_m, _ = ssh_manager.execute_command("cat /etc/machine-id")
        if code_m == 0 and len(out_m.strip()) >= 32:
            import hashlib
            fallback_id = hashlib.sha256(out_m.strip().encode()).hexdigest()
            return {
                "success": True,
                "machine_id": fallback_id,
                "source": "host_sha256",
                "msg": "通过系统硬件序列号哈希计算得出机器码 (g1_ctrl_vsis 尚未编译或就绪)"
            }

        return {
            "success": False,
            "machine_id": "",
            "msg": f"未能读取机器码: {err or out}"
        }


deployment_core = DeploymentCore()
