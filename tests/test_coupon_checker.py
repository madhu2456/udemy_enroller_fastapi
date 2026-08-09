"""Tests for scripts/coupon_checker.py resolver tiers + snapshot/valve wiring.

scripts/ is not a Python package, so the module is loaded by path — the same
mechanism scripts/coupon_checker_loop.py uses. All HTTP is mocked; the suite
blocks external network access.

The pattern fixtures replicate the real shapes observed on Udemy course pages
(verified read-only investigation): the old ``data-course-id`` attribute is
gone, and the numeric course id now appears only in embedded JSON, e.g.
``"urlMobileNativeDeeplink":"udemy://discover?courseId=7220277"`` and
``"courseId":7220277``. The slug-API fixtures use the corrected anonymous
endpoint ``api-2.0/courses/{key}/`` (bare + ``?fields[course]=id`` lean).
"""

import importlib.util
import json
import logging
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


# --- FIX: import must silence httpx INFO logging -----------------------------

def test_import_silences_httpx_info_logging():
    """Module-level side effect: httpx INFO logs full request URLs including
    discountCode=, so importing the checker must raise its level to WARNING."""
    assert logging.getLogger("httpx").level == logging.WARNING


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


# --- FIX 1: bounded retry/backoff in the HTML-tier resolver ------------------

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
    result = await checker._resolve_html_tier(http, "https://www.udemy.com/course/x/")
    assert result == "7220277"
    assert http.get.await_count == 3
    assert sleeps == [4, 4]


@pytest.mark.asyncio
async def test_resolve_gives_up_after_bounded_attempts(monkeypatch):
    http = AsyncMock()
    http.get.return_value = None
    _noop_sleep(monkeypatch)
    result = await checker._resolve_html_tier(http, "https://www.udemy.com/course/x/")
    assert result is None
    assert http.get.await_count == checker._RESOLVE_MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_resolve_does_not_retry_deterministic_no_match(monkeypatch):
    http = AsyncMock()
    http.get.return_value = SimpleNamespace(text="<html>full page, no course id</html>")
    _noop_sleep(monkeypatch)
    result = await checker._resolve_html_tier(http, "https://www.udemy.com/course/x/")
    assert result is None
    assert http.get.await_count == 1


# --- resolver tier chain: fields -> bare -> raw-path-slug -> HTML -------------

@pytest.mark.asyncio
async def test_fields_tier_resolves_id():
    """T1: lean fields endpoint returns the numeric id in one request."""
    http = AsyncMock()
    http.get.return_value = SimpleNamespace(status_code=200, text='{"id": 7220277}')
    http.safe_json = AsyncMock(return_value={"id": 7220277})
    result = await checker._resolve_course_id(
        http,
        "https://www.udemy.com/course/python-course/?couponCode=X",
        slug="python-course",
    )
    assert result == "7220277"
    assert http.get.await_count == 1
    url = http.get.await_args.args[0]
    assert "api-2.0/courses/python-course/" in url
    assert "fields[course]=id" in url


@pytest.mark.asyncio
async def test_fields_miss_falls_to_bare_tier():
    """T2: fields 404 -> bare endpoint with nested ``course.id``."""
    http = AsyncMock()
    http.get.side_effect = [
        SimpleNamespace(status_code=404, text=""),
        SimpleNamespace(status_code=200, text='{"course": {"id": 123}}'),
    ]
    http.safe_json = AsyncMock(return_value={"course": {"id": 123}})
    result = await checker._resolve_course_id(
        http, "https://www.udemy.com/course/x/?couponCode=X", slug="x"
    )
    assert result == "123"
    assert http.get.await_count == 2


@pytest.mark.asyncio
async def test_slug_tiers_miss_falls_to_html_tier():
    """T3: fields+bare miss -> HTML page deeplink fixture resolves the id."""
    http = AsyncMock()
    http.get.side_effect = [
        SimpleNamespace(status_code=404, text=""),
        SimpleNamespace(status_code=404, text=""),
        SimpleNamespace(status_code=404, text=""),
        SimpleNamespace(
            status_code=200,
            text='{"urlMobileNativeDeeplink":"udemy://discover?courseId=7220277"}',
        ),
    ]
    result = await checker._resolve_course_id(
        http, "https://www.udemy.com/course/x/?couponCode=X", slug="x"
    )
    assert result == "7220277"
    assert http.get.await_count == 4


