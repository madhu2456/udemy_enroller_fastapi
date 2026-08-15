"""F-ENRL-C05: user-proxy gate tests.

Server mode (ALLOW_USER_PROXY=False) must ignore user-supplied proxies at every
entry point; local mode honors them. ``AsyncHTTPClient.__init__`` stays ungated
so admin-configured PROXIES (coupon checker) still apply on construction.
"""

import pytest

from app.services.http_client import AsyncHTTPClient
from config.settings import get_settings, resolve_user_proxy


@pytest.fixture(autouse=True)
def _restore_allow_user_proxy(monkeypatch):
    """Isolate ALLOW_USER_PROXY per test; default to enabled (local mode)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ALLOW_USER_PROXY", True)
    yield


def _set_allow_user_proxy(monkeypatch, value: bool):
    monkeypatch.setattr(get_settings(), "ALLOW_USER_PROXY", value)


class TestResolveUserProxy:
    def test_honored_when_enabled(self, monkeypatch):
        _set_allow_user_proxy(monkeypatch, True)
        assert resolve_user_proxy("http://user:pass@proxy.example:8080") == (
            "http://user:pass@proxy.example:8080"
        )

    def test_ignored_when_disabled(self, monkeypatch):
        _set_allow_user_proxy(monkeypatch, False)
        assert resolve_user_proxy("http://user:pass@proxy.example:8080") is None

    def test_none_stays_none(self, monkeypatch):
        _set_allow_user_proxy(monkeypatch, True)
        assert resolve_user_proxy(None) is None


class TestAsyncHTTPClientProxyGate:
    @pytest.mark.asyncio
    async def test_set_proxy_honors_user_proxy_when_enabled(self, monkeypatch):
        _set_allow_user_proxy(monkeypatch, True)
        client = AsyncHTTPClient(proxy=None)
        try:
            await client.set_proxy("http://user:pass@proxy.example:8080")
            assert client.proxy == "http://user:pass@proxy.example:8080"
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_set_proxy_ignores_user_proxy_when_disabled(self, monkeypatch):
        _set_allow_user_proxy(monkeypatch, False)
        client = AsyncHTTPClient(proxy=None)
        try:
            await client.set_proxy("http://user:pass@proxy.example:8080")
            assert client.proxy is None
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_init_keeps_admin_proxy_when_disabled(self, monkeypatch):
        """__init__ is deliberately ungated: admin PROXIES still apply."""
        _set_allow_user_proxy(monkeypatch, False)
        client = AsyncHTTPClient(proxy="http://admin:secret@proxy.corp:3128")
        try:
            assert client.proxy == "http://admin:secret@proxy.corp:3128"
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_set_proxy_clears_when_user_clears(self, monkeypatch):
        _set_allow_user_proxy(monkeypatch, True)
        client = AsyncHTTPClient(proxy=None)
        try:
            await client.set_proxy("http://user:pass@proxy.example:8080")
            await client.set_proxy(None)
            assert client.proxy is None
        finally:
            await client.close()
