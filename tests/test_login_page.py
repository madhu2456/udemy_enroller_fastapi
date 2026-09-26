"""Tests for Login Page hero, UI content, and dedicated /login route."""

import re
import secrets
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from app.models.database import SessionLocal, User, UserSession
from main import app


def test_login_page_hero_summary_content_and_word_count():
    """Verify homepage renders the updated 48-word hero summary paragraph."""
    client = TestClient(app)
    try:
        response = client.get("/")
    finally:
        client.close()

    assert response.status_code == 200
    html = response.text

    expected_snippet = (
        "Udemy Enroller is a free, self-hosted open-source automation tool that securely "
        "uses your session cookies to monitor configured coupon aggregator sources and "
        '<strong class="font-semibold text-gray-700">attempt 100% off course enrollment</strong>. '
        "It never collects passwords or payment credentials. Enrollment operates best-effort "
        "and depends strictly on live coupon availability and platform rate constraints."
    )
    assert expected_snippet in html

    # Extract text content and calculate word count
    # Strip html tags to count words in the hero text
    clean_text = re.sub(r"<[^>]+>", "", expected_snippet)
    words = [w for w in clean_text.split() if w]
    assert len(words) == 48


def test_dedicated_login_page_renders_above_the_fold():
    """Verify GET /login renders dedicated credentials/cookie form above the fold."""
    client = TestClient(app)
    try:
        response = client.get("/login", follow_redirects=False)
    finally:
        client.close()

    assert response.status_code == 200
    html = response.text

    assert "Connect Your Account" in html
    assert 'id="cookie-form"' in html
    assert 'method="POST"' in html
    assert 'action="/api/auth/login/cookies"' in html
    assert 'name="robots" content="noindex, nofollow' in html or "noindex" in html

    # CSRF cookie check
    csrf_val = response.cookies.get("csrf_token") or response.cookies.get("__Host-csrf_token")
    assert csrf_val is not None, "CSRF cookie must be issued on /login render"


def test_dedicated_login_page_trailing_slash():
    """Verify GET /login/ renders dedicated login page with 200 OK."""
    client = TestClient(app)
    try:
        response = client.get("/login/", follow_redirects=False)
    finally:
        client.close()

    assert response.status_code == 200
    assert "Connect Your Account" in response.text


def test_dedicated_login_page_redirects_authenticated_users():
    """Verify authenticated users visiting /login are redirected 303 to /dashboard."""
    db = SessionLocal()
    token = secrets.token_hex(32)
    try:
        user = User(
            email=f"authed_login_{secrets.token_hex(4)}@example.com",
            udemy_display_name="Dedicated Login Tester",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.add(UserSession(token=token, user_id=user.id))
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    try:
        client.cookies.set("session_id", token)
        response = client.get("/login", follow_redirects=False)
    finally:
        client.close()

    assert response.status_code == 303
    assert response.headers.get("location") == "/dashboard"


def test_navigation_header_contains_login_links():
    """Verify navigation header and mobile drawer contain unauthenticated login links."""
    client = TestClient(app)
    try:
        response = client.get("/", follow_redirects=False)
    finally:
        client.close()

    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")

    login_nav = soup.find(id="login-nav-btn")
    assert login_nav is not None
    assert login_nav.get("href") == "/login"
    login_classes = login_nav.get("class") or []
    assert "hidden" in login_classes
    assert "sm:inline-flex" in login_classes

    mobile_nav = soup.find(id="mobile-nav")
    assert mobile_nav is not None
    mobile_login = mobile_nav.find(id="mobile-drawer-login-link")
    assert mobile_login is not None
    assert mobile_login.get("href") == "/login"
