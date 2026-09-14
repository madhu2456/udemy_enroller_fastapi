"""IndexNow (SEO): key-file route + ping payload — mocked HTTP, no live pings.

Mirrors the portfolio test pattern
(madhu_portfolio src/lib/__tests__/indexnow-key-route.test.ts) and the repo's
mocked-transport style from tests/test_alerts.py.
"""

import httpx
from fastapi.testclient import TestClient

import app.services.indexnow as indexnow
from app.services.indexnow import (
    all_deal_paths,
    build_ping_payload,
    indexnow_configured,
    ping_indexnow_sync,
)
from app.services.public_deals_export import (
    STATIC_PAGE_LASTMOD,
    build_sitemap_xml,
    save_public_deals,
)
from main import app

_VALID_KEY = "a" * 32
_OTHER_KEY = "b" * 32
_TEST_SITE = "https://udemyenroller.madhudadi.in"


def _make_client_factory(captured, status=200):
    # Capture the REAL class before monkeypatch replaces the module attribute
    # (same guard as tests/test_alerts.py).
    original_client = httpx.Client

    def handler(request):
        captured.append(request)
        return httpx.Response(status, json={})

    transport = httpx.MockTransport(handler)
    return lambda *a, **k: original_client(transport=transport, **k)


# --- key-file route ----------------------------------------------------------


def _get_key_file(key: str):
    client = TestClient(app)
    try:
        return client.get(f"/{key}.txt", follow_redirects=False)
    finally:
        client.close()


def test_key_file_serves_key_when_set(monkeypatch):
    monkeypatch.setenv("INDEXNOW_KEY", _VALID_KEY)
    response = _get_key_file(_VALID_KEY)
    assert response.status_code == 200
    assert response.text == _VALID_KEY
    assert "text/plain" in response.headers.get("content-type", "")
    cc = response.headers.get("cache-control", "")
    assert "max-age=86400" in cc


def test_key_file_404_when_key_unset(monkeypatch):
    monkeypatch.delenv("INDEXNOW_KEY", raising=False)
    response = _get_key_file(_VALID_KEY)
    assert response.status_code == 404


def test_key_file_404_on_mismatch(monkeypatch):
    monkeypatch.setenv("INDEXNOW_KEY", _VALID_KEY)
    response = _get_key_file(_OTHER_KEY)
    assert response.status_code == 404


def test_key_file_404_on_malformed_key(monkeypatch):
    monkeypatch.setenv("INDEXNOW_KEY", _VALID_KEY)
    response = _get_key_file("not-a-hex-key")
    assert response.status_code == 404


def test_key_file_404_when_malformed_key_configured(monkeypatch):
    """A malformed configured key fails closed (never serves, never pings)."""
    monkeypatch.setenv("INDEXNOW_KEY", "too-short")
    assert indexnow_configured() is False
    response = _get_key_file("too-short")
    assert response.status_code == 404


# --- payload builder ---------------------------------------------------------


def test_ping_payload_includes_hubs_and_deal_urls(monkeypatch):
    monkeypatch.setenv("INDEXNOW_KEY", _VALID_KEY)
    paths = all_deal_paths([{"slug": "python-basics"}])
    payload = build_ping_payload([*indexnow._CATALOG_HUB_PATHS, *paths])
    assert payload is not None
    assert payload["host"] == "udemyenroller.madhudadi.in"
    assert payload["key"] == _VALID_KEY
    assert payload["urlList"] == [
        f"{_TEST_SITE}/udemycoupons",
        f"{_TEST_SITE}/",
        f"{_TEST_SITE}/udemycoupons/c/python-basics",
    ]


def test_ping_payload_none_when_key_unset(monkeypatch):
    monkeypatch.delenv("INDEXNOW_KEY", raising=False)
    assert build_ping_payload(["/udemycoupons"]) is None
    assert indexnow_configured() is False


