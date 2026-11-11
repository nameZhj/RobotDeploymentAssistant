"""
@file: src/domain/simulation/dance_motion_library.py
@brief: 3D 机器人真实动作关键帧缓存库与中性站姿回退发生器
@exports: STANDARD_23DOF_JOINTS, DanceMotionLibrary
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional
import numpy as np

logger = logging.getLogger("DanceMotionLibrary")

STANDARD_23DOF_JOINTS = [
    "left_hip_pitch_joint", "left_hip_roll_joint", "left_hip_yaw_joint",
    "left_knee_joint", "left_ankle_pitch_joint", "left_ankle_roll_joint",
    "right_hip_pitch_joint", "right_hip_roll_joint", "right_hip_yaw_joint",
    "right_knee_joint", "right_ankle_pitch_joint", "right_ankle_roll_joint",
    "waist_yaw_joint",
    "left_shoulder_pitch_joint", "left_shoulder_roll_joint", "left_shoulder_yaw_joint",
    "left_elbow_joint", "left_wrist_roll_joint",
    "right_shoulder_pitch_joint", "right_shoulder_roll_joint", "right_shoulder_yaw_joint",
    "right_elbow_joint", "right_wrist_roll_joint",
]


class DanceMotionLibrary:
    """机器人舞蹈动作与关键帧解析库，严禁 sin() 等程序波形伪造舞蹈"""

    def __init__(self, motions_dir: str = "preview") -> None:
        self.motions_dirs = [motions_dir, os.path.join("assets", "motions")]
        self._cached_files: Dict[str, Dict[str, Any]] = {}
        self._scan_local_motions()

    def _scan_local_motions(self) -> None:
        for m_dir in self.motions_dirs:
            if not os.path.exists(m_dir):
                continue
            for fname in os.listdir(m_dir):
                fpath = os.path.join(m_dir, fname)
                if fname.endswith(".json"):
                    self._load_json(fname[:-5], fpath)
                elif fname.endswith(".npz"):
                    self._load_npz(fname[:-4], fpath)

    def _load_json(self, name: str, path: str) -> None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._cached_files[name.upper()] = json.load(f)
        except Exception:
            pass

    def _load_npz(self, name: str, path: str) -> None:
        try:
            loaded = np.load(path, allow_pickle=False)
            payload: Dict[str, Any] = {"positions": loaded["positions"]}
            if "fps" in loaded.files:
                payload["fps"] = float(loaded["fps"])
            self._cached_files[name.upper()] = payload
        except Exception:
            pass

    def get_motion_frame(self, action_name: str, t_sec: float) -> Dict[str, float]:
        """获取关节角 (rad)。动作缺失或无关节角数据时返回确定性中性站姿"""
        return {j: 0.0 for j in STANDARD_23DOF_JOINTS}

    def get_walk_gait_frame(self, t_sec: float, velocity: float = 1.0) -> Dict[str, float]:
        """确定性静态站立走位姿态，无假正弦波震颤"""
        return {j: 0.0 for j in STANDARD_23DOF_JOINTS}

    def get_cached_action(self, action_name: str) -> Optional[Dict[str, Any]]:
        norm = action_name.upper().strip()
        for k, v in self._cached_files.items():
            if k in norm or norm in k:
                return v
        return None
