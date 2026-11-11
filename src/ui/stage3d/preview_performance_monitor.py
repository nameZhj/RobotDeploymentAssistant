"""
@file: src/ui/stage3d/preview_performance_monitor.py
@brief: 3D 舞台视口离线渲染性能、FPS 与单帧延迟基准监控器
@exports: PreviewPerformanceMonitor, PerformanceBenchmarkReport
"""
import platform
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import numpy as np


@dataclass
class PerformanceBenchmarkReport:
    sample_count: int = 0
    avg_fps: float = 0.0
    min_fps: float = 0.0
    p95_fps: float = 0.0
    avg_frame_time_ms: float = 0.0
    avg_sampling_time_ms: float = 0.0
    platform_info: str = ""
    python_version: str = ""
    backend: str = "QPainter (Software Rasterizer)"


class PreviewPerformanceMonitor:
    """提供高频 60Hz 演播帧渲染耗时统计、P95 抖动分析与性能基准报告"""

    def __init__(self, max_history: int = 300) -> None:
        self.max_history = max_history
        self._frame_times: List[float] = []
        self._sampling_times: List[float] = []
        self._last_tick_time: Optional[float] = None

    def record_sampling_time(self, duration_ms: float) -> None:
        self._sampling_times.append(duration_ms)
        if len(self._sampling_times) > self.max_history:
            self._sampling_times.pop(0)

    def record_frame(self, frame_time_ms: Optional[float] = None) -> None:
        now = time.perf_counter()
        if frame_time_ms is not None:
            dt = frame_time_ms
        elif self._last_tick_time is not None:
            dt = (now - self._last_tick_time) * 1000.0
        else:
            dt = 16.67
        self._last_tick_time = now

        self._frame_times.append(dt)
        if len(self._frame_times) > self.max_history:
            self._frame_times.pop(0)

    def reset(self) -> None:
        self._frame_times.clear()
        self._sampling_times.clear()
        self._last_tick_time = None

    def generate_report(self) -> PerformanceBenchmarkReport:
        if not self._frame_times:
            return PerformanceBenchmarkReport(
                platform_info=platform.platform(),
                python_version=platform.python_version()
            )

        arr = np.array(self._frame_times, dtype=np.float32)
        fps_arr = 1000.0 / np.maximum(arr, 0.1)

        avg_frame_ms = float(np.mean(arr))
        avg_fps = float(np.mean(fps_arr))
        min_fps = float(np.min(fps_arr))
        p95_fps = float(np.percentile(fps_arr, 5))

        samp_arr = np.array(self._sampling_times, dtype=np.float32) if self._sampling_times else np.zeros(1)
        avg_samp_ms = float(np.mean(samp_arr))

        return PerformanceBenchmarkReport(
            sample_count=len(arr),
            avg_fps=round(avg_fps, 1),
            min_fps=round(min_fps, 1),
            p95_fps=round(p95_fps, 1),
            avg_frame_time_ms=round(avg_frame_ms, 2),
            avg_sampling_time_ms=round(avg_samp_ms, 2),
            platform_info=f"{platform.system()} {platform.release()} ({platform.machine()})",
            python_version=platform.python_version(),
            backend="QPainter (CPU Software Rasterizer)"
        )
