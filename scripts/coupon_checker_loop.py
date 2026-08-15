#!/usr/bin/env python3
"""Run coupon validation on an interval and refresh /udemycoupons.

Intended for production (Docker ``coupon-checker`` service). Each cycle:
1. Loads public_deals.json (catalog file — not the multi-tenant user DB)
2. Imports latest coupons (scrapes coupon sources, merges fresh deals —
   toggle with CHECKER_SCRAPE_ON_CYCLE, see .env.example) — before validation
3. Re-validates each coupon via Udemy's unauthenticated pricing API
4. Drops confirmed expired deals, rewrites JSON + sitemap

A tiny HTTP endpoint on 127.0.0.1:<port>/health (F-ENRL-C15) reports liveness
and catalog freshness for the Docker healthcheck:

Environment:
  COUPON_CHECKER_INTERVAL_SECONDS  sleep between cycles (default 7200 = 2h)
  COUPON_CHECKER_RUN_ON_START      if "1"/"true" (default), run once immediately
  PUBLIC_DEALS_PATH                path for public_deals.json (persistent volume)
  COUPON_CHECKER_HEALTH_PORT       health endpoint port (default 8001)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Project root on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("coupon_checker_loop")

# Catalog considered stale when no successful cycle finished within 26 hours
# (F-ENRL-C15): public_deals.json then no longer reflects live coupon status.
STALE_AFTER_SECONDS = 26 * 3600
DEFAULT_HEALTH_PORT = 8001


class HealthState:
    """Thread-safe record of cycle timing for the /health endpoint."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started_at: float | None = None  # epoch seconds, latest cycle start
        self._finished_at: float | None = None  # epoch seconds, last success

    def mark_started(self) -> None:
        with self._lock:
            self._started_at = time.time()

    def mark_finished(self) -> None:
        with self._lock:
            self._finished_at = time.time()

    def snapshot(self) -> tuple[float | None, float | None]:
        with self._lock:
            return self._started_at, self._finished_at


def _health_port() -> int:
    raw = os.getenv("COUPON_CHECKER_HEALTH_PORT", "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            logger.warning(
                "Invalid COUPON_CHECKER_HEALTH_PORT=%r; using %s",
                raw,
                DEFAULT_HEALTH_PORT,
            )
    return DEFAULT_HEALTH_PORT


class _HealthHandler(BaseHTTPRequestHandler):
    """GET /health → 200 + last_run_age_seconds, 503 when stale (F-ENRL-C15).

    Age is measured from the last successful cycle finish; before any success
    it falls back to the latest cycle start. No run ever started → stale.
    """

    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_error(404)
            return
        started_at, finished_at = self.server.health_state.snapshot()
        now = time.time()
        baseline = finished_at if finished_at is not None else started_at
        age_seconds = int(now - baseline) if baseline is not None else None
        stale = age_seconds is None or age_seconds > STALE_AFTER_SECONDS
        body = json.dumps(
            {
                "status": "stale" if stale else "ok",
                "last_run_age_seconds": age_seconds,
            }
        ).encode("utf-8")
        self.send_response(503 if stale else 200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        # Access logs are noise in the loop's own stdout; keep them at debug.
        logger.debug("health: " + fmt % args)


def _start_health_server(health_state: HealthState) -> ThreadingHTTPServer:
    """Bind the health endpoint on loopback and serve it on a daemon thread."""
    port = _health_port()
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), _HealthHandler)
    except OSError as exc:
        logger.error(
            "Cannot bind health endpoint on 127.0.0.1:%s: %s "
            "(set COUPON_CHECKER_HEALTH_PORT to a free port)",
            port,
            exc,
        )
        raise
    server.health_state = health_state
    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
        name="coupon-checker-health",
    )
    thread.start()
    logger.info("Health endpoint: http://127.0.0.1:%d/health", port)
    return server


def _interval_seconds() -> int:
    raw = os.getenv("COUPON_CHECKER_INTERVAL_SECONDS", "").strip()
    if raw:
        try:
            return max(60, int(raw))
        except ValueError:
            logger.warning(
                "Invalid COUPON_CHECKER_INTERVAL_SECONDS=%r; using settings/default",
                raw,
            )
    try:
        from config.settings import get_settings

        return max(60, int(get_settings().COUPON_CHECKER_INTERVAL_SECONDS))
    except Exception:
        return 7200


def _run_on_start() -> bool:
    return os.getenv("COUPON_CHECKER_RUN_ON_START", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _seed_public_deals_if_needed() -> None:
    """Copy image/repo public_deals.json onto the volume path once."""
    try:
        from app.services.public_deals_export import (
            DEFAULT_PUBLIC_DEALS_PATH,
            get_public_deals_path,
        )

        target = get_public_deals_path()
        if not target or os.path.exists(target):
            return
        if target == DEFAULT_PUBLIC_DEALS_PATH:
            return
        if not os.path.exists(DEFAULT_PUBLIC_DEALS_PATH):
            return
        parent = os.path.dirname(os.path.abspath(target))
        if parent:
            os.makedirs(parent, exist_ok=True)
        import shutil

        shutil.copy2(DEFAULT_PUBLIC_DEALS_PATH, target)
        logger.info("Seeded %s from image/repo public_deals.json", target)
    except Exception as exc:
        logger.warning("Could not seed public_deals path: %s", exc)


async def _run_one_cycle() -> None:
    # Load coupon_checker by path (scripts/ is not a Python package)
    import importlib.util

    checker_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coupon_checker.py")
    spec = importlib.util.spec_from_file_location("coupon_checker_job", checker_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load coupon checker from {checker_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    await module.main()


def main() -> None:
    # Fail fast on invalid settings (bad SECRET_KEY / COOKIE_ENCRYPTION_KEY /
    # DEPLOYMENT_ENV) instead of silently retrying forever with a stale catalog.
    try:
        from config.settings import get_settings

        get_settings()
    except Exception as exc:
        logger.error("Settings validation failed: %s", exc)
        print(
            "Coupon checker aborting: settings validation failed "
            "— check SECRET_KEY/COOKIE_ENCRYPTION_KEY/DEPLOYMENT_ENV",
            file=sys.stderr,
        )
        sys.exit(1)

    interval = _interval_seconds()
    logger.info(
        "Coupon checker loop starting (interval=%ss, run_on_start=%s)",
        interval,
        _run_on_start(),
    )
    _seed_public_deals_if_needed()

    health_state = HealthState()
    _start_health_server(health_state)

    first = True
    while True:
        if first and not _run_on_start():
            first = False
            logger.info("Skipping initial run; sleeping %ss", interval)
            time.sleep(interval)
            continue
        first = False

        started = time.monotonic()
        logger.info("=== Coupon check cycle start ===")
        health_state.mark_started()
        try:
            asyncio.run(_run_one_cycle())
            health_state.mark_finished()
            logger.info(
                "=== Coupon check cycle finished in %.1fs ===",
                time.monotonic() - started,
            )
        except Exception as exc:
            logger.exception("Coupon check cycle failed: %s", exc)

        logger.info("Sleeping %ss until next cycle", interval)
        time.sleep(interval)


if __name__ == "__main__":
    main()
