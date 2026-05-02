"""Security utilities for password hashing, cookie encryption, and validation."""

import base64
import hmac
import hashlib
import json
import time
from collections import defaultdict
from typing import Any, Optional
from urllib.parse import urlparse

import bcrypt
from cryptography.fernet import Fernet
from fastapi import HTTPException, Request
from loguru import logger
from pydantic import BaseModel, field_validator

_BCRYPT_ROUNDS = 12

# Lazy-loaded Fernet instance — initialized on first use so Settings are ready.
_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    """Return a Fernet instance, deriving the key from settings if needed."""
    global _fernet
    if _fernet is not None:
        return _fernet

    from config.settings import get_settings

    settings = get_settings()
    key = settings.COOKIE_ENCRYPTION_KEY

    def _derive_key(secret: str) -> str:
        raw = hashlib.sha256(secret.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(raw).decode("ascii")

    def _is_valid_fernet_key(k: str) -> bool:
        try:
            base64.urlsafe_b64decode(k)
            return len(k) == 44  # 32 bytes -> 44 base64 chars with padding
        except Exception:
            return False

    if key and _is_valid_fernet_key(key):
        _fernet = Fernet(key)
        return _fernet

    # Fallback: derive from SECRET_KEY
    derived = _derive_key(settings.SECRET_KEY)
    if key:
        logger.warning(
            f"COOKIE_ENCRYPTION_KEY is invalid ({len(key)} chars, expected 44). "
            "Deriving key from SECRET_KEY instead. "
            "Generate a proper key with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    else:
        logger.warning(
            "COOKIE_ENCRYPTION_KEY is not set; deriving key from SECRET_KEY. "
            "Set COOKIE_ENCRYPTION_KEY explicitly in production for stronger security."
        )
    _fernet = Fernet(derived)
    return _fernet


def encrypt_cookies(cookie_dict: dict) -> str:
    """Encrypt a cookie dict to a string for safe DB storage."""
    if not cookie_dict:
        return ""
    f = _get_fernet()
    return f.encrypt(json.dumps(cookie_dict).encode("utf-8")).decode("utf-8")


def decrypt_cookies(encrypted: Any) -> Optional[dict]:
    """Decrypt a cookie string back to a dict. Returns None on failure.
    Also handles legacy plaintext dicts for backward compatibility.
    """
    if not encrypted:
        return None
    # Backward compatibility: already a dict (legacy plaintext)
    if isinstance(encrypted, dict):
        return encrypted
    if not isinstance(encrypted, str):
        return None
    # If it looks like JSON, it might be a legacy plaintext string stored in JSON col
    if encrypted.strip().startswith(("{", "[")):
        try:
            return json.loads(encrypted)
        except Exception:
            pass
    try:
        f = _get_fernet()
        decrypted = f.decrypt(encrypted.encode("utf-8"))
        return json.loads(decrypted.decode("utf-8"))
    except Exception as e:
        logger.warning(f"Failed to decrypt cookies: {e}")
        return None


class RateLimiter:
    """Simple in-memory sliding-window rate limiter per client."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        # key -> list of timestamps
        self._store: defaultdict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        timestamps = self._store[key]
        # Drop expired entries
        cutoff = now - self.window
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)
        if len(timestamps) >= self.max_requests:
            return False
        timestamps.append(now)
        return True

    def raise_if_limited(self, key: str):
        if not self.is_allowed(key):
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again later.",
            )


def _client_key(request: Request) -> str:
    """Extract a stable client identifier from the request."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# Global limiters — shared across the app
login_rate_limiter = RateLimiter(max_requests=5, window_seconds=60)


# ── CSRF Protection ───────────────────────────────────

def generate_csrf_token(session_token: str) -> str:
    """Generate a CSRF token bound to the session token via HMAC."""
    from config.settings import get_settings

    settings = get_settings()
    secret = settings.SECRET_KEY.encode("utf-8")
    token = session_token.encode("utf-8")
    return hmac.new(secret, token, hashlib.sha256).hexdigest()[:32]


def verify_csrf_token(request: Request) -> None:
    """Validate the X-CSRF-Token header against the session cookie."""
    session_token = request.cookies.get("session_id")
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    csrf_header = request.headers.get("x-csrf-token")
    if not csrf_header:
        raise HTTPException(status_code=403, detail="CSRF token missing")

    expected = generate_csrf_token(session_token)
    if not hmac.compare_digest(expected, csrf_header):
        raise HTTPException(status_code=403, detail="CSRF token invalid")


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt with secure rounds."""
    if not password or not isinstance(password, str):
        raise ValueError("Password must be a non-empty string")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    password_bytes = password.encode("utf-8")
    hashed_bytes = bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=_BCRYPT_ROUNDS))
    return hashed_bytes.decode("utf-8")


def verify_password(
    plain_password: Optional[str], hashed_password: Optional[str]
) -> bool:
    """Verify a plaintext password against its hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


class URLValidator(BaseModel):
    """Validator for URL inputs to prevent injection attacks."""

    url: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format and scheme with enhanced security."""
        if not v:
            raise ValueError("URL cannot be empty")

        if not isinstance(v, str):
            raise ValueError("URL must be a string")

        if len(v) > 2048:
            raise ValueError("URL exceeds maximum length of 2048 characters")

        # Reject control characters anywhere in the raw URL.
        if any(char in v for char in ["\n", "\r", "\x00"]):
            raise ValueError("Invalid characters detected in URL")

        try:
            result = urlparse(v)

            # Validate scheme
            valid_schemes = ("http", "https", "socks5", "socks4", "socks4a")
            if result.scheme not in valid_schemes:
                raise ValueError(
                    f"Invalid URL scheme '{result.scheme}'. Valid schemes: {', '.join(valid_schemes)}"
                )

            # Ensure netloc exists
            if not result.netloc:
                raise ValueError("Invalid URL: no network location specified")

            return v
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Invalid URL format: {str(e)}")


def validate_proxy_url(url: Optional[str]) -> bool:
    """Validate proxy URLs with enhanced error handling."""
    if not url:
        return True  # None/empty proxy URL is valid
    try:
        URLValidator(url=url)
        return True
    except ValueError:
        return False
