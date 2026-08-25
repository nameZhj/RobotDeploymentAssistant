import os
import math
import numpy as np
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("NPZService")


# 宇树 G1 标准 21 关节点定义
G1_JOINT_NAMES = [
    "pelvis",        # 0: 骨盆/根节点
    "spine",         # 1: 脊椎
    "torso",         # 2: 胸腔
    "neck",          # 3: 颈部
    "head",          # 4: 头部
    "left_shoulder", # 5: 左肩
    "left_elbow",    # 6: 左肘
    "left_wrist",    # 7: 左手腕
    "left_hand",     # 8: 左手
    "right_shoulder",# 9: 右肩
    "right_elbow",   # 10: 右肘
    "right_wrist",   # 11: 右手腕
    "right_hand",    # 12: 右手
    "left_hip",      # 13: 左髋
    "left_knee",     # 14: 左膝
    "left_ankle",    # 15: 左踝
    "left_foot",     # 16: 左脚尖
    "right_hip",     # 17: 右髋
    "right_knee",    # 18: 右膝
    "right_ankle",   # 19: 右踝
    "right_foot"     # 20: 右脚尖
]

# 21 关节标准骨骼拓扑
G1_BONE_PAIRS = [
    [0, 1], [1, 2], [2, 3], [3, 4],     # 躯干主干
    [2, 5], [5, 6], [6, 7], [7, 8],     # 左臂
    [2, 9], [9, 10], [10, 11], [11, 12], # 右臂
    [0, 13], [13, 14], [14, 15], [15, 16], # 左腿
    [0, 17], [17, 18], [18, 19], [19, 20]  # 右腿
]

# 宇树 G1 29-DOF 真实机器人 30 刚体连杆名称
G1_30_LINK_NAMES = [
    "pelvis",               # 0
    "left_hip_pitch",       # 1
    "right_hip_pitch",      # 2
    "waist_yaw",            # 3
    "left_hip_roll",        # 4
    "right_hip_roll",       # 5
    "waist_roll",           # 6
    "left_hip_yaw",         # 7
    "right_hip_yaw",        # 8
    "torso",                # 9
    "left_knee",            # 10
    "right_knee",           # 11
    "left_shoulder_pitch",  # 12
    "right_shoulder_pitch", # 13
    "left_ankle_pitch",     # 14
    "right_ankle_pitch",    # 15
    "left_shoulder_roll",   # 16
    "right_shoulder_roll",  # 17
    "left_ankle_roll",      # 18
    "right_ankle_roll",     # 19
    "left_shoulder_yaw",    # 20
    "right_shoulder_yaw",   # 21
    "left_elbow",           # 22
    "right_elbow",          # 23
    "left_wrist_roll",      # 24
    "right_wrist_roll",     # 25
    "left_wrist_pitch",     # 26
    "right_wrist_pitch",    # 27
    "left_wrist_yaw",       # 28
    "right_wrist_yaw"       # 29
]

# 宇树 G1 29-DOF 真实 30 刚体骨骼拓扑 (精确非零运动学连通树)
G1_30_BONE_PAIRS = [
    # 躯干与胸腔 (0: pelvis -> 6: waist_roll -> 12, 13: shoulders)
    [0, 6], [6, 12], [6, 13], [12, 13],
    # 左腿 (0 -> 1 -> 4 -> 7 -> 10 -> 14 -> 18)
    [0, 1], [1, 4], [4, 7], [7, 10], [10, 14], [14, 18],
    # 右腿 (0 -> 2 -> 5 -> 8 -> 11 -> 15 -> 19)
    [0, 2], [2, 5], [5, 8], [8, 11], [11, 15], [15, 19],
    # 左臂 (12 -> 16 -> 20 -> 22 -> 24 -> 26 -> 28)
    [12, 16], [16, 20], [20, 22], [22, 24], [24, 26], [26, 28],
    # 右臂 (13 -> 17 -> 21 -> 23 -> 25 -> 27 -> 29)
    [13, 17], [17, 21], [21, 23], [23, 25], [25, 27], [27, 29]
]


