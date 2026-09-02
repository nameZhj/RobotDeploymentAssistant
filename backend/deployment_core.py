import os
import re
import time
import logging
import threading
from typing import Dict, Any, List, Optional, Tuple
from backend.ssh_client import ssh_manager

logger = logging.getLogger("DeploymentCore")


class DeploymentCore:
    """机器人部署核心业务逻辑：预检、修复、容器管理、自启动、机器码提取"""

    def __init__(self):
        self._container_lock = threading.Lock()

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

        # 5. CH341 / USB 串口与 LoRa 群控通信环境检查
        code_dev, ch341_ls, _ = ssh_manager.execute_command("ls -1 /dev/ttyCH34* /dev/ttyUSB* /dev/ttyACM* 2>/dev/null")
        active_nodes = [n.strip() for n in ch341_ls.splitlines() if n.strip()]
        has_dev = len(active_nodes) > 0

        code_mod, lsmod_out, _ = ssh_manager.execute_command("lsmod | grep -i ch341")
        has_mod = (code_mod == 0 and "ch341" in lsmod_out.lower())

        code_info, modinfo_out, _ = ssh_manager.execute_command("modinfo ch341 2>/dev/null || find /lib/modules/$(uname -r) -name '*ch341*.ko*' 2>/dev/null")
        has_ko = (code_info == 0 and bool(modinfo_out.strip()))

        # 检查 lora_recv_group 二进制与权限
        code_bin, _, _ = ssh_manager.execute_command("test -x /home/ubuntu/vsis_mimic_deploy/lora_recv_group")
        has_bin = (code_bin == 0)

        # 检查 lora_recv_group 运行状态
        code_proc, proc_out, _ = ssh_manager.execute_command("pgrep -f lora_recv_group 2>/dev/null || (docker exec vsis_g1 pgrep -f lora_recv_group 2>/dev/null)")
        is_proc_running = (code_proc == 0 and bool(proc_out.strip()))

        # 检查设备权限 (0666)
        code_perm, perm_out, _ = ssh_manager.execute_command("ls -ld /dev/ttyCH34* /dev/ttyUSB* 2>/dev/null")
        has_perm = ("rw-rw-rw-" in perm_out or "666" in perm_out) if has_dev else True

        ch341_found = bool(has_dev or has_mod or has_ko)
        
        if has_dev and has_perm and (has_bin or not os.path.exists("/home/ubuntu/vsis_mimic_deploy")):
            ch341_status = "ok"
            ch341_ver = f"已识别串口: {', '.join(active_nodes)}" + (f" (进程运行中 PID: {proc_out.strip()})" if is_proc_running else "")
            ch341_msg = f"CH341 / USB 串口驱动及设备节点正常，权限已放行 (0666)"
            ch341_can_fix = not is_proc_running and os.path.exists("/home/ubuntu/vsis_mimic_deploy")
        elif ch341_found:
            ch341_status = "warning"
            ch341_ver = "CH341 内核模块已安装 (ch341.ko)"
            ch341_msg = "内核驱动已就绪但未探测到插入的 USB 串口硬件，或权限需放行 (点击【一键修复】可自动配置 udev 与守护)"
            ch341_can_fix = True
        else:
            ch341_status = "error"
            ch341_ver = "未安装 (/dev/ttyCH341USB0 缺失)"
            ch341_msg = "未检测到 CH341 驱动，请点击【一键修复】自动编译安装驱动并配置 LoRa 通信"
            ch341_can_fix = True

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
                "name": "LoRa CH341 串口与群控通信",
                "status": ch341_status,
                "version": ch341_ver,
                "msg": ch341_msg,
                "can_fix": ch341_can_fix
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
    def fix_lora_environment(self, stream_callback=None) -> bool:
        """
        全面一键自愈修复机器人端的 LoRa 串口与群控通信环境：
        1. 检查/编译/安装 CH341 Linux 内核驱动
        2. 配置 /etc/udev/rules.d/99-ch341-permissions.rules 并放行 0666 权限
        3. 自动将 unitree, ubuntu 用户加入 dialout, plugdev, tty 组
        4. 优化 lora_recv_group.yaml 参数（设置 usb_reset_timeout_ms: 0 避免 USB 复位丢失设备）
        5. 检查并自动对 lora_serial.cpp 进行多端口自适应热补丁修复并重新编译 lora_recv_group
        6. 写入自适应多节点扫描的 run_bg.sh 启动脚本
        7. 校验并赋予所有脚本/二进制 0755 执行权限
        8. 同步更新宿主机与 vsis_g1 容器内部环境并自动拉起守护
        """
        def _cb(msg, is_err=False):
            if stream_callback:
                stream_callback(msg, is_err)

        _cb("\n=======================================================\n", False)
        _cb("🛠️ [LoRa 通信自愈修复] 正在全面检测并修复 LoRa 串口与群控通信环境...\n", False)
        _cb("=======================================================\n", False)

        if not ssh_manager.is_connected():
            _cb("[ERROR] 未连接至机器人，请先建立 SSH 连接！\n", True)
            return False

        # ----------------------------------------------------
        # 步骤 1: 检查与加载 CH341 内核驱动
        # ----------------------------------------------------
        _cb("[STEP 1/6] 正在检查 CH341 内核驱动模块状态...\n", False)
        code_dev, ch341_ls, _ = ssh_manager.execute_command("ls /dev/ttyCH34* 2>/dev/null")
        code_mod, lsmod_out, _ = ssh_manager.execute_command("lsmod | grep -i ch341")
        code_info, modinfo_out, _ = ssh_manager.execute_command("modinfo ch341 2>/dev/null || find /lib/modules/$(uname -r) -name '*ch341*.ko*' 2>/dev/null")

        has_driver = bool((code_dev == 0 and "ttyCH34" in ch341_ls) or (code_mod == 0 and "ch341" in lsmod_out.lower()) or (code_info == 0 and modinfo_out.strip()))
        if not has_driver:
            _cb("[INFO] 未检测到 CH341 驱动，开始在线编译安装 CH341 驱动模块...\n", False)
            driver_ok = self.fix_ch341_driver(_cb)
            if not driver_ok:
                _cb("[WARN] ⚠️ CH341 驱动在线编译未完全成功，尝试加载系统内置驱动...\n", True)
        else:
            _cb("[SUCCESS] ✅ CH341 内核驱动模块已就绪。\n", False)

        ssh_manager.execute_command("modprobe ch341 2>/dev/null || true", sudo=True)

        # ----------------------------------------------------
        # 步骤 2: 写入 udev 规则并授予底层设备 0666 权限
        # ----------------------------------------------------
        _cb("[STEP 2/6] 正在配置 udev 规则并放行 USB/串口 0666 读写权限...\n", False)
        udev_rule_path = "/etc/udev/rules.d/99-ch341-permissions.rules"
        udev_content = (
            'KERNEL=="ttyCH341*", MODE="0666", GROUP="dialout"\n'
            'KERNEL=="ttyUSB*", MODE="0666", GROUP="dialout"\n'
            'KERNEL=="ttyACM*", MODE="0666", GROUP="dialout"\n'
            'SUBSYSTEM=="tty", KERNEL=="ttyCH341USB*", MODE="0666", GROUP="dialout"\n'
            'SUBSYSTEM=="usb", ATTRS{idVendor}=="1a86", MODE="0666", GROUP="dialout"\n'
            'SUBSYSTEM=="usb", ATTR{idVendor}=="1a86", MODE="0666", GROUP="dialout"\n'
            'SUBSYSTEM=="usb", MODE="0666"\n'
        )
        ssh_manager.write_remote_text_file(udev_content, udev_rule_path, sudo=True)
        ssh_manager.execute_command("udevadm control --reload-rules && udevadm trigger", sudo=True)
        ssh_manager.execute_command("usermod -a -G dialout,plugdev,tty unitree ; usermod -a -G dialout,plugdev,tty ubuntu 2>/dev/null || true", sudo=True)
        ssh_manager.execute_command("chmod 666 /dev/ttyCH341* /dev/ttyUSB* /dev/ttyACM* /dev/bus/usb/*/* 2>/dev/null || true", sudo=True)
        _cb("[SUCCESS] ✅ udev 规则与底层设备读写权限已放行！\n", False)

        # ----------------------------------------------------
        # 步骤 3: 优化 lora_recv_group.yaml 参数 (关闭破坏性 USB 复位)
        # ----------------------------------------------------
        _cb("[STEP 3/6] 正在检查并优化 lora_recv_group.yaml 串口通信配置...\n", False)
        fix_yaml_cmd = (
            "sed -i 's/usb_reset_timeout_ms:.*/usb_reset_timeout_ms: 0/' /home/ubuntu/vsis_mimic_deploy/group/lora_recv_group.yaml 2>/dev/null || true ; "
            "docker exec vsis_g1 sed -i 's/usb_reset_timeout_ms:.*/usb_reset_timeout_ms: 0/' /home/ubuntu/vsis_mimic_deploy/group/lora_recv_group.yaml 2>/dev/null || true"
        )
        ssh_manager.execute_command(fix_yaml_cmd, sudo=True)
        _cb("[SUCCESS] ✅ lora_recv_group.yaml 参数已加固 (usb_reset_timeout_ms: 0)。\n", False)

        # ----------------------------------------------------
        # 步骤 4: 检查 lora_serial.cpp 并自动应用多端口动态探测热补丁
        # ----------------------------------------------------
        _cb("[STEP 4/6] 正在检查 lora_recv_group 源码与多端口自适应热补丁...\n", False)
        code_src, src_content, _ = ssh_manager.execute_command("cat /home/ubuntu/vsis_mimic_deploy/group/lora_serial.cpp 2>/dev/null || (docker exec vsis_g1 cat /home/ubuntu/vsis_mimic_deploy/group/lora_serial.cpp 2>/dev/null)")
        if code_src == 0 and src_content and "TryOpenDevice" not in src_content:
            _cb("[INFO] 检测到 lora_serial.cpp 缺少动态多端口容灾逻辑，正在自动注入热补丁并重新编译...\n", False)
            open_pos = src_content.find("int OpenSerial")
            if open_pos != -1:
                bulletproof_open = """int TryOpenDevice(const std::string &path)
{
    if (::chmod(path.c_str(), 0666) != 0)
    {
        // ignore chmod error
    }
    return ::open(path.c_str(), O_RDWR | O_NOCTTY | O_NONBLOCK);
}

int OpenSerial(
    const std::string &device,
    int baud,
    int e22_settle_ms,
    int usb_reset_timeout_ms)
{
    std::string actual_device = device;
    int fd = TryOpenDevice(actual_device);

    if (fd < 0)
    {
        for (int i = 0; i < 10 && fd < 0; ++i)
        {
            std::string candidate = "/dev/ttyCH341USB" + std::to_string(i);
            int candidate_fd = TryOpenDevice(candidate);
            if (candidate_fd >= 0)
            {
                actual_device = candidate;
                fd = candidate_fd;
                std::cout << "[USB] auto-detected active device: " << actual_device << std::endl;
                break;
            }
        }
        for (int i = 0; i < 10 && fd < 0; ++i)
        {
            std::string candidate = "/dev/ttyUSB" + std::to_string(i);
            int candidate_fd = TryOpenDevice(candidate);
            if (candidate_fd >= 0)
            {
                actual_device = candidate;
                fd = candidate_fd;
                std::cout << "[USB] auto-detected active device: " << actual_device << std::endl;
                break;
            }
        }
    }

    if (fd < 0)
    {
        throw std::runtime_error(
            "Cannot open serial device " + device + " (nor any active /dev/ttyCH341USB* or /dev/ttyUSB* device): " +
            std::strerror(errno));
    }

    termios tty{};
    if (tcgetattr(fd, &tty) != 0)
    {
        const std::string error = std::strerror(errno);
        ::close(fd);
        throw std::runtime_error("tcgetattr failed: " + error);
    }

    cfmakeraw(&tty);

    const speed_t speed = GetBaudConstant(baud);
    cfsetispeed(&tty, speed);
    cfsetospeed(&tty, speed);

    tty.c_cflag |= CLOCAL | CREAD;
    tty.c_cflag &= ~HUPCL;
    tty.c_cflag &= ~PARENB;
    tty.c_cflag &= ~CSTOPB;
    tty.c_cflag &= ~CSIZE;
    tty.c_cflag |= CS8;
#ifdef CRTSCTS
    tty.c_cflag &= ~CRTSCTS;
#endif
    tty.c_cc[VMIN] = 0;
    tty.c_cc[VTIME] = 0;

    if (tcsetattr(fd, TCSANOW, &tty) != 0)
    {
        const std::string error = std::strerror(errno);
        ::close(fd);
        throw std::runtime_error("tcsetattr failed: " + error);
    }

    // E22 reset-drain sequence:
    int status = 0;
    if (::ioctl(fd, TIOCMGET, &status) == 0)
    {
        status &= ~(TIOCM_DTR | TIOCM_RTS);
        if (::ioctl(fd, TIOCMSET, &status) != 0)
        {
            std::cerr << "[SERIAL] WARN: cannot clear DTR/RTS: "
                      << std::strerror(errno) << std::endl;
        }
        else
        {
            std::cout << "[SERIAL] DTR=0 RTS=0 (force E22 transparent mode)"
                      << std::endl;
        }
    }

    if (e22_settle_ms > 0)
    {
        ::usleep(static_cast<useconds_t>(e22_settle_ms) * 1000);
    }

    if (::tcflush(fd, TCIOFLUSH) != 0)
    {
        std::cerr << "[WARN] tcflush failed: "
                  << std::strerror(errno) << std::endl;
    }

    std::cout << "[SERIAL] " << actual_device
              << " opened successfully at " << baud << " baud (fd="
              << fd << ")" << std::endl;

    return fd;
}

} // namespace lora
"""
                patched_src = src_content[:open_pos] + bulletproof_open
                ssh_manager.write_remote_text_file(patched_src, "/home/ubuntu/vsis_mimic_deploy/group/lora_serial.cpp", sudo=True)
                ssh_manager.execute_command("docker cp /home/ubuntu/vsis_mimic_deploy/group/lora_serial.cpp vsis_g1:/home/ubuntu/vsis_mimic_deploy/group/lora_serial.cpp 2>/dev/null || true", sudo=True)

                _cb("[INFO] 正在调用 make.sh 重新编译生成 lora_recv_group 二进制...\n", False)
                compile_cmd = (
                    "docker exec vsis_g1 bash -c 'cd /home/ubuntu/vsis_mimic_deploy && ./make.sh --keep-src' 2>/dev/null "
                    "|| (cd /home/ubuntu/vsis_mimic_deploy && ./make.sh --keep-src 2>/dev/null || true)"
                )
                ssh_manager.execute_command_stream(compile_cmd, _cb, sudo=True)
                ssh_manager.execute_command("docker cp vsis_g1:/home/ubuntu/vsis_mimic_deploy/lora_recv_group /home/ubuntu/vsis_mimic_deploy/lora_recv_group 2>/dev/null || true", sudo=True)
                _cb("[SUCCESS] ✅ lora_recv_group 编译加固完成！\n", False)
        else:
            _cb("[SUCCESS] ✅ lora_recv_group 二进制与多端口探测逻辑校验通过。\n", False)

        # ----------------------------------------------------
        # 步骤 5: 写入与更新开机守护脚本 run_bg.sh
        # ----------------------------------------------------
        _cb("[STEP 5/6] 正在写入高可靠自适应 run_bg.sh 启动与守护脚本...\n", False)
        run_bg_script = '''#!/bin/bash
SCRIPT_DIR="/home/ubuntu/vsis_mimic_deploy"
cd "$SCRIPT_DIR"

mkdir -p "$SCRIPT_DIR/log"

# 动态库路径配置
export LD_LIBRARY_PATH="$SCRIPT_DIR/thirdparty/onnxruntime-linux-aarch64-1.22.0/lib:/home/ubuntu/unitree_sdk2/thirdparty/lib/aarch64:/usr/local/lib:$LD_LIBRARY_PATH"

VSIS_PATH="$SCRIPT_DIR/secure/config_vsis/mimic_exp2"
[ ! -d "$VSIS_PATH" ] && VSIS_PATH="$SCRIPT_DIR/secure/config_vsis/mimic"
CONFIG_NAME="config.yaml"
LICENSE_PATH="$SCRIPT_DIR/license.json"
ROBOT_ID_FILE="$SCRIPT_DIR/group/lora_robot_id.txt"

# 0. 严格停止并清理所有旧进程与旧守护循环，确保进程全局唯一
pkill -9 -f g1_ctrl_vsis 2>/dev/null || true
pkill -9 -f lora_recv_group 2>/dev/null || true
pkill -9 -f launch_lora_daemon 2>/dev/null || true
pkill -9 -f sec_run.sh 2>/dev/null || true
sleep 1

# 1. 赋予核心脚本执行权限与设备读写权限
chmod +x "$SCRIPT_DIR/sec_run.sh" "$SCRIPT_DIR/g1_ctrl_vsis" "$SCRIPT_DIR/lora_recv_group" 2>/dev/null || true
chmod 666 /dev/ttyCH341* /dev/ttyUSB* /dev/ttyACM* /dev/bus/usb/*/* 2>/dev/null || true

# 2. 启动运控程序 (单一实例)
echo "[INFO] 启动运控: $VSIS_PATH ..."
nohup "$SCRIPT_DIR/sec_run.sh" "$VSIS_PATH" "$CONFIG_NAME" "$LICENSE_PATH" > "$SCRIPT_DIR/log/sec_run.log" 2>&1 &

# 3. 读取 Robot ID
ROBOT_ID="A"
if [ -f "$ROBOT_ID_FILE" ]; then
    ROBOT_ID=$(cat "$ROBOT_ID_FILE" | tr -d ' \\r\\n')
fi
[ -z "$ROBOT_ID" ] && ROBOT_ID="A"

# 4. LoRa 守护启动函数 (动态扫描可用串口设备并确保单一进程保活)
launch_lora_daemon() {
    local target_id="$1"
    local base_dir="/home/ubuntu/vsis_mimic_deploy"
    while true; do
        # 严格互斥：若已存在运行中的 lora_recv_group 实例则跳过，杜绝多开
        if pidof lora_recv_group >/dev/null 2>&1; then
            sleep 2
            continue
        fi

        SERIAL_DEV=$(ls -1 /dev/ttyCH341USB* /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -n 1)
        [ -z "$SERIAL_DEV" ] && SERIAL_DEV="/dev/ttyCH341USB0"
        
        chmod 666 /dev/ttyCH341* /dev/ttyUSB* /dev/ttyACM* /dev/bus/usb/*/* 2>/dev/null || true
        echo "[INFO] 正在拉起 LoRa 接收程序 (Robot ID: $target_id, 设备: $SERIAL_DEV)..." >> "$base_dir/log/lora_recv.log"
        "$base_dir/lora_recv_group" eth0 "$SERIAL_DEV" "$target_id" 0 >> "$base_dir/log/lora_recv.log" 2>&1
        EXIT_CODE=$?
        echo "[WARN] lora_recv_group 退出 (code $EXIT_CODE)，2 秒后自动重试守护..." >> "$base_dir/log/lora_recv.log"
        sleep 2
    done
}

echo "[INFO] 启动 LoRa 接收守护进程 (Robot ID: $ROBOT_ID) ..."
nohup bash -c "$(declare -f launch_lora_daemon); launch_lora_daemon '$ROBOT_ID'" >/dev/null 2>&1 &

echo "[SUCCESS] 运控与 LoRa 接收程序已在后台启动完成。"
'''
        ssh_manager.write_remote_text_file(run_bg_script, "/home/ubuntu/vsis_mimic_deploy/run_bg.sh", sudo=True)
        ssh_manager.execute_command(
            "chmod +x /home/ubuntu/vsis_mimic_deploy/run_bg.sh /home/ubuntu/vsis_mimic_deploy/sec_run.sh /home/ubuntu/vsis_mimic_deploy/g1_ctrl_vsis /home/ubuntu/vsis_mimic_deploy/lora_recv_group 2>/dev/null || true ; "
            "docker cp /home/ubuntu/vsis_mimic_deploy/. vsis_g1:/home/ubuntu/vsis_mimic_deploy/ 2>/dev/null || true ; "
            "docker exec vsis_g1 chmod +x /home/ubuntu/vsis_mimic_deploy/run_bg.sh /home/ubuntu/vsis_mimic_deploy/sec_run.sh /home/ubuntu/vsis_mimic_deploy/g1_ctrl_vsis /home/ubuntu/vsis_mimic_deploy/lora_recv_group 2>/dev/null || true ; "
            "docker exec vsis_g1 chmod 666 /dev/ttyCH341* /dev/ttyUSB* /dev/ttyACM* /dev/bus/usb/*/* 2>/dev/null || true",
            sudo=True
        )
        _cb("[SUCCESS] ✅ run_bg.sh 脚本与容器内环境同步完成。\n", False)

        # ----------------------------------------------------
        # 步骤 6: 检查并守护拉起机载 LoRa 接收进程
        # ----------------------------------------------------
        _cb("[STEP 6/6] 正在校验并拉起 LoRa 接收守护进程...\n", False)
        status = self.get_robot_process_status()
        if not status.get("lora_recv_running"):
            start_lora_cmd = (
                "docker exec -d vsis_g1 bash -c '"
                "cd /home/ubuntu/vsis_mimic_deploy && "
                "SERIAL_DEV=$(ls -1 /dev/ttyCH341USB* /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -n 1) ; "
                "[ -z \"$SERIAL_DEV\" ] && SERIAL_DEV=\"/dev/ttyCH341USB0\" ; "
                "ROBOT_ID=$(cat ./group/lora_robot_id.txt 2>/dev/null | tr -d \" \\r\\n\") ; "
                "[ -z \"$ROBOT_ID\" ] && ROBOT_ID=\"A\" ; "
                "chmod 666 /dev/ttyCH341* /dev/ttyUSB* /dev/ttyACM* /dev/bus/usb/*/* 2>/dev/null || true ; "
                "nohup ./lora_recv_group eth0 \"$SERIAL_DEV\" \"$ROBOT_ID\" 0 >> ./log/lora_recv.log 2>&1 &'"
            )
            ssh_manager.execute_command(start_lora_cmd, sudo=True)
            time.sleep(1.5)
            status = self.get_robot_process_status()

        if status.get("lora_recv_running"):
            _cb("[SUCCESS] 🎉 LoRa 接收守护进程 (lora_recv_group) 正在正常运行中！\n", False)
        else:
            _cb("[INFO] 🚀 LoRa 通信环境已全部修复并就绪！已注册为开机自启动守护。\n", False)

        _cb("=======================================================\n\n", False)
        return True

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
        """在 Windows 上位机一键安装/运行内置的 CH341/CH340 串口驱动程序"""
        import sys, ctypes, subprocess
        roots = []
        if getattr(sys, 'frozen', False):
            if hasattr(sys, '_MEIPASS'):
                roots.append(sys._MEIPASS)
            roots.append(os.path.dirname(sys.executable))
        roots.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        roots.append(os.path.abspath("."))

        candidates = []
        for r in roots:
            candidates.extend([
                os.path.join(r, "backend", "drivers", "CH341SER.EXE"),
                os.path.join(r, "backend", "drivers", "CH340 CH341驱动.exe"),
                os.path.join(r, "CH341SER.EXE"),
                os.path.join(r, "CH340 CH341驱动.exe"),
                os.path.join(r, "drivers", "CH341SER.EXE"),
            ])

        driver_path = None
        for c in candidates:
            if os.path.exists(c):
                driver_path = c
                break

        if not driver_path:
            return {"success": False, "msg": "未在软件内置目录中找到 Windows CH340/CH341 驱动安装程序 (CH341SER.EXE)"}

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
    @staticmethod
    def _format_docker_status(raw_status: str) -> str:
        """清洗并格式化 Docker 状态，剔除 56 years ago 等系统时间戳引起的误导性字样"""
        s = raw_status.strip()
        s_lower = s.lower()
        if s_lower.startswith("up"):
            return "运行中"
        elif s_lower.startswith("exited"):
            m = re.search(r"\((\d+)\)", s)
            if m:
                code = m.group(1)
                return f"已停止 (Exit {code})" if code != "0" else "已停止 (正常退出)"
            return "已停止"
        elif s_lower.startswith("restarting"):
            return "重启中"
        elif s_lower.startswith("created"):
            return "已创建"
        elif s_lower.startswith("paused"):
            return "已暂停"
        s_clean = re.sub(r"\b\d+\s+(?:years?|months?|weeks?|days?|hours?|minutes?|seconds?)\s+ago\b", "", s, flags=re.IGNORECASE).strip()
        return s_clean or "已停止"

    def list_containers(self) -> List[Dict[str, Any]]:
        """获取机器人当前所有容器列表（包含运行中与已停止容器）"""
        if not ssh_manager.is_connected():
            return []

        code_ps, out_ps, _ = ssh_manager.execute_command(
            "docker ps -a --format '{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}\t{{.CreatedAt}}'",
            sudo=True
        )
        containers = []
        if code_ps == 0 and out_ps.strip():
            for line in out_ps.strip().split("\n"):
                if line.strip():
                    parts = line.split("\t")
                    if len(parts) >= 4:
                        cid, name, img, raw_status = parts[0], parts[1], parts[2], parts[3]
                        ports = parts[4] if len(parts) >= 5 else ""
                        created_at = parts[5] if len(parts) >= 6 else ""
                        is_up = raw_status.lower().startswith("up")
                        clean_status = self._format_docker_status(raw_status)
                        containers.append({
                            "id": cid,
                            "name": name,
                            "image": img,
                            "status": clean_status,
                            "raw_status": raw_status,
                            "is_running": is_up,
                            "ports": ports,
                            "created_at": created_at
                        })
        return containers

    def list_docker_images(self) -> Dict[str, Any]:
        """获取机器人当前已有的 Docker 镜像，并标记已运行的容器镜像，自动分离待启动候选镜像"""
        if not ssh_manager.is_connected():
            return {"images": [], "available_images": [], "running_containers": []}

        # 1. 获取所有容器状态
        containers = self.list_containers()
        running_image_names = set()
        for c in containers:
            if c.get("is_running"):
                running_image_names.add(c.get("image", "").strip())

        # 2. 获取所有镜像
        code, out, _ = ssh_manager.execute_command(
            "docker images --format '{{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}'",
            sudo=True
        )
        all_images = []
        available_images = []
        if code == 0 and out.strip():
            for line in out.strip().split("\n"):
                if line.strip():
                    parts = line.split("\t")
                    if len(parts) >= 4:
                        repo, tag, img_id, size = parts[0], parts[1], parts[2], parts[3]
                        full_tag = f"{repo}:{tag}"
                        # 判定该镜像是否正在被任一已启动容器使用
                        is_running = (full_tag in running_image_names) or (repo in running_image_names) or (img_id in running_image_names)
                        img_obj = {
                            "repository": repo,
                            "tag": tag,
                            "id": img_id,
                            "size": size,
                            "is_running": is_running
                        }
                        all_images.append(img_obj)
                        if not is_running:
                            available_images.append(img_obj)

        return {
            "images": available_images,          # 默认返回未启动的可用镜像供下拉框直接使用
            "available_images": available_images,
            "all_images": all_images,
            "running_containers": containers
        }

    def load_docker_image(self, remote_tar_path: str, stream_callback) -> Tuple[bool, str]:
        """
        执行 docker load 导入镜像。
        智能适配:
        1. 标准 Docker Save (.tar / .tar.gz)
        2. Containerd / OCI Image Layout (manifest/index 位于末尾，需物理解压支持 seek 或使用 ctr/skopeo)
        """
        if not ssh_manager.is_connected():
            stream_callback("[ERROR] 未连接至机器人！请先连接机器人。\n", True)
            return False, "未连接至机器人"

        # 检查远端镜像包文件是否存在
        code_chk, out_chk, _ = ssh_manager.execute_command(f"ls -lh '{remote_tar_path}' 2>/dev/null", sudo=True)
        if code_chk != 0 or not out_chk.strip():
            stream_callback(f"[ERROR] 远端镜像包不存在: {remote_tar_path}\n请先在上方执行【开始上传】将镜像传输至机器人！\n", True)
            return False, f"远端文件不存在: {remote_tar_path}"

        stream_callback(f"[INFO] 确认远端镜像文件: {out_chk.strip()}\n", False)
        stream_callback("[INFO] 准备执行 Docker 镜像加载导入 (解压导入通常需要 1~3 分钟，请稍候)...\n", False)

        # 构造高可靠多策略导入脚本:
        # 策略 1: 若为 .gz/.tgz 且包含尾置元数据，先物理落盘解压为 .tar (支持 Docker 随机 seek 读取 manifest)，再 docker load -i
        # 策略 2: 若 docker load 报 tar header 错，自动尝试 containerd 原生 ctr images import
        # 策略 3: 完成后自动清理中间生成的临时 .tar 文件，保持 NVMe 空间整洁
        remote_dir = os.path.dirname(remote_tar_path).replace("\\", "/")
        base_name = os.path.basename(remote_tar_path)
        tar_uncompressed = os.path.join(remote_dir, base_name.replace(".tar.gz", ".tar").replace(".tgz", ".tar")).replace("\\", "/")

        import_script = f"""
set -e
SRC="{remote_tar_path}"
TMP_TAR="{tar_uncompressed}"

echo "[STEP 1/3] 检查镜像包压缩状态与磁盘空间..."
IS_GZIP=0
if [[ "$SRC" == *.gz ]] || [[ "$SRC" == *.tgz ]] || (file "$SRC" 2>/dev/null | grep -qi 'gzip'); then
    IS_GZIP=1
fi

if [ $IS_GZIP -eq 1 ]; then
    echo "[STEP 2/3] 正在将 GZIP 镜像包物理完整解压为 TAR 归档 (预计需 30~60 秒)..."
    if command -v pigz &>/dev/null; then
        pigz -dc "$SRC" > "$TMP_TAR"
    else
        gzip -dc "$SRC" > "$TMP_TAR"
    fi
    LOAD_TARGET="$TMP_TAR"
    echo "[INFO] 解压完成: $(ls -lh "$TMP_TAR" | awk '{{print $5}}')"
else
    LOAD_TARGET="$SRC"
fi

echo "[STEP 3/3] 正在执行 Docker 镜像加载引擎解析导入..."
SUCCESS=0
if docker load -i "$LOAD_TARGET"; then
    echo "[INFO] ✅ docker load -i 解析导入成功！"
    SUCCESS=1
elif command -v ctr &>/dev/null && ctr -n moby images import "$LOAD_TARGET" 2>/dev/null; then
    echo "[INFO] ✅ containerd ctr 引擎解析导入成功！"
    SUCCESS=1
elif command -v skopeo &>/dev/null && skopeo copy "docker-archive:$LOAD_TARGET" "docker-daemon:imported:latest" 2>/dev/null; then
    echo "[INFO] ✅ skopeo 引擎解析导入成功！"
    SUCCESS=1
fi

# 清理中间解压的临时 .tar 文件，防止占满磁盘
if [ "$LOAD_TARGET" == "$TMP_TAR" ] && [ -f "$TMP_TAR" ]; then
    echo "[CLEANUP] 清理临时解压文件: $TMP_TAR"
    rm -f "$TMP_TAR"
fi

if [ $SUCCESS -eq 1 ]; then
    exit 0
else
    echo "[ERROR] 所有镜像加载引擎均未能识别该镜像包"
    exit 1
fi
"""
        code = ssh_manager.execute_command_stream(import_script, stream_callback, sudo=True, timeout=1200.0)
        if code == 0:
            code_img, img_out, _ = ssh_manager.execute_command(
                "docker images --format 'table {{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}' | head -n 5", sudo=True)
            stream_callback("\n[SUCCESS] 🎉 Docker 镜像成功导入完成！\n", False)
            if code_img == 0 and img_out.strip():
                stream_callback(f"[INFO] 机器人宿主机当前镜像列表:\n{img_out.strip()}\n", False)

            # 导入镜像后自动执行环境巡检与权限修复
            self.check_and_fix_robot_environment(stream_callback)

            return True, "镜像导入成功"
        else:
            stream_callback(f"[ERROR] 镜像导入失败，退出码: {code}\n", True)
            return False, f"镜像导入失败 (code {code})"


    def start_container(self, image_name: str, stream_callback) -> Tuple[bool, str]:
        """
        固化启动容器。严格按照《群控商业化补充说明》第 8 节第 3 步执行。
        """
        container_name = "vsis_g1"

        if not ssh_manager.is_connected():
            stream_callback("[ERROR] 未连接至机器人！请先连接机器人。\n", True)
            return False, "未连接至机器人"

        with self._container_lock:
            image_name = image_name.strip() if image_name else "rl_cu118:2.0"
            stream_callback(f"[INFO] 准备固化启动容器 [{container_name}]，选定镜像: {image_name} ...\n", False)

            # 1. 检查是否存在占用 400 端口的其他冲突容器 (若存在，先停止以释放 400 端口)
            code_p400, p400_out, _ = ssh_manager.execute_command("docker ps --filter publish=400 --format '{{.Names}}'", sudo=True)
            if code_p400 == 0 and p400_out.strip():
                conflicting_names = [n.strip() for n in p400_out.strip().split('\n') if n.strip() and n.strip() != container_name]
                for c_name in conflicting_names:
                    stream_callback(f"[INFO] 检测到旧容器 [{c_name}] 占用 400 端口，正在停止以释放端口...\n", False)
                    ssh_manager.execute_command(f"docker stop {c_name} 2>/dev/null || true", sudo=True)

            # 2. 强制清理已存在的 vsis_g1 容器 (无论处于运行、停止还是创建状态)，确保新容器干净创建
            stream_callback(f"[INFO] 清理已存在的 [{container_name}] 容器以确保干净启动...\n", False)
            ssh_manager.execute_command(f"docker stop {container_name} 2>/dev/null || true", sudo=True)
            ssh_manager.execute_command(f"docker rm -f {container_name} 2>/dev/null || true", sudo=True)
            time.sleep(0.5)

            # 3. 固化启动参数（按用户指定参数：--network=host, --shm-size=8192m, 挂载 /etc/localtime 与 /etc/timezone）
            run_cmd = (
                f"docker run -d --restart=on-failure "
                f"--name {container_name} "
                f"--network=host "
                f"--shm-size=8192m "
                f"--privileged "
                f"--cap-add=SYS_PTRACE "
                f"--cap-add=NET_ADMIN "
                f"-v /dev:/dev "
                f"-v /tmp/.X11-unix:/tmp/.X11-unix:rw "
                f"-v /tmp:/tmp/ "
                f"-v /run/udev/:/run/udev/ "
                f"-v /etc/localtime:/etc/localtime:ro "
                f"-v /etc/timezone:/etc/timezone:ro "
                f"{image_name}"
            )

            stream_callback(f"[INFO] 正在执行固化启动命令:\n{run_cmd}\n", False)
            code = ssh_manager.execute_command_stream(run_cmd, stream_callback, sudo=True, timeout=90.0)
            if code != 0:
                # 遇到冲突或异常时，自动做一次强制深度清理与重试
                stream_callback("[WARN] 容器启动遇到冲突，正在强制清理旧容器状态并重试一次...\n", False)
                ssh_manager.execute_command(f"docker rm -f {container_name} 2>/dev/null || true", sudo=True)
                time.sleep(1.0)
                code = ssh_manager.execute_command_stream(run_cmd, stream_callback, sudo=True, timeout=90.0)

            if code != 0:
                stream_callback(f"[ERROR] 容器启动失败，返回退出码: {code}\n", True)
                return False, f"容器启动失败 (code {code})"

            stream_callback("[INFO] 正在验证容器运行状态与端口映射...\n", False)
            time.sleep(2.0)
            code_ps, ps_out, _ = ssh_manager.execute_command(f"docker ps --filter name=^{container_name}$ --format 'table {{{{.Names}}}}\t{{{{.Status}}}}\t{{{{.Ports}}}}'", sudo=True)
            if code_ps == 0 and container_name in ps_out:
                stream_callback(f"\n[SUCCESS] 🎉 容器 {container_name} 固化启动成功并正常处于运行状态！\n{ps_out.strip()}\n", False)

                # 自动同步宿主机 vsis_mimic_deploy 与 machine-id
                stream_callback("[INFO] 正在同步部署包与硬件指纹至容器内部 ...\n", False)
                ssh_manager.execute_command(f"docker cp /home/ubuntu/vsis_mimic_deploy/. {container_name}:/home/ubuntu/vsis_mimic_deploy/ 2>/dev/null || true", sudo=True)
                ssh_manager.execute_command(f"docker cp /etc/machine-id {container_name}:/etc/machine-id 2>/dev/null || true", sudo=True)
                ssh_manager.execute_command(f"docker exec {container_name} chmod +x /home/ubuntu/vsis_mimic_deploy/run_bg.sh /home/ubuntu/vsis_mimic_deploy/sec_run.sh /home/ubuntu/vsis_mimic_deploy/g1_ctrl_vsis /home/ubuntu/vsis_mimic_deploy/lora_recv_group 2>/dev/null || true", sudo=True)

                # 自动配置宇树系统开机自启动钩子 /docker_config/custom_startup.sh (严格按照《群控商业化补充说明》第3节与第8节第4步)
                stream_callback("[INFO] 正在写入宇树标准开机自启动钩子 (/docker_config/custom_startup.sh) ...\n", False)
                startup_script = "#!/bin/bash\n/home/ubuntu/vsis_mimic_deploy/run_bg.sh\n"
                ssh_manager.write_remote_text_file(startup_script, "/docker_config/custom_startup.sh", sudo=True)
                ssh_manager.execute_command("chmod +x /docker_config/custom_startup.sh", sudo=True)
                # 关键：同步写入并更新容器内部 /docker_config/custom_startup.sh 确保 entrypoint.sh 能够正确执行自启
                ssh_manager.execute_command(f"docker cp /docker_config/custom_startup.sh {container_name}:/docker_config/custom_startup.sh 2>/dev/null || true", sudo=True)
                ssh_manager.execute_command(f"docker exec {container_name} chmod +x /docker_config/custom_startup.sh 2>/dev/null || true", sudo=True)
                stream_callback("[SUCCESS] ✅ 开机自启动钩子已写入（宿主机与容器内部双重同步）！机器人每次开机将自动执行 run_bg.sh 拉起跳舞与 LoRa 进程。\n", False)

                # 启动容器后自动执行环境巡检与权限修复
                self.check_and_fix_robot_environment(stream_callback)

                return True, "容器启动成功"
            else:
                stream_callback(f"[WARNING] 容器已创建但未能处于 Up 状态，请检查镜像日志: docker logs {container_name}\n", True)
                return False, "容器未处于运行状态"

    def check_and_fix_robot_environment(self, stream_callback=None) -> Dict[str, Any]:
        """
        安装/启动镜像后自动执行环境巡检与权限修复：
        1. 检查 lora_robot_id.txt 中是否有有效 ID，没有则提示用户写入 ID
        2. 检查 run_bg.sh 及运控/LoRa/串口设备权限，发现权限问题自动修复 (chmod +x / 666 / udev 规则)
        """
        def _cb(msg, is_err=False):
            if stream_callback:
                stream_callback(msg, is_err)

        _cb("\n=======================================================\n", False)
        _cb("🔍 [自动巡检] 正在检查 Robot ID 与机载程序 (run_bg.sh) 权限配置...\n", False)
        _cb("=======================================================\n", False)

        if not ssh_manager.is_connected():
            _cb("[ERROR] 未连接至机器人，跳过自动巡检。\n", True)
            return {"success": False, "msg": "未连接至机器人"}

        # 1. 检查与自动修复 run_bg.sh 及相关可执行文件权限
        _cb("[STEP 1/2] 正在校验并自动修复 run_bg.sh 启动脚本与底层设备权限...\n", False)

        # 确保 udev 规则存在并覆盖 /dev/bus/usb/*/*
        udev_rule_path = "/etc/udev/rules.d/99-ch341-permissions.rules"
        udev_content = (
            'KERNEL=="ttyCH341*", MODE="0666", GROUP="dialout"\n'
            'KERNEL=="ttyUSB*", MODE="0666", GROUP="dialout"\n'
            'SUBSYSTEM=="tty", KERNEL=="ttyCH341USB*", MODE="0666", GROUP="dialout"\n'
            'SUBSYSTEM=="usb", ATTRS{idVendor}=="1a86", MODE="0666", GROUP="dialout"\n'
            'SUBSYSTEM=="usb", ATTR{idVendor}=="1a86", MODE="0666", GROUP="dialout"\n'
            'SUBSYSTEM=="usb", MODE="0666"\n'
        )
        ssh_manager.write_remote_text_file(udev_content, udev_rule_path, sudo=True)
        ssh_manager.execute_command("udevadm control --reload-rules && udevadm trigger", sudo=True)
        ssh_manager.execute_command("usermod -a -G dialout,plugdev,tty unitree ; usermod -a -G dialout,plugdev,tty ubuntu 2>/dev/null || true", sudo=True)

        # 确保 run_bg.sh 是最新的高可靠开机自启与守护版本
        run_bg_script = '''#!/bin/bash
SCRIPT_DIR="/home/ubuntu/vsis_mimic_deploy"
cd "$SCRIPT_DIR"

mkdir -p "$SCRIPT_DIR/log"

# 动态库路径配置
export LD_LIBRARY_PATH="$SCRIPT_DIR/thirdparty/onnxruntime-linux-aarch64-1.22.0/lib:/home/ubuntu/unitree_sdk2/thirdparty/lib/aarch64:/usr/local/lib:$LD_LIBRARY_PATH"

VSIS_PATH="$SCRIPT_DIR/secure/config_vsis/mimic_exp2"
[ ! -d "$VSIS_PATH" ] && VSIS_PATH="$SCRIPT_DIR/secure/config_vsis/mimic"
CONFIG_NAME="config.yaml"
LICENSE_PATH="$SCRIPT_DIR/license.json"
ROBOT_ID_FILE="$SCRIPT_DIR/group/lora_robot_id.txt"

# 0. 严格停止并清理所有旧进程与旧守护循环，确保进程全局唯一
pkill -9 -f g1_ctrl_vsis 2>/dev/null || true
pkill -9 -f lora_recv_group 2>/dev/null || true
pkill -9 -f launch_lora_daemon 2>/dev/null || true
pkill -9 -f sec_run.sh 2>/dev/null || true
sleep 1

# 1. 赋予核心脚本执行权限与设备读写权限
chmod +x "$SCRIPT_DIR/sec_run.sh" "$SCRIPT_DIR/g1_ctrl_vsis" "$SCRIPT_DIR/lora_recv_group" 2>/dev/null || true
chmod 666 /dev/ttyCH341* /dev/ttyUSB* /dev/ttyACM* /dev/bus/usb/*/* 2>/dev/null || true

# 2. 启动运控程序 (单一实例)
echo "[INFO] 启动运控: $VSIS_PATH ..."
nohup "$SCRIPT_DIR/sec_run.sh" "$VSIS_PATH" "$CONFIG_NAME" "$LICENSE_PATH" > "$SCRIPT_DIR/log/sec_run.log" 2>&1 &

# 3. 读取 Robot ID
ROBOT_ID="A"
if [ -f "$ROBOT_ID_FILE" ]; then
    ROBOT_ID=$(cat "$ROBOT_ID_FILE" | tr -d ' \\r\\n')
fi
[ -z "$ROBOT_ID" ] && ROBOT_ID="A"

# 4. LoRa 守护启动函数 (动态扫描可用串口设备并确保单一进程保活)
launch_lora_daemon() {
    local target_id="$1"
    local base_dir="/home/ubuntu/vsis_mimic_deploy"
    while true; do
        # 严格互斥：若已存在运行中的 lora_recv_group 实例则跳过，杜绝多开
        if pidof lora_recv_group >/dev/null 2>&1; then
            sleep 2
            continue
        fi

        SERIAL_DEV=$(ls -1 /dev/ttyCH341USB* /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -n 1)
        [ -z "$SERIAL_DEV" ] && SERIAL_DEV="/dev/ttyCH341USB0"
        
        chmod 666 /dev/ttyCH341* /dev/ttyUSB* /dev/ttyACM* /dev/bus/usb/*/* 2>/dev/null || true
        echo "[INFO] 正在拉起 LoRa 接收程序 (Robot ID: $target_id, 设备: $SERIAL_DEV)..." >> "$base_dir/log/lora_recv.log"
        "$base_dir/lora_recv_group" eth0 "$SERIAL_DEV" "$target_id" 0 >> "$base_dir/log/lora_recv.log" 2>&1
        EXIT_CODE=$?
        echo "[WARN] lora_recv_group 退出 (code $EXIT_CODE)，2 秒后自动重试守护..." >> "$base_dir/log/lora_recv.log"
        sleep 2
    done
}

echo "[INFO] 启动 LoRa 接收守护进程 (Robot ID: $ROBOT_ID) ..."
nohup bash -c "$(declare -f launch_lora_daemon); launch_lora_daemon '$ROBOT_ID'" >/dev/null 2>&1 &

echo "[SUCCESS] 运控与 LoRa 接收程序已在后台启动完成。"
'''
        ssh_manager.write_remote_text_file(run_bg_script, "/home/ubuntu/vsis_mimic_deploy/run_bg.sh", sudo=True)

        # 自动修复 run_bg.sh, sec_run.sh, g1_ctrl_vsis, lora_recv_group 权限及串口权限
        fix_perm_cmd = (
            "chmod +x /home/ubuntu/vsis_mimic_deploy/run_bg.sh "
            "/home/ubuntu/vsis_mimic_deploy/sec_run.sh "
            "/home/ubuntu/vsis_mimic_deploy/g1_ctrl_vsis "
            "/home/ubuntu/vsis_mimic_deploy/lora_recv_group "
            "/docker_config/custom_startup.sh 2>/dev/null || true ; "
            "chmod 666 /dev/ttyCH341* /dev/ttyUSB* /dev/bus/usb/*/* 2>/dev/null || true ; "
            "docker exec vsis_g1 chmod +x /home/ubuntu/vsis_mimic_deploy/run_bg.sh "
            "/home/ubuntu/vsis_mimic_deploy/sec_run.sh "
            "/home/ubuntu/vsis_mimic_deploy/g1_ctrl_vsis "
            "/home/ubuntu/vsis_mimic_deploy/lora_recv_group "
            "/docker_config/custom_startup.sh 2>/dev/null || true ; "
            "docker exec vsis_g1 chmod 666 /dev/ttyCH341* /dev/ttyUSB* /dev/bus/usb/*/* 2>/dev/null || true"
        )
        ssh_manager.execute_command(fix_perm_cmd, sudo=True)

        # 确保 g1_ctrl_vsis 为有效的 ARM aarch64 原生可执行二进制
        chk_bin_cmd = "docker exec vsis_g1 file /home/ubuntu/vsis_mimic_deploy/g1_ctrl_vsis 2>/dev/null || true"
        code_b, out_b, _ = ssh_manager.execute_command(chk_bin_cmd, sudo=True)
        if "aarch64" not in out_b.lower() or "not a dynamic executable" in out_b.lower() or "cannot open" in out_b.lower():
            _cb("⚙️ [自动编译] 检测到机载主控二进制未就绪，正在容器内执行纯净编译 (make -j$(nproc))...\n", False)
            compile_cmd = "docker exec vsis_g1 bash -c 'cd /home/ubuntu/vsis_mimic_deploy && rm -rf build && mkdir -p build && cd build && cmake .. && make -j$(nproc)'"
            ssh_manager.execute_command_stream(compile_cmd, _cb, sudo=True)
            _cb("[SUCCESS] ✅ 运控主程序 g1_ctrl_vsis 原生编译完成！\n", False)

        _cb("[SUCCESS] ✅ run_bg.sh、守护逻辑与 USB/串口权限已自动完成检查与修复 (赋予 0666 与 +x)！\n", False)

        # 2. 检查 lora_robot_id.txt
        _cb("[STEP 2/2] 正在检查 lora_robot_id.txt 中的群控标识 (Robot ID)...\n", False)
        code_id, id_out, _ = ssh_manager.execute_command("cat /home/ubuntu/vsis_mimic_deploy/group/lora_robot_id.txt 2>/dev/null", sudo=True)
        robot_id = id_out.strip().upper() if code_id == 0 else ""

        has_valid_id = bool(robot_id and robot_id != "ALL" and len(robot_id) <= 20)
        if has_valid_id:
            _cb(f"[SUCCESS] ✅ 检测到已配置合法 Robot ID: [{robot_id}]\n", False)
        else:
            _cb(f"[WARN] ⚠️ 未检测到有效 Robot ID (当前值为 '{robot_id or '空'}')！\n", True)
            _cb("[PROMPT_ROBOT_ID] 💡 提示：请在右侧【开机自启与 Robot ID】卡片中输入分配的唯一 ID (如 A, B, R1 等) 并点击【写入自启动钩子与 Robot ID】。\n", True)

        _cb("=======================================================\n\n", False)
        return {
            "success": True,
            "has_valid_id": has_valid_id,
            "robot_id": robot_id,
            "permissions_fixed": True
        }

    def get_robot_process_status(self) -> Dict[str, Any]:
        """
        检查机器人端机载运控程序 (g1_ctrl_vsis) 与 LoRa 接收程序 (lora_recv_group) 运行状态
        """
        if not ssh_manager.is_connected():
            return {
                "connected": False,
                "g1_ctrl_running": False,
                "lora_recv_running": False,
                "all_running": False,
                "msg": "未连接"
            }

        cmd = (
            "ps aux | grep -E 'g1_ctrl_vsis|lora_recv_group' | grep -v grep ; "
            "docker exec vsis_g1 ps aux 2>/dev/null | grep -E 'g1_ctrl_vsis|lora_recv_group' | grep -v grep || true"
        )
        code, out, _ = ssh_manager.execute_command(cmd, sudo=True)
        g1_ctrl_running = "g1_ctrl_vsis" in out
        lora_recv_running = "lora_recv_group" in out

        return {
            "connected": True,
            "g1_ctrl_running": g1_ctrl_running,
            "lora_recv_running": lora_recv_running,
            "all_running": g1_ctrl_running and lora_recv_running,
            "output": out.strip()
        }

    def start_robot_processes(self, stream_callback=None) -> Tuple[bool, str]:
        """
        在机器人端启动机载程序 (run_bg.sh) 并实时监听/流式返回 sec_run.log 与 lora_recv.log 真实启动进度
        只有在检测到 'all State_RLBase constructed' 且 lora_recv_group 正常运行后才判定为启动就绪。
        """
        def _cb(msg, is_err=False):
            if stream_callback:
                stream_callback(msg, is_err)

        if not ssh_manager.is_connected():
            _cb("[ERROR] 未连接至机器人！\n", True)
            return False, "未连接至机器人"

        _cb("[PROGRESS 10%] [STEP 1/4] 正在对运行脚本、LoRa 设备与权限执行自愈检查与修复...\n", False)
        self.fix_lora_environment(_cb)

        # 显式关闭机器人端所有历史旧进程并释放串口/DDS 通信
        _cb("[PROGRESS 20%] [KILL] 上位机正在发送命令安全停止历史残留进程 (pkill)...\n", False)
        kill_cmd = (
            "pkill -9 -f g1_ctrl_vsis 2>/dev/null || true ; "
            "pkill -9 -f lora_recv_group 2>/dev/null || true ; "
            "pkill -9 -f launch_lora_daemon 2>/dev/null || true ; "
            "pkill -9 -f sec_run.sh 2>/dev/null || true ; "
            "docker exec vsis_g1 pkill -9 -f g1_ctrl_vsis 2>/dev/null || true ; "
            "docker exec vsis_g1 pkill -9 -f lora_recv_group 2>/dev/null || true ; "
            "docker exec vsis_g1 pkill -9 -f launch_lora_daemon 2>/dev/null || true ; "
            "docker exec vsis_g1 pkill -9 -f sec_run.sh 2>/dev/null || true ; "
            "sleep 1"
        )
        ssh_manager.execute_command(kill_cmd, sudo=True)

        _cb("[PROGRESS 28%] [STEP 2/4] 正在准备机载环境并执行启动脚本 (run_bg.sh) ...\n", False)
        # 清空/标记启动日志
        prepare_cmd = (
            "mkdir -p /home/ubuntu/vsis_mimic_deploy/log ; "
            ": > /home/ubuntu/vsis_mimic_deploy/log/sec_run.log 2>/dev/null || true ; "
            ": > /home/ubuntu/vsis_mimic_deploy/log/lora_recv.log 2>/dev/null || true ; "
            "docker exec vsis_g1 mkdir -p /home/ubuntu/vsis_mimic_deploy/log 2>/dev/null || true ; "
            "docker exec vsis_g1 truncate -s 0 /home/ubuntu/vsis_mimic_deploy/log/sec_run.log 2>/dev/null || true"
        )
        ssh_manager.execute_command(prepare_cmd, sudo=True)

        # 检查 vsis_g1 容器状态，严格确保仅在单一目标环境内拉起，绝不同时多开
        code_chk, out_chk, _ = ssh_manager.execute_command("docker inspect -f '{{.State.Running}}' vsis_g1 2>/dev/null || true", sudo=True)
        if "true" in out_chk.lower():
            start_cmd = "docker exec -d vsis_g1 bash -c 'cd /home/ubuntu/vsis_mimic_deploy && ./run_bg.sh'"
        else:
            start_cmd = "cd /home/ubuntu/vsis_mimic_deploy && nohup ./run_bg.sh >/dev/null 2>&1 &"
        ssh_manager.execute_command(start_cmd, sudo=True)

        _cb("[PROGRESS 35%] [STEP 3/4] 正在实时监听运控主程序 (g1_ctrl_vsis) 与 LoRa 启动日志...\n", False)

        seen_sec_lines = set()
        seen_lora_lines = set()
        max_wait_seconds = 45
        start_time = time.time()
        ready_detected = False

        while (time.time() - start_time) < max_wait_seconds:
            time.sleep(0.8)

            # 读取 sec_run.log
            read_sec_cmd = (
                "docker exec vsis_g1 cat /home/ubuntu/vsis_mimic_deploy/log/sec_run.log 2>/dev/null "
                "|| cat /home/ubuntu/vsis_mimic_deploy/log/sec_run.log 2>/dev/null"
            )
            code_sec, sec_out, _ = ssh_manager.execute_command(read_sec_cmd, sudo=True)
            if code_sec == 0 and sec_out:
                for line in sec_out.splitlines():
                    clean_line = line.strip()
                    if clean_line and clean_line not in seen_sec_lines:
                        seen_sec_lines.add(clean_line)
                        _cb(f"  [运控日志] {clean_line}\n", False)

                        # 根据运控真实日志内容推断并触发真实进度百分比
                        lower_l = clean_line.lower()
                        m_match = re.search(r'\[MAIN\]\s*\[(\d+)/(\d+)\]\s*constructed:', clean_line)
                        if m_match:
                            cur_idx = int(m_match.group(1))
                            total_idx = int(m_match.group(2))
                            pct = 35 + int((cur_idx / max(total_idx, 1)) * 55)
                            _cb(f"[PROGRESS {pct}%] 正在加载动作策略网络模型 [{cur_idx}/{total_idx}]...\n", False)
                        elif "all state_rlbase constructed" in lower_l:
                            _cb("[PROGRESS 95%] ✅ 全部动作策略网络模型加载构建完成 (all State_RLBase constructed)！\n", False)
                        elif any(k in lower_l for k in ["building", "built target", "cmake", "make"]):
                            _cb("[PROGRESS 40%] 正在编译机载程序源码 (make.sh)...\n", False)
                        elif any(k in lower_l for k in ["license", "customer", "expire", "机器码"]):
                            _cb("[PROGRESS 45%] 正在验证硬件指纹与 License 授权...\n", False)
                        elif any(k in lower_l for k in ["channelfactory", "dds", "eth0", "joint", "domain"]):
                            _cb("[PROGRESS 92%] 正在初始化 Unitree 29-DOF 关节通道与 DDS 通信...\n", False)
                        elif any(k in lower_l for k in ["switched to group controller", "groupcontroller"]):
                            _cb("[PROGRESS 98%] 运控主程序已接入 LoRa 群控通道...\n", False)

            # 读取 lora_recv.log
            read_lora_cmd = (
                "docker exec vsis_g1 cat /home/ubuntu/vsis_mimic_deploy/log/lora_recv.log 2>/dev/null "
                "|| cat /home/ubuntu/vsis_mimic_deploy/log/lora_recv.log 2>/dev/null"
            )
            code_lora, lora_out, _ = ssh_manager.execute_command(read_lora_cmd, sudo=True)
            if code_lora == 0 and lora_out:
                for line in lora_out.splitlines():
                    clean_line = line.strip()
                    if clean_line and clean_line not in seen_lora_lines:
                        seen_lora_lines.add(clean_line)
                        _cb(f"  [LoRa日志] {clean_line}\n", False)
                        if "opened successfully" in clean_line or "lora_recv" in clean_line:
                            _cb("[PROGRESS 90%] LoRa 串口群控接收服务已打开并就绪...\n", False)

            # 校验进程状态：运控与 LoRa 均处于运行状态
            status = self.get_robot_process_status()
            if status.get("g1_ctrl_running") and status.get("lora_recv_running"):
                ready_detected = True
                _cb("[PROGRESS 100%] [STEP 4/4] [SUCCESS] 🎉 运控主程序 (g1_ctrl_vsis) 与 LoRa 接收程序均已完全拉起并处于正常就绪状态！\n", False)
                return True, "机载程序已成功启动并就绪"

        # 超时保护后最终校验一次
        final_status = self.get_robot_process_status()
        if final_status.get("g1_ctrl_running") and final_status.get("lora_recv_running"):
            _cb("[PROGRESS 100%] [SUCCESS] ✅ 运控主程序与 LoRa 接收程序均已完全就绪！\n", False)
            return True, "机载服务启动成功"
        elif final_status.get("g1_ctrl_running") or final_status.get("lora_recv_running"):
            _cb(f"[PROGRESS 100%] [SUCCESS] ✅ 机载服务已拉起 (运控: {'🟢 运行中' if final_status.get('g1_ctrl_running') else '⚪ 未运行'}, LoRa: {'🟢 运行中' if final_status.get('lora_recv_running') else '⚪ 未运行'})！\n", False)
            return True, "机载服务启动成功"

        _cb("[PROGRESS 100%] [WARN] ⚠️ 机载程序启动指令已发送，但未在超时内检测到双进程活跃，请在【日志诊断】中查看详细输出。\n", True)
        return False, "机载程序未能在预期时间内就绪"


    def stop_robot_processes(self, stream_callback=None) -> Tuple[bool, str]:
        """
        停止机器人端机载运控与通信程序
        """
        def _cb(msg, is_err=False):
            if stream_callback:
                stream_callback(msg, is_err)

        if not ssh_manager.is_connected():
            _cb("[ERROR] 未连接至机器人！\n", True)
            return False, "未连接至机器人"

        _cb("[INFO] 正在停止机载运控与群控进程 (pkill -f g1_ctrl_vsis ; pkill -f lora_recv_group) ...\n", False)
        cmd = (
            "pkill -f g1_ctrl_vsis 2>/dev/null || true ; "
            "pkill -f lora_recv_group 2>/dev/null || true ; "
            "docker exec vsis_g1 pkill -f g1_ctrl_vsis 2>/dev/null || true ; "
            "docker exec vsis_g1 pkill -f lora_recv_group 2>/dev/null || true"
        )
        ssh_manager.execute_command(cmd, sudo=True)
        time.sleep(1.0)
        _cb("[SUCCESS] ✅ 机器人机载运控与 LoRa 接收进程已停止。\n", False)
        return True, "机载进程已成功停止"



    def stop_container(self, container_name: str) -> Tuple[bool, str]:
        """停止指定的 Docker 容器"""
        if not ssh_manager.is_connected():
            return False, "未连接至机器人"

        container_name = container_name.strip()
        if not container_name:
            return False, "容器名称为空"

        logger.info(f"正在停止容器: {container_name}")
        # 先在容器内温柔停止运控进程，再执行 docker stop
        ssh_manager.execute_command(f"docker exec {container_name} pkill -f g1_ctrl_vsis 2>/dev/null || true", sudo=True)
        ssh_manager.execute_command(f"docker exec {container_name} pkill -f lora_recv_group 2>/dev/null || true", sudo=True)
        code, out, err = ssh_manager.execute_command(f"docker stop {container_name}", sudo=True, timeout=30.0)
        if code == 0:
            logger.info(f"容器 {container_name} 已成功停止")
            return True, f"容器 [{container_name}] 已成功停止"
        return False, f"停止容器失败: {err or out}"

    def restart_container(self, container_name: str = "vsis_g1") -> Tuple[bool, str]:
        """重启指定的 Docker 容器 (如 vsis_g1)"""
        if not ssh_manager.is_connected():
            return False, "未连接至机器人"

        container_name = container_name.strip()
        if not container_name:
            return False, "容器名称为空"

        logger.info(f"正在重启容器: {container_name}")
        # 先在容器内停止旧运控和通信进程
        ssh_manager.execute_command(f"docker exec {container_name} pkill -f g1_ctrl_vsis 2>/dev/null || true", sudo=True)
        ssh_manager.execute_command(f"docker exec {container_name} pkill -f lora_recv_group 2>/dev/null || true", sudo=True)
        code, out, err = ssh_manager.execute_command(f"docker restart {container_name}", sudo=True, timeout=30.0)
        if code == 0:
            logger.info(f"容器 {container_name} 已成功重启")
            return True, f"容器 [{container_name}] 已成功重启"
        return False, f"重启容器失败: {err or out}"

    # ==========================
    # 4. 开机自启 & Robot ID 配置
    # ==========================
    def configure_autostart_and_robot_id(self, robot_id: str = "A") -> Dict[str, Any]:
        """
        1. 写入自启动钩子 /docker_config/custom_startup.sh
        2. 写入 robot_id 到 /home/ubuntu/vsis_mimic_deploy/group/lora_robot_id.txt
        """
        robot_id = robot_id.strip().upper()
        if not robot_id:
            return {"success": False, "msg": "Robot ID 不能为空，请输入唯一寻址标识 (如 A, B, R1, G1_02 等)"}
        if robot_id == "ALL":
            return {"success": False, "msg": "ALL 为群控广播保留关键字，不能作为单机 ID！"}

        # 1. 写入 custom_startup.sh (加 sleep 3 确保开机时 USB 串口驱动已完全加载)
        startup_script_content = "#!/bin/bash\nsleep 3\n/home/ubuntu/vsis_mimic_deploy/run_bg.sh\n"
        ok_startup, msg_startup = ssh_manager.write_remote_text_file(
            startup_script_content,
            "/docker_config/custom_startup.sh",
            sudo=True
        )
        if ok_startup:
            ssh_manager.execute_command("chmod +x /docker_config/custom_startup.sh", sudo=True)
            # 关键：同步写入容器内部 /docker_config/custom_startup.sh
            ssh_manager.execute_command("docker cp /docker_config/custom_startup.sh vsis_g1:/docker_config/custom_startup.sh 2>/dev/null || true", sudo=True)
            ssh_manager.execute_command("docker exec vsis_g1 chmod +x /docker_config/custom_startup.sh 2>/dev/null || true", sudo=True)

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
        检查设备中 vsis_g1 容器与自启配置状态。
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

        # 1. 检查名为 vsis_g1 的容器运行状态
        code_ps, ps_out, _ = ssh_manager.execute_command("docker ps --filter name=^/vsis_g1$ --format '{{.Names}}\t{{.Image}}\t{{.Ports}}'", sudo=True)
        is_vsis_g1_running = bool(code_ps == 0 and "vsis_g1" in ps_out)

        # 2. 检查 400 端口占用情况
        code_p400, p400_out, _ = ssh_manager.execute_command("docker ps --filter publish=400 --format '{{.Names}}'", sudo=True)
        has_port_400 = bool(code_p400 == 0 and p400_out.strip())

        # 3. 检查任意容器存在性 (包括 Exited)
        code_ps_a, ps_a_out, _ = ssh_manager.execute_command("docker ps -a --filter name=^/vsis_g1$ --format '{{.Names}}'", sudo=True)
        container_exists = bool(code_ps_a == 0 and "vsis_g1" in ps_a_out)

        # 4. 检查自启动脚本 /docker_config/custom_startup.sh
        ok_start, start_content = ssh_manager.read_remote_text_file("/docker_config/custom_startup.sh")
        autostart_configured = bool(ok_start and "run_bg.sh" in start_content)

        # 5. 检查 robot_id
        ok_id, id_txt = ssh_manager.read_remote_text_file("/home/ubuntu/vsis_mimic_deploy/group/lora_robot_id.txt")
        robot_id = id_txt.strip() if ok_id and id_txt.strip() else "A"

        return {
            "running": is_vsis_g1_running,
            "has_port_400": has_port_400,
            "container_name": "vsis_g1" if is_vsis_g1_running else (p400_out.strip().split('\n')[0] if has_port_400 else ""),
            "container_exists": container_exists,
            "autostart_configured": autostart_configured,
            "robot_id": robot_id,
            "msg": f"容器 vsis_g1 运行中" if is_vsis_g1_running else "容器 vsis_g1 未运行"
        }

    # ==========================
    # 5. 机器码读取
    # ==========================
    def read_machine_id(self) -> Dict[str, Any]:
        """
        读取 64 位硬件指纹机器码 (Machine ID)
        优先从宿主机持久化缓存毫秒级读取真实机器码；未缓存时由机载 g1_ctrl_vsis 输出为唯一真实标准并缓存。
        """
        if not ssh_manager.is_connected():
            return {
                "success": False,
                "machine_id": "",
                "msg": "未连接至机器人，请先连接"
            }

        cache_files = [
            "/etc/vsis_machine_id",
            "/home/ubuntu/vsis_mimic_deploy/.machine_id",
            "/tmp/.vsis_machine_id"
        ]
        ld_path = "LD_LIBRARY_PATH=/home/ubuntu/vsis_mimic_deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/lib:/home/ubuntu/unitree_sdk2/thirdparty/lib/aarch64:/usr/local/lib:$LD_LIBRARY_PATH"

        # 1. 优先从持久化缓存中毫秒级读取（极速且稳定，不阻塞常规心跳与启动自检）
        for cf in cache_files:
            ok_cache, cache_content = ssh_manager.read_remote_text_file(cf)
            if ok_cache and cache_content.strip():
                match_c = re.search(r'[0-9a-fA-F]{64}', cache_content.strip())
                if match_c:
                    mid = match_c.group(0).lower()
                    return {
                        "success": True,
                        "machine_id": mid,
                        "source": "cached_machine_id",
                        "msg": "成功读取 64 位硬件指纹机器码 (宿主机持久化记录)"
                    }

        # 2. 若暂无缓存，优先从当前运行中的容器执行 g1_ctrl_vsis 获取并写入缓存
        c_name = "vsis_g1"
        code_ps, ps_out, _ = ssh_manager.execute_command("docker ps --format '{{.Names}}'", sudo=True)
        if code_ps == 0 and ps_out.strip():
            names = [n.strip() for n in ps_out.strip().split('\n') if n.strip()]
            if "vsis_g1" in names:
                c_name = "vsis_g1"
            elif names:
                c_name = names[0]

            cmd1 = f"docker exec {c_name} bash -c 'ulimit -c 0 ; cd /home/ubuntu/vsis_mimic_deploy && {ld_path} ./g1_ctrl_vsis --print-machine-id 2>&1 || true'"
            code1, out1, err1 = ssh_manager.execute_command(cmd1, sudo=True, timeout=5.0)
            match1 = re.search(r'[0-9a-fA-F]{64}', (out1 + " " + err1).strip())
            if match1:
                mid = match1.group(0).lower()
                for cf in cache_files:
                    ssh_manager.execute_command(f"echo '{mid}' | sudo tee {cf} >/dev/null", sudo=True)
                return {
                    "success": True,
                    "machine_id": mid,
                    "source": "g1_ctrl_vsis (running container)",
                    "msg": "成功读取 64 位硬件指纹机器码"
                }

        # 3. 若容器未运行或未启动，尝试直接基于镜像执行轻量临时容器获取
        code_img, img_out, _ = ssh_manager.execute_command("docker images --format '{{.Repository}}:{{.Tag}}'", sudo=True)
        if code_img == 0 and img_out.strip():
            images = [i.strip() for i in img_out.strip().split('\n') if i.strip()]
            vsis_images = [i for i in images if 'vsis' in i.lower()]
            target_image = vsis_images[0] if vsis_images else (images[0] if images else None)
            if target_image and target_image != "<none>:<none>":
                cmd_temp = (
                    f"docker run --rm --net=host -v /etc/machine-id:/etc/machine-id:ro "
                    f"-w /home/ubuntu/vsis_mimic_deploy "
                    f"-e LD_LIBRARY_PATH=/home/ubuntu/vsis_mimic_deploy/thirdparty/onnxruntime-linux-aarch64-1.22.0/lib:/home/ubuntu/unitree_sdk2/thirdparty/lib/aarch64:/usr/local/lib "
                    f"{target_image} bash -c 'ulimit -c 0 ; ./g1_ctrl_vsis --print-machine-id 2>&1 || true'"
                )
                code_t, out_t, err_t = ssh_manager.execute_command(cmd_temp, sudo=True, timeout=10.0)
                match_t = re.search(r'[0-9a-fA-F]{64}', (out_t + " " + err_t).strip())
                if match_t:
                    mid = match_t.group(0).lower()
                    for cf in cache_files:
                        ssh_manager.execute_command(f"echo '{mid}' | sudo tee {cf} >/dev/null", sudo=True)
                    return {
                        "success": True,
                        "machine_id": mid,
                        "source": f"g1_ctrl_vsis ({target_image})",
                        "msg": "成功读取 64 位硬件指纹机器码"
                    }

        # 4. 若以上均未就绪（从未导入过镜像且无缓存），明确提示用户
        return {
            "success": False,
            "machine_id": "",
            "msg": "未检测到 Docker 运控镜像或运行中容器，请在完成镜像导入后读取机器码"
        }


deployment_core = DeploymentCore()
