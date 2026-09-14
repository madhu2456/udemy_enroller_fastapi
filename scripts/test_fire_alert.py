"""Owner test-fire for the F230 alert webhook (A09) — labeled TEST payload.

Posts ONE clearly-labeled test alert through the real ``send_alert`` code
path (``app/services/alerts.py``) so the owner can verify end-to-end
webhook delivery — sink receipt plus payload shape — without waiting for a
real enrollment failure. Matches production semantics: no-op when
``ALERT_WEBHOOK_URL`` is unset (default OFF), best-effort delivery that
never raises. A failed delivery is reported as a captured WARNING and a
non-zero exit code so the owner sees it; the webhook URL itself is never
printed (same rule as the app: secrets stay out of logs).

Usage:
    ALERT_WEBHOOK_URL="https://hooks.example.in/your-webhook" \
        venv/bin/python scripts/test_fire_alert.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.alerts import send_alert  # noqa: E402
from loguru import logger  # noqa: E402


async def main() -> int:
    """Fire one labeled test alert; 0 = OK/no-op, 1 = delivery warned."""
    webhook = (os.environ.get("ALERT_WEBHOOK_URL") or "").strip()
    if not webhook:
        print("ALERT_WEBHOOK_URL is unset — nothing to test (default OFF). OK.")
        return 0

    warnings = []

    def _capture(message: str) -> None:
        warnings.append(message)

    sink_id = logger.add(_capture, level="WARNING")
    try:
        print("Posting ONE labeled TEST alert (event=test_fire) ...")
        await send_alert(
            "test_fire",
            "TEST alert — manual owner test-fire; safe to ignore",
            test=True,
            note="A09/F230 test-fire",
        )
    finally:
        logger.remove(sink_id)

    if any("alert webhook" in w for w in warnings):
        print("RESULT: delivery WARNING captured (see above) — check the URL/sink.")
        return 1
    print("RESULT: posted with no delivery warning — check the sink for the test payload.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