def test_ping_payload_rejects_off_origin_paths(monkeypatch):
    monkeypatch.setenv("INDEXNOW_KEY", _VALID_KEY)
    payload = build_ping_payload(
        [
            "/udemycoupons/c/ok",
            "//evil.example/x",  # protocol-relative → foreign origin
            "https://evil.example/abs",  # not a path → skipped
            "/udemycoupons/c/ok",  # duplicate → deduped
        ]
    )
    assert payload is not None
    assert payload["urlList"] == [f"{_TEST_SITE}/udemycoupons/c/ok"]


def test_all_deal_paths_filters_unsafe_slugs():
    paths = all_deal_paths(
        [
            {"slug": "good-course"},
            {"slug": "../escape"},
            {"slug": None},
            {},
        ]
    )
    assert paths == ["/udemycoupons/c/good-course"]


# --- ping dispatch ------------------------------------------------------------


def test_ping_noop_when_key_unset(monkeypatch):
    monkeypatch.delenv("INDEXNOW_KEY", raising=False)
    called = []

    def _boom(*a, **k):
        called.append(1)
        raise AssertionError("must not POST when key unset")

    monkeypatch.setattr(indexnow.httpx, "Client", _boom)
    assert ping_indexnow_sync(["/udemycoupons"]) is False
    assert called == []


def test_ping_posts_correct_payload(monkeypatch):
    monkeypatch.setenv("INDEXNOW_KEY", _VALID_KEY)
    captured = []
    monkeypatch.setattr(
        indexnow.httpx, "Client", _make_client_factory(captured, status=200)
    )
    ok = ping_indexnow_sync(["/udemycoupons/c/python-basics"])
    assert ok is True
    assert len(captured) == 1
    request = captured[0]
    assert str(request.url) == indexnow.INDEXNOW_ENDPOINT
    import json

    parsed = json.loads(request.content.decode())
    assert parsed["host"] == "udemyenroller.madhudadi.in"
    assert parsed["key"] == _VALID_KEY
    assert f"{_TEST_SITE}/udemycoupons" in parsed["urlList"]
    assert f"{_TEST_SITE}/udemycoupons/c/python-basics" in parsed["urlList"]


def test_ping_non_2xx_swallowed(monkeypatch):
    monkeypatch.setenv("INDEXNOW_KEY", _VALID_KEY)
    captured = []
    monkeypatch.setattr(
        indexnow.httpx, "Client", _make_client_factory(captured, status=500)
    )
    ok = ping_indexnow_sync(["/udemycoupons"])  # must not raise
    assert ok is False
    assert len(captured) == 1


def test_ping_transport_error_swallowed(monkeypatch):
    monkeypatch.setenv("INDEXNOW_KEY", _VALID_KEY)

    class _Broken:
        def __init__(self, *a, **k):
            raise OSError("indexnow unreachable")

    monkeypatch.setattr(indexnow.httpx, "Client", _Broken)
    ok = ping_indexnow_sync(["/udemycoupons"])  # must not raise
    assert ok is False


# --- export trigger ------------------------------------------------------------


def _publish_deal():
    return [
        {
            "id": 1,
            "title": "Python Basics Course",
            "url": "https://www.udemy.com/course/python-basics/",
            "coupon_code": "FREE",
            "is_coupon_valid": True,
            "slug": "python-basics",
        }
    ]


def test_save_public_deals_pings_on_publish(monkeypatch, tmp_path):
    """save_public_deals(refresh_sitemap=True) fires a ping with deal URLs."""
    monkeypatch.setenv("INDEXNOW_KEY", _VALID_KEY)
    monkeypatch.setattr(
        "app.services.public_deals_export.get_public_deals_path",
        lambda: str(tmp_path / "public_deals.json"),
    )
    captured = []

    def _fake_ping_sync(paths, **kwargs):
        captured.append(list(paths))
        return True

    monkeypatch.setattr("app.services.indexnow.ping_indexnow_sync", _fake_ping_sync)
    n = save_public_deals(_publish_deal(), path=str(tmp_path / "pd.json"))
    assert n == 1
    assert len(captured) == 1
    assert "/udemycoupons/c/python-basics" in captured[0]


