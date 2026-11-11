"""
@file: src/domain/stage/sketch_and_audio_helper.py
@brief: 2D/3D 舞台草图笔轨迹辅助绘制与音频波形提取解析器
@exports: StageSketchManager, AudioWaveHelper
"""
import math
import os
import struct
from typing import Any, Dict, List, Optional, Tuple
import wave


class StageSketchManager:
    """舞台自由手绘草图笔画管理器，与正式轨迹物理隔离"""

    def __init__(self) -> None:
        self.strokes: List[List[Tuple[float, float]]] = []
        self._current_stroke: List[Tuple[float, float]] = []

    def begin_stroke(self) -> None:
        self._current_stroke = []

    def add_point(self, x: float, y: float) -> None:
        self._current_stroke.append((round(float(x), 3), round(float(y), 3)))

    def end_stroke(self) -> None:
        if len(self._current_stroke) >= 2:
            self.strokes.append(self._current_stroke)
        self._current_stroke = []

    def undo_stroke(self) -> bool:
        if not self.strokes:
            return False
        self.strokes.pop()
        return True

    def clear_strokes(self) -> None:
        self.strokes.clear()
        self._current_stroke = []

    def get_strokes(self) -> List[List[Tuple[float, float]]]:
        return [list(s) for s in self.strokes]


class AudioWaveHelper:
    """读取 WAV 音频时长与振幅包络，提供离散峰值点供时间轴渲染"""

    @classmethod
    def generate_synthetic_waveform(cls, duration_s: float = 120.0,
                                    num_peaks: int = 100) -> List[float]:
        peaks: List[float] = []
        for i in range(num_peaks):
            phase = (i / max(1, num_peaks - 1)) * 20.0
            val = 0.35 + 0.45 * math.sin(phase) * math.cos(phase * 0.4)
            peaks.append(round(max(0.05, min(1.0, abs(val))), 3))
        return peaks

    @classmethod
    def get_audio_info(cls, file_path: Optional[str],
                       num_peaks: int = 100) -> Dict[str, Any]:
        if not file_path or not os.path.exists(file_path):
            return {
                "duration_s": 120.0, "sample_rate": 44100,
                "peaks": cls.generate_synthetic_waveform(120.0, num_peaks),
                "is_synthetic": True
            }
        try:
            with wave.open(file_path, "rb") as wf:
                channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                framerate = wf.getframerate()
                n_frames = wf.getnframes()
                duration_s = round(n_frames / float(framerate), 2)
                raw_bytes = wf.readframes(n_frames)
                fmt = f"<{n_frames * channels}h" if sampwidth == 2 else f"<{n_frames * channels}b"
                samples = struct.unpack(fmt, raw_bytes[:n_frames * channels * sampwidth])
                mono = [abs(samples[i]) for i in range(0, len(samples), channels)]
                chunk_size = max(1, len(mono) // num_peaks)
                max_amp = float(max(mono)) if mono and max(mono) > 0 else 1.0
                peaks = [
                    round(max(mono[i:i + chunk_size]) / max_amp, 3)
                    for i in range(0, len(mono), chunk_size)
                ][:num_peaks]
                return {
                    "duration_s": duration_s, "sample_rate": framerate,
                    "peaks": peaks, "is_synthetic": False
                }
        except Exception:
            return {
                "duration_s": 120.0, "sample_rate": 44100,
                "peaks": cls.generate_synthetic_waveform(120.0, num_peaks),
                "is_synthetic": True
            }

