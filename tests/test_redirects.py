"""Regression tests for the public-deals redirects (trailing slash + numeric -> slug).

Guards the redirect change (app/routers/public_deals.py):
- ``/udemycoupons/`` 301 -> ``/udemycoupons`` (was 307), no dangling ``?``
- query params preserved: ``/udemycoupons/?page=2`` -> ``/udemycoupons?page=2``
- query re-encoding: the Location is built from ``str(QueryParams)``, which
  urlencodes the decoded pairs, so ``%20`` renders as ``+`` (assert on what the
  production code actually produces)
- empty query dropped: ``/udemycoupons/?`` -> ``/udemycoupons`` (no ``?``)
- both 301s carry ``Cache-Control: no-cache`` so caches never freeze the
  redirect (a cached 301 keyed without the query string would break
  pagination for every ``/?page=N``)
- no-loop: the canonical form ``/udemycoupons?page=2`` never redirects
- numeric ``/c/{id}`` 301 -> ``/c/{slug}`` with query params preserved
- double-slash ``/udemycoupons//`` chain (framework-generated 307) terminates
  at a 200 final response

All redirect assertions use ``follow_redirects=False`` so the raw 301 is
inspected; only the chain-termination test follows redirects.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.routers.public_deals as public_deals_router
from app.security import RateLimiter
from app.services import public_deals_export
from main import app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DEALS_PATH = PROJECT_ROOT / "public_deals.json"


def _use_real_fixture(monkeypatch):
    """Point the deals loader at the committed repo-root public_deals.json."""
    monkeypatch.setattr(
        public_deals_export, "DEFAULT_PUBLIC_DEALS_PATH", str(FIXTURE_DEALS_PATH)
    )
    monkeypatch.setattr(
        public_deals_export,
        "get_public_deals_path",
        lambda: str(FIXTURE_DEALS_PATH),
    )
    monkeypatch.setattr(
        public_deals_router,
        "public_coupons_api_limiter",
        RateLimiter(max_requests=50, window_seconds=60),
    )


def _get(client, url, **kwargs):
    return client.get(url, headers={"cf-connecting-ip": "203.0.113.200"}, **kwargs)


def _numeric_slug_pair() -> tuple[str, str]:
    """A real (numeric id, slug) pair that resolves in the committed fixture."""
    deals = json.loads(FIXTURE_DEALS_PATH.read_text(encoding="utf-8"))
    for course in deals:
        if not (course.get("is_coupon_valid") and course.get("coupon_code")):
            continue
        numeric = str(course.get("id") or "")
        slug = course.get("slug") or ""
        if numeric.isdigit() and slug and slug != numeric:
            return numeric, slug
    pytest.fail("no numeric-id -> slug pair found in public_deals.json fixture")


def test_trailing_slash_301_to_bare_path_no_dangling_question():
    """/udemycoupons/ must 301 to /udemycoupons with no '?' in the Location.

    The Location is built from str(QueryParams), which is empty and falsy
    here, so no ``?`` may be appended. The bare path is not rewritten by the
    central cache-headers middleware, so the route's exact ``no-cache``
    header survives.
    """
    client = TestClient(app)
    try:
        response = _get(client, "/udemycoupons/", follow_redirects=False)
    finally:
        client.close()

    assert response.status_code == 301
    assert response.headers["location"] == "/udemycoupons"
    assert response.headers["cache-control"] == "no-cache"


def test_trailing_slash_301_preserves_query_params():
    """/udemycoupons/?page=2 must 301 to /udemycoupons?page=2."""
    client = TestClient(app)
    try:
        response = _get(client, "/udemycoupons/?page=2", follow_redirects=False)
    finally:
        client.close()

    assert response.status_code == 301
    assert response.headers["location"] == "/udemycoupons?page=2"
    assert response.headers["cache-control"] == "no-cache"


def test_trailing_slash_301_reencodes_query_params():
    """Query values must be re-encoded as str(QueryParams) does.

    The production code builds the Location via ``f"{url}?{request.query_params}"``;
    str(QueryParams) urlencodes the decoded pairs, so the space in ``a b`` is
    emitted as ``+`` (not ``%20``). Assert the actual produced form.
    """
    client = TestClient(app)
    try:
        response = _get(
            client, "/udemycoupons/?page=2&q=a%20b", follow_redirects=False
        )
    finally:
        client.close()

    assert response.status_code == 301
    assert response.headers["location"] == "/udemycoupons?page=2&q=a+b"


def test_trailing_slash_301_drops_empty_query():
    """/udemycoupons/? (empty query) must 301 to bare /udemycoupons.

    An empty QueryParams is falsy, so no ``?`` may appear in the Location.
    """
    client = TestClient(app)
    try:
        response = _get(client, "/udemycoupons/?", follow_redirects=False)
    finally:
        client.close()

    assert response.status_code == 301
    assert response.headers["location"] == "/udemycoupons"


def test_canonical_bare_path_never_redirects(monkeypatch):
    """GET /udemycoupons?page=2 -> 200 with NO Location header.

    Guards against a redirect loop: the canonical form must render, never
    bounce back to the trailing-slash URL.
    """
    _use_real_fixture(monkeypatch)
    client = TestClient(app)
    try:
        response = _get(client, "/udemycoupons?page=2", follow_redirects=False)
    finally:
        client.close()

    assert response.status_code == 200
    assert "location" not in response.headers


def test_numeric_id_301_to_slug_preserves_query(monkeypatch):
    """/udemycoupons/c/{numeric_id}?utm_source=test -> 301 to the slug URL.

    Guards the numeric -> slug SEO redirect: status 301, query params kept,
    and no-cache so a stale cached 301 never freezes the slug mapping. The
    cache-headers middleware rewrites the value for /udemycoupons/c/ paths on
    non-200 responses to ``no-cache, no-store, must-revalidate``, so assert
    the no-cache directive rather than the route's exact value.
    """
    _use_real_fixture(monkeypatch)
    numeric_id, slug = _numeric_slug_pair()
    client = TestClient(app)
    try:
        response = _get(
            client,
            f"/udemycoupons/c/{numeric_id}?utm_source=test",
            follow_redirects=False,
        )
    finally:
        client.close()

    assert response.status_code == 301
    assert (
        response.headers["location"]
        == f"/udemycoupons/c/{slug}?utm_source=test"
    )
    assert response.headers["cache-control"].startswith("no-cache")


def test_numeric_id_301_no_cache_header(monkeypatch):
    """The numeric -> slug 301 must not be heuristically cacheable.

    Separate no-cache assertion for the numeric redirect (the trailing-slash
    one is covered above) so a regression in either route fails its own test.
    """
    _use_real_fixture(monkeypatch)
    numeric_id, _ = _numeric_slug_pair()
    client = TestClient(app)
    try:
        response = _get(
            client,
            f"/udemycoupons/c/{numeric_id}?utm_source=test",
            follow_redirects=False,
        )
    finally:
        client.close()

    assert response.status_code == 301
    assert "no-cache" in response.headers["cache-control"]


def test_double_slash_chain_terminates_at_200():
    """/udemycoupons// must end at a 200 (framework 307 -> canonical 200).

    The intermediate 307 is generated by Starlette's redirect_slashes, not by
    the application routes, so only the final status is asserted; the chain
    must terminate rather than loop.
    """
    client = TestClient(app)
    try:
        response = _get(client, "/udemycoupons//", follow_redirects=True)
    finally:
        client.close()

    assert response.status_code == 200
