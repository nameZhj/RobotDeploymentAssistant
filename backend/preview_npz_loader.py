import os
import numpy as np
from typing import Any, Dict, List, Optional
from backend.npz_service import G1_30_LINK_NAMES, G1_30_BONE_PAIRS, G1_JOINT_NAMES, G1_BONE_PAIRS


class PreviewNpzLoader:
    """NPZ 动捕动作数据加载与骨骼插值"""

    @staticmethod
    def load_npz_motion(npz_path: str) -> Dict[str, Any]:
        data = np.load(npz_path, allow_pickle=True)
        fps = int(data.get("fps", 50))
        dof_pos = data.get("dof_pos")
        root_pos = data.get("root_pos")
        root_rot = data.get("root_rot")

        total_frames = len(dof_pos) if dof_pos is not None else 0
        duration = round(total_frames / fps, 2) if fps > 0 else 0

        pelvis_trajectories = []
        joint_trajectories = []

        for i in range(total_frames):
            pos = root_pos[i].tolist() if root_pos is not None else [0.0, 0.0, 0.76]
            rot = root_rot[i].tolist() if root_rot is not None else [0.0, 0.0, 0.0, 1.0]
            pelvis_trajectories.append({"pos": pos, "rot": rot})

            frame_joints = {}
            if dof_pos is not None and len(dof_pos[i]) >= len(G1_JOINT_NAMES):
                for j_idx, j_name in enumerate(G1_JOINT_NAMES):
                    frame_joints[j_name] = float(dof_pos[i][j_idx])
            joint_trajectories.append(frame_joints)

        return {
            "fps": fps,
            "total_frames": total_frames,
            "duration_seconds": duration,
            "pelvis_trajectory": pelvis_trajectories,
            "joint_trajectory": joint_trajectories,
            "bones": G1_BONE_PAIRS,
            "link_names": G1_30_LINK_NAMES,
        }


preview_npz_loader = PreviewNpzLoader()

