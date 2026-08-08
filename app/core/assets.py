"""Content-hash cache busters for self-hosted frontend bundles."""

import hashlib
from pathlib import Path

# app/core/assets.py -> <repo root>/app/static/js/lucide-icons.min.js
_LUCIDE_ICONS_PATH = (
    Path(__file__).resolve().parents[2] / "app/static/js/lucide-icons.min.js"
)

_cache_buster: str | None = None


def lucide_cache_buster() -> str:
    """First 10 hex chars of the lucide subset bundle's sha256.

    Computed once per process and reused for every template render. The value
    changes whenever scripts/build-lucide-subset.js regenerates the bundle, so
    the immutable-cache URL query (?v=...) always matches the served file.
    """
    global _cache_buster
    if _cache_buster is None:
        digest = hashlib.sha256(_LUCIDE_ICONS_PATH.read_bytes()).hexdigest()
        _cache_buster = digest[:10]
    return _cache_buster
