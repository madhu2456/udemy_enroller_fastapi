"""T2 safe_json Cloudflare-aware red-green proof (mock httpx.Response only).

Acceptance:
 (1) CF HTML returns None with zero ERROR logs
 (2) exactly 1x WARNING with host/path+ctype+120ch snippet
 (3) valid JSON still parses; non-CF invalid -> None with single truncated ERROR
 (4) no contract/signature change
"""
import inspect

import httpx
import pytest
from unittest.mock import AsyncMock, patch

from app.services.http_client import AsyncHTTPClient


CF_HTML = (
    "<html><head><title>Just a moment...</title></head><body>"
    '<div id="cf-browser-verification">Verifying you are human. '
    "Attention Required! | Cloudflare cf-challenge cf_chl "
    + "x" * 800
    + "</div></body></html>"
)

CF_URL = "https://www.udemy.com/api-2.0/courses/?category=dev"


async def _make_client():
    c = AsyncHTTPClient()
    c._apply_human_like_delay = AsyncMock(return_value=None)
    return c


def _resp(status, ctype, body: bytes, url=CF_URL):
    return httpx.Response(
        status,
        headers={"content-type": ctype},
        content=body,
        request=httpx.Request("GET", url),
    )


@pytest.mark.asyncio
async def test_cf_html_returns_none_with_zero_error_and_single_warning():
    """Acceptance (1): CF HTML -> None, zero ERROR, exactly 1x WARNING."""
    client = await _make_client()
    try:
        resp = _resp(403, "text/html; charset=UTF-8", CF_HTML.encode())
        with patch("app.services.http_client.logger") as mock_logger:
            out = await client.safe_json(resp, context="test-cf")
            assert out is None
            assert mock_logger.error.call_count == 0, (
                f"CF must not log ERROR, got {mock_logger.error.call_args_list!r}"
            )
            assert mock_logger.warning.call_count == 1, (
                f"CF must log exactly 1x WARNING, got {mock_logger.warning.call_count}"
            )
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_cf_warning_contains_host_path_ctype_and_120ch_snippet():
    """Acceptance (2): WARNING carries host/path+ctype+120ch single-line snippet."""
    client = await _make_client()
    try:
        resp = _resp(403, "text/html", CF_HTML.encode())
        with patch("app.services.http_client.logger") as mock_logger:
            await client.safe_json(resp, context="cat-page")
            assert mock_logger.warning.call_count == 1
            text = str(mock_logger.warning.call_args)
            assert "udemy.com" in text, f"WARNING must contain host, got {text!r}"
            assert "text/html" in text, f"WARNING must contain ctype, got {text!r}"
            assert "\n" not in mock_logger.warning.call_args[0][0], "snippet must be single-line"
            # snippet portion after 'snippet' marker must be <=120 chars (+tolerance for surrounding fmt)
            # enforce hygiene: no 500-char body dump
            logged = mock_logger.warning.call_args[0][0]
            assert len(logged) < 500, f"WARNING must not dump full body, len={len(logged)}"
            # extract snippet tail: must not contain >120 contiguous body chars
            assert "x" * 121 not in logged, "snippet must be truncated to <=120 chars"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_valid_json_still_parses():
    """Acceptance (3a): valid JSON dict+list parse unchanged."""
    client = await _make_client()
    try:
        r1 = httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=b'{"a": 1}',
            request=httpx.Request("GET", CF_URL),
        )
        r2 = httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=b"[1, 2]",
            request=httpx.Request("GET", CF_URL),
        )
        with patch("app.services.http_client.logger") as mock_logger:
            assert await client.safe_json(r1) == {"a": 1}
            assert await client.safe_json(r2) == [1, 2]
            assert mock_logger.error.call_count == 0
            assert mock_logger.warning.call_count == 0
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_non_cf_invalid_json_single_truncated_error():
    """Acceptance (3b): non-CF invalid -> None, single ERROR, truncated single line."""
    client = await _make_client()
    try:
        body = b"not-json!! " + b"y" * 800
        resp = _resp(200, "application/json", body)
        with patch("app.services.http_client.logger") as mock_logger:
            out = await client.safe_json(resp, context="api-breakage")
            assert out is None
            assert mock_logger.warning.call_count == 0
            assert mock_logger.error.call_count == 1, (
                f"non-CF must log exactly 1x ERROR, got {mock_logger.error.call_count}"
            )
            logged = mock_logger.error.call_args[0][0]
            assert "\n" not in logged
            assert len(logged) < 500, f"ERROR must be truncated, len={len(logged)}"
            assert "y" * 121 not in logged, "ERROR snippet must be <=120 chars"
            assert "200" in logged and "application/json" in logged
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_safe_json_none_returns_none_without_log():
    client = await _make_client()
    try:
        with patch("app.services.http_client.logger") as mock_logger:
            assert await client.safe_json(None) is None
            assert mock_logger.error.call_count == 0
            assert mock_logger.warning.call_count == 0
    finally:
        await client.close()


def test_no_signature_change():
    """Acceptance (4): safe_json signature/contract unchanged."""
    assert list(inspect.signature(AsyncHTTPClient.safe_json).parameters) == [
        "self",
        "response",
        "context",
    ]
