"""Targeted tests for AsyncHTTPClient boundary SSRF protection (WP-UDEMY-04 / SEC-UDEMY-04)."""

import socket
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.http_client import AsyncHTTPClient, _resolve_host_ips


@pytest.mark.asyncio
async def test_boundary_ssrf_rejects_loopback():
    client = AsyncHTTPClient()
    try:
        # Loopback IPv4
        res = await client.request("GET", "http://127.0.0.1/test")
        assert res is None

        res_get = await client.get("http://127.0.0.1/test")
        assert res_get is None

        # Localhost
        res_local = await client.request("GET", "http://localhost/test")
        assert res_local is None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_boundary_ssrf_rejects_link_local_and_private():
    client = AsyncHTTPClient()
    try:
        # Cloud metadata / link-local
        res_meta = await client.request("GET", "http://169.254.169.254/latest/meta-data/")
        assert res_meta is None

        # Private RFC 1918
        res_priv1 = await client.request("GET", "http://10.0.0.1/admin")
        assert res_priv1 is None

        res_priv2 = await client.request("POST", "http://192.168.1.1/admin")
        assert res_priv2 is None

        res_priv3 = await client.head("http://172.16.0.1/admin")
        assert res_priv3 is None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_boundary_ssrf_rejects_unsafe_scheme_and_ports():
    client = AsyncHTTPClient()
    try:
        # FTP scheme
        res_ftp = await client.request("GET", "ftp://example.com/file")
        assert res_ftp is None

        # Non-standard safe port
        res_port = await client.request("GET", "http://example.com:22/ssh")
        assert res_port is None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_request_delegates_to_get_post_head():
    client = AsyncHTTPClient()
    try:
        with patch.object(client, "_is_safe_url", return_value=True):
            with patch.object(client, "get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = httpx.Response(200, request=httpx.Request("GET", "https://example.com"))
                resp = await client.request("GET", "https://example.com")
                assert resp is not None
                mock_get.assert_called_once()

            with patch.object(client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = httpx.Response(200, request=httpx.Request("POST", "https://example.com"))
                resp = await client.request("POST", "https://example.com")
                assert resp is not None
                mock_post.assert_called_once()

            with patch.object(client, "head", new_callable=AsyncMock) as mock_head:
                mock_head.return_value = httpx.Response(200, request=httpx.Request("HEAD", "https://example.com"))
                resp = await client.request("HEAD", "https://example.com")
                assert resp is not None
                mock_head.assert_called_once()
    finally:
        await client.close()


def test_build_scraper_headers_local_preserves_expected_headers():
    client = AsyncHTTPClient()
    input_headers = {
        "Referer": "https://www.udemy.com/",
        "Authorization": "Bearer mytoken",
        "User-Agent": "okhttp/4.9.2",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.udemy.com",
        "Content-Type": "application/json",
        "x-custom-tracking": "track_123",
        "X-App-Version": "1.0.0",
        "sec-ch-ua": '"Chromium";v="133"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Linux"',
        "Accept-Encoding": "gzip, deflate, br",
        "Host": "www.udemy.com",
        "Cookie": "session=abc",
        "Disallowed-Header": "drop_me",
    }
    result = client._build_scraper_headers_local(input_headers, {}, is_mobile_request=False)

    # Required preserved headers
    assert result["Referer"] == "https://www.udemy.com/"
    assert result["Authorization"] == "Bearer mytoken"
    assert result["User-Agent"] == "okhttp/4.9.2"
    assert result["X-Requested-With"] == "XMLHttpRequest"
    assert result["Accept"] == "application/json, text/plain, */*"
    assert result["Origin"] == "https://www.udemy.com"
    assert result["Content-Type"] == "application/json"
    assert result["x-custom-tracking"] == "track_123"
    assert result["X-App-Version"] == "1.0.0"
    assert result["sec-ch-ua"] == '"Chromium";v="133"'
    assert result["sec-ch-ua-mobile"] == "?0"
    assert result["sec-ch-ua-platform"] == '"Linux"'

    # Accept-Encoding forced to identity
    assert result["Accept-Encoding"] == "identity"

    # Dropped headers
    assert "Host" not in result
    assert "Cookie" not in result
    assert "Disallowed-Header" not in result


def test_build_scraper_headers_local_empty_and_none():
    client = AsyncHTTPClient()
    assert client._build_scraper_headers_local(None, {}, False) == {"Accept-Encoding": "identity"}
    assert client._build_scraper_headers_local({}, {}, False) == {"Accept-Encoding": "identity"}


def test_resolve_host_ips_caching():
    _resolve_host_ips.cache_clear()
    try:
        with patch("socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))
            ]
            first = _resolve_host_ips("example.com")
            second = _resolve_host_ips("example.com")
            assert first == ("93.184.216.34",)
            assert second == ("93.184.216.34",)
            assert mock_gai.call_count == 1
    finally:
        _resolve_host_ips.cache_clear()


def test_resolve_host_ips_negative_cache_exclusion():
    _resolve_host_ips.cache_clear()
    try:
        with patch("socket.getaddrinfo") as mock_gai:
            mock_gai.side_effect = socket.gaierror(-2, "Name or service not known")
            with pytest.raises(socket.gaierror):
                _resolve_host_ips("unresolvable-domain.test")
            assert mock_gai.call_count == 1

            mock_gai.side_effect = None
            mock_gai.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))
            ]
            second = _resolve_host_ips("unresolvable-domain.test")
            assert second == ("93.184.216.34",)
            assert mock_gai.call_count == 2
    finally:
        _resolve_host_ips.cache_clear()


