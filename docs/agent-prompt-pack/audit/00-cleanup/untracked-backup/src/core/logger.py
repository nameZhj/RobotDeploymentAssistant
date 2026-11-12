import datetime
import logging
from pathlib import Path
from typing import Any
from src.core.config_loader import config_loader


def _get_log_dir() -> Path:
    log_dir = config_loader.resolve_path("logs_dir", "runtime/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_system_logging(level: int = logging.INFO) -> None:
    log_dir = _get_log_dir()
    log_file = log_dir / "system.log"

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if not any(isinstance(h, logging.FileHandler) for h in root_logger.handlers):
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)


def get_logger(name: str) -> logging.Logger:
    setup_system_logging()
    return logging.getLogger(name)


class CommFrameLogger:
    """
    Dedicated protocol frame logger enforcing SRC_ID presence in compliance with LRMP V1.0-R3.
    """

    def __init__(self) -> None:
        self._comm_log_path = _get_log_dir() / "comm_frames.log"

    def log_frame(
        self,
        src_id: str,
        dst_id: str,
        frame_type: str,
        payload: str,
        status: str = "SENT",
        seq: int = 0,
    ) -> None:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        record = (
            f"[{timestamp}] [{status}] SRC={src_id} -> DST={dst_id} | "
            f"TYPE={frame_type} SEQ={seq} | PAYLOAD={payload}\n"
        )
        try:
            with open(self._comm_log_path, "a", encoding="utf-8") as f:
                f.write(record)
        except Exception as e:
            get_logger("CommLogger").error(f"Failed to append comm log: {e}")


comm_logger = CommFrameLogger()

