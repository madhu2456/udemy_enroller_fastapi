"""Tests for security features: encryption, CSRF, rate limiting, and session cache."""

import asyncio
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, Request
from starlette.datastructures import State

from app.security import (
    encrypt_cookies,
    decrypt_cookies,
    generate_csrf_token,
    verify_csrf_token,
    RateLimiter,
    login_rate_limiter,
    _client_key,
)
from app.core.cache import SessionCache
from app.services.course import Course


# ── Cookie Encryption ─────────────────────────────────────


class TestCookieEncryption:
    """Test Fernet-based cookie encryption."""

    def test_roundtrip_encryption(self):
        cookies = {"access_token": "abc123", "client_id": "xyz"}
        encrypted = encrypt_cookies(cookies)
        assert isinstance(encrypted, str)
        assert encrypted != str(cookies)
        decrypted = decrypt_cookies(encrypted)
        assert decrypted == cookies

    def test_empty_dict_returns_empty(self):
        assert encrypt_cookies({}) == ""
        assert encrypt_cookies(None) == ""

    def test_decrypt_empty_returns_none(self):
        assert decrypt_cookies("") is None
        assert decrypt_cookies(None) is None

    def test_decrypt_legacy_plaintext_dict(self):
        """Backward compatibility: plaintext dicts should still work."""
        legacy = {"access_token": "old", "client_id": "legacy"}
        assert decrypt_cookies(legacy) == legacy

    def test_decrypt_legacy_json_string(self):
        """Backward compatibility: JSON string stored in DB."""
        import json
        legacy = {"access_token": "token"}
        assert decrypt_cookies(json.dumps(legacy)) == legacy

    def test_decrypt_invalid_returns_none(self):
        assert decrypt_cookies("totally-invalid-garbage") is None

    def test_encryption_is_deterministic_with_same_key(self):
        cookies = {"key": "value"}
        e1 = encrypt_cookies(cookies)
        e2 = encrypt_cookies(cookies)
        # Fernet with same key produces different ciphertexts (random IV)
        assert e1 != e2
        assert decrypt_cookies(e1) == decrypt_cookies(e2)


# ── CSRF Protection ───────────────────────────────────────


class TestCsrfProtection:
    """Test HMAC-based CSRF token generation and verification."""

    def test_generate_csrf_token_is_stable(self):
        token = "my-session-token"
        t1 = generate_csrf_token(token)
        t2 = generate_csrf_token(token)
        assert t1 == t2
        assert len(t1) == 32

    def test_different_sessions_produce_different_tokens(self):
        t1 = generate_csrf_token("session-a")
        t2 = generate_csrf_token("session-b")
        assert t1 != t2

    def test_verify_csrf_token_success(self):
        req = MagicMock(spec=Request)
        req.cookies = {"session_id": "sess-123"}
        req.headers = {"x-csrf-token": generate_csrf_token("sess-123")}
        # Should not raise
        verify_csrf_token(req)

    def test_verify_csrf_missing_session(self):
        req = MagicMock(spec=Request)
        req.cookies = {}
        req.headers = {"x-csrf-token": "foo"}
        with pytest.raises(HTTPException) as exc:
            verify_csrf_token(req)
        assert exc.value.status_code == 401

    def test_verify_csrf_missing_header(self):
        req = MagicMock(spec=Request)
        req.cookies = {"session_id": "sess-123"}
        req.headers = {}
        with pytest.raises(HTTPException) as exc:
            verify_csrf_token(req)
        assert exc.value.status_code == 403

    def test_verify_csrf_invalid_token(self):
        req = MagicMock(spec=Request)
        req.cookies = {"session_id": "sess-123"}
        req.headers = {"x-csrf-token": "wrong-token"}
        with pytest.raises(HTTPException) as exc:
            verify_csrf_token(req)
        assert exc.value.status_code == 403


# ── Rate Limiting ─────────────────────────────────────────


