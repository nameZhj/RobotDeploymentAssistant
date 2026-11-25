# @file: src/core/settings.py
# @brief: Strongly-typed configuration loader and persistent settings manager backed by configs/app_settings.yaml.
# @exports: StageDefaults, VirtualInterfaceSettings, StudioSettings, get_settings, save_settings

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
import yaml

from src.core.paths import get_paths


@dataclass
class StageDefaults:
    """Default physical stage, physics, and timeline sampling parameters."""

    stage_width_m: float = 12.0
    stage_height_m: float = 8.0
    safety_margin_m: float = 0.5
    grid_step_m: float = 1.0
    subgrid_step_m: float = 0.2
    export_fps: int = 50
    collision_check_dt_s: float = 0.05
    safety_distance_m: float = 0.60
    default_max_acc: float = 1.5
    default_max_speed: float = 3.0
    default_run_mode: int = 504
    default_bpm: float = 120.0
    default_time_signature: str = "4/4"


@dataclass
class VirtualInterfaceSettings:
    """Configuration toggles for Wi-Fi HTTP robot communication and SLAM stream interfaces."""

    http_upload_virtual_fallback: bool = False
    http_upload_timeout_s: float = 5.0
    http_default_port: int = 8090
    slam_stream_virtual_fallback: bool = False
    slam_stream_default_port: int = 8091


@dataclass
class UiLayoutSettings:
    """Fixed desktop shell dimensions without magic numbers."""

    default_width: int = 1440
    default_height: int = 900
    min_width: int = 1200
    min_height: int = 760
    header_height_px: int = 32
    statusbar_height_px: int = 28
    right_lib_width_px: int = 330
    opbar_width_px: int = 40
    track_head_width_px: int = 168


@dataclass
class StudioSettings:
    """Top-level settings aggregate loaded from YAML."""

    app_title: str = "舞台编导与群控工作台"
    version: str = "3.2.0"
    stage_defaults: StageDefaults = field(default_factory=StageDefaults)
    virtual_interfaces: VirtualInterfaceSettings = field(default_factory=VirtualInterfaceSettings)
    ui_layout: UiLayoutSettings = field(default_factory=UiLayoutSettings)


def _merge_dataclass(cls: type, raw: Optional[Dict[str, Any]]) -> Any:
    if not isinstance(raw, dict):
        return cls()
    valid_keys = {f for f in cls.__dataclass_fields__}
    filtered = {k: v for k, v in raw.items() if k in valid_keys}
    return cls(**filtered)


def _overlay_path() -> Path:
    return get_paths().runtime_dir / "user_settings.yaml"


def load_settings(config_path: Optional[Path] = None) -> StudioSettings:
    """Load StudioSettings from YAML plus runtime user_settings.yaml overlay."""
    path = config_path or (get_paths().configs_dir / "app_settings.yaml")
    data: Dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {} if path.exists() else {}
    if config_path is None:
        overlay = _overlay_path()
        if overlay.exists():
            ov = yaml.safe_load(overlay.read_text(encoding="utf-8")) or {}
            for sec in ("app_info", "stage_defaults", "virtual_interfaces", "ui_layout"):
                if isinstance(ov.get(sec), dict):
                    data[sec] = {**(data.get(sec) or {}), **ov[sec]}
    app_info = data.get("app_info", {})
    raw_title = str(app_info.get("app_title", StudioSettings.app_title))
    low_t = raw_title.lower()
    if any(tok in low_t for tok in ("uniswarm", "uniuni", "unitree")):
        raw_title = StudioSettings.app_title
    return StudioSettings(
        app_title=raw_title,
        version=str(app_info.get("version", StudioSettings.version)),
        stage_defaults=_merge_dataclass(StageDefaults, data.get("stage_defaults")),
        virtual_interfaces=_merge_dataclass(VirtualInterfaceSettings, data.get("virtual_interfaces")),
        ui_layout=_merge_dataclass(UiLayoutSettings, data.get("ui_layout")),
    )


def save_settings(settings: StudioSettings, config_path: Optional[Path] = None) -> Path:
    """Persist runtime-editable settings sections to user_settings.yaml (or explicit config_path)."""
    path = config_path or _overlay_path()
    existing: Dict[str, Any] = {}
    if path.exists():
        existing = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    existing["app_info"] = {
        **(existing.get("app_info") or {}),
        "app_title": settings.app_title,
        "version": settings.version,
    }
    existing["stage_defaults"] = asdict(settings.stage_defaults)
    existing["virtual_interfaces"] = asdict(settings.virtual_interfaces)
    existing["ui_layout"] = asdict(settings.ui_layout)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(existing, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


_CACHED_SETTINGS: Optional[StudioSettings] = None
_CACHED_OVERLAY_PATH: Optional[Path] = None


def get_settings(reload: bool = False) -> StudioSettings:
    """Return the cached StudioSettings singleton (workspace-overlay aware)."""
    global _CACHED_SETTINGS, _CACHED_OVERLAY_PATH
    cur_overlay = _overlay_path()
    if _CACHED_SETTINGS is None or reload or _CACHED_OVERLAY_PATH != cur_overlay:
        _CACHED_SETTINGS = load_settings()
        _CACHED_OVERLAY_PATH = cur_overlay
    return _CACHED_SETTINGS
