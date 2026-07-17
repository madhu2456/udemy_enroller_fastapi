"""Tests for security features: encryption, CSRF, rate limiting, and session cache."""

import asyncio
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException, Request

from app.security import (
    encrypt_cookies,
    decrypt_cookies,
    generate_csrf_token,
    verify_csrf_token,
    RateLimiter,
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


# ── Analytics Event Logging ─────────────────────────────


class _SyntheticAnalyticsRequest:
    """Minimal request double for direct analytics-handler tests."""

    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.json_calls = 0
        self.headers = {"cf-connecting-ip": "203.0.113.121"}
        self.client = None

    async def json(self):
        self.json_calls += 1
        if self.error is not None:
            raise self.error
        return self.payload


class TestAnalyticsEventLogging:
    """Analytics logs retain only approved categories and target presence."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "event_type",
        [
            "outbound_click",
            "cta_click",
            "file_download",
            "scroll_depth",
            "login",
            "coupon_click",
            "enrollment_start",
            "enrollment_stop",
        ],
    )
    async def test_known_event_categories_remain_available(self, monkeypatch, event_type):
        import main as main_mod

        info_messages = []
        limiter = MagicMock()
        request = _SyntheticAnalyticsRequest({"type": event_type})
        monkeypatch.setattr(main_mod, "analytics_rate_limiter", limiter)
        monkeypatch.setattr(main_mod.logger, "info", info_messages.append)

        response = await main_mod.track_analytics_event(request)

        assert response == {"status": "ok"}
        assert info_messages == [f"[analytics] event received (type={event_type}, target_supplied=false)"]
        limiter.raise_if_limited.assert_called_once_with("203.0.113.121")

    @pytest.mark.asyncio
    async def test_submitted_target_details_never_enter_log(self, monkeypatch):
        import main as main_mod

        info_messages = []
        limiter = MagicMock()
        private_target = "https://person@example.test/path?token=PRIVATE_TOKEN\nPRIVATE_INJECTED_LINE"
        request = _SyntheticAnalyticsRequest({"type": "cta_click", "target": private_target})
        monkeypatch.setattr(main_mod, "analytics_rate_limiter", limiter)
        monkeypatch.setattr(main_mod.logger, "info", info_messages.append)

        response = await main_mod.track_analytics_event(request)

        assert response == {"status": "ok"}
        assert info_messages == ["[analytics] event received (type=cta_click, target_supplied=true)"]
        assert private_target not in "\n".join(info_messages)
        assert "PRIVATE_" not in "\n".join(info_messages)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "event_type",
        [
            "custom_event",
            "CTA_CLICK",
            "cta_click\nPRIVATE_INJECTED_LINE",
            "coupon_clické",
            "x" * 65,
            123,
            ["cta_click"],
            {"type": "cta_click"},
            None,
            "",
        ],
    )
    async def test_unapproved_or_malformed_event_types_become_unknown(self, monkeypatch, event_type):
        import main as main_mod

        info_messages = []
        monkeypatch.setattr(main_mod, "analytics_rate_limiter", MagicMock())
        monkeypatch.setattr(main_mod.logger, "info", info_messages.append)
        request = _SyntheticAnalyticsRequest({"type": event_type})

        response = await main_mod.track_analytics_event(request)

        assert response == {"status": "ok"}
        assert info_messages == ["[analytics] event received (type=unknown, target_supplied=false)"]
        assert "PRIVATE_" not in "\n".join(info_messages)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("target", "expected"),
        [
            (None, "false"),
            ("", "false"),
            ("   ", "false"),
            (123, "false"),
            ([], "false"),
            ({}, "false"),
            ("destination", "true"),
        ],
    )
    async def test_target_presence_is_a_server_generated_boolean(self, monkeypatch, target, expected):
        import main as main_mod

        info_messages = []
        monkeypatch.setattr(main_mod, "analytics_rate_limiter", MagicMock())
        monkeypatch.setattr(main_mod.logger, "info", info_messages.append)
        request = _SyntheticAnalyticsRequest({"type": "cta_click", "target": target})

        response = await main_mod.track_analytics_event(request)

        assert response == {"status": "ok"}
        assert info_messages == [f"[analytics] event received (type=cta_click, target_supplied={expected})"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("payload", [None, [], "not-an-object"])
    async def test_non_object_payload_preserves_quiet_success(self, monkeypatch, payload):
        import main as main_mod

        info_messages = []
        monkeypatch.setattr(main_mod, "analytics_rate_limiter", MagicMock())
        monkeypatch.setattr(main_mod.logger, "info", info_messages.append)
        request = _SyntheticAnalyticsRequest(payload)

        response = await main_mod.track_analytics_event(request)

        assert response == {"status": "ok"}
        assert info_messages == []

    @pytest.mark.asyncio
    async def test_parse_error_preserves_quiet_success(self, monkeypatch):
        import main as main_mod

        info_messages = []
        detail = "PRIVATE_ANALYTICS_PARSE_DETAIL"
        monkeypatch.setattr(main_mod, "analytics_rate_limiter", MagicMock())
        monkeypatch.setattr(main_mod.logger, "info", info_messages.append)
        request = _SyntheticAnalyticsRequest(error=RuntimeError(detail))

        response = await main_mod.track_analytics_event(request)

        assert response == {"status": "ok"}
        assert info_messages == []

    @pytest.mark.asyncio
    async def test_rate_limit_runs_before_body_parsing(self, monkeypatch):
        import main as main_mod

        info_messages = []
        limiter = MagicMock()
        limiter.raise_if_limited.side_effect = HTTPException(
            status_code=429,
            detail="Too many requests.",
        )
        request = _SyntheticAnalyticsRequest({"type": "cta_click", "target": "PRIVATE_TARGET"})
        monkeypatch.setattr(main_mod, "analytics_rate_limiter", limiter)
        monkeypatch.setattr(main_mod.logger, "info", info_messages.append)

        with pytest.raises(HTTPException) as exc:
            await main_mod.track_analytics_event(request)

        assert exc.value.status_code == 429
        assert request.json_calls == 0
        assert info_messages == []
        limiter.raise_if_limited.assert_called_once_with("203.0.113.121")


# ── CSP Violation Logging ────────────────────────────────


class _SyntheticCspRequest:
    """Minimal request double for direct CSP handler tests."""

    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.json_calls = 0
        self.headers = {"cf-connecting-ip": "203.0.113.120"}
        self.client = None

    async def json(self):
        self.json_calls += 1
        if self.error is not None:
            raise self.error
        return self.payload


class TestCspViolationLogging:
    """CSP reports retain safe diagnostics without logging submitted details."""

    @pytest.mark.asyncio
    async def test_csp_log_keeps_only_validated_summary(self, monkeypatch):
        import main as main_mod

        warning_messages = []
        limiter = MagicMock()
        request = _SyntheticCspRequest(
            {
                "csp-report": {
                    "effective-directive": "script-src-elem",
                    "disposition": "enforce",
                    "status-code": 200,
                    "document-uri": "https://example.test/?token=PRIVATE_DOCUMENT_URI",
                    "blocked-uri": "https://user:PRIVATE_PASSWORD@blocked.test/PRIVATE_PATH?key=PRIVATE_QUERY",
                    "source-file": "https://example.test/PRIVATE_SOURCE.js",
                    "referrer": "https://example.test/PRIVATE_REFERRER",
                    "original-policy": "script-src 'nonce-PRIVATE_NONCE'",
                    "script-sample": "PRIVATE_SCRIPT_SAMPLE",
                    "unknown-field": "PRIVATE_UNKNOWN_FIELD",
                }
            }
        )
        monkeypatch.setattr(main_mod, "csp_report_rate_limiter", limiter)
        monkeypatch.setattr(main_mod.logger, "warning", warning_messages.append)

        response = await main_mod.csp_violation(request)

        assert response.status_code == 204
        assert warning_messages == [
            "CSP violation report received (directive=script-src-elem, disposition=enforce, status=200)"
        ]
        assert "PRIVATE_" not in "\n".join(str(message) for message in warning_messages)
        limiter.raise_if_limited.assert_called_once_with("203.0.113.120")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "directive",
        [
            "script-src\nPRIVATE_CONTROL",
            "x" * 65,
            "script-src-é",
            123,
        ],
    )
    async def test_csp_log_rejects_unsafe_directive(self, monkeypatch, directive):
        import main as main_mod

        warning_messages = []
        monkeypatch.setattr(main_mod, "csp_report_rate_limiter", MagicMock())
        monkeypatch.setattr(main_mod.logger, "warning", warning_messages.append)
        request = _SyntheticCspRequest(
            {
                "csp-report": {
                    "effective-directive": directive,
                    "disposition": "report",
                    "status-code": 0,
                }
            }
        )

        response = await main_mod.csp_violation(request)

        assert response.status_code == 204
        assert warning_messages == ["CSP violation report received (directive=unknown, disposition=report, status=0)"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "payload",
        [
            None,
            [],
            {"csp-report": "not-an-object"},
        ],
    )
    async def test_csp_log_handles_unexpected_report_shapes(self, monkeypatch, payload):
        import main as main_mod

        warning_messages = []
        monkeypatch.setattr(main_mod, "csp_report_rate_limiter", MagicMock())
        monkeypatch.setattr(main_mod.logger, "warning", warning_messages.append)

        response = await main_mod.csp_violation(_SyntheticCspRequest(payload))

        assert response.status_code == 204
        assert warning_messages == [
            "CSP violation report received (directive=unknown, disposition=unknown, status=unknown)"
        ]

    @pytest.mark.asyncio
    async def test_csp_log_uses_safe_fallback_and_rejects_other_invalid_fields(self, monkeypatch):
        import main as main_mod

        warning_messages = []
        monkeypatch.setattr(main_mod, "csp_report_rate_limiter", MagicMock())
        monkeypatch.setattr(main_mod.logger, "warning", warning_messages.append)
        request = _SyntheticCspRequest(
            {
                "csp-report": {
                    "effective-directive": "script-src\nPRIVATE_EFFECTIVE",
                    "violated-directive": "style-src-elem",
                    "disposition": ["PRIVATE_DISPOSITION"],
                    "status-code": True,
                }
            }
        )

        response = await main_mod.csp_violation(request)

        assert response.status_code == 204
        assert warning_messages == [
            "CSP violation report received (directive=style-src-elem, disposition=unknown, status=unknown)"
        ]
        assert "PRIVATE_" not in "\n".join(str(message) for message in warning_messages)

    @pytest.mark.asyncio
    async def test_csp_parse_error_log_excludes_exception_detail(self, monkeypatch):
        import main as main_mod

        warning_messages = []
        limiter = MagicMock()
        detail = "PRIVATE_CSP_PARSE_DETAIL"
        request = _SyntheticCspRequest(error=RuntimeError(detail))
        monkeypatch.setattr(main_mod, "csp_report_rate_limiter", limiter)
        monkeypatch.setattr(main_mod.logger, "warning", warning_messages.append)

        response = await main_mod.csp_violation(request)

        assert response.status_code == 204
        assert warning_messages == ["CSP violation report rejected (RuntimeError)"]
        assert detail not in "\n".join(str(message) for message in warning_messages)
        limiter.raise_if_limited.assert_called_once_with("203.0.113.120")

    @pytest.mark.asyncio
    async def test_csp_rate_limit_still_runs_before_report_parsing(self, monkeypatch):
        import main as main_mod

        warning_messages = []
        limiter = MagicMock()
        limiter.raise_if_limited.side_effect = HTTPException(
            status_code=429,
            detail="Too many requests.",
        )
        request = _SyntheticCspRequest({"csp-report": {}})
        monkeypatch.setattr(main_mod, "csp_report_rate_limiter", limiter)
        monkeypatch.setattr(main_mod.logger, "warning", warning_messages.append)

        with pytest.raises(HTTPException) as exc:
            await main_mod.csp_violation(request)

        assert exc.value.status_code == 429
        assert request.json_calls == 0
        assert warning_messages == []
        limiter.raise_if_limited.assert_called_once_with("203.0.113.120")


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

    def test_csp_violation_endpoint_rate_limited(self, monkeypatch):
        """Unauthenticated CSP report edge is rate-limited per client."""
        from fastapi.testclient import TestClient
        import main as main_mod

        tight = RateLimiter(max_requests=2, window_seconds=60)
        monkeypatch.setattr(main_mod, "csp_report_rate_limiter", tight)
        client = TestClient(main_mod.app)
        headers = {"cf-connecting-ip": "203.0.113.90"}
        assert (
            client.post("/api/csp-violation", json={"csp-report": {}}, headers=headers).status_code
            == 204
        )
        assert (
            client.post("/api/csp-violation", json={"csp-report": {}}, headers=headers).status_code
            == 204
        )
        assert (
            client.post("/api/csp-violation", json={"csp-report": {}}, headers=headers).status_code
            == 429
        )

    def test_public_coupons_api_rate_limited(self, monkeypatch):
        """Public coupon JSON API is rate-limited per client."""
        from fastapi.testclient import TestClient
        import main as main_mod
        import app.routers.public_deals as deals_mod

        tight = RateLimiter(max_requests=2, window_seconds=60)
        monkeypatch.setattr(deals_mod, "public_coupons_api_limiter", tight)
        client = TestClient(main_mod.app)
        headers = {"cf-connecting-ip": "203.0.113.91"}
        assert client.get("/udemycoupons/api/coupons", headers=headers).status_code == 200
        assert client.get("/udemycoupons/api/coupons", headers=headers).status_code == 200
        assert client.get("/udemycoupons/api/coupons", headers=headers).status_code == 429

    def test_auth_status_rate_limited(self, monkeypatch):
        """Auth status probe is rate-limited per client."""
        from fastapi.testclient import TestClient
        import main as main_mod
        import app.routers.auth as auth_mod

        tight = RateLimiter(max_requests=2, window_seconds=60)
        monkeypatch.setattr(auth_mod, "auth_status_rate_limiter", tight)
        client = TestClient(main_mod.app)
        headers = {"cf-connecting-ip": "203.0.113.92"}
        assert client.get("/api/auth/status", headers=headers).status_code == 200
        assert client.get("/api/auth/status", headers=headers).status_code == 200
        assert client.get("/api/auth/status", headers=headers).status_code == 429

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

    def test_lru_eviction_log_excludes_session_token(self, monkeypatch):
        info_messages = []
        monkeypatch.setattr("app.core.cache.logger.info", info_messages.append)
        session_token = "0123456789abcdef" * 4
        replacement_token = "fedcba9876543210" * 4
        cache = SessionCache(max_size=1)

        cache.set(session_token, "first-client")
        cache.set(replacement_token, "replacement-client")

        assert cache.get(session_token) is None
        assert cache.get(replacement_token) == "replacement-client"
        assert info_messages == ["Evicted oldest session from cache (max entries=1)"]
        logged = "\n".join(str(message) for message in info_messages)
        assert session_token not in logged
        assert session_token[:8] not in logged

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

    def test_stop_cleanup_task_handles_its_own_cancellation(self):
        async def run_cleanup():
            cache = SessionCache()
            cleanup_task = cache.start_cleanup_task()

            await cache.stop_cleanup_task()

            assert cleanup_task.cancelled()

        asyncio.run(run_cleanup())

    def test_stop_cleanup_task_propagates_caller_cancellation(self):
        async def run_cleanup():
            first_cancel_seen = asyncio.Event()

            class DelayedCleanupCache(SessionCache):
                async def cleanup_expired(self, interval=300):
                    try:
                        await asyncio.Event().wait()
                    except asyncio.CancelledError:
                        first_cancel_seen.set()
                        await asyncio.Event().wait()

            cache = DelayedCleanupCache()
            cleanup_task = cache.start_cleanup_task()
            stopper = asyncio.create_task(cache.stop_cleanup_task())

            try:
                await asyncio.wait_for(first_cancel_seen.wait(), timeout=1)
                stopper.cancel()

                with pytest.raises(asyncio.CancelledError):
                    await stopper

                assert stopper.cancelled()
                assert cleanup_task.cancelled()
            finally:
                if not stopper.done():
                    stopper.cancel()
                if not cleanup_task.done():
                    cleanup_task.cancel()
                await asyncio.gather(stopper, cleanup_task, return_exceptions=True)

        asyncio.run(run_cleanup())

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
