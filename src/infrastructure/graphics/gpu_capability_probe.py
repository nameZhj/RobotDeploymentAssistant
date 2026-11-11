import logging
import platform
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from src.core.config_loader import config_loader
from src.core.event_bus import event_bus

logger = logging.getLogger("GPUCapabilityProbe")


@dataclass(frozen=True)
class GPUInfo:
    name: str
    is_discrete: bool
    vram_mb: int = 0


class GPUCapabilityProbe:
    """
    Probes system GPU capabilities on Windows/Linux to automatically select
    between Eco profile (integrated GPU, OpenGL 3.3) and Pro profile (discrete GPU, OpenGL 4.3).
    """

    def __init__(self) -> None:
        self._cfg = config_loader.get_graphics_3d()
        self._profiles = self._cfg.get("profiles", {})
        self._detected_gpus: List[GPUInfo] = []
        self._has_discrete_gpu: bool = False
        self._active_profile_key: str = self._cfg.get("default_fallback_profile", "eco")

        self.detect_gpus()
        if self._cfg.get("auto_detect_gpu", True):
            self._active_profile_key = "pro" if self._has_discrete_gpu else "eco"

    def detect_gpus(self) -> List[GPUInfo]:
        """Query system video controllers to identify integrated vs discrete GPUs."""
        gpus: List[GPUInfo] = []
        os_type = platform.system().lower()

        if "windows" in os_type:
            gpus = self._probe_windows_gpus()
        else:
            gpus = self._probe_linux_gpus()

        self._detected_gpus = gpus
        self._has_discrete_gpu = any(g.is_discrete for g in gpus)
        logger.info(
            f"Detected {len(gpus)} GPU(s). Discrete present: {self._has_discrete_gpu}. "
            f"Active profile: {self._active_profile_key}"
        )
        return gpus

    def _probe_windows_gpus(self) -> List[GPUInfo]:
        results: List[GPUInfo] = []
        try:
            cmd = 'powershell -NoProfile -Command "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"'
            out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL, timeout=3.0)
            for line in out.splitlines():
                clean_name = line.strip()
                if not clean_name:
                    continue
                is_discrete = self._is_discrete_name(clean_name)
                results.append(GPUInfo(name=clean_name, is_discrete=is_discrete))
        except Exception as e:
            logger.debug(f"PowerShell GPU probe fallback to generic: {e}")
            results.append(GPUInfo(name="Generic Display Adapter", is_discrete=False))
        return results

    def _probe_linux_gpus(self) -> List[GPUInfo]:
        results: List[GPUInfo] = []
        try:
            out = subprocess.check_output(
                "lspci | grep -i 'vga\\|3d'", shell=True, text=True, stderr=subprocess.DEVNULL, timeout=2.0
            )
            for line in out.splitlines():
                clean = line.strip()
                if clean:
                    is_discrete = self._is_discrete_name(clean)
                    results.append(GPUInfo(name=clean, is_discrete=is_discrete))
        except Exception:
            results.append(GPUInfo(name="Generic Linux Display", is_discrete=False))
        return results

    @staticmethod
    def _is_discrete_name(name: str) -> bool:
        lower = name.lower()
        discrete_tokens = ["nvidia", "geforce", "quadro", "rtx", "gtx", "tesla", "radeon rx", "discrete"]
        integrated_tokens = ["intel", "uhd", "iris", "hd graphics", "vega 8", "basic display"]

        for d in discrete_tokens:
            if d in lower:
                return True
        for i in integrated_tokens:
            if i in lower:
                return False
        return False

    @property
    def has_discrete_gpu(self) -> bool:
        return self._has_discrete_gpu

    @property
    def active_profile_name(self) -> str:
        return self._active_profile_key

    @property
    def active_profile_key(self) -> str:
        return self._active_profile_key

    def get_active_profile(self) -> Dict[str, Any]:
        """Return the dictionary configuration of the currently active profile."""
        return self._profiles.get(self._active_profile_key, self._profiles.get("eco", {}))

    def get_render_policy(self) -> Dict[str, Any]:
        """Resolve dynamic rendering thresholds including voxel downsampling and shader params."""
        profile = self.get_active_profile()
        is_pro = self._active_profile_key == "pro"
        return {
            "profile": self._active_profile_key,
            "opengl_version": profile.get("opengl_version", "4.3" if is_pro else "3.3"),
            "voxel_downsample_m": 0.05 if is_pro else 0.15,
            "msaa_samples": profile.get("msaa_samples", 4 if is_pro else 0),
            "enable_shadows": profile.get("enable_shadows", is_pro),
            "avatar_lod": profile.get("avatar_lod", "high_detail_mesh" if is_pro else "low_poly_primitive"),
            "target_fps": profile.get("target_fps", 60),
        }

    def switch_profile(self, profile_key: str) -> bool:
        """Manually toggle between 'eco' and 'pro' profiles."""
        clean_key = profile_key.lower().strip()
        if clean_key not in self._profiles and clean_key not in ["eco", "pro"]:
            logger.warning(f"Unknown profile '{profile_key}'")
            return False

        self._active_profile_key = clean_key
        logger.info(f"Switched graphics profile to: {self._active_profile_key}")
        event_bus.publish("GRAPHICS_PROFILE_CHANGED", {
            "profile": self._active_profile_key,
            "config": self.get_render_policy(),
        })
        return True


gpu_capability_probe = GPUCapabilityProbe()