@pytest.mark.asyncio
async def test_all_tiers_miss_check_deal_returns_error(monkeypatch):
    """T4: every tier misses -> check_deal errors without touching the flag."""
    http = AsyncMock()
    http.get.return_value = SimpleNamespace(status_code=404, text="")
    _noop_sleep(monkeypatch)
    deal = {
        "title": "T",
        "url": "https://www.udemy.com/course/x/?couponCode=ABC",
        "coupon_code": "ABC",
    }
    status = await checker.check_deal(http, deal)
    assert status == "error"
    assert "is_coupon_valid" not in deal


@pytest.mark.asyncio
async def test_collision_slug_uses_deal_key_then_verbatim_path():
    """T13: collision-suffixed deal slug for fields/bare; raw uses URL path."""
    http = AsyncMock()
    http.get.side_effect = [
        SimpleNamespace(status_code=404, text=""),
        SimpleNamespace(status_code=404, text=""),
        SimpleNamespace(status_code=200, text='{"id": 14768}'),
    ]
    http.safe_json = AsyncMock(return_value={"id": 14768})
    result = await checker._resolve_course_id(
        http, "https://www.udemy.com/course/valid/?couponCode=FREE", slug="valid-14768"
    )
    assert result == "14768"
    urls = [c.args[0] for c in http.get.call_args_list]
    assert "api-2.0/courses/valid-14768/" in urls[0]
    assert "api-2.0/courses/valid-14768/" in urls[1]
    assert "api-2.0/courses/valid/" in urls[2]


def test_raw_path_slug_keeps_underscores_verbatim():
    """T14: underscore slugs are never kebab-cased by the raw tier."""
    assert (
        checker._raw_path_slug("https://www.udemy.com/course/situational_leadership/")
        == "situational_leadership"
    )


@pytest.mark.asyncio
async def test_raw_tier_request_keeps_underscores():
    http = AsyncMock()
    http.get.return_value = SimpleNamespace(status_code=404, text="")
    result = await checker._resolve_raw_tier(
        http, "https://www.udemy.com/course/situational_leadership/"
    )
    assert result is None
    url = http.get.await_args.args[0]
    assert "courses/situational_leadership/" in url
    assert "situational-leadership" not in url


def test_raw_path_slug_unquotes_encoded_slash():
    """T15: pre-encoded %2F inside the segment becomes a literal slash key."""
    assert checker._raw_path_slug("https://www.udemy.com/course/foo%2Fbar/") == "foo/bar"


@pytest.mark.asyncio
async def test_raw_tier_encoded_slash_stays_single_encoded():
    http = AsyncMock()
    http.get.return_value = SimpleNamespace(status_code=404, text="")
    await checker._resolve_raw_tier(http, "https://www.udemy.com/course/foo%2Fbar/")
    url = http.get.await_args.args[0]
    assert "api-2.0/courses/foo%2Fbar/" in url
    assert url.count("%2F") == 1


@pytest.mark.asyncio
async def test_raw_tier_without_course_segment_makes_no_request():
    """T16: no /course/ segment -> raw tier returns None without http.get."""
    http = AsyncMock()
    result = await checker._resolve_raw_tier(http, "https://www.udemy.com/other/x/")
    assert result is None
    http.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_slug_429_backoff_then_success(monkeypatch):
    """T17: one 429 -> single 2s sleep + retry -> success."""
    http = AsyncMock()
    http.get.side_effect = [
        SimpleNamespace(status_code=429, text=""),
        SimpleNamespace(status_code=200, text='{"id": 7}'),
    ]
    http.safe_json = AsyncMock(return_value={"id": 7})
    sleeps = _noop_sleep(monkeypatch)
    result = await checker._resolve_course_id(
        http, "https://www.udemy.com/course/x/", slug="x"
    )
    assert result == "7"
    assert http.get.await_count == 2
    assert sleeps == [2]


