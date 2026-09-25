"""Unit tests for public deals, coupon detail, and category hub template rendering."""

from unittest import mock

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_public_deals_price_and_date_formatting(client):
    fake_deals = [
        {
            "id": 1,
            "title": "Python Bootcamp",
            "slug": "python-bootcamp",
            "category": "Development",
            "coupon_code": "PYFREE2026",
            "price": 1419.0,
            "enrolled_at": "2026-08-12T14:00:00Z",
            "is_coupon_valid": True,
            "url": "https://www.udemy.com/course/python-bootcamp/?couponCode=PYFREE2026",
        }
    ]
    with mock.patch("app.routers.public_deals.list_valid_deals", return_value=fake_deals):
        response = client.get("/udemycoupons")

    assert response.status_code == 200
    assert "₹1,419" in response.text
    assert "₹1419.0" not in response.text
    assert "Discovered: 2026-08-12" in response.text
    assert "whitespace-nowrap flex-shrink-0" in response.text


def test_coupon_detail_price_and_code_classes(client):
    fake_deal = {
        "id": 1,
        "title": "Python Bootcamp",
        "slug": "python-bootcamp",
        "category": "Development",
        "coupon_code": "PYFREE2026",
        "price": 1419.0,
        "enrolled_at": "2026-08-12T14:00:00Z",
        "is_coupon_valid": True,
        "url": "https://www.udemy.com/course/python-bootcamp/?couponCode=PYFREE2026",
    }
    with mock.patch("app.routers.public_deals.get_valid_deal_by_slug", return_value=fake_deal):
        response = client.get("/udemycoupons/c/python-bootcamp")

    assert response.status_code == 200
    assert "₹1,419" in response.text
    assert (
        "font-mono text-xs sm:text-base text-gray-900 font-semibold tracking-tight select-all truncate"
        in response.text
    )


def test_announcement_banner_suppression_on_deals(client):
    with mock.patch("app.routers.public_deals.list_valid_deals", return_value=[]):
        response = client.get("/udemycoupons")
        assert response.status_code == 200
        assert 'id="announcement-bar"' not in response.text

    response = client.get("/")
    assert response.status_code == 200
    assert 'id="announcement-bar"' in response.text


def test_category_hub_cards_parity(client):
    fake_category_data = (
        "Development",
        [
            {
                "id": 1,
                "title": "Python Bootcamp",
                "slug": "python-bootcamp",
                "category": "Development",
                "coupon_code": "PYFREE2026",
                "price": 1419.0,
                "enrolled_at": "2026-08-12T14:00:00Z",
                "is_coupon_valid": True,
            }
        ],
    )
    with mock.patch(
        "app.routers.public_deals.get_deals_for_category_slug",
        return_value=fake_category_data,
    ):
        response = client.get("/udemycoupons/category/development")

    assert response.status_code == 200
    assert "Discovered: 2026-08-12" in response.text
    assert "₹1,419" in response.text
    assert 'text-green-800 font-bold">Free</span>' in response.text


def test_contrast_and_touch_target_classes(client):
    response = client.get("/udemycoupons")
    assert response.status_code == 200
    assert 'class="text-gray-600"' in response.text
    assert "min-h-[24px]" in response.text


def test_homepage_hero_disclaimer_spacing_and_contrast(client):
    response = client.get("/")
    assert response.status_code == 200
    # Hero vertical spacing assertions
    assert "mt-6 mb-8 inline-flex" in response.text
    assert (
        "animate-fade-in-up delay-300 flex flex-col sm:flex-row items-center justify-center gap-3 mb-8"
        in response.text
    )
    assert "items-center justify-center gap-3 mb-10" not in response.text

    # Touch target assertions
    assert "min-h-[24px]" in response.text
    assert response.text.count("min-h-[24px]") >= 2

    # Hyphen contrast & strict count (100% mutation survival)
    assert response.text.count("text-gray-600 mr-2 mt-px select-none") == 12
    assert "text-gray-400 mr-2 mt-px select-none" not in response.text

    # Marketing CTAs preserved
    assert "Start Automating Free" in response.text
    assert "View Source Code" in response.text


def test_footer_adticks_badge_layout_and_contrast(client):
    """Verify footer Adticks badge layout resilience, contrast compliance, and no overflow tokens."""
    response = client.get("/")
    assert response.status_code == 200

    # Adticks marketing link and href verification
    assert "https://adticks.com" in response.text
    assert "SEO &amp; GEO improved by" in response.text or "SEO & GEO improved by" in response.text
    assert "Adticks" in response.text

    # Extract the Adticks badge container / anchor snippet (bounded strictly to </a>)
    badge_start = response.text.find('id="adticks-badge"')
    assert badge_start != -1
    badge_end = response.text.find("</a>", badge_start)
    assert badge_end != -1
    badge_snippet = response.text[badge_start : badge_end + 4]

    # Anti-shrink and anti-wrap layout guardrails on the badge
    assert "inline-flex items-center gap-1.5 whitespace-nowrap" in badge_snippet
    assert "flex-shrink-0" in badge_snippet
    assert '<span class="whitespace-nowrap">' in badge_snippet

    # WCAG 2.1 AA Contrast compliance tokens on the badge
    assert "text-gray-600" in badge_snippet
    assert "text-blue-700" in badge_snippet
    assert "text-blue-600" in badge_snippet

    # Negative assertion against regressed low-contrast tokens in the badge
    assert "text-[#2563EB]" not in badge_snippet
    assert "text-gray-500" not in badge_snippet
    assert "text-blue-500" not in badge_snippet

    # Verify Credits container flex-shrink-0
    credits_container_idx = response.text.rfind("<!-- Credits & Disclaimer -->")
    assert credits_container_idx != -1
    credits_snippet = response.text[credits_container_idx:badge_start]
    assert "flex-shrink-0" in credits_snippet

    # Disclaimer integrity preserved
    assert "Not affiliated with Udemy, Inc." in response.text
    assert "Enroller by Madhu Dadi" in response.text