def test_save_public_deals_no_ping_when_unset(monkeypatch, tmp_path):
    """Key unset → publish path never dispatches a ping (default OFF)."""
    monkeypatch.delenv("INDEXNOW_KEY", raising=False)
    monkeypatch.setattr(
        "app.services.public_deals_export.get_public_deals_path",
        lambda: str(tmp_path / "public_deals.json"),
    )
    called = []

    def _boom(*a, **k):
        called.append(1)
        raise AssertionError("must not ping when key unset")

    monkeypatch.setattr("app.services.indexnow.ping_indexnow_sync", _boom)
    n = save_public_deals(_publish_deal(), path=str(tmp_path / "pd.json"))
    assert n == 1
    assert called == []


def test_save_public_deals_no_ping_when_unchanged(monkeypatch, tmp_path):
    """RPN-24: byte-identical re-export of the same catalog must NOT ping.

    Patches ``ping_catalog_publish`` (late-imported by ``save_public_deals``
    inside the changed branch) so the gate is observed synchronously, without
    the daemon-thread dispatch race.
    """
    monkeypatch.setenv("INDEXNOW_KEY", _VALID_KEY)
    monkeypatch.setattr(
        "app.services.public_deals_export.get_public_deals_path",
        lambda: str(tmp_path / "public_deals.json"),
    )
    dispatched = []

    def _fake_publish(deals, **kwargs):
        dispatched.append(list(deals))
        return None

    monkeypatch.setattr(
        "app.services.indexnow.ping_catalog_publish", _fake_publish
    )
    p = str(tmp_path / "pd.json")
    first = save_public_deals(_publish_deal(), path=p)  # initial publish pings
    second = save_public_deals(_publish_deal(), path=p)  # identical payload
    assert first == 1 and second == 1
    assert len(dispatched) == 1  # the no-change re-export dispatched nothing


def test_save_public_deals_pings_again_after_change(monkeypatch, tmp_path):
    """RPN-24: a genuinely changed catalog re-arms the ping."""
    monkeypatch.setenv("INDEXNOW_KEY", _VALID_KEY)
    monkeypatch.setattr(
        "app.services.public_deals_export.get_public_deals_path",
        lambda: str(tmp_path / "public_deals.json"),
    )
    dispatched = []

    def _fake_publish(deals, **kwargs):
        dispatched.append(list(deals))
        return None

    monkeypatch.setattr(
        "app.services.indexnow.ping_catalog_publish", _fake_publish
    )
    p = str(tmp_path / "pd.json")
    save_public_deals(_publish_deal(), path=p)  # initial publish → ping 1
    save_public_deals(_publish_deal(), path=p)  # identical → no ping
    changed = _publish_deal()
    changed[0]["title"] = "Python Basics Course (Updated)"
    save_public_deals(changed, path=p)  # changed → ping 2
    assert len(dispatched) == 2


# --- sitemap static-page lastmod (×7) ------------------------------------------


def test_sitemap_static_pages_have_honest_lastmod(tmp_path):
    """The 7 static SEO pages carry lastmod values in W3C date format.

    Values are pinned git content-change dates (see STATIC_PAGE_LASTMOD) —
    honest signals, not fabricated freshness. Format must be YYYY-MM-DD.
    """
    import re

    deals_path = tmp_path / "public_deals.json"
    deals_path.write_text("[]", encoding="utf-8")
    xml, _n = build_sitemap_xml(deals_path=str(deals_path))
    for page in (
        "/faq",
        "/about",
        "/guides",
        "/privacy",
        "/contact",
        "/terms",
        "/accessibility",
    ):
        loc = f"{_TEST_SITE}{page}</loc>"
        assert loc in xml, page
        block = xml.split(loc, 1)[1]
        m = re.match(r"\s*<lastmod>(\d{4}-\d{2}-\d{2})</lastmod>", block)
        assert m, f"missing/invalid lastmod for {page}"
        assert m.group(1) == STATIC_PAGE_LASTMOD[page]
    # url count sanity: static + hubs all present, each with lastmod
    assert xml.count("<url>") == xml.count("<lastmod>")


