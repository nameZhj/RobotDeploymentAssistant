from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml


class ConfigLoader:
    """
    Centralized configuration manager ensuring zero-hardcoding across all modules.
    Reads immutable definitions from configs/lrmp_protocol.yaml and configs/app_settings.yaml.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self._root = project_root or Path(__file__).resolve().parent.parent.parent
        self._configs_dir = self._root / "configs"
        self._lrmp_path = self._configs_dir / "lrmp_protocol.yaml"
        self._app_settings_path = self._configs_dir / "app_settings.yaml"

        self._lrmp_data: Dict[str, Any] = {}
        self._app_settings_data: Dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        """Reload all configuration files from disk."""
        if self._lrmp_path.exists():
            with open(self._lrmp_path, "r", encoding="utf-8") as f:
                self._lrmp_data = yaml.safe_load(f) or {}
        if self._app_settings_path.exists():
            with open(self._app_settings_path, "r", encoding="utf-8") as f:
                self._app_settings_data = yaml.safe_load(f) or {}

    @property
    def lrmp(self) -> Dict[str, Any]:
        return self._lrmp_data

    @property
    def app_settings(self) -> Dict[str, Any]:
        return self._app_settings_data

    # Raw section getters
    def get_protocol_meta(self) -> Dict[str, Any]:
        return self._lrmp_data.get("protocol_meta", {})

    def get_target_rules(self) -> Dict[str, Any]:
        return self._lrmp_data.get("target_rules", {})

    def get_frame_types(self) -> Dict[str, str]:
        return self._lrmp_data.get("frame_types", {})

    def get_control_authorities(self) -> Dict[str, str]:
        return self._lrmp_data.get("control_authorities", {})

    def get_transport_policy(self) -> Dict[str, Any]:
        return self._lrmp_data.get("transport_policy", {})

    def get_device_commands(self) -> Dict[str, Any]:
        return self._lrmp_data.get("device_management_commands", {})

    def get_motion_commands(self) -> Dict[str, Any]:
        return self._lrmp_data.get("direct_motion_commands", {})

    def get_choreography_commands(self) -> Dict[str, Any]:
        return self._lrmp_data.get("choreography_commands", {})

    def get_legacy_commands(self) -> Dict[str, Any]:
        return self._lrmp_data.get("legacy_admin_commands", {})

    # Delimiters and target tokens
    def get_target_delimiter(self) -> str:
        return self.get_protocol_meta().get("delimiter_target", "|")

    def get_param_delimiter(self) -> str:
        return self.get_protocol_meta().get("delimiter_param", ",")

    def get_broadcast_token(self) -> str:
        return self.get_target_rules().get("broadcast_token", "ALL")

    def get_allowed_broadcast_commands(self) -> List[str]:
        return self.get_target_rules().get("allow_broadcast_commands", ["DISCOVER"])

    def get_registered_aliases(self) -> List[str]:
        return self.get_target_rules().get("registered_aliases", [])

    def get_unbound_gateway_prefix(self) -> str:
        return self.get_target_rules().get("unbound_gateway_prefix", "GW_")

    # Unified command lookup
    def find_command_meta(self, cmd_name: str) -> Optional[Dict[str, Any]]:
        """Look up command metadata across all command categories."""
        clean_name = cmd_name.strip().upper()
        categories = [
            "device_management_commands",
            "direct_motion_commands",
            "choreography_commands",
        ]
        for cat in categories:
            cmds = self._lrmp_data.get(cat, {})
            for key, val in cmds.items():
                if isinstance(val, dict) and val.get("cmd", "").upper() == clean_name:
                    meta = dict(val)
                    meta["category"] = cat
                    return meta

        legacy_cmds = self.get_legacy_commands().get("commands", [])
        if clean_name in [c.upper() for c in legacy_cmds]:
            return {"cmd": clean_name, "category": "legacy_admin_commands", "params_count": 0}

        return None

    # Paths and System Settings
    def get_app_info(self) -> Dict[str, Any]:
        return self._app_settings_data.get("app_info", {})

    def get_paths(self) -> Dict[str, str]:
        return self._app_settings_data.get("paths", {})

    def get_ui_layout(self) -> Dict[str, Any]:
        return self._app_settings_data.get("ui_layout", {})

    def get_graphics_3d(self) -> Dict[str, Any]:
        return self._app_settings_data.get("graphics_3d", {})

    def resolve_path(self, key: str, default: str = "") -> Path:
        rel_path = self.get_paths().get(key, default)
        return self._root / rel_path


config_loader = ConfigLoader()
