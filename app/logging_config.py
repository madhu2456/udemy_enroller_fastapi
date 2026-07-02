"""Logging configuration with readable output and context tracking."""

import sys
import logging
import json
import re
from loguru import logger
from config.settings import get_settings

settings = get_settings()

# Sensitive data patterns for log redaction
SENSITIVE_PATTERNS = [
    # Credential fields in various formats:
    # - key=value (coupon=ABC123)
    # - key: value (coupon: ABC123)
    # - "key": "value" (JSON: "coupon_code": "ABC123")
    # - 'key': 'value' (dict repr: 'coupon_code': 'PROMO123')
    # - URL query strings (?couponCode=DISCOUNT50)
    (r"(coupon_code|couponCode|coupon|access_token|client_id|csrf_token|csrftoken|password)(=|: |\":\s*\"|':\s*'|\?|&)([^\s,}&'\"]+)", r"\1\2***REDACTED***"),
    # Authorization headers
    (r"(Authorization|authorization)(:\s*|=)([^\s,}&'\"]+)", r"\1\2***REDACTED***"),
    # Email addresses
    (r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", "***EMAIL_REDACTED***"),
]


def sanitize_log_message(message: str) -> str:
    """Redact sensitive data from log messages.
    
    Applies regex-based redaction for credentials, tokens, and PII.
    Use this for any log message that may contain user input or API responses.
    """
    if not isinstance(message, str):
        message = str(message)
    
    for pattern, replacement in SENSITIVE_PATTERNS:
        message = re.sub(pattern, replacement, message, flags=re.IGNORECASE)
    
    return message


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

    def concise_fmt(record):
        fmt = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}"
        if "user_id" in record["extra"]:
            fmt += " [user:{extra[user_id]}]"
        fmt += "\n"
        return fmt

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
    """Log structured data with context and automatic sanitization."""
    # Sanitize sensitive fields in kwargs
    SENSITIVE_KEYS = ['token', 'cookie', 'secret', 'key', 'password', 'coupon', 'auth', 'credential']
    sanitized = {}
    for key, value in kwargs.items():
        if any(sensitive in key.lower() for sensitive in SENSITIVE_KEYS):
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, str):
            # Sanitize string values that may contain sensitive data
            sanitized[key] = sanitize_log_message(value)
        else:
            sanitized[key] = value
    
    log_data = {"event": event, **sanitized}
    log_message = sanitize_log_message(json.dumps(log_data))
    
    if level == "info":
        logger.info(log_message)
    elif level == "warning":
        logger.warning(log_message)
    elif level == "error":
        logger.error(log_message)
    elif level == "debug":
        logger.debug(log_message)
    else:
        logger.info(log_message)
