"""Loguru configuration for WireGUI."""

import sys
from datetime import datetime

from loguru import logger


def setup_logging(log_to_file: bool = False) -> None:
    """Configure loguru sinks. Call once at startup."""
    # Remove default stderr sink and re-add with our format
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level="DEBUG",
    )

    if log_to_file:
        timestamp = datetime.now().strftime("%Y%m%d")
        logger.add(
            f"logs/wiregui_{timestamp}.log",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {name}:{function}:{line} - {message}",
            level="DEBUG",
            rotation="10 MB",
            retention="7 days",
        )
        logger.info("File logging enabled: logs/wiregui_{}.log", timestamp)
