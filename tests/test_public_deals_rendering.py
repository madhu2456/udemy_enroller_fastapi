"""Unit tests for public deals, coupon detail, and category hub template rendering."""

from unittest import mock

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import pytest

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


def test_public_deals_csp_nonce_on_style_tag(client):
    """Verify static skeleton styles use request nonce and no dynamic style element is created."""
    response = client.get("/udemycoupons")
    assert response.status_code == 200
    assert '<style nonce="' in response.text
    assert "pulse-light" in response.text
    assert "document.createElement('style')" not in response.text
    assert 'document.createElement("style")' not in response.text


def test_guides_escaped_cli_placeholders(client):
    """Verify CLI placeholders on /guides are HTML entity escaped to prevent DOM tag corruption."""
    response = client.get("/guides")
    assert response.status_code == 200
    assert (
        "python cli.py login --token &lt;TOKEN&gt; --client-id &lt;ID&gt; --csrf &lt;CSRF&gt;"
        in response.text
    )
    assert "<TOKEN>" not in response.text
    assert "<ID>" not in response.text
    assert "<CSRF>" not in response.text


def test_coupon_category_touch_targets_and_stacking(client):
    """Verify category hub cards use responsive column stacking and min-h-[44px] touch targets."""
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
                "url": "https://www.udemy.com/course/python-bootcamp/",
            }
        ],
    )
    with mock.patch(
        "app.routers.public_deals.get_deals_for_category_slug",
        return_value=fake_category_data,
    ):
        response = client.get("/udemycoupons/category/development")

    assert response.status_code == 200
    assert "flex flex-col sm:flex-row" in response.text
    assert "min-h-[44px]" in response.text
    assert 'aria-label="Related links"' in response.text
    assert "← All free coupons" in response.text


def test_faq_scraper_fleet_and_certificate_policy(client):
    """Verify /faq mirrors the 17-source scraper fleet and certificate completion policy."""
    response = client.get("/faq")
    assert response.status_code == 200
    assert "17-source" in response.text
    assert "12-source" not in response.text
    assert "Real Discount" in response.text
    assert "OnlineCourses.ooo" in response.text
    assert "certificates of completion" in response.text
    assert "April 2020" in response.text


def test_invalid_tailwind_classes_absence(client):
    """Verify bg-gray-55 and bg-yellow-55 are absent across all rendered public templates."""
    public_routes = [
        "/",
        "/udemycoupons",
        "/faq",
        "/about",
        "/guides",
        "/privacy",
        "/contact",
    ]
    for route in public_routes:
        response = client.get(route)
        assert response.status_code == 200, f"Route {route} failed with status {response.status_code}"
        assert "bg-gray-55" not in response.text, f"bg-gray-55 leaked into {route}"
        assert "bg-yellow-55" not in response.text, f"bg-yellow-55 leaked into {route}"


def test_login_heading_sequence_hierarchy(client):
    """Verify / renders How It Works as H2 and has no H3 How It Works sequence inversion."""
    response = client.get("/")
    assert response.status_code == 200
    assert '<h2 class="text-base font-semibold text-gray-900">How It Works</h2>' in response.text
    assert "<h3>How It Works</h3>" not in response.text

    soup = BeautifulSoup(response.text, "html.parser")
    h2_elements = soup.find_all("h2")
    how_it_works_h2 = [h for h in h2_elements if "How It Works" in h.get_text()]
    assert len(how_it_works_h2) == 1, "Expected exactly one <h2>How It Works</h2>"
    assert "text-base" in how_it_works_h2[0].get("class", [])
    assert "font-semibold" in how_it_works_h2[0].get("class", [])
    assert "text-gray-900" in how_it_works_h2[0].get("class", [])

    h3_elements = soup.find_all("h3")
    how_it_works_h3 = [h for h in h3_elements if "How It Works" in h.get_text()]
    assert len(how_it_works_h3) == 0, "Did not expect any <h3>How It Works</h3>"


def test_base_schema_graph_integrity(client):
    """Verify base schema graph eliminates dangling organization refs and declares All OS."""
    response = client.get("/")
    assert response.status_code == 200
    assert "https://madhudadi.in/#organization" not in response.text
    assert '"operatingSystem": "All"' in response.text
