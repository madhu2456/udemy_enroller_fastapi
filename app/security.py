"""Security utilities for password hashing and validation."""

import bcrypt
from pydantic import BaseModel, field_validator
from typing import Optional
from urllib.parse import urlparse

_BCRYPT_ROUNDS = 12


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
