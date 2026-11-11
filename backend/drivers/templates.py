"""
Templates and source patches for robot drivers and daemon configurations.
"""

DEFAULT_LORA_RECV_GROUP_YAML = '''serial:
  baud: 9600              # CH341 <-> E22 波特率
  e22_settle_ms: 200      # DTR/RTS 复位后等 E22 醒来的时间
  usb_reset_timeout_ms: 0 # 关闭破坏性 USB 复位，避免通信句柄丢失
dds:
  topic: rt/groupcontroller   # 虚拟手柄 DDS topic
  publish_hz: 50.0
motion:
  forward_axis: 0.60      # 前后速度比 [-1,1]
  lateral_axis: 0.50      # 横移速度比
  turn_axis: 0.70         # 转向速度比
  default_move_seconds: 0.2
dance_map:                # 33 个标准舞蹈动作映射
  # Group 1: select key L1
  G1_TURN_JUMP:    [L1, DOWN]     # 转身跳跃 RL_Mimic_CMU_83_58
  G1_FRONT_FLIP:   [L1, RIGHT]    # 前空翻 RL_Mimic_CMU_85_07
  G1_SIDE_FLIP:    [L1, A]        # 侧空翻 RL_Mimic_CMU_90_08
  G1_CARTWHEEL:    [L1, B]        # 侧手翻 RL_Mimic_CMU_90_03
  G1_TIKTOK:       [L1, X]        # 抖音舞蹈1 RL_Mimic_TikTok_dance1_30fps
  G1_TAIJI:        [L1, Y]        # 太极 RL_Mimic_CMU_12_04
  G1_ROLL_BACK:    [L1, SELECT]   # 地面滚动-后向 RL_Mimic_CMU_90_01
  G1_GYMNASTICS:   [L1, F1]       # 单腿支撑+旋转体操 RL_Mimic_CMU_05_05
  G1_RUN:          [L1, F3]       # soma 奔跑 RL_Mimic_soma_g1_running_120fps
  G1_CXK:          [L1, START]    # ikun RL_Mimic_cxk_dance
  G1_JUMP:         [L1, L2]       # 双腿跳+单腿跳 RL_Mimic_CMU_49_02
  G1_OPPO:         [L1, R1]       # oppo 原地舞蹈 RL_Mimic_oppo_dance2_50fps

  # Group 2: select key R1
  G2_SPIN_KICK:    [R1, DOWN]     # 旋转飞踢-俯身 RL_Mimic_CMU_88_06
  G2_MOONWALK:     [R1, RIGHT]    # 太空步 RL_Mimic_CMU_90_32
  G2_TAIJI:        [R1, A]        # 太极-KungfuAthlete RL_Mimic_taichi_1307
  G2_GYMNASTICS_07: [R1, B]       # 单腿支撑+旋转体操 RL_Mimic_CMU_05_07
  G2_GYMNASTICS_13: [R1, X]       # 单腿支撑+旋转体操 RL_Mimic_CMU_05_13
  G2_GYMNASTICS_19: [R1, Y]       # 单腿支撑+旋转体操 RL_Mimic_CMU_05_19
  G2_GYMNASTICS_20: [R1, SELECT]  # 单腿支撑+旋转体操 RL_Mimic_CMU_05_20
  G2_GOPAK:        [R1, F1]       # 蹲步舞/戈帕克舞 RL_Mimic_CMU_90_30
  G2_FLYING_KICK:  [R1, F3]       # 飞旋踢 RL_Mimic_CMU_90_06
  G2_SPIN_KICK_87: [R1, START]    # 旋转飞踢-俯身 RL_Mimic_CMU_87_01

  # Group 3: select key L2
  G3_DANCE1_S1:    [L2, DOWN]     # D1S1 RL_Mimic_dance1_subject1
  G3_DANCE1_S2:    [L2, RIGHT]    # 查尔斯顿 RL_Mimic_dance1_subject2
  G3_DANCE1_S3:    [L2, A]        # D1S3 RL_Mimic_dance1_subject3
  G3_DANCE2_S1:    [L2, B]        # D2S1 RL_Mimic_dance2_subject1
  G3_DANCE2_S2:    [L2, X]        # D2S2 RL_Mimic_dance2_subject2
  G3_DANCE2_S3:    [L2, Y]        # D2S3 RL_Mimic_dance2_subject3
  G3_DANCE2_S4:    [L2, SELECT]   # 地板动作 RL_Mimic_dance2_subject4
  G3_DANCE2_S5:    [L2, F1]       # D2S5 RL_Mimic_dance2_subject5
  G3_KUNGFU:       [L2, F3]       # 功夫 RL_Mimic_fightAndSports1_subject4
  G3_ROLL_FORWARD: [L2, START]    # 地面滚动-前向 RL_Mimic_CMU_90_34
  G3_FALL_GETUP:   [L2, L1]       # 摔到恢复 RL_Mimic_fallAndGetUp1_subject1
'''

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

