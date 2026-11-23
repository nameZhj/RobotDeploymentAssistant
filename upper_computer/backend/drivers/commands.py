"""
VSISLAB 机器人助手 - 下位机与硬件驱动注入命令及配置常量规范库
集中分类管理所有注入到机器人下位机的 Shell 指令、udev 权限规则、C++ 容灾补丁与守护脚本模板
"""

# =========================================================
# 1. Linux 内核驱动状态探测与加载指令
# =========================================================
CH341_DEV_PROBE_CMD = "ls /dev/ttyCH34* 2>/dev/null"
CH341_ALL_SERIAL_DEVS_CMD = "ls -1 /dev/ttyCH34* /dev/ttyUSB* /dev/ttyACM* 2>/dev/null"
CH341_LSMOD_CMD = "lsmod | grep -i ch341"
CH341_MODINFO_CMD = "modinfo ch341 2>/dev/null || find /lib/modules/$(uname -r) -name '*ch341*.ko*' 2>/dev/null"
CH341_MODPROBE_CMD = "modprobe ch341 2>/dev/null || true"

# =========================================================
# 2. Linux 驱动在线自动化编译与安装流水线
# =========================================================
CH341_LINUX_BUILD_PIPELINE = [
    (
        "更新软件包并安装编译工具与内核头文件",
        "DEBIAN_FRONTEND=noninteractive apt-get update && "
        "DEBIAN_FRONTEND=noninteractive apt-get install -y build-essential bc git dkms && "
        "(DEBIAN_FRONTEND=noninteractive apt-get install -y nvidia-l4t-kernel-headers || "
        "DEBIAN_FRONTEND=noninteractive apt-get install -y linux-headers-$(uname -r) || true)"
    ),
    (
        "清理旧版驱动源码目录",
        "rm -rf /tmp/ch341ser_linux"
    ),
    (
        "获取 CH341 官方 Linux 驱动源码",
        "git clone --depth 1 https://github.com/WCHSoftGroup/ch341ser_linux /tmp/ch341ser_linux || "
        "git clone --depth 1 https://gitee.com/mirrors_WCHSoftGroup/ch341ser_linux.git /tmp/ch341ser_linux"
    ),
    (
        "编译驱动模块",
        "cd /tmp/ch341ser_linux/driver && make clean && make"
    ),
    (
        "安装驱动模块",
        "cd /tmp/ch341ser_linux/driver && make install"
    ),
    (
        "加载驱动模块",
        "modprobe ch341"
    ),
    (
        "移除冲突的盲文串口服务 (brltty)",
        "DEBIAN_FRONTEND=noninteractive apt-get purge -y 'brltty*' || true"
    ),
]

# =========================================================
# 3. 下位机 Udev 规则与底层设备读写权限放行
# =========================================================
UDEV_RULES_PATH = "/etc/udev/rules.d/99-ch341-permissions.rules"
UDEV_RULES_CONTENT = (
    'KERNEL=="ttyCH341*", MODE="0666", GROUP="dialout"\n'
    'KERNEL=="ttyUSB*", MODE="0666", GROUP="dialout"\n'
    'KERNEL=="ttyACM*", MODE="0666", GROUP="dialout"\n'
    'SUBSYSTEM=="tty", KERNEL=="ttyCH341USB*", MODE="0666", GROUP="dialout"\n'
    'SUBSYSTEM=="usb", ATTRS{idVendor}=="1a86", MODE="0666", GROUP="dialout"\n'
    'SUBSYSTEM=="usb", ATTR{idVendor}=="1a86", MODE="0666", GROUP="dialout"\n'
    'SUBSYSTEM=="usb", MODE="0666"\n'
)

UDEV_RELOAD_CMD = "udevadm control --reload-rules && udevadm trigger"
USER_GROUPS_CMD = "usermod -a -G dialout,plugdev,tty unitree ; usermod -a -G dialout,plugdev,tty ubuntu 2>/dev/null || true"
CHMOD_DEV_NODES_CMD = "chmod 666 /dev/ttyCH341* /dev/ttyUSB* /dev/ttyACM* /dev/bus/usb/*/* 2>/dev/null || true"

# 关闭破坏性 USB 硬件复位（避免复位导致串口句柄丢失）
YAML_DISABLE_USB_RESET_CMD = (
    "sed -i 's/usb_reset_timeout_ms:.*/usb_reset_timeout_ms: 0/' /home/ubuntu/vsis_mimic_deploy/group/lora_recv_group.yaml 2>/dev/null || true ; "
    "docker exec vsis_g1 sed -i 's/usb_reset_timeout_ms:.*/usb_reset_timeout_ms: 0/' /home/ubuntu/vsis_mimic_deploy/group/lora_recv_group.yaml 2>/dev/null || true"
)