@pytest.mark.asyncio
async def test_slug_double_429_falls_to_next_tier(monkeypatch):
    """T18: 429 twice -> tier miss -> the rest of the chain still runs."""
    http = AsyncMock()
    http.get.side_effect = [
        SimpleNamespace(status_code=429, text=""),
        SimpleNamespace(status_code=429, text=""),
        SimpleNamespace(status_code=404, text=""),  # bare
        SimpleNamespace(status_code=404, text=""),  # raw
        SimpleNamespace(
            status_code=200,
            text='{"urlMobileNativeDeeplink":"udemy://discover?courseId=99"}',
        ),  # html
    ]
    sleeps = _noop_sleep(monkeypatch)
    result = await checker._resolve_course_id(
        http, "https://www.udemy.com/course/x/", slug="x"
    )
    assert result == "99"
    assert http.get.await_count == 5
    assert sleeps == [2]


@pytest.mark.asyncio
async def test_slug_200_challenge_body_falls_through():
    """T27: 200 with a non-JSON (HTML challenge) body is a tier miss, no crash."""
    http = AsyncMock()
    http.get.side_effect = [
        SimpleNamespace(status_code=200, text="<html>challenge</html>"),
        SimpleNamespace(status_code=200, text="<html>challenge</html>"),
        SimpleNamespace(status_code=200, text="<html>challenge</html>"),
        SimpleNamespace(
            status_code=200,
            text='{"urlMobileNativeDeeplink":"udemy://discover?courseId=55"}',
        ),
    ]
    http.safe_json = AsyncMock(return_value=None)
    result = await checker._resolve_course_id(
        http, "https://www.udemy.com/course/x/", slug="x"
    )
    assert result == "55"
    assert http.get.await_count == 4


@pytest.mark.asyncio
async def test_empty_slug_skips_fields_and_bare_tiers(monkeypatch):
    """T28: explicit empty slug -> fields/bare skip; raw + HTML still run."""
    http = AsyncMock()
    http.get.side_effect = [
        SimpleNamespace(status_code=404, text=""),  # raw (key from URL path)
        SimpleNamespace(
            status_code=200,
            text='{"urlMobileNativeDeeplink":"udemy://discover?courseId=31"}',
        ),  # html
    ]
    _noop_sleep(monkeypatch)
    result = await checker._resolve_course_id(
        http, "https://www.udemy.com/course/x/", slug=""
    )
    assert result == "31"
    urls = [c.args[0] for c in http.get.call_args_list]
    assert "api-2.0/courses/x/" in urls[0]
    assert urls[1].startswith("https://www.udemy.com/course/x/")
    assert http.get.await_count == 2


@pytest.mark.asyncio
async def test_literal_slash_in_segment_skips_raw_tier():
    """T32: nested path (literal /) -> raw tier returns None; HTML attempted."""
    http = AsyncMock()
    http.get.side_effect = [
        SimpleNamespace(
            status_code=200,
            text='{"urlMobileNativeDeeplink":"udemy://discover?courseId=77"}',
        ),
    ]
    result = await checker._resolve_course_id(
        http, "https://www.udemy.com/course/foo/bar/", slug=""
    )
    assert result == "77"
    assert http.get.await_count == 1


@pytest.mark.parametrize(
    "path,deal_slug,verbatim",
    [
        ("/course/valid/", "valid-14768", "valid"),
        (
            "/course/sustainable-architecture-and-green-buildings/",
            "sustainable-architecture-and-green-buildings-13951",
            "sustainable-architecture-and-green-buildings",
        ),
        (
            "/course/prompt-hr-chatgpt-claude-ai-ru/",
            "prompt-hr-chatgpt-claude-ai-ru-10318",
            "prompt-hr-chatgpt-claude-ai-ru",
        ),
        ("/course/ic-ua-rk/", "ic-ua-rk-10319", "ic-ua-rk"),
        (
            "/course/hr-ai-people-analytics-claude-excel-ru/",
            "hr-ai-people-analytics-claude-excel-ru-10320",
            "hr-ai-people-analytics-claude-excel-ru",
        ),
        ("/course/senior-it-recruiter-ua/", "senior-it-recruiter-ua-9733", "senior-it-recruiter-ua"),
    ],
)
def test_raw_path_slug_real_deal_pairs(path, deal_slug, verbatim):
    """T31: real catalog pairs — raw tier key equals the verbatim URL-path slug
    (never the collision-suffixed deal slug)."""
    raw = checker._raw_path_slug(f"https://www.udemy.com{path}")
    assert raw == verbatim
    assert raw != deal_slug