def test_is_safe_url_dns_error_fail_open_local():
    _resolve_host_ips.cache_clear()
    try:
        mock_settings = MagicMock()
        mock_settings.DEPLOYMENT_ENV = "local"
        with patch("config.settings.get_settings", return_value=mock_settings):
            with patch("socket.getaddrinfo", side_effect=socket.gaierror(-2, "Name or service not known")):
                assert AsyncHTTPClient._is_safe_url("http://failing-dns.example.com/test") is True
    finally:
        _resolve_host_ips.cache_clear()


def test_is_safe_url_dns_error_fail_closed_server():
    _resolve_host_ips.cache_clear()
    try:
        mock_settings = MagicMock()
        mock_settings.DEPLOYMENT_ENV = "server"
        with patch("config.settings.get_settings", return_value=mock_settings):
            with patch("socket.getaddrinfo", side_effect=socket.gaierror(-2, "Name or service not known")):
                assert AsyncHTTPClient._is_safe_url("http://failing-dns.example.com/test") is False
    finally:
        _resolve_host_ips.cache_clear()


@pytest.mark.parametrize("env", ["local", "server", "test"])
def test_is_safe_url_private_ip_after_dns_rejected(env):
    _resolve_host_ips.cache_clear()
    try:
        mock_settings = MagicMock()
        mock_settings.DEPLOYMENT_ENV = env
        with patch("config.settings.get_settings", return_value=mock_settings):
            with patch("socket.getaddrinfo") as mock_gai:
                mock_gai.return_value = [
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0))
                ]
                assert AsyncHTTPClient._is_safe_url("http://dns-rebinding-private.example.com/path") is False

                _resolve_host_ips.cache_clear()
                mock_gai.return_value = [
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", 0))
                ]
                assert AsyncHTTPClient._is_safe_url("http://dns-rebinding-lan.example.com/path") is False
    finally:
        _resolve_host_ips.cache_clear()


@pytest.mark.asyncio
async def test_async_http_client_connection_pool_limits():
    client = AsyncHTTPClient()
    try:
        assert client.limits.max_keepalive_connections == 40
        assert client.limits.max_connections == 40
        assert client.limits.keepalive_expiry == 120.0
    finally:
        await client.close()