# =========================================================
# 4. 下位机 C++ 串口动态多节点自适应探测容灾补丁
# =========================================================
LORA_SERIAL_SRC_REMOTE_PATH = "/home/ubuntu/vsis_mimic_deploy/group/lora_serial.cpp"
LORA_SERIAL_CONTAINER_PATH = "vsis_g1:/home/ubuntu/vsis_mimic_deploy/group/lora_serial.cpp"

BULLETPROOF_SERIAL_CPP_PATCH = """int TryOpenDevice(const std::string &path)
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

LORA_SERIAL_RECOMPILE_CMD = (
    "docker exec vsis_g1 bash -c 'cd /home/ubuntu/vsis_mimic_deploy && ./make.sh --keep-src' 2>/dev/null "
    "|| (cd /home/ubuntu/vsis_mimic_deploy && ./make.sh --keep-src 2>/dev/null || true)"
)

LORA_RECV_SYNC_CMD = "docker cp vsis_g1:/home/ubuntu/vsis_mimic_deploy/lora_recv_group /home/ubuntu/vsis_mimic_deploy/lora_recv_group 2>/dev/null || true"

# =========================================================
# 5. 下位机开机自启动与进程自愈守护脚本 (run_bg.sh)
# =========================================================
RUN_BG_REMOTE_PATH = "/home/ubuntu/vsis_mimic_deploy/run_bg.sh"

RUN_BG_SCRIPT_TEMPLATE = '''#!/bin/bash
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

CUSTOM_STARTUP_REMOTE_PATH = "/docker_config/custom_startup.sh"
CUSTOM_STARTUP_SCRIPT_TEMPLATE = "#!/bin/bash\nsleep 3\n/home/ubuntu/vsis_mimic_deploy/run_bg.sh\n"

RUN_BG_SYNC_AND_CHMOD_CMD = (
    "chmod +x /home/ubuntu/vsis_mimic_deploy/run_bg.sh /home/ubuntu/vsis_mimic_deploy/sec_run.sh /home/ubuntu/vsis_mimic_deploy/g1_ctrl_vsis /home/ubuntu/vsis_mimic_deploy/lora_recv_group /docker_config/custom_startup.sh 2>/dev/null || true ; "
    "chmod 666 /dev/ttyCH341* /dev/ttyUSB* /dev/ttyACM* /dev/bus/usb/*/* 2>/dev/null || true ; "
    "docker cp /home/ubuntu/vsis_mimic_deploy/. vsis_g1:/home/ubuntu/vsis_mimic_deploy/ 2>/dev/null || true ; "
    "docker exec vsis_g1 chmod +x /home/ubuntu/vsis_mimic_deploy/run_bg.sh /home/ubuntu/vsis_mimic_deploy/sec_run.sh /home/ubuntu/vsis_mimic_deploy/g1_ctrl_vsis /home/ubuntu/vsis_mimic_deploy/lora_recv_group /docker_config/custom_startup.sh 2>/dev/null || true ; "
    "docker exec vsis_g1 chmod 666 /dev/ttyCH341* /dev/ttyUSB* /dev/ttyACM* /dev/bus/usb/*/* 2>/dev/null || true"
)

# 容器内守护拉起 LoRa 接收程序指令
START_LORA_DAEMON_CONTAINER_CMD = (
    "docker exec -d vsis_g1 bash -c '"
    "cd /home/ubuntu/vsis_mimic_deploy && "
    "SERIAL_DEV=$(ls -1 /dev/ttyCH341USB* /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -n 1) ; "
    "[ -z \"$SERIAL_DEV\" ] && SERIAL_DEV=\"/dev/ttyCH341USB0\" ; "
    "ROBOT_ID=$(cat ./group/lora_robot_id.txt 2>/dev/null | tr -d \" \\r\\n\") ; "
    "[ -z \"$ROBOT_ID\" ] && ROBOT_ID=\"A\" ; "
    "chmod 666 /dev/ttyCH341* /dev/ttyUSB* /dev/ttyACM* /dev/bus/usb/*/* 2>/dev/null || true ; "
    "nohup ./lora_recv_group eth0 \"$SERIAL_DEV\" \"$ROBOT_ID\" 0 >> ./log/lora_recv.log 2>&1 &'"
)

# =========================================================
# 6. Windows 上位机 CH341 驱动可执行文件名
# =========================================================
WINDOWS_DRIVER_FILENAMES = ["CH341SER.EXE", "CH340 CH341驱动.exe"]
