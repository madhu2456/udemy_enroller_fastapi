"""Security utilities for password hashing, cookie encryption, and validation."""

import asyncio
import base64
import hmac
import hashlib
import ipaddress
import json
import re
import secrets
import time
from collections import defaultdict
from typing import Any, Optional
from urllib.parse import urlparse

import bcrypt
import httpx
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import HTTPException, Request
from loguru import logger
from pydantic import BaseModel, field_validator

_BCRYPT_ROUNDS = 12

# Lazy-loaded Fernet instance — initialized on first use so Settings are ready.
_fernet: Optional[Fernet] = None
# Raw 32-byte master key backing the Fernet instance (set together with _fernet).
_fernet_key_bytes: Optional[bytes] = None


def _get_fernet() -> Fernet:
    """Return a Fernet instance, deriving the key from settings if needed."""
    global _fernet, _fernet_key_bytes
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
        except (ValueError, TypeError):
            return False

    if key and _is_valid_fernet_key(key):
        _fernet = Fernet(key)
        _fernet_key_bytes = base64.urlsafe_b64decode(key)
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
    _fernet_key_bytes = base64.urlsafe_b64decode(derived)
    return _fernet


def encrypt_cookies(cookie_dict: dict) -> str:
    """Encrypt a cookie dict to a string for safe DB storage.

    LEGACY writer (F-ENRL-C01 migration path): encrypts under the master key
    only, with no per-session salt. New writes must use
    ``encrypt_cookies_salted(data, salt)``; blobs produced here only decrypt
    while ``ALLOW_LEGACY_COOKIE_DECRYPT`` is enabled.
    """
    if not cookie_dict:
        return ""
    f = _get_fernet()
    return f.encrypt(json.dumps(cookie_dict).encode("utf-8")).decode("utf-8")


# ── Per-session cookie envelope (F-ENRL-C01) ─────────────────

# Stable HKDF info string — changing it would rotate every session key.
_SESSION_KEY_INFO = b"udemy-enroller-session-key-v1"


def generate_cookie_salt() -> str:
    """Generate a fresh per-session salt (16 random bytes, urlsafe base64).

    Stored on the user row next to the encrypted cookie blob; binds the Fernet
    envelope to the session that wrote it.
    """
    return base64.urlsafe_b64encode(secrets.token_bytes(16)).decode("ascii")


def _get_master_key_bytes() -> bytes:
    """Raw 32-byte master key backing the configured Fernet instance."""
    _get_fernet()
    if _fernet_key_bytes is None:
        raise RuntimeError("Fernet key not initialized")
    return _fernet_key_bytes


def _derive_session_key(salt: str) -> bytes:
    """Derive a per-session 32-byte key via HKDF-SHA256.

    Master key material (COOKIE_ENCRYPTION_KEY or the SECRET_KEY-derived
    fallback) + per-session salt + stable info string. A different salt yields
    a different key, so a ciphertext written under one session's salt can
    never be decrypted with another session's salt (fail-closed).
    """
    if not salt:
        raise ValueError("cookie salt must be non-empty")
    try:
        salt_bytes = base64.urlsafe_b64decode(salt.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise ValueError("cookie salt is not valid urlsafe base64") from exc
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt_bytes,
        info=_SESSION_KEY_INFO,
    )
    return hkdf.derive(_get_master_key_bytes())


def encrypt_cookies_salted(data: dict, salt: str) -> str:
    """Encrypt a cookie dict under a per-session derived key; "" when empty."""
    if not data:
        return ""
    session_key = base64.urlsafe_b64encode(_derive_session_key(salt))
    f = Fernet(session_key)
    return f.encrypt(json.dumps(data).encode("utf-8")).decode("utf-8")


