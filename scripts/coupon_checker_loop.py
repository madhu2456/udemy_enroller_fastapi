#!/usr/bin/env python3
"""Run coupon validation on an interval and refresh /udemycoupons.

Intended for production (Docker ``coupon-checker`` service). Each cycle:
1. Re-validates coupon codes on recent EnrolledCourse rows (Udemy pricing API)
2. Rebuilds public_deals.json + sitemap deal URLs

Environment:
  COUPON_CHECKER_INTERVAL_SECONDS  sleep between cycles (default 7200 = 2h)
  COUPON_CHECKER_RUN_ON_START      if "1"/"true" (default), run once immediately
  PUBLIC_DEALS_PATH                write path for public_deals.json (persistent volume)
  DATABASE_URL                     same DB as the web service
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

# Project root on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("coupon_checker_loop")


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
    interval = _interval_seconds()
    logger.info(
        "Coupon checker loop starting (interval=%ss, run_on_start=%s)",
        interval,
        _run_on_start(),
    )
    _seed_public_deals_if_needed()

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
        try:
            asyncio.run(_run_one_cycle())
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
