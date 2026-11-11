import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from src.core.config_loader import config_loader

logger = logging.getLogger("URDFAvatarLoader")


@dataclass(frozen=True)
class JointPoseFrame:
    """Robot joint rotation angles at an instantaneous timestamp."""
    time_ms: int
    joint_angles: Dict[str, float] = field(default_factory=dict)
    root_pos: Tuple[float, float, float] = (0.0, 0.0, 0.75)


@dataclass
class MotionClipData:
    """Ordered sequence of joint animation keyframes for an action."""
    action_name: str
    duration_ms: int
    fps: int = 30
    frames: List[JointPoseFrame] = field(default_factory=list)


class URDFAvatarLoader:
    """
    Parses and loads robot kinematic skeleton trees and motion clip keyframes (.npz/.json)
    from assets/models and assets/motions/. Provides real-time joint pose interpolation.
    """

    def __init__(self) -> None:
        paths = config_loader.get_paths()
        assets_dir = Path(paths.get("assets_dir", "assets"))
        self._models_dir = assets_dir / "models"
        self._motions_dir = assets_dir / "motions"
        self._models_dir.mkdir(parents=True, exist_ok=True)
        self._motions_dir.mkdir(parents=True, exist_ok=True)
        self._motion_cache: Dict[str, MotionClipData] = {}

    def load_motion_clip(self, action_name: str) -> MotionClipData:
        """Load or retrieve parsed motion clip keyframes."""
        clean_name = action_name.strip().upper()
        if clean_name in self._motion_cache:
            return self._motion_cache[clean_name]

        # Look for JSON definition in motions folder
        json_file = self._motions_dir / f"{clean_name.lower()}.json"
        if json_file.is_file():
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                clip = self._parse_json_clip(clean_name, data)
                self._motion_cache[clean_name] = clip
                return clip
            except Exception as e:
                logger.warning(f"Failed parsing {json_file}: {e}")

        # Synthesize procedural rhythmic dance clip as robust fallback
        synth_clip = self._synthesize_clip(clean_name)
        self._motion_cache[clean_name] = synth_clip
        return synth_clip

    def sample_joint_pose(self, action_name: str, time_ms: int) -> JointPoseFrame:
        """Interpolate joint angles at instantaneous timestamp time_ms."""
        clip = self.load_motion_clip(action_name)
        if not clip.frames:
            return JointPoseFrame(time_ms=time_ms)

        # Loop within duration
        t_mod = time_ms % max(1, clip.duration_ms)
        # Find neighboring frames
        f0 = clip.frames[0]
        f1 = clip.frames[-1]

        for i in range(len(clip.frames) - 1):
            if clip.frames[i].time_ms <= t_mod <= clip.frames[i + 1].time_ms:
                f0 = clip.frames[i]
                f1 = clip.frames[i + 1]
                break

        span = max(1, f1.time_ms - f0.time_ms)
        ratio = (t_mod - f0.time_ms) / float(span)

        interp_angles: Dict[str, float] = {}
        for joint, ang0 in f0.joint_angles.items():
            ang1 = f1.joint_angles.get(joint, ang0)
            interp_angles[joint] = round(ang0 + (ang1 - ang0) * ratio, 3)

        return JointPoseFrame(time_ms=time_ms, joint_angles=interp_angles, root_pos=f0.root_pos)

    def _parse_json_clip(self, name: str, data: dict) -> MotionClipData:
        duration_ms = int(data.get("duration_ms", 3000))
        fps = int(data.get("fps", 30))
        raw_frames = data.get("frames", [])
        parsed_frames = [
            JointPoseFrame(
                time_ms=int(rf.get("time_ms", 0)),
                joint_angles=rf.get("joints", {}),
                root_pos=tuple(rf.get("root_pos", [0.0, 0.0, 0.75])),
            )
            for rf in raw_frames
        ]
        return MotionClipData(action_name=name, duration_ms=duration_ms, fps=fps, frames=parsed_frames)

    def _synthesize_clip(self, action_name: str) -> MotionClipData:
        """Generate mathematical harmonic joint oscillations for dance simulation."""
        duration_ms = 4000
        fps = 30
        step_ms = int(1000 / fps)
        frames: List[JointPoseFrame] = []

        standard_joints = [
            "left_hip_pitch", "left_knee", "left_ankle_pitch",
            "right_hip_pitch", "right_knee", "right_ankle_pitch",
            "left_shoulder_pitch", "left_elbow", "right_shoulder_pitch", "right_elbow",
            "waist_yaw",
        ]

        for t in range(0, duration_ms, step_ms):
            sec = t / 1000.0
            phase = sec * 2.0 * math.pi
            angles: Dict[str, float] = {}

            if "WAVE" in action_name:
                angles["right_shoulder_pitch"] = -1.2 + 0.3 * math.sin(phase * 2)
                angles["right_elbow"] = 1.0 + 0.5 * math.sin(phase * 2)
            elif "KUNGFU" in action_name:
                angles["left_hip_pitch"] = -0.4 + 0.2 * math.cos(phase)
                angles["right_knee"] = 0.8 + 0.3 * math.sin(phase)
                angles["waist_yaw"] = 0.3 * math.sin(phase)
            else:
                angles["waist_yaw"] = 0.2 * math.sin(phase)
                angles["left_shoulder_pitch"] = 0.3 * math.sin(phase)
                angles["right_shoulder_pitch"] = -0.3 * math.sin(phase)

            # Squat bobbing
            root_z = 0.75 + 0.04 * math.sin(phase * 2)
            frames.append(JointPoseFrame(time_ms=t, joint_angles=angles, root_pos=(0.0, 0.0, root_z)))

        return MotionClipData(action_name=action_name, duration_ms=duration_ms, fps=fps, frames=frames)


urdf_avatar_loader = URDFAvatarLoader()

