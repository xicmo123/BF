from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def configure_logging(log_path: Path, level: str = "INFO") -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level=level, enqueue=True, backtrace=False, diagnose=False)
    logger.add(
        log_path,
        rotation="10 MB",
        retention="14 days",
        compression="zip",
        level=level,
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )

