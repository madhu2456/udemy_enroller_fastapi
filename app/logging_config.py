"""Logging configuration with readable output and context tracking."""

import sys
import logging
import json
from loguru import logger
from config.settings import get_settings

settings = get_settings()


def setup_logging():
    """Configure logging with compact output and context tracking."""
    # Remove default loguru handler
    logger.remove()
    concise_fmt = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}"

    # Keep third-party logs readable and aligned with app log style.
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s"
    )

    if settings.LOG_FORMAT == "json":
        # "json" mode keeps text output compact (no color) for readability.
        logger.add(
            sys.stdout,
            format=concise_fmt,
            level=settings.LOG_LEVEL,
            colorize=False,
        )
        logger.add(
            settings.LOG_FILE,
            format=concise_fmt,
            level=settings.LOG_LEVEL,
            colorize=False,
            rotation="10 MB",
            retention="7 days",
            encoding="utf-8"
        )
    else:
        # Text logging setup with colors
        fmt = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        logger.add(sys.stdout, format=fmt, level=settings.LOG_LEVEL)
        logger.add(
            settings.LOG_FILE,
            format=fmt,
            level=settings.LOG_LEVEL,
            rotation="10 MB",
            retention="7 days",
            encoding="utf-8"
        )

    return logger


# Utility function to log structured data
def log_structured(event: str, level: str = "info", **kwargs):
    """Log structured data with context."""
    log_data = {
        "event": event,
        **kwargs
    }
    if level == "info":
        logger.info(json.dumps(log_data))
    elif level == "warning":
        logger.warning(json.dumps(log_data))
    elif level == "error":
        logger.error(json.dumps(log_data))
    elif level == "debug":
        logger.debug(json.dumps(log_data))
    else:
        logger.info(json.dumps(log_data))
