"""Centralized caching for API responses."""

import datetime
from typing import Any, Dict, Callable, Optional
from datetime import UTC


def _utcnow_naive() -> datetime.datetime:
    """Return current UTC timestamp without tzinfo for DB compatibility."""
    return datetime.datetime.now(UTC).replace(tzinfo=None)


# Global cache stores
_history_cache: Dict[str, Any] = {}
_analytics_cache: Dict[int, Any] = {}
_stats_cache: Dict[int, Any] = {}


def get_cached_or_compute(
    cache_dict: Dict[Any, Any], 
    key: Any, 
    compute_func: Callable[[], Any], 
    ttl_seconds: int = 10
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
    # Clear stats and analytics (keyed by user_id directly)
    _stats_cache.pop(user_id, None)
    _analytics_cache.pop(user_id, None)
    
    # Clear history (keyed by f"{user_id}_{limit}")
    user_prefix = f"{user_id}_"
    keys_to_remove = [k for k in _history_cache.keys() if str(k).startswith(user_prefix)]
    for k in keys_to_remove:
        _history_cache.pop(k, None)
