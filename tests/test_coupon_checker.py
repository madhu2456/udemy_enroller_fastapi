"""Tests for scripts/coupon_checker.py resolver patterns + auto-import wiring.

scripts/ is not a Python package, so the module is loaded by path — the same
mechanism scripts/coupon_checker_loop.py uses. All HTTP is mocked; the suite
blocks external network access.

The pattern fixtures replicate the real shapes observed on Udemy course pages
(verified read-only investigation): the old ``data-course-id`` attribute is
gone, and the numeric course id now appears only in embedded JSON, e.g.
``"urlMobileNativeDeeplink":"udemy://discover?courseId=7220277"`` and
``"courseId":7220277``.
"""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

_CHECKER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "coupon_checker.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("coupon_checker_tests", _CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


# --- FIX 1: course-id pattern extraction -------------------------------------

def test_extract_course_id_legacy_data_course_id():
    html = '<div class="course" data-course-id="7228401">CISCO</div>'
    assert checker._extract_course_id_from_html(html) == "7228401"


def test_extract_course_id_new_deeplink_form():
    html = (
        '<script>{"pageObject":{"urlMobileNativeDeeplink":'
        '"udemy://discover?courseId=7220277"}}</script>'
    )
    assert checker._extract_course_id_from_html(html) == "7220277"


def test_extract_course_id_json_form():
    assert checker._extract_course_id_from_html('{"courseId":7220277}') == "7220277"
    assert checker._extract_course_id_from_html('{"courseId": 7220277}') == "7220277"


def test_extract_course_id_generic_query_form():
    assert checker._extract_course_id_from_html("?courseId=7220277&x=1") == "7220277"
    assert checker._extract_course_id_from_html("courseId= 7220277") == "7220277"


def test_extract_course_id_generic_does_not_match_other_id_words():
    html = '{"relatedCourseId": 42, "precourseId": 7}'
    assert checker._extract_course_id_from_html(html) is None


def test_extract_course_id_no_match_returns_none():
    assert checker._extract_course_id_from_html("<html>nothing here</html>") is None
    assert checker._extract_course_id_from_html("") is None


def test_extract_course_id_new_forms_take_priority_over_legacy():
    html = (
        '<div data-course-id="111111"></div>'
        '<script>{"urlMobileNativeDeeplink":"udemy://discover?courseId=222222"}</script>'
    )
    assert checker._extract_course_id_from_html(html) == "222222"


def test_extract_course_id_realistic_page_fixture():
    """Full-page shape: embedded JSON carrying both deeplink and courseId."""
    html = (
        "<!doctype html><html><head><script>window.__data = "
        '{"course":{"id":7220277,"title":"CISCO ENARSI 300-410"},'
        '"pageObject":{"urlMobileNativeDeeplink":'
        '"udemy://discover?courseId=7220277"}}'
        "</script></head><body></body></html>"
    )
    assert checker._extract_course_id_from_html(html) == "7220277"


# --- FIX 1: bounded retry/backoff in the resolver ----------------------------

def _noop_sleep(monkeypatch):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(checker.asyncio, "sleep", fake_sleep)
    return sleeps


@pytest.mark.asyncio
async def test_resolve_retries_blocked_fetch_then_succeeds(monkeypatch):
    http = AsyncMock()
    http.get.side_effect = [
        None,
        SimpleNamespace(text=""),
        SimpleNamespace(text='{"courseId": 7220277}'),
    ]
    sleeps = _noop_sleep(monkeypatch)
    result = await checker._resolve_course_id(http, "https://www.udemy.com/course/x/")
    assert result == "7220277"
    assert http.get.await_count == 3
    assert sleeps == [4, 4]


@pytest.mark.asyncio
async def test_resolve_gives_up_after_bounded_attempts(monkeypatch):
    http = AsyncMock()
    http.get.return_value = None
    _noop_sleep(monkeypatch)
    result = await checker._resolve_course_id(http, "https://www.udemy.com/course/x/")
    assert result is None
    assert http.get.await_count == checker._RESOLVE_MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_resolve_does_not_retry_deterministic_no_match(monkeypatch):
    http = AsyncMock()
    http.get.return_value = SimpleNamespace(text="<html>full page, no course id</html>")
    _noop_sleep(monkeypatch)
    result = await checker._resolve_course_id(http, "https://www.udemy.com/course/x/")
    assert result is None
    assert http.get.await_count == 1


@pytest.mark.asyncio
async def test_check_deal_skips_page_fetch_when_course_id_present():
    """A deal that already carries course_id must not fetch the course page."""
    http = AsyncMock()
    api_body = {
        "purchase": {
            "data": {"pricing_result": {"is_free": True, "price": {"amount": 0}}}
        }
    }
    http.get.return_value = SimpleNamespace(text=json.dumps(api_body))
    http.safe_json = AsyncMock(return_value=api_body)
    deal = {
        "title": "CISCO ENARSI",
        "url": "https://www.udemy.com/course/cisco-enarsi-300-410/?couponCode=ABC123",
        "coupon_code": "ABC123",
        "course_id": "7228401",
    }
    status = await checker.check_deal(http, deal)
    assert status == "valid"
    assert deal["course_id"] == "7228401"
    assert deal["last_checked_at"]
    assert http.get.await_count == 1
    assert "api-2.0/course-landing-components/7228401" in http.get.await_args.args[0]


# --- FIX 2: auto-import latest coupons ---------------------------------------

