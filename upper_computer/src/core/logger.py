# @file: src/core/logger.py
# @brief: Isolated logging configurator directing Studio logs strictly under .agent_workspace/runtime/logs/.
# @exports: get_studio_logger, configure_studio_logging

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

from src.core.paths import get_paths

_LOG_MAX_BYTES = 2 * 1024 * 1024
_LOG_BACKUP_COUNT = 3
_CONFIGURED = False


def configure_studio_logging(level: int = logging.INFO) -> None:
    """Attach rotating file and console handlers for the Stage Studio logger hierarchy."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    paths = get_paths()
    paths.ensure_runtime_dirs()
    log_file = paths.logs_dir / "stage_studio.log"

    root_logger = logging.getLogger("stage_studio")
    root_logger.setLevel(level)
    root_logger.propagate = False

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root_logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    root_logger.addHandler(stream_handler)
    _CONFIGURED = True


def get_studio_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a child logger under the configured stage_studio namespace."""
    configure_studio_logging()
    full_name = f"stage_studio.{name}" if name else "stage_studio"
    return logging.getLogger(full_name)
