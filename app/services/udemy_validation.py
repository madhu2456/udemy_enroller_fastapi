"""Parse-based Udemy host validation (F-ENRL-C07).

Single source of truth for "is this a Udemy URL/host" decisions. Substring
allowlist checks (`"udemy.com" in url`) allow hostile hosts such as
`udemy.com.evil.example` to pass — every production check must go through the
helpers here. The CI gate `scripts/verify-no-udemy-substring.sh` fails if a
substring-style check reappears in ``app/services``.
"""

from typing import Any
from urllib.parse import urlparse

# Exact-netloc allowlist (lowercase, no ports, no userinfo, no trailing dot).
UDEMY_NETLOCS = frozenset({"udemy.com", "www.udemy.com", "trk.udemy.com"})

_UDEMY_PATH_COURSE = "course"


def is_udemy_netloc(host: Any) -> bool:
    """Whether *host* (a raw netloc/host string) is an exact Udemy netloc.

    Rejects: userinfo (``user@udemy.com``), ports (``udemy.com:8443``),
    trailing dots (``udemy.com.``), IP literals (``192.168.1.1``, ``[::1]``),
    percent-encoding (``udemy%2Ecom``), and anything not in the exact set.
    """
    if not isinstance(host, str):
        return False
    candidate = host.strip().lower()
    if not candidate:
        return False
    # No trailing dot, no userinfo, no port, no path/query remnants.
    if (
        candidate != candidate.rstrip(".")
        or "@" in candidate
        or ":" in candidate
        or "/" in candidate
        or "\\" in candidate
        or candidate.startswith("[")
    ):
        return False
    # Reject IP literals (IPv4: digits+dots only; IPv6 covered by "[" check).
    if candidate.replace(".", "").isdigit():
        return False
    return candidate in UDEMY_NETLOCS


def is_udemy_url(url: Any) -> bool:
    """Whether *url* points at an exact Udemy netloc over http(s).

    Parse-based: the netloc (including any userinfo/port) must pass
    :func:`is_udemy_netloc`. Scheme-less strings and non-http(s) schemes are
    rejected.
    """
    if not isinstance(url, str) or not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.netloc:
        return False
    return is_udemy_netloc(parsed.netloc)


def is_udemy_course_url(url: Any) -> bool:
    """Whether *url* is an exact Udemy netloc whose path starts with /course/."""
    if not is_udemy_url(url):
        return False
    try:
        path = urlparse(url).path
    except ValueError:
        return False
    parts = [p for p in path.split("/") if p]
    return bool(parts) and parts[0] == _UDEMY_PATH_COURSE


def is_trk_udemy_url(url: Any) -> bool:
    """Whether *url* is an exact ``trk.udemy.com`` redirector URL."""
    if not is_udemy_url(url):
        return False
    try:
        netloc = urlparse(url).netloc
    except ValueError:
        return False
    return netloc.lower() == "trk.udemy.com"
