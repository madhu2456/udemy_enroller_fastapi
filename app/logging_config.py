"""Logging configuration with readable output and context tracking."""

import sys
import logging
import json
from loguru import logger
from config.settings import get_settings

settings = get_settings()


def setup_logging():
    """Configure logging with compact output and context tracking."""
    # Force everything to WARNING to silence info/debug
    settings_level = settings.LOG_LEVEL.upper()
    numeric_level = getattr(logging, settings_level, logging.WARNING)

    # 1. Silence standard logging (urllib3, httpx, etc.)
    logging.root.setLevel(numeric_level)
    for name in logging.root.manager.loggerDict:
        logging.getLogger(name).setLevel(numeric_level)

    # Specific aggressive silencing for noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # 2. Silence loguru
    logger.remove()
    concise_fmt = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}"

    # Standard logging bridge
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s",
        force=True,
    )

    # Add sinks with explicit level
    logger.add(
        sys.stdout,
        format=concise_fmt,
        level=settings_level,
        colorize=False,
    )
    logger.add(
        settings.LOG_FILE,
        format=concise_fmt,
        level=settings_level,
        colorize=False,
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
    )

    return logger


# Utility function to log structured data
def log_structured(event: str, level: str = "info", **kwargs):
    """Log structured data with context."""
    log_data = {"event": event, **kwargs}
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
