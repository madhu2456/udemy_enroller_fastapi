"""F230: alert webhook — mocked transport, no live calls.

ALERT_WEBHOOK_URL unset -> no-op (default OFF). When set, send_alert POSTs a
JSON payload with event/message/fields; delivery failures are swallowed
(alerting must never raise into the enrollment pipeline).
"""

import pytest

from app.services import alerts
from app.services.alerts import send_alert


def _make_client_factory(captured, status=200):
    import httpx

    # Capture the REAL class before monkeypatch replaces the module
    # attribute; otherwise the factory would recurse into itself.
    original_async_client = httpx.AsyncClient

    def handler(request):
        captured.append(request)
        return httpx.Response(status, json={})

    transport = httpx.MockTransport(handler)
    return lambda *a, **k: original_async_client(transport=transport, **k)


@pytest.mark.asyncio
async def test_noop_when_webhook_unset(monkeypatch):
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    called = []

    async def _boom(*a, **k):
        called.append(1)
        raise AssertionError("must not POST when webhook unset")

    monkeypatch.setattr(alerts.httpx, "AsyncClient", _boom)
    await send_alert("enrollment_failed", "x")
    assert called == []


@pytest.mark.asyncio
async def test_posts_json_payload(monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.example.in/alert")
    captured = []
    monkeypatch.setattr(
        alerts.httpx, "AsyncClient", _make_client_factory(captured, status=200)
    )
    await send_alert(
        "enrollment_stuck",
        "Enrollment run 7 (user 3) marked failed",
        run_id=7,
        user_id=3,
    )
    assert len(captured) == 1
    request = captured[0]
    assert request.url == "https://hooks.example.in/alert"
    payload = request.content.decode()
    import json

    parsed = json.loads(payload)
    assert parsed["event"] == "enrollment_stuck"
    assert parsed["run_id"] == 7
    assert parsed["user_id"] == 3
    assert parsed["source"] == "udemy-enroller"


@pytest.mark.asyncio
async def test_non_2xx_swallowed(monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.example.in/alert")
    captured = []
    monkeypatch.setattr(
        alerts.httpx, "AsyncClient", _make_client_factory(captured, status=500)
    )
    await send_alert("enrollment_failed", "boom")  # must not raise
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_transport_error_swallowed(monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.example.in/alert")

    class _Broken:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            raise OSError("webhook unreachable")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(alerts.httpx, "AsyncClient", _Broken)
    await send_alert("enrollment_failed", "boom")  # must not raise
