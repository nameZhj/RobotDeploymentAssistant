import threading
import time
from typing import Dict, Optional, Tuple
from src.core.constants import ControlAuthority
from src.core.logger import get_logger

logger = get_logger("ControlArbiter")


class ControlArbiter:
    """
    Manages mutual exclusion between FREE, MANUAL, and CHOREO authorities.
    Tracks lease TTLs to prevent abandoned control locks.
    Enforces RELEASE only for MANUAL authority, and routes STOP semantic branching.
    """

    def __init__(self, default_ttl_s: float = 3.0) -> None:
        self._lock = threading.RLock()
        self._authorities: Dict[str, ControlAuthority] = {}
        self._owners: Dict[str, str] = {}
        self._lease_expire_at: Dict[str, float] = {}
        self._default_ttl_s = default_ttl_s

    def get_authority(self, robot_id: str) -> ControlAuthority:
        """Return active authority, auto-reverting to FREE if lease expired."""
        with self._lock:
            self._check_expiry(robot_id)
            return self._authorities.get(robot_id, ControlAuthority.FREE)

    def get_owner(self, robot_id: str) -> str:
        with self._lock:
            self._check_expiry(robot_id)
            return self._owners.get(robot_id, "")

    def _check_expiry(self, robot_id: str) -> None:
        if robot_id in self._lease_expire_at:
            if time.time() > self._lease_expire_at[robot_id]:
                old_auth = self._authorities.get(robot_id, ControlAuthority.FREE)
                self._authorities[robot_id] = ControlAuthority.FREE
                self._owners.pop(robot_id, None)
                self._lease_expire_at.pop(robot_id, None)
                logger.warning(f"Robot {robot_id} lease expired ({old_auth.value} -> FREE)")

    def request_authority(
        self,
        robot_id: str,
        requested: ControlAuthority,
        requester_id: str,
        ttl_s: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """Acquire or upgrade authority lease for a robot."""
        with self._lock:
            self._check_expiry(robot_id)
            current = self._authorities.get(robot_id, ControlAuthority.FREE)
            current_owner = self._owners.get(robot_id, "")

            if current == requested and current_owner == requester_id:
                self._extend_lease(robot_id, ttl_s)
                return True, f"Authority {requested.value} renewed"

            if current == ControlAuthority.CHOREO and requested == ControlAuthority.MANUAL:
                return False, f"Robot {robot_id} is locked in CHOREO authority"

            if current == ControlAuthority.MANUAL and requested == ControlAuthority.CHOREO:
                return False, f"Robot {robot_id} has active MANUAL lease held by {current_owner}"

            self._authorities[robot_id] = requested
            self._owners[robot_id] = requester_id
            self._extend_lease(robot_id, ttl_s)
            logger.info(f"Robot {robot_id} granted {requested.value} to [{requester_id}]")
            return True, f"Granted {requested.value}"

    def renew_lease(self, robot_id: str, requester_id: str, ttl_s: Optional[float] = None) -> bool:
        """Heartbeat renewal of an existing active lease."""
        with self._lock:
            self._check_expiry(robot_id)
            if self._owners.get(robot_id) == requester_id:
                self._extend_lease(robot_id, ttl_s)
                return True
            return False

    def _extend_lease(self, robot_id: str, ttl_s: Optional[float]) -> None:
        duration = ttl_s if ttl_s is not None else self._default_ttl_s
        self._lease_expire_at[robot_id] = time.time() + duration

    def release_manual(self, robot_id: str) -> Tuple[bool, str]:
        """Release MANUAL control authority strictly. CHOREO cannot be released via this path."""
        with self._lock:
            self._check_expiry(robot_id)
            current = self._authorities.get(robot_id, ControlAuthority.FREE)
            if current == ControlAuthority.MANUAL:
                self._authorities[robot_id] = ControlAuthority.FREE
                self._owners.pop(robot_id, None)
                self._lease_expire_at.pop(robot_id, None)
                logger.info(f"Robot {robot_id} MANUAL authority released to FREE")
                return True, "Released to FREE"
            return False, f"Cannot release non-MANUAL authority ({current.value})"

    def handle_stop(self, robot_id: str) -> str:
        """Semantic branching for STOP command."""
        with self._lock:
            self._check_expiry(robot_id)
            current = self._authorities.get(robot_id, ControlAuthority.FREE)
            if current == ControlAuthority.CHOREO:
                self._authorities[robot_id] = ControlAuthority.FREE
                self._owners.pop(robot_id, None)
                self._lease_expire_at.pop(robot_id, None)
                logger.warning(f"Robot {robot_id} CHOREO interrupted by STOP, reset to FREE")
                return "CHOREO_INTERRUPTED"
            elif current == ControlAuthority.MANUAL:
                logger.info(f"Robot {robot_id} MANUAL jog halted, authority maintained")
                return "MANUAL_STOPPED"
            return "IDLE_STOP"

    def reset(self) -> None:
        with self._lock:
            self._authorities.clear()
            self._owners.clear()
            self._lease_expire_at.clear()


control_arbiter = ControlArbiter()
