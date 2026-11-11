from typing import Dict, List, Optional
from src.core.config_loader import config_loader
from src.core.logger import get_logger
from src.domain.fleet.robot_entity import RobotEntity, validate_robot_id
from src.infrastructure.storage.cache_manager import cache_manager

logger = get_logger("FleetService")
FLEET_CACHE_FILE = "robot_fleet.json"


class FleetService:
    """
    Manages fleet topology, discovery registration, and local persistence.
    """

    def __init__(self) -> None:
        self._robots: Dict[str, RobotEntity] = {}
        self.load_persisted_fleet()

    def load_persisted_fleet(self) -> None:
        cached_data = cache_manager.load_json(FLEET_CACHE_FILE, default=[])
        if isinstance(cached_data, list):
            for item in cached_data:
                alias = item if isinstance(item, str) else item.get("alias", "")
                ok, clean_id, _ = validate_robot_id(alias)
                if ok:
                    ip = item.get("ip", "") if isinstance(item, dict) else ""
                    self._robots[clean_id] = RobotEntity(alias=clean_id, ip=ip)
        elif not self._robots:
            aliases = config_loader.get_target_rules().get("registered_aliases", ["A", "B", "C"])
            for alias in aliases:
                self._robots[alias] = RobotEntity(alias=alias)

    def persist_fleet(self) -> bool:
        export_data = [
            {"alias": r.alias, "ip": r.ip, "is_online": r.is_online}
            for r in self._robots.values()
        ]
        return cache_manager.save_json(FLEET_CACHE_FILE, export_data)

    def add_robot(self, alias: str, ip: str = "") -> bool:
        ok, clean_id, err = validate_robot_id(alias)
        if not ok:
            logger.warning(f"Failed to add robot: {err}")
            return False
        self._robots[clean_id] = RobotEntity(alias=clean_id, ip=ip)
        self.persist_fleet()
        return True

    def remove_robot(self, alias: str) -> bool:
        clean_id = alias.strip().upper()
        if clean_id in self._robots:
            del self._robots[clean_id]
            self.persist_fleet()
            return True
        return False

    def list_robots(self) -> List[RobotEntity]:
        return list(self._robots.values())

    def get_robot(self, alias: str) -> Optional[RobotEntity]:
        return self._robots.get(alias.strip().upper())


fleet_service = FleetService()
