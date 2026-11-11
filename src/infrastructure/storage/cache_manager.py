import json
from pathlib import Path
from typing import Any, Dict, Optional
from src.core.config_loader import config_loader
from src.core.logger import get_logger

logger = get_logger("CacheManager")


class CacheManager:
    """
    Manages runtime file caching in runtime/cache/ conforming to Guardrail E.
    """

    def __init__(self) -> None:
        self._cache_dir = config_loader.resolve_path("cache_dir", "runtime/cache")
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    def get_cache_file(self, filename: str) -> Path:
        return self._cache_dir / filename

    def save_json(self, filename: str, data: Any) -> bool:
        target = self.get_cache_file(filename)
        try:
            with open(target, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save cache json {filename}: {e}")
            return False

    def load_json(self, filename: str, default: Optional[Any] = None) -> Any:
        target = self.get_cache_file(filename)
        if not target.exists():
            return default
        try:
            with open(target, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load cache json {filename}: {e}")
            return default

    def delete(self, filename: str) -> bool:
        target = self.get_cache_file(filename)
        if target.exists():
            try:
                target.unlink()
                return True
            except Exception as e:
                logger.error(f"Failed to delete cache {filename}: {e}")
                return False
        return True


cache_manager = CacheManager()