def _allow_legacy_cookie_decrypt() -> bool:
    """Whether legacy (unsalted) cookie blobs may be decrypted.

    Server/production deployments reject legacy blobs by default (fail-closed):
    a blob without a valid per-session salt yields None -> 401 and the user
    must log in again. Local/dev keeps backward compatibility so existing local
    databases keep working during the migration window. Emergency override:
    ALLOW_LEGACY_COOKIE_DECRYPT=1 (not recommended on shared hosts).
    """
    import os

    flag = (os.environ.get("ALLOW_LEGACY_COOKIE_DECRYPT") or "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return True
    if flag in ("0", "false", "no", "off"):
        return False

    from config.settings import get_settings

    env = (get_settings().DEPLOYMENT_ENV or "").strip().lower()
    return env not in ("server", "production")


def _allow_plaintext_cookies() -> bool:
    """Whether legacy plaintext cookie blobs may be accepted on decrypt.

    Server/production deployments reject plaintext by default (F019). Local/dev
    keeps backward compatibility. Emergency override: ALLOW_PLAINTEXT_COOKIES=1
    (not recommended on shared hosts).
    """
    import os

    flag = (os.environ.get("ALLOW_PLAINTEXT_COOKIES") or "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return True
    if flag in ("0", "false", "no", "off"):
        return False

    from config.settings import get_settings

    env = (get_settings().DEPLOYMENT_ENV or "").strip().lower()
    return env not in ("server", "production")


def _legacy_plaintext_decrypt(value: dict) -> Optional[dict]:
    """Accept a legacy plaintext cookie blob only while plaintext is allowed."""
    if not _allow_plaintext_cookies():
        logger.warning(
            "Rejected plaintext cookie blob — server mode requires Fernet ciphertext"
        )
        return None
    return value


def decrypt_cookies(encrypted: Any, salt: Optional[str] = None) -> Optional[dict]:
    """Decrypt a cookie blob back to a dict. Returns None on failure.

    Post-F-ENRL-C01 envelopes are Fernet ciphertext under a per-session
    HKDF-derived key; pass the user's ``cookies_salt`` to decrypt them.
    Legacy blobs (master-key Fernet ciphertext, plaintext dicts/JSON strings)
    are accepted only while the legacy path is enabled — ``ALLOW_LEGACY_
    COOKIE_DECRYPT`` defaults ON for local/dev and OFF for server/production
    (fail-closed). Any failure returns None so callers take the 401 path;
    ciphertext is never returned as a usable secret.
    """
    if not encrypted:
        return None
    # Legacy plaintext dict (pre-encryption format)
    if isinstance(encrypted, dict):
        return _legacy_plaintext_decrypt(encrypted)
    if not isinstance(encrypted, str):
        return None
    # Legacy plaintext JSON stored in a text column
    if encrypted.strip().startswith(("{", "[")):
        try:
            return _legacy_plaintext_decrypt(json.loads(encrypted))
        except (json.JSONDecodeError, ValueError):
            return None
    # Per-session envelope first (salt binds the key to the writing session)
    if salt:
        try:
            session_key = base64.urlsafe_b64encode(_derive_session_key(salt))
            f = Fernet(session_key)
            decrypted = f.decrypt(encrypted.encode("utf-8"))
            return json.loads(decrypted.decode("utf-8"))
        except Exception:
            logger.warning(
                "Failed to decrypt cookies with per-session salt — "
                "falling back to legacy path"
            )
    # Legacy master-key Fernet envelope — gated by the legacy flag
    if not _allow_legacy_cookie_decrypt():
        logger.warning(
            "Rejected legacy (unsalted) cookie ciphertext — "
            "ALLOW_LEGACY_COOKIE_DECRYPT is off"
        )
        return None
    logger.warning(
        "Decrypting legacy (unsalted) cookie blob — set "
        "ALLOW_LEGACY_COOKIE_DECRYPT=0 to fail closed"
    )
    try:
        f = _get_fernet()
        decrypted = f.decrypt(encrypted.encode("utf-8"))
        return json.loads(decrypted.decode("utf-8"))
    except Exception:
        logger.warning("Failed to decrypt cookies — possible key rotation or tampering")
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

    async def is_allowed_redis(self, key: str) -> bool:
        """Async, Upstash-Redis-backed variant of is_allowed() for async callers.

        Returns True when the call is ALLOWED (same contract as is_allowed).
        Env-gated: UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN must both
        be set or the call degrades to the in-memory limiter. On ANY Redis
        failure it fails OPEN to the same in-memory limiter — a limiter outage
        can never lock out traffic. Transient failures (network, 5xx, timeout,
        unparseable response) log one warning; 4xx responses mean a
        misconfigured URL/token and log a warning on EVERY call. Bucket
        semantics are identical to is_allowed (max_requests per window_seconds
        per key, window anchored at the first hit); Redis keys are namespaced
        `udemy:` so shared Upstash databases never collide.
        """
        from config.settings import get_settings

        settings = get_settings()
        base_url = (settings.UPSTASH_REDIS_REST_URL or "").strip()
        token = (settings.UPSTASH_REDIS_REST_TOKEN or "").strip()
        if not base_url or not token:
            return self.is_allowed(key)

        redis_key = _sanitize_redis_key(f"udemy:{key}")
        try:
            count, _ttl = await _upstash_pipeline(
                base_url, token, redis_key, int(self.window * 1000)
            )
        except UpstashHttpError as exc:
            if 400 <= exc.status < 500:
                _record_rl_redis_fallback(
                    f"rate-limit: Upstash misconfiguration (HTTP {exc.status}) — "
                    "check UPSTASH_REDIS_REST_URL/TOKEN — falling back to in-memory",
                    every_call=True,
                )
            else:
                _record_rl_redis_fallback(
                    "rate-limit: Upstash Redis unreachable (HTTP "
                    f"{exc.status}) — failing open to in-memory limiting"
                )
            return self.is_allowed(key)
        except (httpx.HTTPError, asyncio.TimeoutError, ValueError) as exc:
            _record_rl_redis_fallback(
                "rate-limit: Upstash Redis unreachable — failing open to "
                f"in-memory limiting: {exc.__class__.__name__}"
            )
            return self.is_allowed(key)

        return count <= self.max_requests


# ── Upstash Redis REST rate limiting (optional shared buckets) ──

# Transient-failure warning is emitted once per process; 4xx warnings never
# use this flag (misconfigurations stay loud on every call).
_REDIS_WARNED_ONCE = False
# Process-local fail-open counter (F035). Do not fail-closed globally.
_REDIS_FALLBACK_COUNT = 0


def _record_rl_redis_fallback(message: str, *, every_call: bool = False) -> None:
    """Increment ``rl_redis_fallback`` and log per the warn-once / 4xx policy."""
    global _REDIS_FALLBACK_COUNT, _REDIS_WARNED_ONCE
    _REDIS_FALLBACK_COUNT += 1
    if every_call or not _REDIS_WARNED_ONCE:
        if not every_call:
            _REDIS_WARNED_ONCE = True
        logger.warning(f"rl_redis_fallback count={_REDIS_FALLBACK_COUNT} {message}")


class UpstashHttpError(Exception):
    """Non-2xx Upstash REST response — status distinguishes 4xx config errors."""

    def __init__(self, status: int):
        super().__init__(f"Upstash pipeline HTTP {status}")
        self.status = status


def _sanitize_redis_key(key: str) -> str:
    """Keys may embed user-derived parts (IPs) — keep Redis keys well-formed."""
    return re.sub(r"[^a-zA-Z0-9:._@-]", "_", key)[:200]


async def _upstash_pipeline(
    base_url: str, token: str, redis_key: str, window_ms: int
) -> tuple[int, int]:
    """Run the atomic Upstash rate-limit pipeline; return (count, ttl_seconds).

    SET ... NX PX seeds the window only when the key is absent (no-op otherwise,
    so the window stays anchored at the first hit — same semantics as the
    in-memory limiter); INCR counts; TTL yields the remaining window. SET starts
    at 0 so the first hit counts as 1 after INCR. Raises UpstashHttpError on
    non-2xx; network/timeout/parse failures propagate so the caller can fail
    open. 1.5s hard cap — fail-open means Redis must never add real latency.
    """
    body = [
        ["SET", redis_key, "0", "NX", "PX", str(window_ms)],
        ["INCR", redis_key],
        ["TTL", redis_key],
    ]
    async with asyncio.timeout(1.5):
        async with httpx.AsyncClient(timeout=1.5) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/pipeline",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
    if response.status_code < 200 or response.status_code >= 300:
        raise UpstashHttpError(response.status_code)
    try:
        results = response.json()
        count_raw = results[1]["result"]
        ttl_raw = results[2]["result"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ValueError("Upstash pipeline returned an unreadable response") from exc
    try:
        count = int(count_raw)
        ttl = int(ttl_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Upstash INCR/TTL returned invalid values") from exc
    if count < 1:
        raise ValueError("Upstash INCR returned invalid count")
    return count, ttl


def _normalize_ip(value: str | None) -> str | None:
    """Normalize an IP string to its canonical form; return None if empty/invalid."""
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def _client_key(request: Request) -> str:
    """Extract a stable, spoof-resistant client identifier for rate limiting.

    Trust model (mirrors blog_platform fastapi_backend/app/core/limiter.py):
    - The direct TCP peer (request.client.host) is the only inherently
      trustworthy source. Behind the nginx reverse proxy the peer is nginx
      (127.0.0.1); when the app is directly exposed it is the real client.
    - X-Forwarded-For is trusted ONLY when the direct peer is a configured
      trusted proxy (TRUSTED_PROXY_IPS). We walk the chain right-to-left,
      skipping trusted-proxy IPs, to find the first untrusted (real) client.
    - Client-supplied proxy headers (e.g. Cloudflare's connecting-IP header,
      X-Forwarded-For) from an UNTRUSTED peer are never used — a client could
      otherwise set them to evade or collide rate-limit buckets. x-real-ip is
      used only as a secondary hint when the peer is trusted and the XFF walk
      yields nothing.
    """
    from config.settings import get_settings

    direct_ip = _normalize_ip(request.client.host if request.client else None)
    trusted_proxies = set(get_settings().TRUSTED_PROXY_IPS)

    if direct_ip and direct_ip in trusted_proxies:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ips = [ip.strip() for ip in forwarded.split(",")]
            # Walk right-to-left past trusted proxies to the first real client.
            for ip_str in reversed(ips):
                ip_cand = _normalize_ip(ip_str)
                if not ip_cand:
                    continue
                if ip_cand not in trusted_proxies:
                    return ip_cand
            # All forwarded entries were trusted proxies; fall back to the last
            # valid value so the key stays stable.
            for ip_str in ips:
                ip_cand = _normalize_ip(ip_str)
                if ip_cand:
                    return ip_cand
        # Secondary hint: nginx X-Real-IP (only trustworthy when peer is nginx).
        real_ip = _normalize_ip(request.headers.get("x-real-ip"))
        if real_ip:
            return real_ip

    return direct_ip or "unknown"


# Global limiters — shared across the app (unauthenticated / abuse-sensitive edges)
login_rate_limiter = RateLimiter(max_requests=5, window_seconds=60)
analytics_rate_limiter = RateLimiter(max_requests=30, window_seconds=60)
csp_report_rate_limiter = RateLimiter(max_requests=20, window_seconds=60)
public_coupons_api_limiter = RateLimiter(max_requests=60, window_seconds=60)
auth_status_rate_limiter = RateLimiter(max_requests=90, window_seconds=60)


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


def generate_login_csrf_token() -> str:
    """Generate an anonymous double-submit CSRF token for the login page.

    Set as the ``csrf_token`` cookie (samesite=strict) when the login page is
    rendered; the login POST must echo it in the X-CSRF-Token header. The
    post-login session-bound csrf cookie overwrites it (F-ENRL-C03).
    """
    return secrets.token_urlsafe(32)


def _same_netloc(left: str, right: str) -> bool:
    """Case-insensitive host[:port] equality; scheme and path are ignored."""
    left_netloc = urlparse(left).netloc.lower()
    right_netloc = urlparse(right).netloc.lower()
    return bool(left_netloc) and left_netloc == right_netloc


def _expected_origin(request: Request) -> str:
    """Origin the server identifies as itself; PUBLIC_BASE_URL overrides it.

    Behind Cloudflare Flexible SSL, nginx forwards X-Forwarded-Proto: http
    ($scheme) while browsers send https Origins, so request.base_url's scheme
    must not participate in the comparison.
    """
    from config.settings import get_settings

    public_base = get_settings().PUBLIC_BASE_URL
    if public_base:
        return public_base.rstrip("/")
    return str(request.base_url).rstrip("/")


def _is_same_origin(request: Request) -> bool:
    """Reject browser requests whose Origin/Referer is not this server's origin.

    Comparison is netloc-only (host[:port], case-insensitive) and scheme-
    agnostic; the samesite=strict double-submit cookie remains the primary
    CSRF control. Clients that send neither header (curl, API tests) are not
    browser-based and cannot be CSRF targets, so they are allowed.
    """
    origin = request.headers.get("origin")
    if origin:
        return _same_netloc(origin, _expected_origin(request))
    referer = request.headers.get("referer")
    if referer:
        parsed = urlparse(referer)
        return parsed.hostname is not None and _same_netloc(
            f"{parsed.scheme}://{parsed.netloc}", _expected_origin(request)
        )
    return True


def verify_login_csrf(request: Request) -> None:
    """CSRF guard for unauthenticated login POSTs (double-submit + origin).

    Mirrors ``verify_csrf_token`` for state-changers but works without a
    session: the browser must send the anonymous ``csrf_token`` cookie AND
    echo it in the X-CSRF-Token header. ``samesite=strict`` on the cookie
    means cross-site browsers never attach it, so forged POSTs fail closed.
    An Origin/Referer same-origin check runs first when either header exists.
    """
    if not _is_same_origin(request):
        raise HTTPException(status_code=403, detail="Cross-origin request rejected")

    cookie_token = request.cookies.get("csrf_token")
    header_token = request.headers.get("x-csrf-token")
    if not cookie_token or not header_token:
        raise HTTPException(status_code=403, detail="CSRF token missing")
    if not hmac.compare_digest(cookie_token, header_token):
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
    except (ValueError, TypeError):
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
