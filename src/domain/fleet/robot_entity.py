import re
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
from src.core.constants import ControlAuthority

ROBOT_ID_REGEX = re.compile(r"^[A-Za-z0-9_-]{1,20}$")


def validate_robot_id(robot_id: str) -> Tuple[bool, str, str]:
    if not robot_id:
        return False, "", "Robot ID cannot be empty"
    clean_id = robot_id.strip().upper()
    if not ROBOT_ID_REGEX.match(clean_id):
        return False, "", "Robot ID must be 1-20 alphanumeric, _, or - characters"
    if clean_id == "ALL":
        return False, "", "Robot ID cannot be broadcast token 'ALL'"
    if "," in clean_id or "|" in clean_id:
        return False, "", "Robot ID cannot contain delimiters"
    return True, clean_id, ""


@dataclass
class RobotEntity:
    alias: str
    ip: str = ""
    is_online: bool = False
    last_seen: float = field(default_factory=time.time)
    authority: ControlAuthority = ControlAuthority.FREE
    metadata: Dict[str, str] = field(default_factory=dict)

    def update_heartbeat(self) -> None:
        self.last_seen = time.time()
        self.is_online = True

    def mark_offline_if_stale(self, timeout_s: float = 8.0) -> bool:
        if self.is_online and (time.time() - self.last_seen > timeout_s):
            self.is_online = False
            return True
        return False
