"""Re-validate public coupon catalog (public_deals.json) — no user DB.

Each cycle:
1. (optional, CHECKER_SCRAPE_ON_CYCLE=true) Scrapes the coupon sources and
   merges fresh deals into the catalog (failure-tolerant; log + continue).
2. Loads deals from PUBLIC_DEALS_PATH (or project-root public_deals.json),
   checks each coupon against Udemy's unauthenticated pricing API, drops
   confirmed expired deals, preserves deals that could not be checked, then
   rewrites the JSON and refreshes sitemap deal URLs.

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

# Course-id extraction. Udemy removed the data-course-id attribute from course
# HTML; the numeric id now appears only in embedded JSON as
# "urlMobileNativeDeeplink":"udemy://discover?courseId=7220277" and
# "courseId":7220277. Current forms come first (priority order); the legacy
# patterns stay as fallbacks for cached/older HTML.
_COURSE_ID_PATTERNS = (
    re.compile(r"udemy://discover\?courseId=(\d+)"),
    re.compile(r'"courseId"\s*:\s*(\d+)'),
    re.compile(r"(?<![A-Za-z])courseId[=:]\s*[\"']?(\d+)"),
    re.compile(r'data-course-id="(\d+)"'),
    re.compile(r'"id"\s*:\s*(\d{3,})\s*,\s*"title"'),
    re.compile(r"course_id=(\d+)"),
    re.compile(r"/course/(\d{3,})/"),
)

# Course-page fetches are intermittently blocked (403 / empty body), so the
# resolver retries a bounded number of times before giving up. Added latency
# per deal stays under ~15s worst case (2 retries x 4s sleep).
_RESOLVE_MAX_ATTEMPTS = 3
_RESOLVE_RETRY_SLEEP_SECONDS = 4


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


def _extract_course_id_from_html(html: str) -> Optional[str]:
    """Pull the numeric course id from a fetched course page (first match wins)."""
    for pattern in _COURSE_ID_PATTERNS:
        match = pattern.search(html)
        if match:
            return match.group(1)
    return None


async def _resolve_course_id(http: AsyncHTTPClient, url: str) -> Optional[str]:
    """Fetch the course page and extract its numeric course id.

    Retries on blocked/empty fetches (403 or empty body); a full page that
    simply contains no matching pattern is treated as deterministic and not
    retried. Bounded: at most ``_RESOLVE_MAX_ATTEMPTS`` fetches.
    """
    for attempt in range(1, _RESOLVE_MAX_ATTEMPTS + 1):
        resp = await http.get(url, use_cloudscraper=True, log_failures=False)
        html = resp.text if resp and getattr(resp, "text", None) else ""
        if html:
            return _extract_course_id_from_html(html)
        if attempt < _RESOLVE_MAX_ATTEMPTS:
            await asyncio.sleep(_RESOLVE_RETRY_SLEEP_SECONDS)
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


def _scrape_enabled() -> bool:
    """Env toggle: import latest coupons each cycle (default on)."""
    return os.getenv("CHECKER_SCRAPE_ON_CYCLE", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _scrape_source_limit() -> int:
    """Env cap on how many sources to scrape per cycle (0 = all)."""
    raw = os.getenv("CHECKER_SCRAPE_MAX_SOURCES", "0").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def _deal_from_course(course) -> dict:
    """Shape a scraped ``Course`` into a catalog deal dict for the merge.

    ``slug`` is set from the URL path so the merge dedupes against catalog
    rows by slug. ``enrolled_at`` is set to now so freshly scraped deals sort
    above the 500-deal cap (the sort falls back to enrolled_at when
    last_checked_at is absent). ``last_checked_at`` is deliberately NOT set:
    a merged-but-unvalidated deal must not look "checked"; the validation
    pass stamps it with the real value moments later.
    """
    now = _utcnow_iso()
    return {
        "title": course.title,
        "url": course.url,
        "slug": course.slug,
        "course_id": str(course.course_id) if course.course_id else None,
        "coupon_code": course.coupon_code,
        "site": course.site,
        "is_coupon_valid": True,
        "enrolled_at": now,
    }


async def _import_latest_coupons() -> int:
    """Scrape the coupon sources and merge fresh deals into the catalog.

    Runs BEFORE validation so the merged deals are re-checked in the same
    cycle. Failure-tolerant by design: any scrape/merge error is logged and
    the cycle continues with the existing catalog (a scraper outage must not
    kill coupon validation). Returns the number of scraped deals merged.
    """
    if not _scrape_enabled():
        logger.info("Coupon import disabled (CHECKER_SCRAPE_ON_CYCLE != true)")
        return 0
    try:
        from app.services.public_deals_export import merge_deals_into_public_catalog
        from app.services.scraper import SCRAPER_REGISTRY, ScraperService

        sites = list(SCRAPER_REGISTRY.keys())
        limit = _scrape_source_limit()
        if limit:
            sites = sites[:limit]
        logger.info("Importing latest coupons: scraping %s source(s)...", len(sites))
        # ScraperService owns pacing: worker semaphore (MAX_SCRAPER_WORKERS),
        # per-site timeout (SCRAPER_SITE_TIMEOUT_SECONDS) and overall run
        # timeout (SCRAPER_RUN_TIMEOUT_SECONDS); per-source failures already
        # yield state "failed" without raising.
        service = ScraperService(sites_to_scrape=sites)
        try:
            courses = await service.scrape_all()
        finally:
            await service.close()

        payload = [_deal_from_course(c) for c in courses]
        if not payload:
            logger.info("Scrapers found no coupon deals to import")
            return 0
        merge_deals_into_public_catalog(payload)
        logger.info("Merged %s scraped deal(s) into the catalog", len(payload))
        return len(payload)
    except Exception as exc:
        logger.error("Coupon import failed — continuing with validation: %s", exc)
        return 0


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

    # Auto-import: scrape the coupon sources and merge fresh deals in, then
    # validate the merged set in this same cycle (new coupons get checked
    # before the file is rewritten). Failure-tolerant — see _import_latest_coupons.
    imported = await _import_latest_coupons()
    if imported:
        deals = load_public_deals()
        if not deals:
            logger.warning("Catalog empty after import — nothing to check.")
            return
        logger.info(
            "Validating %s deals (incl. %s freshly imported)",
            len(deals),
            imported,
        )

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