class TestRateLimiting:
    """Test sliding-window rate limiter."""

    def test_rate_limiter_allows_under_limit(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        assert limiter.is_allowed("key1") is True
        assert limiter.is_allowed("key1") is True
        assert limiter.is_allowed("key1") is True

    def test_rate_limiter_blocks_over_limit(self):
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        limiter.is_allowed("key1")
        limiter.is_allowed("key1")
        assert limiter.is_allowed("key1") is False

    def test_rate_limiter_isolated_per_key(self):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        limiter.is_allowed("key-a")
        assert limiter.is_allowed("key-b") is True

    def test_rate_limiter_window_expires(self):
        limiter = RateLimiter(max_requests=1, window_seconds=0.05)
        limiter.is_allowed("key1")
        assert limiter.is_allowed("key1") is False
        import time
        time.sleep(0.06)
        assert limiter.is_allowed("key1") is True

    def test_rate_limiter_raise_if_limited(self):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        limiter.is_allowed("key1")
        with pytest.raises(HTTPException) as exc:
            limiter.raise_if_limited("key1")
        assert exc.value.status_code == 429

    def test_client_key_extracts_forwarded_for(self):
        req = MagicMock(spec=Request)
        req.headers = {"x-forwarded-for": "1.2.3.4, 5.6.7.8"}
        req.client = MagicMock(host="10.0.0.1")
        assert _client_key(req) == "1.2.3.4"

    def test_client_key_fallback_to_direct(self):
        req = MagicMock(spec=Request)
        req.headers = {}
        req.client = MagicMock(host="10.0.0.1")
        assert _client_key(req) == "10.0.0.1"


# ── Session Cache ─────────────────────────────────────────


class TestSessionCache:
    """Test LRU-bounded session cache with TTL."""

    def test_basic_get_set(self):
        cache = SessionCache()
        cache.set("a", "value-a")
        assert cache.get("a") == "value-a"

    def test_missing_key_returns_none(self):
        cache = SessionCache()
        assert cache.get("missing") is None

    def test_lru_eviction(self):
        cache = SessionCache(max_size=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        assert cache.get("a") is None  # Evicted
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_lru_access_order(self):
        cache = SessionCache(max_size=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.get("a")  # Touch 'a'
        cache.set("c", 3)
        assert cache.get("a") == 1  # Still here
        assert cache.get("b") is None  # 'b' evicted

    def test_ttl_expiration(self):
        cache = SessionCache(default_ttl_seconds=0.01)
        cache.set("a", 1)
        assert cache.get("a") == 1
        import time
        time.sleep(0.02)
        assert cache.get("a") is None

    def test_contains_and_len(self):
        cache = SessionCache()
        cache.set("a", 1)
        assert "a" in cache
        assert len(cache) == 1

    def test_pop_returns_value(self):
        cache = SessionCache()
        cache.set("a", 1)
        assert cache.pop("a") == 1
        assert cache.pop("a") is None

    def test_dict_interface(self):
        cache = SessionCache()
        cache["a"] = 1
        assert cache["a"] == 1
        del cache["a"]
        assert "a" not in cache

    def test_cleanup_task_removes_expired(self):
        cache = SessionCache(default_ttl_seconds=0.05)
        cache.set("a", 1)
        cache.set("b", 2, ttl=3600)  # Long TTL

        async def run_cleanup():
            await asyncio.sleep(0.1)
            # Cancel immediately after one cycle
            await cache.stop_cleanup_task()

        asyncio.run(run_cleanup())
        assert cache.get("a") is None
        assert cache.get("b") == 2

    def test_items_values_keys(self):
        cache = SessionCache()
        cache.set("a", 1)
        cache.set("b", 2)
        assert set(cache.keys()) == {"a", "b"}
        assert set(cache.values()) == {1, 2}
        assert set(cache.items()) == {("a", 1), ("b", 2)}


# ── Course.normalize_link ─────────────────────────────────


class TestCourseNormalizeLink:
    """Test URL normalization and coupon preservation."""

    def test_basic_udemy_url(self):
        url = "https://www.udemy.com/course/python-bootcamp"
        result = Course.normalize_link(url)
        assert "udemy.com/course/python-bootcamp" in result

    def test_preserves_coupon_code(self):
        url = "https://www.udemy.com/course/python/?couponCode=FREE2024"
        result = Course.normalize_link(url)
        assert "couponCode=FREE2024" in result

    def test_preserves_coupon_from_redirect_url(self):
        """Coupon on outer redirect URL should survive unwrapping."""
        url = "https://trk.udemy.com/?link=https%3A%2F%2Fwww.udemy.com%2Fcourse%2Fpython%2F&couponCode=SAVE50"
        result = Course.normalize_link(url)
        assert "couponCode=SAVE50" in result

    def test_extracts_inner_url(self):
        url = "https://example.com/redirect?url=https%3A%2F%2Fwww.udemy.com%2Fcourse%2Fjs%2F"
        result = Course.normalize_link(url)
        assert "udemy.com/course/js" in result

    def test_upgrades_http_to_https(self):
        url = "http://udemy.com/course/docker/"
        result = Course.normalize_link(url)
        assert result.startswith("https://")

    def test_adds_trailing_slash(self):
        url = "https://www.udemy.com/course/docker"
        result = Course.normalize_link(url)
        assert "/docker/" in result

    def test_unescapes_html_entities(self):
        url = "https://www.udemy.com/course/test&amp;foo"
        result = Course.normalize_link(url)
        assert "&amp;" not in result

    def test_empty_url(self):
        assert Course.normalize_link("") == ""

    def test_non_udemy_url(self):
        url = "https://example.com/something"
        result = Course.normalize_link(url)
        assert "example.com" in result

    def test_course_object_extracts_coupon(self):
        c = Course("Test", "https://udemy.com/course/test/?couponCode=ABC")
        assert c.coupon_code == "ABC"

    def test_course_object_sets_slug(self):
        c = Course("Test", "https://udemy.com/course/test-course/")
        assert c.slug == "test-course"

    def test_course_equality_by_url(self):
        c1 = Course("A", "https://udemy.com/course/same/")
        c2 = Course("B", "https://udemy.com/course/same/")
        assert c1 == c2

    def test_course_hash_by_url(self):
        c1 = Course("A", "https://udemy.com/course/same/")
        c2 = Course("B", "https://udemy.com/course/same/")
        assert hash(c1) == hash(c2)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
