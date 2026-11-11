import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from src.core.config_loader import config_loader


@dataclass(frozen=True)
class ParsedCommand:
    """Standardized structured representation of an upper-layer raw command."""
    raw_text: str
    target: str
    targets: List[str]
    command: str
    params: List[str]
    meta: Dict[str, Any] = field(default_factory=dict)
    is_broadcast: bool = False
    is_long_task: bool = False
    auto_acquire_authority: Optional[str] = None
    is_valid: bool = True
    error_msg: str = ""


class CommandParser:
    """
    Parses upper-layer string formatted as TARGET|COMMAND[,PARAM1,PARAM2...]
    Enforces MOVE axis normalization [-1.0, 1.0], alphanumeric action name checks,
    and strict broadcast interception (only ALL|DISCOVER is permitted).
    """

    def __init__(self) -> None:
        self._target_delim = config_loader.get_target_delimiter()
        self._param_delim = config_loader.get_param_delimiter()
        self._broadcast_token = config_loader.get_broadcast_token()
        self._allowed_broadcast = set(config_loader.get_allowed_broadcast_commands())
        self._action_name_regex = re.compile(r"^[A-Za-z0-9_\-]+$")

    def parse(self, raw_command: str) -> ParsedCommand:
        """Parse raw command string into strongly-typed ParsedCommand with deep validation."""
        if not raw_command or not raw_command.strip():
            return self._build_invalid(raw_command, "Command string is empty")

        clean = raw_command.strip()
        if self._target_delim not in clean:
            return self._build_invalid(clean, f"Missing target delimiter '{self._target_delim}'")

        parts = clean.split(self._target_delim, 1)
        target_part = parts[0].strip()
        cmd_part = parts[1].strip()

        if not target_part:
            return self._build_invalid(clean, "Target specifier cannot be empty")
        if not cmd_part:
            return self._build_invalid(clean, "Command specifier cannot be empty", target=target_part)

        cmd_tokens = [p.strip() for p in cmd_part.split(self._param_delim)]
        command_name = cmd_tokens[0].upper()
        params = cmd_tokens[1:] if len(cmd_tokens) > 1 else []

        targets = [t.strip().upper() for t in target_part.split(self._param_delim) if t.strip()]
        is_broadcast = target_part.upper() == self._broadcast_token or self._broadcast_token in targets

        # Intercept illegal broadcast commands (only ALL|DISCOVER allowed)
        if is_broadcast and command_name not in self._allowed_broadcast:
            err = f"Broadcast '{target_part}' is strictly restricted to DISCOVER. Blocked command: {command_name}"
            return self._build_invalid(clean, err, target=target_part)

        meta = config_loader.find_command_meta(command_name) or {}
        is_long_task = bool(meta.get("is_long_task", False))
        auto_acquire = meta.get("auto_acquire") or meta.get("acquire_authority")

        # Specific Command Validations
        valid, err_msg = self._validate_specific_command(command_name, params, meta)

        return ParsedCommand(
            raw_text=clean,
            target=target_part,
            targets=targets,
            command=command_name,
            params=params,
            meta=meta,
            is_broadcast=is_broadcast,
            is_long_task=is_long_task,
            auto_acquire_authority=auto_acquire,
            is_valid=valid,
            error_msg=err_msg,
        )

    def _validate_specific_command(self, cmd: str, params: List[str], meta: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate parameter counts, velocity bounds, and action naming."""
        if meta:
            if "params_count" in meta and len(params) != meta["params_count"]:
                return False, f"Command [{cmd}] expects {meta['params_count']} parameters, got {len(params)}"
            elif "params" in meta and len(params) < len(meta["params"]):
                return False, f"Command [{cmd}] missing required params: {meta['params'][len(params):]}"

        # Validate MOVE [-1.0, 1.0] axis range and duration
        if cmd == "MOVE":
            if len(params) < 3:
                return False, "MOVE command requires at least [forward, left, turn]"
            axis_range = meta.get("axis_range", [-1.0, 1.0])
            min_val, max_val = float(axis_range[0]), float(axis_range[1])
            for i, axis_name in enumerate(["forward", "left", "turn"]):
                try:
                    val = float(params[i])
                    if not (min_val <= val <= max_val):
                        return False, f"MOVE {axis_name} value {val} out of bounds [{min_val}, {max_val}]"
                except ValueError:
                    return False, f"MOVE {axis_name} parameter '{params[i]}' is not a valid float"

        # Validate DANCE action name
        if cmd == "DANCE":
            if not params or not params[0].strip():
                return False, "DANCE command requires a valid action_name"
            action_name = params[0].strip()
            if not self._action_name_regex.match(action_name):
                return False, f"Invalid action name '{action_name}': only alphanumeric, underscore, hyphen allowed"

        return True, ""

    def _build_invalid(self, raw: str, msg: str, target: str = "") -> ParsedCommand:
        targets = [t.strip() for t in target.split(self._param_delim) if t.strip()] if target else []
        return ParsedCommand(
            raw_text=raw,
            target=target,
            targets=targets,
            command="",
            params=[],
            is_valid=False,
            error_msg=msg,
        )


command_parser = CommandParser()
