"""Re-validate public coupon catalog (public_deals.json) — no user DB.

Loads deals from PUBLIC_DEALS_PATH (or project-root public_deals.json), checks
each coupon against Udemy's unauthenticated pricing API, drops confirmed
expired deals, preserves deals that could not be checked, then rewrites the
JSON and refreshes sitemap deal URLs.

Used by:
  ./scripts/coupon_checker.sh
  scripts/coupon_checker_loop.py (Docker coupon-checker service, every 2h)
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import sys
from datetime import UTC, datetime
from typing import Any, Optional

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.http_client import AsyncHTTPClient
from app.services.public_deals_export import (
    get_public_deals_path,
    load_public_deals,
    save_public_deals,
)
from config.settings import get_settings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

_COURSE_ID_PATTERNS = (
    re.compile(r'data-course-id="(\d+)"'),
    re.compile(r'"id"\s*:\s*(\d{3,})\s*,\s*"title"'),
    re.compile(r"course_id=(\d+)"),
    re.compile(r"/course/(\d{3,})/"),
)


def _utcnow_iso() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _course_id_from_deal(deal: dict) -> Optional[str]:
    raw = deal.get("course_id")
    if raw is None:
        return None
    text = str(raw).strip()
    return text if text.isdigit() else None


async def _resolve_course_id(http: AsyncHTTPClient, url: str) -> Optional[str]:
    resp = await http.get(url, use_cloudscraper=True, log_failures=False)
    if not resp or not getattr(resp, "text", None):
        return None
    html = resp.text
    for pattern in _COURSE_ID_PATTERNS:
        match = pattern.search(html)
        if match:
            return match.group(1)
    return None


async def check_deal(http: AsyncHTTPClient, deal: dict[str, Any]) -> str:
    """Validate one public deal. Mutates deal in place.

    Returns one of: ``valid``, ``expired``, ``skipped``, ``error``.
    """
    url = (deal.get("url") or "").strip()
    coupon = (deal.get("coupon_code") or "").strip()
    title = deal.get("title") or url or "?"

    if not url or not coupon:
        return "skipped"

    try:
        course_id = _course_id_from_deal(deal)
        if not course_id:
            course_id = await _resolve_course_id(http, url)
            if course_id:
                deal["course_id"] = course_id
            else:
                logger.warning("Could not find course_id for %s", title)
                return "error"

        api_url = (
            f"https://www.udemy.com/api-2.0/course-landing-components/"
            f"{course_id}/me/?components=purchase,redeem_coupon"
            f"&discountCode={coupon}"
        )
        # Unauthenticated pricing check — no auth headers (WAF-friendly).
        raw_resp = await http.get(api_url, use_cloudscraper=True, log_failures=False)
        resp = await http.safe_json(raw_resp)
        if not resp:
            logger.warning("No pricing JSON for %s", title)
            return "error"

        purchase = resp.get("purchase") or resp.get("cacheable_purchase")
        if not purchase:
            logger.warning("No purchase data for %s", title)
            return "error"

        purchase_data = purchase.get("data") or {}
        pricing_result = purchase_data.get("pricing_result") or {}
        lp = (purchase_data.get("list_price") or {}).get("amount") or 0

        price_obj = pricing_result.get("price")
        if price_obj is None:
            is_free = bool(pricing_result.get("is_free", False))
            final_price = 0.0 if is_free else 9999.0
        else:
            final_price = float(price_obj.get("amount") or 0)
            is_free = bool(pricing_result.get("is_free", False) or final_price == 0)

        deal["last_checked_at"] = _utcnow_iso()
        if lp:
            try:
                deal["price"] = float(lp)
            except (TypeError, ValueError):
                pass

        if is_free:
            deal["is_coupon_valid"] = True
            logger.info("[VALID] %s (price=%s)", title, final_price)
            return "valid"

        deal["is_coupon_valid"] = False
        logger.info("[EXPIRED] %s (price=%s)", title, final_price)
        return "expired"

    except Exception as exc:
        logger.error("Error checking %s: %s", title, exc)
        return "error"


async def main() -> None:
    logger.info("Starting Coupon Checker (public_deals.json catalog)...")
    settings = get_settings()
    # Write target (volume path in Docker). load_public_deals() falls back to the
    # image/repo copy when the volume file is not seeded yet.
    json_path = get_public_deals_path()
    deals = load_public_deals()

    logger.info("Loaded %s deals (write path: %s)", len(deals), json_path)

    if not deals:
        logger.warning("No deals to check — public_deals.json empty or missing.")
        return

    proxy_url = None
    if settings.PROXIES:
        proxies = [p.strip() for p in settings.PROXIES.split(",") if p.strip()]
        if proxies:
            proxy_url = random.choice(proxies)
            logger.info("Using proxy for network configuration.")

    http = AsyncHTTPClient(proxy=proxy_url)
    stats = {"valid": 0, "expired": 0, "error": 0, "skipped": 0}

    try:
        batch_size = 5
        total = len(deals)
        for i in range(0, total, batch_size):
            batch = deals[i : i + batch_size]
            results = await asyncio.gather(*[check_deal(http, d) for d in batch])
            for status in results:
                stats[status] = stats.get(status, 0) + 1

            done = min(i + batch_size, total)
            logger.info(
                "Processed batch %s/%s (%s/%s deals)",
                i // batch_size + 1,
                (total + batch_size - 1) // batch_size,
                done,
                total,
            )
            # Rate limit between batches
            if done < total:
                await asyncio.sleep(3)
    finally:
        try:
            await http.close()
        except Exception:
            pass

    # Keep valid deals + deals we could not verify (retry next cycle).
    # Drop confirmed expired so /udemycoupons stays accurate.
    kept: list[dict] = []
    for deal in deals:
        if deal.get("is_coupon_valid") is False:
            continue
        # Normalize flag for catalog consumers
        deal["is_coupon_valid"] = True
        kept.append(deal)

    logger.info(
        "Results: valid=%s expired=%s error=%s skipped=%s → keeping %s deals",
        stats["valid"],
        stats["expired"],
        stats["error"],
        stats["skipped"],
        len(kept),
    )

    # Never write an empty catalog after a total failure wave
    if not kept and deals:
        still_marked_valid = sum(1 for d in deals if d.get("is_coupon_valid") is not False)
        if stats["error"] > 0 and stats["valid"] == 0 and stats["expired"] == 0:
            logger.error(
                "All checks failed and none expired — preserving existing catalog "
                "(%s deals) without rewrite.",
                len(deals),
            )
            return
        if still_marked_valid == 0 and stats["expired"] == len(deals):
            logger.warning("All coupons confirmed expired — writing empty catalog.")

    n = save_public_deals(kept, path=json_path, refresh_sitemap=True)
    logger.info("Wrote %s deals to %s (+ sitemap refreshed)", n, json_path)
    logger.info("Coupon Check Completed.")


if __name__ == "__main__":
    asyncio.run(main())
