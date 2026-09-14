"""IndexNow ping (SEO) — optional, env-gated with ``INDEXNOW_KEY``, OFF by default.

Mirrors the portfolio reference implementation
(madhud_portfolio ``src/app/api/indexnow/route.ts`` +
``src/app/[key].txt/route.ts`` + ``docs/ops/indexnow.md``, pattern F207),
adapted to FastAPI/Python:

- **Key:** the 32-hex IndexNow verification key for
  udemyenroller.madhudadi.in, read from the ``INDEXNOW_KEY`` env var (never
  hardcoded; rotation is owner-ops — update the env var, no code change).
  Documented in docs/ops/indexnow.md (``.env.example`` is not editable under
  the repo tool policy — see docker-compose.yml COUPON_CHECKER note).
- **Key file:** the ownership-verification route ``GET /{key}.txt`` in
  ``app/routers/seo.py`` serves the key only when it matches the configured
  value (fail-closed 404 on unset/mismatch/malformed — same posture as the
  portfolio route).
- **Ping:** when the public coupon catalog is published *and its payload
  changed* (``public_deals_export.save_public_deals`` with
  ``refresh_sitemap=True`` and a byte-diff vs the previous file, i.e. the
  coupon-checker cycle / enrollment-run merge; mid-run snapshots use
  ``refresh_sitemap=False`` and do NOT ping; unchanged re-exports are
  skipped by the RPN-24 change gate), POST the changed URLs to
  https://api.indexnow.org/IndexNow — the same Bing/Yandex-compatible
  endpoint the portfolio uses.

Delivery is best-effort fire-and-forget on a short-lived **daemon thread**
with a synchronous HTTP client: the coupon-checker's asyncio loop closes
immediately after its final save, so an asyncio task could be cancelled
before the request is sent; a daemon thread survives that shutdown and the
5-second timeout applies inside the thread. Failures are logged (never the
key itself) and never raised, so an IndexNow outage can never break the
export pipeline. The key value is never logged.
"""

from __future__ import annotations

import os
import re
import threading
from typing import Callable, Optional
from urllib.parse import urlparse

import httpx
from loguru import logger

# Same endpoint the portfolio IndexNow route posts to (Bing/Yandex et al.).
INDEXNOW_ENDPOINT = "https://api.indexnow.org/IndexNow"
# IndexNow caps a submission at 10,000 URLs; the catalog is bounded at 500
# deals + a handful of hub pages, so 1000 is a generous internal cap.
INDEXNOW_MAX_URLS = 1000
_PING_TIMEOUT_SECONDS = 5.0
# 32-hex shape enforced by the portfolio verification route; the key file
# route and the ping gate share it so a malformed env value can never
# half-work.
_HEX_KEY_RE = re.compile(r"^[a-f0-9]{32}$", re.I)
# Canonical production origin (robots.txt / sitemap SSOT in this repo).
SITE_URL_DEFAULT = "https://udemyenroller.madhudadi.in"
# Hubs whose content is entirely the coupon catalog: pinged on every publish
# so search engines re-crawl refreshed listings.
_CATALOG_HUB_PATHS = ("/udemycoupons", "/")


def _indexnow_key() -> str:
    """INDEXNOW_KEY env value, stripped; empty when unset."""
    return (os.environ.get("INDEXNOW_KEY") or "").strip()


def indexnow_configured() -> bool:
    """True when INDEXNOW_KEY is set AND a valid 32-hex key.

    A malformed key fails closed: pings would be rejected by IndexNow anyway,
    and serving/gating on a half-configured key must never happen.
    """
    return bool(_HEX_KEY_RE.match(_indexnow_key()))


