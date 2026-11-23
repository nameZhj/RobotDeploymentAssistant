# @file: src/protocol/lrmp_constants.py
# @brief: Authoritative LRMP V1.0-R3 command set, control authorities, and official 33 dance registry.
# @exports: ControlAuthority, LRMP_COMMANDS, BROADCAST_ALLOWED, DANCE_ALIAS_TO_NAME, is_valid_lrmp_command

from __future__ import annotations

from enum import Enum
from typing import Dict, FrozenSet

from backend.serial_dance_parser import DEFAULT_DANCE_GROUPS


class ControlAuthority(str, Enum):
    """Per-robot arbitration lease state per LRMP V1.0-R3 §5."""

    FREE = "FREE"
    MANUAL = "MANUAL"
    CHOREO = "CHOREO"


LRMP_COMMANDS: FrozenSet[str] = frozenset(
    {
        "DISCOVER",
        "BIND",
        "SETUP",
        "DEPLOY",
        "STATUS",
        "STAND",
        "GAIT",
        "PASSIVE",
        "FORWARD",
        "BACK",
        "BACKWARD",
        "MOVE_LEFT",
        "MOVE_RIGHT",
        "TURN_LEFT",
        "TURN_RIGHT",
        "MOVE",
        "DANCE",
        "PREP",
        "PLAY",
        "BARRIER",
        "STOP",
        "RELEASE",
        "EMERGENCY",
    }
)

# Commands safe for global ALL|<CMD> broadcast; multi-target motion/choreo expands A|, B|, C|
BROADCAST_ALLOWED: FrozenSet[str] = frozenset(
    {"DISCOVER", "STATUS", "STAND", "GAIT", "PASSIVE", "STOP", "EMERGENCY", "RELEASE", "DANCE"}
)

MANUAL_MOTION_COMMANDS: FrozenSet[str] = frozenset(
    {
        "STAND",
        "GAIT",
        "PASSIVE",
        "FORWARD",
        "BACK",
        "BACKWARD",
        "MOVE_LEFT",
        "MOVE_RIGHT",
        "TURN_LEFT",
        "TURN_RIGHT",
        "MOVE",
        "DANCE",
    }
)

DANCE_ALIAS_TO_NAME: Dict[str, str] = {
    item["alias"]: item["name"]
    for group in DEFAULT_DANCE_GROUPS
    for item in group.get("items", [])
}

DANCE_NAME_TO_ALIAS: Dict[str, str] = {v: k for k, v in DANCE_ALIAS_TO_NAME.items()}


def is_valid_lrmp_command(cmd: str) -> bool:
    """Return True if cmd belongs strictly to the documented LRMP V1.0-R3 command set."""
    return cmd.strip().upper() in LRMP_COMMANDS