def test_coerce_valid_course_id_predicate():
    """T22: only positive ASCII integer strings are valid course ids."""
    assert checker._coerce_valid_course_id(None) is None
    assert checker._coerce_valid_course_id(0) is None
    assert checker._coerce_valid_course_id("0") is None
    assert checker._coerce_valid_course_id("00") is None
    assert checker._coerce_valid_course_id("abc") is None
    assert checker._coerce_valid_course_id("42.0") is None
    assert checker._coerce_valid_course_id("²") is None
    assert checker._coerce_valid_course_id(42) == "42"


@pytest.mark.asyncio
async def test_course_id_persists_on_pricing_error():
    """T30: a resolved course_id stays on the deal when pricing later errors."""
    http = AsyncMock()
    http.get.side_effect = [
        SimpleNamespace(status_code=200, text='{"id": 5}'),  # fields tier
        SimpleNamespace(status_code=200, text='{"foo": 1}'),  # pricing (no purchase)
    ]
    http.safe_json = AsyncMock(side_effect=[{"id": 5}, {"foo": 1}])
    deal = {
        "title": "T",
        "url": "https://www.udemy.com/course/x/?couponCode=ABC",
        "coupon_code": "ABC",
    }
    status = await checker.check_deal(http, deal)
    assert status == "error"
    assert deal["course_id"] == "5"


# --- pricing stage: plain httpx first, cloudscraper fallback -----------------

@pytest.mark.asyncio
async def test_check_deal_skips_page_fetch_when_course_id_present():
    """A deal that already carries course_id must not fetch the course page."""
    http = AsyncMock()
    api_body = {
        "purchase": {
            "data": {"pricing_result": {"is_free": True, "price": {"amount": 0}}}
        }
    }
    http.get.return_value = SimpleNamespace(status_code=200, text=json.dumps(api_body))
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
    kwargs = http.get.await_args.kwargs
    assert kwargs["req_type"] == "api"
    assert kwargs["use_cloudscraper"] is False
    assert kwargs["log_failures"] is False
    assert kwargs["raise_for_status"] is False
    assert kwargs["headers"]["User-Agent"] == checker._BROWSER_UA


@pytest.mark.asyncio
async def test_pricing_plain_httpx_success():
    """T5: 200 + free pricing result -> valid, checked, plain httpx first."""
    body = {
        "purchase": {
            "data": {"pricing_result": {"is_free": True, "price": {"amount": 0}}}
        }
    }
    http = AsyncMock()
    http.get.return_value = SimpleNamespace(status_code=200, text=json.dumps(body))
    http.safe_json = AsyncMock(return_value=body)
    deal = {
        "title": "T",
        "url": "https://www.udemy.com/course/x/?couponCode=ABC",
        "coupon_code": "ABC",
        "course_id": "7220277",
    }
    status = await checker.check_deal(http, deal)
    assert status == "valid"
    assert deal["last_checked_at"]
    assert http.get.await_count == 1
    assert http.get.call_args_list[0].kwargs["use_cloudscraper"] is False


@pytest.mark.asyncio
async def test_pricing_transport_failure_falls_back_to_cloudscraper():
    """T6: plain httpx transport None -> cloudscraper fallback -> valid."""
    body = {
        "purchase": {
            "data": {"pricing_result": {"is_free": True, "price": {"amount": 0}}}
        }
    }
    http = AsyncMock()
    http.get.side_effect = [
        None,
        SimpleNamespace(status_code=200, text=json.dumps(body)),
    ]
    http.safe_json = AsyncMock(return_value=body)
    deal = {
        "title": "T",
        "url": "https://www.udemy.com/course/x/?couponCode=ABC",
        "coupon_code": "ABC",
        "course_id": "7220277",
    }
    status = await checker.check_deal(http, deal)
    assert status == "valid"
    assert http.get.await_count == 2
    assert http.get.call_args_list[0].kwargs["use_cloudscraper"] is False
    assert http.get.call_args_list[1].kwargs["use_cloudscraper"] is True