def test_scrape_enabled_env_parsing(monkeypatch):
    monkeypatch.delenv("CHECKER_SCRAPE_ON_CYCLE", raising=False)
    assert checker._scrape_enabled() is True  # default: on
    monkeypatch.setenv("CHECKER_SCRAPE_ON_CYCLE", "false")
    assert checker._scrape_enabled() is False
    monkeypatch.setenv("CHECKER_SCRAPE_ON_CYCLE", "0")
    assert checker._scrape_enabled() is False
    monkeypatch.setenv("CHECKER_SCRAPE_ON_CYCLE", "1")
    assert checker._scrape_enabled() is True


def test_scrape_source_limit_env_parsing(monkeypatch):
    monkeypatch.delenv("CHECKER_SCRAPE_MAX_SOURCES", raising=False)
    assert checker._scrape_source_limit() == 0
    monkeypatch.setenv("CHECKER_SCRAPE_MAX_SOURCES", "3")
    assert checker._scrape_source_limit() == 3
    monkeypatch.setenv("CHECKER_SCRAPE_MAX_SOURCES", "bogus")
    assert checker._scrape_source_limit() == 0


def test_deal_from_course_shape():
    course = SimpleNamespace(
        title="Python Course",
        url="https://www.udemy.com/course/python-course/?couponCode=Z9X8",
        slug="python-course",
        course_id="7220277",
        coupon_code="Z9X8",
        site="Test Source",
    )
    deal = checker._deal_from_course(course)
    assert deal["slug"] == "python-course"
    assert deal["course_id"] == "7220277"
    assert deal["coupon_code"] == "Z9X8"
    assert deal["is_coupon_valid"] is True
    assert deal["enrolled_at"]  # enrolled_at fallback keeps it above the cap
    assert "last_checked_at" not in deal  # unvalidated: must not look checked


@pytest.mark.asyncio
async def test_import_merges_scraped_deals(monkeypatch):
    monkeypatch.setattr(checker, "_scrape_enabled", lambda: True)
    monkeypatch.setattr(checker, "_scrape_source_limit", lambda: 0)

    scraped = [
        SimpleNamespace(
            title="Fresh Course",
            url="https://www.udemy.com/course/fresh-course/?couponCode=FREE1",
            slug="fresh-course",
            course_id=None,
            coupon_code="FREE1",
            site="Test Source",
        )
    ]
    fake_service = MagicMock()
    fake_service.scrape_all = AsyncMock(return_value=scraped)
    fake_service.close = AsyncMock()
    monkeypatch.setattr(
        "app.services.scraper.ScraperService", MagicMock(return_value=fake_service)
    )

    merged_payloads = []
    monkeypatch.setattr(
        "app.services.public_deals_export.merge_deals_into_public_catalog",
        lambda payload, **kwargs: merged_payloads.extend(payload) or len(payload),
    )

    n = await checker._import_latest_coupons()
    assert n == 1
    assert len(merged_payloads) == 1
    assert merged_payloads[0]["coupon_code"] == "FREE1"
    assert merged_payloads[0]["slug"] == "fresh-course"
    fake_service.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_import_disabled_skips_scrape_and_merge(monkeypatch):
    monkeypatch.setenv("CHECKER_SCRAPE_ON_CYCLE", "false")

    def boom(*args, **kwargs):
        raise AssertionError("must not run when import is disabled")

    monkeypatch.setattr("app.services.scraper.ScraperService", boom)
    monkeypatch.setattr(
        "app.services.public_deals_export.merge_deals_into_public_catalog", boom
    )

    assert await checker._import_latest_coupons() == 0


@pytest.mark.asyncio
async def test_import_failure_is_tolerated(monkeypatch):
    """A scraper outage must log and return 0 — never raise."""
    monkeypatch.setattr(checker, "_scrape_enabled", lambda: True)
    monkeypatch.setattr(checker, "_scrape_source_limit", lambda: 0)

    fake_service = MagicMock()
    fake_service.scrape_all = AsyncMock(side_effect=RuntimeError("network down"))
    fake_service.close = AsyncMock()
    monkeypatch.setattr(
        "app.services.scraper.ScraperService", MagicMock(return_value=fake_service)
    )
    monkeypatch.setattr(
        "app.services.public_deals_export.merge_deals_into_public_catalog", MagicMock()
    )

    assert await checker._import_latest_coupons() == 0


@pytest.mark.asyncio
async def test_import_merge_failure_is_tolerated(monkeypatch):
    monkeypatch.setattr(checker, "_scrape_enabled", lambda: True)
    monkeypatch.setattr(checker, "_scrape_source_limit", lambda: 1)

    scraped = [
        SimpleNamespace(
            title="Fresh Course",
            url="https://www.udemy.com/course/fresh-course/?couponCode=FREE1",
            slug="fresh-course",
            course_id=None,
            coupon_code="FREE1",
            site="Test Source",
        )
    ]
    fake_service = MagicMock()
    fake_service.scrape_all = AsyncMock(return_value=scraped)
    fake_service.close = AsyncMock()
    monkeypatch.setattr(
        "app.services.scraper.ScraperService", MagicMock(return_value=fake_service)
    )

    def failing_merge(payload, **kwargs):
        raise RuntimeError("catalog write failed")

    monkeypatch.setattr(
        "app.services.public_deals_export.merge_deals_into_public_catalog",
        failing_merge,
    )

    assert await checker._import_latest_coupons() == 0
