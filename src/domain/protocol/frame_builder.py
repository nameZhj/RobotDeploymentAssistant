import time
from typing import Any, List, Optional
from src.core.config_loader import config_loader
from src.core.constants import ProtocolTokens


class FrameBuilder:
    """
    Constructs LRMP protocol frames conforming to V1.0-R3.
    Enforces multi-target expansion: list of targets expands into multiple unicast lines.
    """

    def __init__(self) -> None:
        self._seq = 0
        self._target_delim = ProtocolTokens.target_delimiter()
        self._param_delim = ProtocolTokens.param_delimiter()
        self._broadcast = ProtocolTokens.broadcast_target()

    def next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFFFF
        return self._seq

    def build_command_line(self, target: str, command: str, params: Optional[List[Any]] = None) -> str:
        cmd_part = command
        if params:
            p_str = self._param_delim.join(str(p) for p in params)
            cmd_part = f"{command}{self._param_delim}{p_str}"
        return f"{target}{self._target_delim}{cmd_part}"

    def build_expanded_frames(
        self, targets: List[str], command: str, params: Optional[List[Any]] = None
    ) -> List[str]:
        """
        Multi-target expansion rule:
        Only allow_broadcast_commands (like DISCOVER) or explicit ALL can stay as broadcast.
        Any checked list like ['A', 'B'] is expanded into individual directed frames.
        """
        allow_broadcast = config_loader.get_target_rules().get("allow_broadcast_commands", [])

        if len(targets) == 1 and targets[0] == self._broadcast:
            if command not in allow_broadcast and command != "STOP":
                pass
            return [self.build_command_line(self._broadcast, command, params)]

        expanded = []
        for tgt in targets:
            clean_tgt = tgt.strip().upper()
            if not clean_tgt:
                continue
            expanded.append(self.build_command_line(clean_tgt, command, params))
        return expanded


frame_builder = FrameBuilder()
