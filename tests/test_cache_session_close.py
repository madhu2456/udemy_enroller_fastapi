"""F-ENRL-C09: cached/enrolled session clients are closed on expiry and eviction.

Covers the close-on-expiry path in ``app/deps.get_session`` and the two cache
paths in ``app/core.cache.SessionCache`` (LRU eviction + periodic expired
cleanup). Async closers are scheduled on the running loop; outside a loop the
coroutine is closed without being awaited.
"""

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.cache import SessionCache
from app.deps import get_session
from app.models.database import UserSession, _utcnow_naive


def _request(token: str) -> Request:
    request = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/session",
            "raw_path": b"/api/session",
            "query_string": b"",
            "root_path": "",
            "headers": [(b"cookie", b"session_id=" + token.encode("ascii"))],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
    )
    request.scope["app"] = SimpleNamespace(
        state=SimpleNamespace(session_cache=MagicMock(), udemy_clients={})
    )
    return request


def _expired_session() -> UserSession:
    session = MagicMock(spec=UserSession)
    session.token = "expired-token"
    session.user_id = 1
    session.expires_at = _utcnow_naive() - timedelta(hours=1)
    return session


class TestGetSessionCloseOnExpiry:
    @pytest.mark.asyncio
    async def test_expired_session_closes_sync_client(self, monkeypatch):
        client = MagicMock()
        client.close = MagicMock(return_value=None)
        monkeypatch.setattr(
            "app.deps.cleanup_expired_session", MagicMock(return_value=client)
        )

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = (
            _expired_session()
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_session(_request("expired-token"), db)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Session expired"
        client.close.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_expired_session_awaits_async_client_close(self, monkeypatch):
        client = MagicMock()
        client.close = AsyncMock()
        monkeypatch.setattr(
            "app.deps.cleanup_expired_session", MagicMock(return_value=client)
        )

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = (
            _expired_session()
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_session(_request("expired-token"), db)

        assert exc_info.value.status_code == 401
        client.close.assert_awaited_once_with()

    @pytest.mark.asyncio
    async def test_expired_session_without_client_skips_close(self, monkeypatch):
        monkeypatch.setattr(
            "app.deps.cleanup_expired_session", MagicMock(return_value=None)
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = (
            _expired_session()
        )

        with pytest.raises(HTTPException):
            await get_session(_request("expired-token"), db)

    @pytest.mark.asyncio
    async def test_active_session_returns_without_closing(self, monkeypatch):
        cleanup = MagicMock()
        monkeypatch.setattr("app.deps.cleanup_expired_session", cleanup)
        active = MagicMock(spec=UserSession)
        active.token = "active-token"
        active.user_id = 1
        active.expires_at = _utcnow_naive() + timedelta(hours=5)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = active

        result = await get_session(_request("active-token"), db)

        assert result is active
        cleanup.assert_not_called()


class TestCacheEvictionCloses:
    def test_eviction_closes_sync_value(self):
        cache = SessionCache(max_size=2)
        first, second, third = MagicMock(), MagicMock(), MagicMock()
        cache.set("a", first)
        cache.set("b", second)
        cache.set("c", third)

        first.close.assert_called_once_with()
        second.close.assert_not_called()
        third.close.assert_not_called()
        assert set(cache.keys()) == {"b", "c"}

    @pytest.mark.asyncio
    async def test_eviction_schedules_async_close_on_running_loop(self):
        client = MagicMock()
        client.close = AsyncMock()
        cache = SessionCache(max_size=1)
        cache.set("a", client)
        cache.set("b", object())

        await asyncio.sleep(0.01)
        client.close.assert_awaited_once_with()

    def test_eviction_closes_coroutine_when_no_loop(self):
        """Outside a running loop the async closer is closed, never awaited."""
        cache = SessionCache(max_size=1)
        created = []

        class AsyncCloseValue:
            def close(self):
                coro = self._close()
                created.append(coro)
                return coro

            async def _close(self):
                pass

        cache.set("a", AsyncCloseValue())
        cache.set("b", object())

        assert len(created) == 1
        # cr_frame is None once a coroutine is closed without running.
        assert created[0].cr_frame is None


class TestCacheExpiryCloses:
    @pytest.mark.asyncio
    async def test_cleanup_expired_closes_sync_value(self):
        spy = MagicMock()
        cache = SessionCache()
        cache.set("k1", spy, ttl=-1)

        task = asyncio.create_task(cache.cleanup_expired(interval=0.01))
        try:
            await asyncio.sleep(0.05)
            spy.close.assert_called_once_with()
            assert "k1" not in cache
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    @pytest.mark.asyncio
    async def test_cleanup_expired_schedules_async_close(self):
        client = MagicMock()
        client.close = AsyncMock()
        cache = SessionCache()
        cache.set("k1", client, ttl=-1)

        task = asyncio.create_task(cache.cleanup_expired(interval=0.01))
        try:
            await asyncio.sleep(0.05)
            client.close.assert_awaited_once_with()
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    @pytest.mark.asyncio
    async def test_cleanup_expired_keeps_fresh_entries(self):
        fresh = MagicMock()
        cache = SessionCache()
        cache.set("fresh", fresh, ttl=3600)
        cache.set("stale", MagicMock(), ttl=-1)

        task = asyncio.create_task(cache.cleanup_expired(interval=0.01))
        try:
            await asyncio.sleep(0.05)
            assert "fresh" in cache
            assert "stale" not in cache
            fresh.close.assert_not_called()
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    def test_get_expired_entry_closes_value(self):
        spy = MagicMock()
        cache = SessionCache()
        cache.set("k1", spy, ttl=-1)

        assert cache.get("k1") is None
        spy.close.assert_called_once_with()
        assert "k1" not in cache

    @pytest.mark.asyncio
    async def test_get_expired_entry_schedules_async_close(self):
        client = MagicMock()
        client.close = AsyncMock()
        cache = SessionCache()
        cache.set("k1", client, ttl=-1)

        assert cache.get("k1") is None
        await asyncio.sleep(0.01)
        client.close.assert_awaited_once_with()

    def test_get_fresh_entry_does_not_close(self):
        spy = MagicMock()
        cache = SessionCache()
        cache.set("k1", spy, ttl=3600)

        assert cache.get("k1") is spy
        spy.close.assert_not_called()
