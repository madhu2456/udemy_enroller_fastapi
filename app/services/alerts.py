"""Minimal operational alerting (F230) — optional webhook, OFF by default.

When ALERT_WEBHOOK_URL is set, selected operational events (enrollment task
failure, stuck-run recovery) POST a small JSON payload to that URL. When
unset, every function is a no-op — no behavior change.

Delivery is best-effort: failures are logged (never the webhook URL or any
secret) and never raised, so alerting can never break the enrollment
pipeline. The webhook URL is read from the environment only and is never
logged.
"""

import datetime
import os
from typing import Any

import httpx
from loguru import logger

_ALERT_TIMEOUT_SECONDS = 5.0
_ALERT_SOURCE = "udemy-enroller"


def _alert_webhook_url() -> str:
    """ALERT_WEBHOOK_URL env value; never logged, never echoed."""
    return (os.environ.get("ALERT_WEBHOOK_URL") or "").strip()


async def send_alert(event: str, message: str, **fields: Any) -> None:
    """Best-effort POST of a JSON alert; no-op when ALERT_WEBHOOK_URL is unset.

    Payload contains only the event name, a human-readable message, the
    supplied fields (run/user ids, never credentials), and a timestamp.
    """
    webhook = _alert_webhook_url()
    if not webhook:
        return
    payload = {
        "source": _ALERT_SOURCE,
        "event": event,
        "message": message,
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat() + "Z",
    }
    payload.update(fields)
    try:
        async with httpx.AsyncClient(timeout=_ALERT_TIMEOUT_SECONDS) as client:
            response = await client.post(webhook, json=payload)
        if response.status_code >= 400:
            logger.warning(
                f"alert webhook returned HTTP {response.status_code} "
                f"for event {event}"
            )
    except Exception as exc:
        logger.warning(
            f"alert webhook delivery failed for event {event} "
            f"({type(exc).__name__})"
        )