def test_static_page_lastmod_values_are_valid_w3c_dates():
    """Every pinned lastmod parses as a real calendar date (W3C sitemap)."""
    import datetime

    for page, raw in STATIC_PAGE_LASTMOD.items():
        assert page.startswith("/"), page
        # W3C sitemap lastmod: YYYY-MM-DD (datetime forms allowed; we pin dates)
        datetime.date.fromisoformat(raw)  # raises on invalid calendar date
        assert len(raw) == 10


# --- RPN-30: template content-hash pin -----------------------------------------
# Update procedure when a static template changes:
#   1. Edit the template (app/templates/pages/<name>.html).
#   2. Recompute its normalized sha256:
#      python -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read().replace(b'\r\n',b'\n')).hexdigest())" app/templates/pages/<name>.html
#   3. Bump STATIC_PAGE_LASTMOD["/<name>"] in app/services/public_deals_export.py
#      to the template's content-change date (the honest lastmod).
#   4. Update the pinned hash below to the recomputed value.
# Any template edit that skips step 3 trips this test, pointing at the policy
# above (docs/ops/indexnow.md → "Bump the value when a page's template
# content actually changes").

_STATIC_PAGE_TEMPLATES = {  # page path → template file (mirrors seo.py routes)
    "/faq": "faq.html",
    "/about": "about.html",
    "/guides": "guides.html",
    "/privacy": "privacy.html",
    "/contact": "contact.html",
    "/terms": "terms.html",
    "/accessibility": "accessibility.html",
}

# sha256 of each template's raw bytes with CRLF normalized to LF, pinned at the
# same time as STATIC_PAGE_LASTMOD (see procedure above).
_STATIC_PAGE_TEMPLATE_HASHES = {
    "/faq": "44b952ec08f24046b420103f2014a180fc25204c38e6838e0868da346a9c5d10",
    "/about": "4823e7c777c26713ada428c47bae3f77957dd6f0a9de52683c728faf39c36a52",
    "/guides": "01763d3004f889eea1945c063f0091dd56162bde4322f83693e28f41bbb131a0",
    "/privacy": "bc9a770a9790b381eb6c595c881a17f255a1aed9ac0cddb8d9f134a94db906de",
    "/contact": "22f78d96c9c73e0ae430428d0f6e76252b4a540d3ab410f5e40eeb84e4d25acc",
    "/terms": "b5ff50d200eea1086081778205cbe1bc3c09ad5e8af4bbd7a9c24434f0d2c2e2",
    "/accessibility": "a699a6842111af1bf0a0d974b7a72b7ecd8b15cca43f5b1db524b336ae9bcf1d",
}


def test_static_page_templates_match_pinned_hashes():
    """RPN-30: template content must match the hash pinned beside its lastmod.

    Hashes the ACTUAL template file bytes on disk (CRLF-normalized), so any
    edit — however small — changes the digest and fails this test until the
    lastmod is bumped and the pin updated per the procedure in the comment
    block above.
    """
    import hashlib
    import os

    templates_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app",
        "templates",
        "pages",
    )
    for page, filename in _STATIC_PAGE_TEMPLATES.items():
        template_path = os.path.join(templates_dir, filename)
        with open(template_path, "rb") as f:
            digest = hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()
        assert digest == _STATIC_PAGE_TEMPLATE_HASHES[page], (
            f"{filename} changed but STATIC_PAGE_LASTMOD['{page}'] was not "
            "bumped: edit template → recompute hash → bump lastmod → update "
            "the pinned hash (see procedure in the comment block above)"
        )