@pytest.mark.asyncio
async def test_pricing_json_without_purchase_errors():
    """T7: pricing JSON object without purchase/cacheable_purchase -> error."""
    http = AsyncMock()
    http.get.return_value = SimpleNamespace(status_code=200, text='{"foo": 1}')
    http.safe_json = AsyncMock(return_value={"foo": 1})
    deal = {
        "title": "T",
        "url": "https://www.udemy.com/course/x/?couponCode=ABC",
        "coupon_code": "ABC",
        "course_id": "7220277",
    }
    assert await checker.check_deal(http, deal) == "error"


@pytest.mark.asyncio
async def test_pricing_url_quote_encodes_percent_coupon():
    """T23: 50%OFF is percent-encoded in discountCode."""
    body = {
        "purchase": {
            "data": {"pricing_result": {"is_free": True, "price": {"amount": 0}}}
        }
    }
    http = AsyncMock()
    http.get.return_value = SimpleNamespace(status_code=200, text=json.dumps(body))
    http.safe_json = AsyncMock(return_value=body)
    deal = {
        "title": "T",
        "url": "https://www.udemy.com/course/x/?couponCode=ABC",
        "coupon_code": "50%OFF",
        "course_id": "1",
    }
    assert await checker.check_deal(http, deal) == "valid"
    assert "discountCode=50%25OFF" in http.get.await_args.args[0]


@pytest.mark.asyncio
async def test_pricing_url_quote_encodes_ampersand_coupon():
    """T24: A&B is percent-encoded in discountCode."""
    body = {
        "purchase": {
            "data": {"pricing_result": {"is_free": True, "price": {"amount": 0}}}
        }
    }
    http = AsyncMock()
    http.get.return_value = SimpleNamespace(status_code=200, text=json.dumps(body))
    http.safe_json = AsyncMock(return_value=body)
    deal = {
        "title": "T",
        "url": "https://www.udemy.com/course/x/?couponCode=ABC",
        "coupon_code": "A&B",
        "course_id": "1",
    }
    assert await checker.check_deal(http, deal) == "valid"
    assert "discountCode=A%26B" in http.get.await_args.args[0]


# --- call-site hygiene: log_failures=False + req_type="api" + browser UA -----

@pytest.mark.asyncio
async def test_all_call_sites_disable_failure_logs(monkeypatch):
    """T11: log_failures=False on every JSON call site (fields/bare/raw/pricing)."""
    http = AsyncMock()
    http.get.side_effect = [
        SimpleNamespace(status_code=404, text=""),  # fields
        SimpleNamespace(status_code=404, text=""),  # bare
        SimpleNamespace(status_code=404, text=""),  # raw
        SimpleNamespace(status_code=200, text="<html>no id</html>"),  # html (deterministic miss)
    ]
    _noop_sleep(monkeypatch)
    assert (
        await checker._resolve_course_id(
            http, "https://www.udemy.com/course/x/", slug="x"
        )
        is None
    )
    assert http.get.await_count == 4
    for call in http.get.call_args_list:
        assert call.kwargs["log_failures"] is False

    body = {
        "purchase": {
            "data": {"pricing_result": {"is_free": True, "price": {"amount": 0}}}
        }
    }
    http2 = AsyncMock()
    http2.get.side_effect = [
        None,  # plain transport failure
        SimpleNamespace(status_code=200, text=json.dumps(body)),  # cloudscraper
    ]
    http2.safe_json = AsyncMock(return_value=body)
    deal = {
        "title": "T",
        "url": "https://www.udemy.com/course/x/?couponCode=ABC",
        "coupon_code": "ABC",
        "course_id": "1",
    }
    assert await checker.check_deal(http2, deal) == "valid"
    assert http2.get.await_count == 2
    for call in http2.get.call_args_list:
        assert call.kwargs["log_failures"] is False