def build_ping_payload(
    paths: list[str], *, site_url: str = SITE_URL_DEFAULT, key: Optional[str] = None
) -> Optional[dict]:
    """Build the IndexNow POST body, or None when the key is unset/invalid.

    Only same-origin paths from the canonical site are submitted: each entry
    must start with a single leading ``/`` (not ``//``), resolve against the
    canonical origin, and stay on that origin. Duplicates are removed
    (order preserved) and the list is capped at ``INDEXNOW_MAX_URLS``.
    """
    resolved_key = key if key is not None else _indexnow_key()
    if not _HEX_KEY_RE.match(resolved_key or ""):
        return None
    origin = site_url.rstrip("/")
    origin_base = f"{urlparse(origin).scheme}://{urlparse(origin).netloc}"
    seen: set[str] = set()
    urls: list[str] = []
    for value in paths:
        if len(urls) >= INDEXNOW_MAX_URLS:
            break
        if not isinstance(value, str):
            continue
        path = value.strip()
        if not path.startswith("/") or path.startswith("//"):
            continue
        try:
            parsed = urlparse(f"{origin}{path}")
        except ValueError:
            continue
        # Defensive: only the canonical host may ever be submitted.
        if f"{parsed.scheme}://{parsed.netloc}" != origin_base:
            continue
        normalized = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        if normalized not in seen:
            seen.add(normalized)
            urls.append(f"{origin}{normalized}")
    if not urls:
        return None
    return {"host": urlparse(origin).netloc, "key": resolved_key, "urlList": urls}


def ping_indexnow_sync(
    paths: list[str], *, site_url: str = SITE_URL_DEFAULT
) -> bool:
    """Submit URLs to IndexNow; no-op unless INDEXNOW_KEY is set/valid.

    Best-effort: transport errors and non-2xx responses are logged at WARNING
    (without the key) and never raised. Returns True only when a submission
    was attempted and accepted (2xx).
    """
    if not indexnow_configured():
        return False
    payload = build_ping_payload([*_CATALOG_HUB_PATHS, *paths], site_url=site_url)
    if payload is None:
        return False
    try:
        with httpx.Client(timeout=_PING_TIMEOUT_SECONDS) as client:
            response = client.post(
                INDEXNOW_ENDPOINT,
                json=payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
        if 200 <= response.status_code < 300:
            logger.info(f"IndexNow ping accepted ({len(payload['urlList'])} URL(s))")
            return True
        logger.warning(
            f"IndexNow ping returned HTTP {response.status_code} "
            f"for {len(payload['urlList'])} URL(s) — continuing"
        )
        return False
    except Exception as exc:
        logger.warning(f"IndexNow ping failed ({type(exc).__name__}) — continuing")
        return False


def _spawn_daemon(worker: Callable[[], None]) -> None:
    """Run the ping worker on a short-lived daemon thread (fire-and-forget).

    Daemon so a process exit never waits on IndexNow; the worker owns its
    own error handling and can never raise into the caller.
    """
    thread = threading.Thread(target=worker, daemon=True, name="indexnow-ping")
    thread.start()


def all_deal_paths(deals: list[dict]) -> list[str]:
    """SEO detail-page paths (``/udemycoupons/c/{slug}``) for exported deals.

    Returns ALL slugged, path-safe entries (the caller decides whether the
    publish warrants a ping — see the RPN-24 change gate in
    ``public_deals_export.save_public_deals``); the export payload is already
    slug-assigned by ``assign_unique_slugs``.
    """
    paths: list[str] = []
    for deal in deals:
        if not isinstance(deal, dict):
            continue
        slug = deal.get("slug")
        if not slug or not isinstance(slug, str):
            continue
        safe = slug.strip().strip("/")
        if not safe or "/" in safe or ".." in safe:
            continue
        paths.append(f"/udemycoupons/c/{safe}")
    return paths


def ping_catalog_publish(
    deals: list[dict], *, spawn: Callable[[Callable[[], None]], None] = _spawn_daemon
) -> None:
    """Fire-and-forget IndexNow ping for a published catalog.

    Called by ``public_deals_export.save_public_deals`` (refresh_sitemap=True
    publish path). No-op unless INDEXNOW_KEY is set (env-gated like
    GTM_CONTAINER_ID / ALERT_WEBHOOK_URL). Never raises: the export pipeline
    must not break on an IndexNow outage. ``spawn`` is injectable so tests can
    run the worker inline (production default: daemon thread).
    """
    try:
        if not indexnow_configured():
            return

        def _worker() -> None:
            # Every failure path is handled inside ping_indexnow_sync; this
            # wrapper is the thread's outer guard so nothing ever escapes.
            try:
                ping_indexnow_sync(all_deal_paths(deals))
            except Exception as exc:  # pragma: no cover - defensive outer guard
                logger.warning(
                    f"IndexNow catalog ping error ({type(exc).__name__})"
                )

        spawn(_worker)
    except Exception as exc:
        logger.warning(f"IndexNow catalog ping dispatch failed ({type(exc).__name__})")
