"""Centralized caching for API responses."""

import asyncio
import datetime
from collections import OrderedDict
from typing import Any, Callable, Dict, Optional

from loguru import logger


def _utcnow_naive() -> datetime.datetime:
    """Return current UTC timestamp without tzinfo for DB compatibility."""
    from datetime import UTC
    return datetime.datetime.now(UTC).replace(tzinfo=None)


class SessionCache:
    """Thread-safe LRU-bounded cache for active sessions with TTL cleanup."""

    def __init__(self, max_size: int = 100, default_ttl_seconds: int = 3600):
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl_seconds
        self._cleanup_task: Optional[asyncio.Task] = None

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        entry = self._cache[key]
        if _utcnow_naive() > entry["expires_at"]:
            self.pop(key)
            return None
        self._cache.move_to_end(key)
        return entry["value"]

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = {
            "value": value,
            "expires_at": _utcnow_naive() + datetime.timedelta(seconds=ttl or self._default_ttl),
        }
        while len(self._cache) > self._max_size:
            oldest_key, _ = self._cache.popitem(last=False)
            logger.info(f"Evicted oldest session from cache: {oldest_key[:8]}...")

    def pop(self, key: str) -> Optional[Any]:
        entry = self._cache.pop(key, None)
        return entry["value"] if entry else None

    def __contains__(self, key: str) -> bool:
        return key in self._cache

    def __len__(self) -> int:
        return len(self._cache)

    def keys(self):
        return self._cache.keys()

    def values(self):
        return [entry["value"] for entry in self._cache.values()]

    def items(self):
        return [(k, entry["value"]) for k, entry in self._cache.items()]

    def __getitem__(self, key: str) -> Any:
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key: str, value: Any):
        self.set(key, value)

    def __delitem__(self, key: str):
        if self.pop(key) is None:
            raise KeyError(key)

    async def cleanup_expired(self, interval: int = 300):
        """Periodically remove expired entries. Run as background task."""
        while True:
            await asyncio.sleep(interval)
            expired = [
                k for k, v in self._cache.items()
                if _utcnow_naive() > v["expires_at"]
            ]
            for k in expired:
                self._cache.pop(k, None)
            if expired:
                logger.info(f"Cleaned up {len(expired)} expired sessions from cache.")

    def start_cleanup_task(self) -> asyncio.Task:
        """Start the periodic cleanup background task."""
        self._cleanup_task = asyncio.create_task(self.cleanup_expired())
        return self._cleanup_task

    async def stop_cleanup_task(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass


# Global cache stores
_history_cache: Dict[str, Any] = {}
_analytics_cache: Dict[int, Any] = {}
_stats_cache: Dict[int, Any] = {}


def get_cached_or_compute(
    cache_dict: Dict[Any, Any],
    key: Any,
    compute_func: Callable[[], Any],
    ttl_seconds: int = 10,
) -> Any:
    """Helper to cache DB heavy responses for a short time."""
    now = _utcnow_naive()

    if key in cache_dict:
        entry = cache_dict[key]
        if (now - entry["time"]).total_seconds() < ttl_seconds:
            return entry["data"]

    data = compute_func()
    cache_dict[key] = {"time": now, "data": data}
    return data


def clear_user_caches(user_id: int):
    """Clear all caches related to a specific user to ensure UI consistency after mutations."""
    _stats_cache.pop(user_id, None)
    _analytics_cache.pop(user_id, None)

    user_prefix = f"{user_id}_"
    keys_to_remove = [
        k for k in _history_cache.keys() if str(k).startswith(user_prefix)
    ]
    for k in keys_to_remove:
        _history_cache.pop(k, None)