@pytest.mark.asyncio
async def test_json_call_sites_use_api_reqtype_and_browser_ua(monkeypatch):
    """T12: req_type="api" + _BROWSER_UA on JSON sites; HTML tier is not "api"."""
    http = AsyncMock()
    http.get.side_effect = [
        SimpleNamespace(status_code=404, text=""),
        SimpleNamespace(status_code=404, text=""),
        SimpleNamespace(status_code=404, text=""),
        SimpleNamespace(status_code=200, text="<html>x</html>"),
    ]
    _noop_sleep(monkeypatch)
    await checker._resolve_course_id(http, "https://www.udemy.com/course/x/", slug="x")
    api_calls = [
        c for c in http.get.call_args_list if c.kwargs.get("req_type") == "api"
    ]
    assert len(api_calls) == 3
    for call in api_calls:
        assert call.kwargs["headers"]["User-Agent"] == checker._BROWSER_UA
    html_call = http.get.call_args_list[-1]
    assert html_call.kwargs.get("req_type") != "api"
    assert html_call.kwargs["headers"]["User-Agent"] == checker._BROWSER_UA

    body = {
        "purchase": {
            "data": {"pricing_result": {"is_free": True, "price": {"amount": 0}}}
        }
    }
    http2 = AsyncMock()
    http2.get.side_effect = [
        None,
        SimpleNamespace(status_code=200, text=json.dumps(body)),
    ]
    http2.safe_json = AsyncMock(return_value=body)
    deal = {
        "title": "T",
        "url": "https://www.udemy.com/course/x/?couponCode=ABC",
        "coupon_code": "ABC",
        "course_id": "1",
    }
    assert await checker.check_deal(http2, deal) == "valid"
    for call in http2.get.call_args_list:
        assert call.kwargs["req_type"] == "api"
        assert call.kwargs["headers"]["User-Agent"] == checker._BROWSER_UA


# --- snapshot + safety valve --------------------------------------------------

def test_maybe_snapshot_valve_tripped(monkeypatch, caplog):
    """T19: expired > 75% + errors < 5% -> valve; no write; loud log."""
    caplog.set_level(logging.INFO)

    def boom(*args, **kwargs):
        raise AssertionError("valve must not write")

    monkeypatch.setattr(checker, "save_public_deals", boom)
    stats = {"valid": 2, "expired": 8, "error": 0, "skipped": 0}
    kept = [{"title": "V1"}, {"title": "V2"}]
    result = checker._maybe_snapshot(kept, stats, 10, "/tmp/none.json")
    assert result == "valve"
    assert "SAFETY VALVE" in caplog.text


def test_maybe_snapshot_empty_guard(monkeypatch):
    """T25: nothing kept yet -> "empty" and no write (even when all expired)."""
    calls = []

    def rec(payload, **kwargs):
        calls.append(payload)
        return len(payload)

    monkeypatch.setattr(checker, "save_public_deals", rec)
    stats = {"valid": 0, "expired": 10, "error": 0, "skipped": 0}
    result = checker._maybe_snapshot([], stats, 10, "/tmp/none.json")
    assert result == "empty"
    assert calls == []


def test_maybe_snapshot_writes_when_valve_clear(monkeypatch):
    """T21 (unit part): expired <= 75% -> snapshot written, no sitemap refresh."""
    calls = []

    def rec(payload, **kwargs):
        calls.append(([dict(d) for d in payload], kwargs))
        return len(payload)

    monkeypatch.setattr(checker, "save_public_deals", rec)
    stats = {"valid": 4, "expired": 6, "error": 0, "skipped": 0}
    result = checker._maybe_snapshot([{"title": "V1"}], stats, 10, "/tmp/none.json")
    assert result == "wrote"
    assert len(calls) == 1
    assert calls[0][1]["refresh_sitemap"] is False


def _main_deal(title, result, flag=None):
    deal = {
        "title": title,
        "url": f"https://www.udemy.com/course/{title}/?couponCode=TEST",
        "coupon_code": "TEST",
        "_result": result,
    }
    if flag is not None:
        deal["is_coupon_valid"] = flag
    return deal