class NPZService:
    """3D 舞蹈 NPZ 动作数据解析与仿真动作序列生成器"""

    def __init__(self, demo_dir: str = ""):
        import sys
        if getattr(sys, 'frozen', False):
            base_root = sys._MEIPASS
        else:
            base_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.demo_dir = demo_dir or os.path.join(base_root, "web", "assets", "demo_dances")
        os.makedirs(self.demo_dir, exist_ok=True)

    def parse_npz_file(self, npz_path: str) -> Dict[str, Any]:
        """
        读取并解析 .npz 文件，提取 50fps 3D 关节坐标轨迹
        """
        if not os.path.exists(npz_path):
            return {"success": False, "msg": f"NPZ 文件不存在: {npz_path}"}

        try:
            data = np.load(npz_path, allow_pickle=True)
            files = data.files
            
            fps = 50.0
            if "fps" in files:
                try:
                    fps_val = data["fps"]
                    if hasattr(fps_val, "item"):
                        fps = float(fps_val.item())
                    elif hasattr(fps_val, "__len__") and len(fps_val) > 0:
                        fps = float(fps_val[0])
                    else:
                        fps = float(fps_val)
                except Exception:
                    fps = 50.0

            # 寻找关键点矩阵：常见键名 pos, positions, joints, keypoints, body_pos, x, body_pos_w
            keypoint_key = None
            candidate_keys = ["body_pos_w", "positions", "joints", "keypoints", "pos", "body_pos", "x", "motion", "joint_pos"]
            
            # 1. 精确匹配
            for k in candidate_keys:
                if k in files:
                    keypoint_key = k
                    break
            
            # 2. 模糊匹配
            if keypoint_key is None:
                for f_key in files:
                    for k in candidate_keys:
                        if k in f_key.lower():
                            keypoint_key = f_key
                            break
                    if keypoint_key:
                        break

            # 3. 维度匹配兜底 (寻找维度为3且最后一维为3的数组，或维度为2的运动数组)
            if keypoint_key is None:
                for f_key in files:
                    if hasattr(data[f_key], 'ndim') and data[f_key].ndim == 3 and data[f_key].shape[2] == 3:
                        keypoint_key = f_key
                        break
                if keypoint_key is None:
                    for f_key in files:
                        if hasattr(data[f_key], 'ndim') and data[f_key].ndim == 2 and data[f_key].shape[0] > 1:
                            keypoint_key = f_key
                            break
                if keypoint_key is None:
                    keypoint_key = files[0]

            arr = data[keypoint_key]
            # 维度适配: 期望 (Frames, Joints, 3)
            if arr.ndim == 2:
                # 若为 (Frames, Joints*3)
                n_frames = arr.shape[0]
                n_joints = arr.shape[1] // 3
                arr = arr.reshape(n_frames, n_joints, 3)
            elif arr.ndim == 3:
                pass
            else:
                return {"success": False, "msg": f"不支持的数组维度: {arr.shape}"}

            n_frames, n_joints, _ = arr.shape
            duration = round(n_frames / fps, 2)

            # 转换为前端方便消费的浮点列表
            frames_data = arr.round(4).tolist()

            # 舞蹈名称
            dance_name = os.path.splitext(os.path.basename(npz_path))[0]

            # 根据关节数量自动适配骨骼拓扑与连杆命名
            if n_joints >= 29:
                joint_names = G1_30_LINK_NAMES[:n_joints] if n_joints <= len(G1_30_LINK_NAMES) else [f"joint_{i}" for i in range(n_joints)]
                bone_pairs = G1_30_BONE_PAIRS
            else:
                joint_names = G1_JOINT_NAMES[:n_joints] if n_joints <= len(G1_JOINT_NAMES) else [f"joint_{i}" for i in range(n_joints)]
                bone_pairs = G1_BONE_PAIRS

            return {
                "success": True,
                "dance_name": dance_name,
                "fps": fps,
                "total_frames": n_frames,
                "duration_seconds": duration,
                "joint_count": n_joints,
                "joint_names": joint_names,
                "bone_pairs": bone_pairs,
                "frames": frames_data
            }

        except Exception as e:
            logger.error(f"解析 NPZ 失败: {e}")
            return {"success": False, "msg": f"NPZ 解析异常: {str(e)}"}

    def _ensure_demo_npz_files(self):
        """生成内置的标准演示舞蹈动作 NPZ 文件 (50fps)"""
        dances = [
            ("G1_TIKTOK", "抖音热曲魔性摇摆舞", self._generate_tiktok_motion),
            ("G1_TURN_JUMP", "旋转跳跃与空中变向", self._generate_turn_jump_motion),
            ("G1_MOONWALK", "太空漫步与滑步滑行", self._generate_moonwalk_motion),
            ("G2_WAVE", "机械波浪与手臂律动", self._generate_wave_motion),
            ("G3_CYBER", "赛博重节拍与全身震感", self._generate_cyber_motion),
            ("G1_KUNG_FU", "国风太极抱拳开合式", self._generate_kungfu_motion),
        ]

        for name, desc, gen_func in dances:
            npz_file = os.path.join(self.demo_dir, f"{name}.npz")
            if not os.path.exists(npz_file):
                logger.info(f"生成演示舞蹈 NPZ: {name} ({desc})")
                frames = gen_func()
                np.savez_compressed(npz_file, positions=frames, fps=50.0, dance_name=name, description=desc)

    def list_demo_dances(self) -> List[Dict[str, Any]]:
        """获取所有内置及已存的演示舞蹈列表"""
        res = []
        if not os.path.exists(self.demo_dir):
            return res

        for f in os.listdir(self.demo_dir):
            if f.endswith(".npz"):
                path = os.path.join(self.demo_dir, f)
                info = self.parse_npz_file(path)
                if info.get("success"):
                    res.append({
                        "id": os.path.splitext(f)[0],
                        "filename": f,
                        "name": os.path.splitext(f)[0],
                        "duration": info.get("duration_seconds", 0),
                        "frames": info.get("total_frames", 0),
                        "fps": info.get("fps", 50.0)
                    })
        return res

    # ==========================
    # 动作运动学轨迹生成算法 (50fps)
    # ==========================
    def _create_base_pose(self) -> np.ndarray:
        """G1 机器人标准站立姿态 (21 关节 x 3D 空间坐标, 单位: 米)"""
        # 身高约 1.30 米 (Unitree G1 真实尺寸)
        pose = np.zeros((21, 3), dtype=np.float32)
        pose[0] = [0.0, 0.0, 0.70]     # pelvis (0)
        pose[1] = [0.0, 0.0, 0.85]     # spine (1)
        pose[2] = [0.0, 0.0, 1.05]     # torso (2)
        pose[3] = [0.0, 0.0, 1.18]     # neck (3)
        pose[4] = [0.0, 0.0, 1.30]     # head (4)

        # 左臂
        pose[5] = [-0.18, 0.0, 1.05]   # L shoulder (5)
        pose[6] = [-0.22, 0.0, 0.80]   # L elbow (6)
        pose[7] = [-0.24, 0.0, 0.58]   # L wrist (7)
        pose[8] = [-0.25, 0.0, 0.50]   # L hand (8)

        # 右臂
        pose[9] = [0.18, 0.0, 1.05]    # R shoulder (9)
        pose[10] = [0.22, 0.0, 0.80]   # R elbow (10)
        pose[11] = [0.24, 0.0, 0.58]   # R wrist (11)
        pose[12] = [0.25, 0.0, 0.50]   # R hand (12)

        # 左腿
        pose[13] = [-0.10, 0.0, 0.68]  # L hip (13)
        pose[14] = [-0.10, 0.0, 0.36]  # L knee (14)
        pose[15] = [-0.10, 0.0, 0.08]  # L ankle (15)
        pose[16] = [-0.10, 0.12, 0.02] # L foot (16)

        # 右腿
        pose[17] = [0.10, 0.0, 0.68]   # R hip (17)
        pose[18] = [0.10, 0.0, 0.36]   # R knee (18)
        pose[19] = [0.10, 0.0, 0.08]   # R ankle (19)
        pose[20] = [0.10, 0.12, 0.02]  # R foot (20)

        return pose

    def _generate_tiktok_motion(self, duration_sec: float = 6.0, fps: float = 50.0) -> np.ndarray:
        """抖音魔性律动摇摆"""
        n_frames = int(duration_sec * fps)
        frames = np.zeros((n_frames, 21, 3), dtype=np.float32)
        base = self._create_base_pose()

        for t in range(n_frames):
            f = base.copy()
            phase = (t / fps) * 2.0 * math.pi * 1.5 # 1.5 Hz 节拍
            
            # 骨盆左右摇摆与轻微上下弹跳
            pelvis_x = 0.08 * math.sin(phase)
            pelvis_z = -0.04 * abs(math.sin(phase * 2))
            f[0:5, 0] += pelvis_x
            f[0:5, 2] += pelvis_z

            # 双手在胸前做卡点波浪律动
            arm_swing = 0.25 * math.sin(phase)
            f[6, 1] += 0.25 + 0.1 * math.sin(phase)
            f[6, 2] += 0.15 + 0.08 * math.cos(phase)
            f[7, 1] += 0.35 + 0.12 * math.sin(phase + 0.5)
            f[7, 2] += 0.25 + 0.10 * math.cos(phase + 0.5)
            f[8, 1] = f[7, 1] + 0.08
            f[8, 2] = f[7, 2]

            f[10, 1] += 0.25 - 0.1 * math.sin(phase)
            f[10, 2] += 0.15 - 0.08 * math.cos(phase)
            f[11, 1] += 0.35 - 0.12 * math.sin(phase + 0.5)
            f[11, 2] += 0.25 - 0.10 * math.cos(phase + 0.5)
            f[12, 1] = f[11, 1] + 0.08
            f[12, 2] = f[11, 2]

            # 双脚随节奏轻点
            f[14, 2] += 0.03 * math.sin(phase)
            f[18, 2] -= 0.03 * math.sin(phase)

            frames[t] = f

        return frames

    def _generate_turn_jump_motion(self, duration_sec: float = 5.0, fps: float = 50.0) -> np.ndarray:
        """旋转跳跃动作"""
        n_frames = int(duration_sec * fps)
        frames = np.zeros((n_frames, 21, 3), dtype=np.float32)
        base = self._create_base_pose()

        for t in range(n_frames):
            f = base.copy()
            progress = (t / n_frames) * 2.0 * math.pi
            
            # 跳起高度
            jump_h = 0.25 * max(0.0, math.sin(progress * 2))
            f[:, 2] += jump_h

            # 身体旋转 (绕 Z 轴)
            angle = progress * 2.0
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)

            for j in range(21):
                x = f[j, 0]
                y = f[j, 1]
                f[j, 0] = x * cos_a - y * sin_a
                f[j, 1] = x * sin_a + y * cos_a

            # 手臂张开高举
            f[6, 2] += 0.3 * math.sin(progress)
            f[10, 2] += 0.3 * math.sin(progress)

            frames[t] = f

        return frames

    def _generate_moonwalk_motion(self, duration_sec: float = 6.0, fps: float = 50.0) -> np.ndarray:
        """太空滑步"""
        n_frames = int(duration_sec * fps)
        frames = np.zeros((n_frames, 21, 3), dtype=np.float32)
        base = self._create_base_pose()

        for t in range(n_frames):
            f = base.copy()
            phase = (t / fps) * 2.0 * math.pi * 0.8
            
            # 后退位移
            backward = -0.15 * math.sin(phase)
            f[:, 1] += backward

            # 经典压脚尖滑步
            f[15, 2] += 0.08 * max(0.0, math.sin(phase))
            f[16, 2] += 0.02 * max(0.0, math.sin(phase))

            f[19, 2] += 0.08 * max(0.0, -math.sin(phase))
            f[20, 2] += 0.02 * max(0.0, -math.sin(phase))

            # 手臂摆动
            f[6, 1] += 0.2 * math.cos(phase)
            f[10, 1] -= 0.2 * math.cos(phase)

            frames[t] = f

        return frames

    def _generate_wave_motion(self, duration_sec: float = 5.0, fps: float = 50.0) -> np.ndarray:
        """机械臂波浪舞"""
        n_frames = int(duration_sec * fps)
        frames = np.zeros((n_frames, 21, 3), dtype=np.float32)
        base = self._create_base_pose()

        for t in range(n_frames):
            f = base.copy()
            phase = (t / fps) * 2.0 * math.pi * 1.2

            # 两臂侧平举
            f[6, 0] = -0.40
            f[6, 2] = 1.05 + 0.15 * math.sin(phase)
            f[7, 0] = -0.60
            f[7, 2] = 1.05 + 0.18 * math.sin(phase + 0.8)
            f[8, 0] = -0.70
            f[8, 2] = 1.05 + 0.20 * math.sin(phase + 1.2)

            f[10, 0] = 0.40
            f[10, 2] = 1.05 + 0.15 * math.sin(phase + math.pi)
            f[11, 0] = 0.60
            f[11, 2] = 1.05 + 0.18 * math.sin(phase + math.pi + 0.8)
            f[12, 0] = 0.70
            f[12, 2] = 1.05 + 0.20 * math.sin(phase + math.pi + 1.2)

            frames[t] = f

        return frames

    def _generate_cyber_motion(self, duration_sec: float = 5.5, fps: float = 50.0) -> np.ndarray:
        """赛博朋克重节拍震感舞"""
        n_frames = int(duration_sec * fps)
        frames = np.zeros((n_frames, 21, 3), dtype=np.float32)
        base = self._create_base_pose()

        for t in range(n_frames):
            f = base.copy()
            beat = (t % 25) / 25.0
            decay = math.exp(-beat * 6.0)
            
            # 瞬间重拍下顿
            f[:, 2] -= 0.08 * decay
            f[6:9, 1] += 0.25 * decay
            f[10:13, 1] += 0.25 * decay

            frames[t] = f

        return frames

    def _generate_kungfu_motion(self, duration_sec: float = 6.0, fps: float = 50.0) -> np.ndarray:
        """太极武术开合"""
        n_frames = int(duration_sec * fps)
        frames = np.zeros((n_frames, 21, 3), dtype=np.float32)
        base = self._create_base_pose()

        for t in range(n_frames):
            f = base.copy()
            phase = (t / fps) * 2.0 * math.pi * 0.6

            # 马步微沉
            squat = 0.12 * (1.0 - math.cos(phase))
            f[:, 2] -= squat
            f[13:17, 0] -= 0.08
            f[17:21, 0] += 0.08

            # 双手行云流水画圆抱球
            r = 0.25
            f[7, 0] = -0.15 + r * math.cos(phase)
            f[7, 1] = 0.30
            f[7, 2] = 0.95 + r * math.sin(phase)
            f[8] = f[7] + [0.05, 0.05, 0.0]

            f[11, 0] = 0.15 - r * math.cos(phase)
            f[11, 1] = 0.30
            f[11, 2] = 0.95 - r * math.sin(phase)
            f[12] = f[11] + [-0.05, 0.05, 0.0]

            frames[t] = f

        return frames


npz_service = NPZService()
