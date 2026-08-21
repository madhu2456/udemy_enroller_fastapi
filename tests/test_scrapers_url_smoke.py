"""Bounded live URL smoke for the 12 registry scrapers.

Opt-in: RUN_LIVE_TESTS=true and pytest -o addopts= (pytest.ini deselects live_third_party).
Does not scrape Real Discount or Discudemy. Does not patch scraper.py.
Stops after a few Udemy course URLs (target 5) or 180s per source.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path
from typing import Optional

import pytest
import pytest_asyncio

from app.services.http_client import AsyncHTTPClient
from app.services.scraper import SCRAPER_REGISTRY

pytestmark = [
    pytest.mark.allow_network,
    pytest.mark.live_third_party,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_TESTS") != "true",
        reason="Live scraper tests require RUN_LIVE_TESTS=true",
    ),
]

LIVE_FLEET = [
    "FreeCourseSites",
    "E-next",
    "Interview Gig",
    "UdemyXpert",
    "Coursesity",
    "Course Folder",
    "Couponami",
    "Korshub",
    "UdemyFreebies",
    "iDownloadCoupon",
    "Courson",
    "CouponScorpion",
]

CLASS_ATTR_CAPS = {
    "FreeCourseSites": {
        "MAX_COURSES": 5,
        "MAX_REST_PAGES": 1,
        "MAX_FALLBACK_ARCHIVE_PAGES": 1,
    },
    "E-next": {"MAX_COURSES": 5, "MAX_LISTING_PAGES": 1},
    "Interview Gig": {"MAX_COURSES": 5, "MAX_API_PAGES": 1},
    "CouponScorpion": {"MAX_COURSES": 5},
    "Courson": {"MAX_COUPON_PAGES": 2},
}

# Local max_courses=500 inside scrape(); listing limiter + StopSmoke after 5 URLs.
LOCAL_MAX_SITES = {
    "UdemyXpert",
    "Coursesity",
    "Course Folder",
    "Couponami",
    "Korshub",
    "UdemyFreebies",
    "iDownloadCoupon",
}

LISTING_URL_RE = {
    "UdemyXpert": re.compile(r"sitemap\.xml", re.I),
    "Coursesity": re.compile(r"/provider/free/udemy-courses", re.I),
    "Course Folder": re.compile(r"free-udemy-coupon\.php", re.I),
    "Couponami": re.compile(r"post-sitemap", re.I),
    "Korshub": re.compile(r"/courses\?page=", re.I),
    "UdemyFreebies": re.compile(r"/free-udemy-courses/", re.I),
    "iDownloadCoupon": re.compile(r"idownloadcoupon\.com/page/", re.I),
}

HOP_URL_RE = re.compile(
    r"/go/|/out/|out\.php|/udemy/\d+|trk\.udemy|/coupon/"
    r"|/course-detail/|/courses/[A-Za-z0-9_-]+",
    re.I,
)

TARGET_UNIQUE = 5
PER_SOURCE_TIMEOUT = 180
LOG_PATH = Path("logs/scraper_url_smoke.log")
REPO_ROOT = Path(__file__).resolve().parents[1]


class StopSmoke(BaseException):
    """Not a subclass of Exception, so scrape() except Exception will not swallow it."""


class _DummyResponse:
    def __init__(self, url: str = ""):
        self.status_code = 200
        self.text = "<html></html>"
        self.content = b"<html></html>"
        self.headers = {}
        self.url = url


def _udemy_urls(scraper) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for course in scraper.data:
        url = getattr(course, "url", "") or ""
        if "udemy.com/course/" not in url:
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def _apply_caps(site: str, scraper) -> None:
    for attr, value in CLASS_ATTR_CAPS.get(site, {}).items():
        setattr(scraper, attr, value)


def _classify(unique: int, outcome: str, scraper, calls: list[dict]) -> str:
    if unique >= 1:
        return "working"
    if outcome == "timeout":
        return "timeout"
    err = scraper.error or ""
    real = [c for c in calls if not c.get("dummy")]
    ok = [c for c in real if c.get("status") == 200]
    hops = [c for c in real if HOP_URL_RE.search(c.get("url") or "")]
    if scraper.circuit_open or "Circuit breaker" in err:
        return "not working"
    if hops:
        return "hop-fail"
    if not ok:
        return "not working"
    return "origin-empty"


def _notes(status: str, outcome: str, scraper, elapsed: float, calls: list[dict]) -> str:
    real = [c for c in calls if not c.get("dummy")]
    ok = sum(1 for c in real if c.get("status") == 200)
    hops = sum(1 for c in real if HOP_URL_RE.search(c.get("url") or ""))
    bits = [f"{elapsed:.1f}s", f"http200={ok}/{len(real)}", f"hops={hops}", f"stop={outcome}"]
    if scraper.circuit_open:
        bits.append("circuit_open")
    err = scraper.error
    if err and status != "working":
        one_line = " ".join(str(err).split())[:180]
        bits.append(f"error={one_line}")
    return "; ".join(bits)


def _append_log(text: str) -> None:
    log_path = REPO_ROOT / LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(text)
        if not text.endswith("\n"):
            fh.write("\n")


def _format_table(rows: list[dict]) -> str:
    lines = [
        "| Source | Status | unique Udemy URLs | sample | notes |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for row in rows:
        sample = row["sample"] or ""
        notes = row["notes"].replace("|", "/")
        sample = sample.replace("|", "%7C")
        lines.append(
            f"| {row['source']} | {row['status']} | {row['unique']} | {sample} | {notes} |"
        )
    return "\n".join(lines)


@pytest_asyncio.fixture(loop_scope="function")
async def http_client():
    client = AsyncHTTPClient()
    yield client
    await client.close()


async def _smoke_one(site: str, http: AsyncHTTPClient) -> dict:
    scraper_cls = SCRAPER_REGISTRY[site]
    scraper = scraper_cls(http)
    _apply_caps(site, scraper)

    calls: list[dict] = []
    listing_hits = 0
    listing_lock = asyncio.Lock()
    listing_re: Optional[re.Pattern] = LISTING_URL_RE.get(site)
    orig_get = http.get
    orig_append = scraper.append_to_list

    def wrapped_append(title: str, url: str):
        orig_append(title, url)
        if len(_udemy_urls(scraper)) >= TARGET_UNIQUE:
            raise StopSmoke()

    scraper.append_to_list = wrapped_append

    async def wrapped_get(url, *args, **kwargs):
        nonlocal listing_hits
        if listing_re and listing_re.search(str(url) or ""):
            async with listing_lock:
                if listing_hits >= 1:
                    calls.append({"url": str(url), "status": 200, "dummy": True})
                    return _DummyResponse(str(url))
                listing_hits += 1
        if len(_udemy_urls(scraper)) >= TARGET_UNIQUE:
            raise StopSmoke()
        try:
            resp = await orig_get(url, *args, **kwargs)
            status = getattr(resp, "status_code", None) if resp is not None else None
            calls.append({"url": str(url), "status": status, "dummy": False})
            return resp
        except StopSmoke:
            raise
        except Exception as exc:
            calls.append(
                {
                    "url": str(url),
                    "status": None,
                    "dummy": False,
                    "error": type(exc).__name__,
                }
            )
            raise

    http.get = wrapped_get
    sem = asyncio.Semaphore(5)
    loop = asyncio.get_running_loop()
    pre_tasks = set(asyncio.all_tasks(loop))
    started = time.monotonic()
    outcome = "done"
    scrape_task = asyncio.create_task(scraper.scrape(sem), name=f"smoke-{site}")

    async def _watch():
        while not scrape_task.done():
            if len(_udemy_urls(scraper)) >= TARGET_UNIQUE:
                return "enough"
            await asyncio.sleep(0.15)
        return "done"

    try:
        try:
            outcome = await asyncio.wait_for(_watch(), timeout=PER_SOURCE_TIMEOUT)
        except asyncio.TimeoutError:
            outcome = "timeout"
        except StopSmoke:
            outcome = "enough"
    finally:
        if not scrape_task.done():
            scrape_task.cancel()
        try:
            await scrape_task
        except StopSmoke:
            if outcome == "done":
                outcome = "enough"
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        extras = set(asyncio.all_tasks(loop)) - pre_tasks
        extras.discard(asyncio.current_task())
        for task in extras:
            task.cancel()
        if extras:
            await asyncio.gather(*extras, return_exceptions=True)
        http.get = orig_get
        scraper.append_to_list = orig_append

    elapsed = time.monotonic() - started
    urls = _udemy_urls(scraper)
    unique = len(urls)
    status = _classify(unique, outcome, scraper, calls)
    row = {
        "source": site,
        "status": status,
        "unique": unique,
        "sample": urls[0] if urls else "",
        "notes": _notes(status, outcome, scraper, elapsed, calls),
    }
    return row


@pytest.mark.asyncio(loop_scope="function")
async def test_live_registry_scrapers_yield_udemy_urls(http_client):
    assert list(SCRAPER_REGISTRY) == LIVE_FLEET
    assert "FreeWebCart" not in SCRAPER_REGISTRY
    assert "Real Discount" not in SCRAPER_REGISTRY
    assert "Discudemy" not in SCRAPER_REGISTRY

    log_path = REPO_ROOT / LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as fh:
        fh.write(f"# scraper URL smoke started RUN_LIVE_TESTS={os.getenv('RUN_LIVE_TESTS')!r}\n")
        fh.write(f"# fleet={LIVE_FLEET}\n")
        fh.write(f"# per_source_timeout={PER_SOURCE_TIMEOUT}s target_unique={TARGET_UNIQUE}\n")

    rows: list[dict] = []
    for site in LIVE_FLEET:
        print(f"\n=== SMOKE {site} (budget {PER_SOURCE_TIMEOUT}s) ===", flush=True)
        _append_log(f"\n=== SMOKE {site} ===")
        row = await _smoke_one(site, http_client)
        rows.append(row)
        line = (
            f"{row['source']}: status={row['status']} unique={row['unique']} "
            f"sample={row['sample']} notes={row['notes']}"
        )
        print(line, flush=True)
        _append_log(line)

    table = _format_table(rows)
    print("\n" + table, flush=True)
    _append_log("\n" + table + "\n")

    failing = [r["source"] for r in rows if r["unique"] < 1]
    _append_log(f"failing={failing}")
    if failing:
        pytest.fail(
            "Live fleet sources with 0 Udemy URLs: "
            + ", ".join(failing)
            + "\n"
            + table
        )