def _setup_main(monkeypatch, tmp_path, load_side_effect, imported=0):
    """Wire main() deps: fake settings/client/check_deal, record saves."""
    calls = []
    http = AsyncMock()

    async def fake_check(http, deal):
        result = deal.get("_result", "valid")
        if result == "valid":
            deal["is_coupon_valid"] = True
            deal["last_checked_at"] = "2026-08-09T00:00:00Z"
            return "valid"
        if result == "expired":
            deal["is_coupon_valid"] = False
            return "expired"
        return "error"

    def fake_save(payload, **kwargs):
        calls.append(([dict(d) for d in payload], kwargs))
        return len(payload)

    monkeypatch.setattr(
        checker, "get_settings", lambda: SimpleNamespace(PROXIES=None)
    )
    monkeypatch.setattr(
        checker, "get_public_deals_path", lambda: str(tmp_path / "public_deals.json")
    )
    monkeypatch.setattr(
        checker, "load_public_deals", MagicMock(side_effect=load_side_effect)
    )
    monkeypatch.setattr(
        checker, "_import_latest_coupons", AsyncMock(return_value=imported)
    )
    monkeypatch.setattr(checker, "AsyncHTTPClient", lambda **kw: http)
    monkeypatch.setattr(checker, "check_deal", fake_check)
    monkeypatch.setattr(checker, "save_public_deals", fake_save)
    _noop_sleep(monkeypatch)
    return http, calls


@pytest.mark.asyncio
async def test_main_snapshot_cadence_at_done_10(monkeypatch, tmp_path):
    """T8: at done=10 a snapshot is saved (refresh_sitemap=False) containing
    valid+error deals and excluding expired."""
    deals = [_main_deal(f"V{i}", "valid") for i in range(4)]
    deals += [_main_deal(f"E{i}", "expired") for i in range(4)]
    deals += [_main_deal(f"X{i}", "error") for i in range(2)]
    _, calls = _setup_main(monkeypatch, tmp_path, [deals])
    await checker.main()
    assert len(calls) == 2  # snapshot + final save
    snap_payload, snap_kwargs = calls[0]
    assert snap_kwargs["refresh_sitemap"] is False
    titles = [d["title"] for d in snap_payload]
    assert len(snap_payload) == 6
    assert not any(t.startswith("E") for t in titles)
    assert any(t.startswith("V") for t in titles)
    assert any(t.startswith("X") for t in titles)
    assert calls[1][1]["refresh_sitemap"] is True


@pytest.mark.asyncio
async def test_main_total_failure_wave_preserves_file(monkeypatch, tmp_path):
    """T9: all error, zero valid/expired -> no write (catalog preserved)."""
    deals = [_main_deal(f"X{i}", "error", flag=False) for i in range(10)]
    _, calls = _setup_main(monkeypatch, tmp_path, [deals])
    await checker.main()
    assert calls == []


