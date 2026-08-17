"""Coupon detail page FAQ body/JSON-LD parity (Fix 34)."""

import json
import re
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


def test_coupon_detail_faq_matches_json_ld():
    course = {
        "id": 1,
        "title": "Test Course AEO",
        "slug": "test-course-aeo",
        "category": "Development",
        "language": "English",
        "coupon_code": "TESTCODE",
        "is_coupon_valid": True,
        "url": "https://www.udemy.com/course/test/",
        "rating": 4.5,
        "price": 1000,
        "last_checked_at": "2026-07-30T00:00:00",
    }
    with patch(
        "app.routers.public_deals.get_valid_deal_by_slug", return_value=course
    ), patch("app.routers.public_deals.related_deals", return_value=[]):
        client = TestClient(app)
        try:
            r = client.get("/udemycoupons/c/test-course-aeo")
        finally:
            client.close()

    assert r.status_code == 200
    html = r.text
    assert "What is the free coupon for Test Course AEO?" in html
    assert "TESTCODE" in html

    blocks = re.findall(
        r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
        html,
        flags=re.DOTALL,
    )
    assert any('"@type": "FAQPage"' in b or '"@type":"FAQPage"' in b for b in blocks)

    faq = None
    for b in blocks:
        data = json.loads(b)
        if data.get("@type") == "FAQPage":
            faq = data
            break
    assert faq is not None
    entities = faq["mainEntity"]
    assert len(entities) == 3
    for ent in entities:
        q = ent["name"]
        a = ent["acceptedAnswer"]["text"]
        assert q in html
        assert a in html


def test_coupon_detail_empty_coupon_code_hides_code_ui():
    course = {
        "id": 2,
        "title": "Link Only Course",
        "slug": "link-only-course",
        "category": "Development",
        "language": "English",
        "coupon_code": "",
        "is_coupon_valid": True,
        "url": "https://www.udemy.com/course/link-only/",
        "rating": 4.0,
        "price": 500,
        "last_checked_at": "2026-07-30T00:00:00",
    }
    with patch(
        "app.routers.public_deals.get_valid_deal_by_slug", return_value=course
    ), patch("app.routers.public_deals.related_deals", return_value=[]):
        client = TestClient(app)
        try:
            r = client.get("/udemycoupons/c/link-only-course")
        finally:
            client.close()

    assert r.status_code == 200
    html = r.text
    assert 'id="coupon-code"' not in html
    assert 'class="copy-btn' not in html
    assert "No separate coupon code" in html
    assert "Open the Udemy link below — the free price may be applied via the special offer URL." in html
    assert "If the offer fails, the offer may have expired" in html
    assert "Code None" not in html
    assert "Code ." not in html
    # meta keywords must not include empty/None coupon token
    assert "free udemy coupon, ," not in html
    assert "free udemy coupon, None," not in html

    blocks = re.findall(
        r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
        html,
        flags=re.DOTALL,
    )
    webpage = None
    for b in blocks:
        data = json.loads(b)
        if data.get("@type") == "WebPage":
            webpage = data
            break
    assert webpage is not None
    desc = webpage.get("description") or ""
    assert "Code None" not in desc
    assert "Code ." not in desc
    assert "Free Udemy coupon listing for Link Only Course" in desc
    assert "Validity can change" in desc


def test_coupon_detail_course_schema_and_offer_parity():
    course = {
        "id": 3,
        "title": "Schema Test Course",
        "slug": "schema-test-course",
        "description": "A comprehensive course on python testing.",
        "category": "Development",
        "language": "English",
        "coupon_code": "SCHEMAPASS",
        "is_coupon_valid": True,
        "url": "https://www.udemy.com/course/schema-test/",
        "rating": 4.8,
        "price": 1200,
        "last_checked_at": "2026-07-30T00:00:00",
    }
    with patch(
        "app.routers.public_deals.get_valid_deal_by_slug", return_value=course
    ), patch("app.routers.public_deals.related_deals", return_value=[]):
        client = TestClient(app)
        try:
            r = client.get("/udemycoupons/c/schema-test-course")
        finally:
            client.close()

    assert r.status_code == 200
    blocks = re.findall(
        r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
        r.text,
        flags=re.DOTALL,
    )
    webpage = None
    for b in blocks:
        data = json.loads(b)
        if data.get("@type") == "WebPage":
            webpage = data
            break
    assert webpage is not None
    assert "about" in webpage
    course_node = webpage["about"]
    assert course_node["@type"] == "Course"
    assert course_node["name"] == "Schema Test Course"
    assert course_node["description"] == "A comprehensive course on python testing."
    assert course_node["provider"]["name"] == "Udemy"

    assert "mainEntity" in webpage
    offer_node = webpage["mainEntity"]
    assert offer_node["@type"] == "Offer"
    assert offer_node["price"] == "0"
    assert offer_node["priceCurrency"] == "USD"

