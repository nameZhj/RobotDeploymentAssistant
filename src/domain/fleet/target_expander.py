import logging
import threading
from typing import Dict, List, Optional, Set, Tuple
from src.core.config_loader import config_loader
from src.infrastructure.lrmp.command_parser import command_parser

logger = logging.getLogger("TargetExpander")


class TargetExpander:
    """
    Expands multi-robot target specifications into discrete directed commands,
    while managing immutable locked cohort sets during choreography performances.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._target_delim = config_loader.get_target_delimiter()
        self._param_delim = config_loader.get_param_delimiter()
        self._broadcast_token = config_loader.get_broadcast_token()
        self._locked_cohorts: Dict[str, Set[str]] = {}

    def expand_command(self, raw_command: str) -> List[str]:
        """
        Expand multi-target or grouped commands into individual directed command strings.
        Preserves allowed broadcast commands (e.g. ALL|DISCOVER).
        """
        parsed = command_parser.parse(raw_command)
        if not parsed.is_valid:
            logger.warning(f"Rejecting invalid command expansion: {parsed.error_msg}")
            return []

        if parsed.is_broadcast:
            return [parsed.raw_text]

        if len(parsed.targets) <= 1:
            return [parsed.raw_text]

        cmd_suffix = parsed.command
        if parsed.params:
            cmd_suffix = f"{cmd_suffix}{self._param_delim}{self._param_delim.join(parsed.params)}"

        expanded = []
        for tgt in parsed.targets:
            expanded.append(f"{tgt}{self._target_delim}{cmd_suffix}")

        return expanded

    def lock_choreo_cohort(self, plan_id: str, robot_targets: List[str]) -> Tuple[bool, str]:
        """Lock active choreography cohort members to prevent modification mid-show."""
        clean_targets = {t.strip().upper() for t in robot_targets if t.strip()}
        if not clean_targets:
            return False, "Target list cannot be empty"

        with self._lock:
            for pid, members in self._locked_cohorts.items():
                if pid != plan_id:
                    intersection = clean_targets.intersection(members)
                    if intersection:
                        return False, f"Targets {sorted(intersection)} already locked by plan [{pid}]"

            self._locked_cohorts[plan_id] = clean_targets
            logger.info(f"Cohort locked for plan [{plan_id}]: {sorted(clean_targets)}")
            return True, f"Locked {len(clean_targets)} robots"

    def unlock_choreo_cohort(self, plan_id: str) -> bool:
        """Unlock cohort upon choreography completion or stop."""
        with self._lock:
            if plan_id in self._locked_cohorts:
                removed = self._locked_cohorts.pop(plan_id)
                logger.info(f"Cohort unlocked for plan [{plan_id}]: {sorted(removed)}")
                return True
            return False

    def is_target_locked(self, robot_id: str) -> Optional[str]:
        """Check if robot target is locked in an active choreography cohort, returning plan_id."""
        clean = robot_id.strip().upper()
        with self._lock:
            for pid, members in self._locked_cohorts.items():
                if clean in members:
                    return pid
            return None

    def get_locked_members(self, plan_id: str) -> List[str]:
        with self._lock:
            return sorted(list(self._locked_cohorts.get(plan_id, set())))

    def clear(self) -> None:
        with self._lock:
            self._locked_cohorts.clear()


target_expander = TargetExpander()