@pytest.mark.asyncio
async def test_main_happy_path_saves_and_logs(monkeypatch, tmp_path):
    """T10: happy path — final save with kept list, refresh_sitemap=True.

    The "Results:" INFO line is captured via a direct handler on the checker
    logger: app logging config calls basicConfig(force=True) during the full
    suite, which resets root handlers and level, so caplog cannot be relied on.
    """
    records = []

    class _Recorder(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    target = logging.getLogger(checker.__name__)
    handler = _Recorder()
    target.addHandler(handler)
    target.setLevel(logging.INFO)
    try:
        deals = [_main_deal(f"V{i}", "valid") for i in range(6)]
        deals += [_main_deal(f"E{i}", "expired") for i in range(3)]
        deals += [_main_deal("X1", "error", flag=True)]
        _, calls = _setup_main(monkeypatch, tmp_path, [deals])
        await checker.main()
    finally:
        target.removeHandler(handler)
    assert len(calls) == 2
    final_payload, final_kwargs = calls[-1]
    assert final_kwargs["refresh_sitemap"] is True
    assert len(final_payload) == 7
    assert any("Results: valid=6 expired=3 error=1 skipped=0" in r for r in records)


@pytest.mark.asyncio
async def test_main_valve_at_final_skips_all_saves(monkeypatch, tmp_path):
    """T20: expired > 75% + error < 5% -> valve; save never called."""
    deals = [_main_deal(f"V{i}", "valid") for i in range(2)]
    deals += [_main_deal(f"E{i}", "expired") for i in range(8)]
    _, calls = _setup_main(monkeypatch, tmp_path, [deals])
    await checker.main()
    assert calls == []


@pytest.mark.asyncio
async def test_main_valve_not_tripped_writes_snapshot_and_final(monkeypatch, tmp_path):
    """T21 (main part): expired = 60% -> snapshot and final save both happen."""
    deals = [_main_deal(f"V{i}", "valid") for i in range(4)]
    deals += [_main_deal(f"E{i}", "expired") for i in range(6)]
    _, calls = _setup_main(monkeypatch, tmp_path, [deals])
    await checker.main()
    assert len(calls) == 2
    assert calls[0][1]["refresh_sitemap"] is False
    assert calls[1][1]["refresh_sitemap"] is True
    assert len(calls[1][0]) == 4


@pytest.mark.asyncio
async def test_main_all_expired_preserves_file(monkeypatch, tmp_path):
    """T33: all-expired cycle (kept == []) — the final-gate valve fires, no
    snapshot is taken (done=5 never reaches the 10-deal cadence), the catalog
    file is left byte-for-byte untouched, and save_public_deals is never called.
    """
    deals = [_main_deal(f"E{i}", "expired") for i in range(5)]
    # Seed the "last known-good catalog" exactly at the write path main() would
    # use; if the final-gate valve ever failed, save_public_deals would rewrite
    # this file with an empty/expired catalog.
    json_path = tmp_path / "public_deals.json"
    json_path.write_text(json.dumps(deals, indent=2), encoding="utf-8")
    original = json_path.read_bytes()

    # Direct handler on the checker logger: app logging config calls
    # basicConfig(force=True) during the full suite, so caplog cannot be
    # relied on (same rationale as T10).
    records = []

    class _Recorder(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    target = logging.getLogger(checker.__name__)
    handler = _Recorder()
    target.addHandler(handler)
    target.setLevel(logging.INFO)
    try:
        _, calls = _setup_main(monkeypatch, tmp_path, [deals])
        await checker.main()
    finally:
        target.removeHandler(handler)

    assert calls == []  # no mid-run snapshot (done=5) and no final save
    assert json_path.read_bytes() == original  # file not rewritten
    assert any("SAFETY VALVE" in r for r in records)
    assert any("preserving last known-good catalog" in r for r in records)


@pytest.mark.asyncio
async def test_main_snapshot_mixed_drops_expired(monkeypatch, tmp_path):
    """T26: mixed run — snapshot keeps valid+error, drops expired."""
    deals = [_main_deal(f"V{i}", "valid") for i in range(3)]
    deals += [_main_deal(f"E{i}", "expired") for i in range(4)]
    deals += [_main_deal(f"X{i}", "error") for i in range(3)]
    _, calls = _setup_main(monkeypatch, tmp_path, [deals])
    await checker.main()
    snap = calls[0][0]
    titles = [d["title"] for d in snap]
    assert len(snap) == 6
    assert not any(t.startswith("E") for t in titles)
    assert len([t for t in titles if t.startswith("V")]) == 3
    assert len([t for t in titles if t.startswith("X")]) == 3


@pytest.mark.asyncio
async def test_main_validates_reloaded_set_after_import(monkeypatch, tmp_path):
    """T29: import returns 3 -> main reloads and saves the merged set."""
    initial = [_main_deal(f"I{i}", "valid") for i in range(3)]
    reloaded = [_main_deal(f"R{i}", "valid") for i in range(5)]
    reloaded += [_main_deal("RX1", "error")]
    _, calls = _setup_main(monkeypatch, tmp_path, [initial, reloaded], imported=3)
    await checker.main()
    assert len(calls) == 1
    final_payload, final_kwargs = calls[-1]
    assert final_kwargs["refresh_sitemap"] is True
    assert len(final_payload) == 6
    assert all(t.startswith("R") for t in [d["title"] for d in final_payload])


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
