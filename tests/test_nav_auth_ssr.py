"""Nav auth SSR: cold HTML must not show Logout without hidden class (Fix 23)."""

import re
import secrets

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from app.models.database import SessionLocal, User, UserSession
from main import app


def test_anonymous_homepage_logout_btn_is_hidden():
    client = TestClient(app)
    try:
        response = client.get("/", follow_redirects=False)
    finally:
        client.close()

    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    logout = soup.find(id="logout-btn")
    assert logout is not None
    classes = logout.get("class") or []
    assert "hidden" in classes
    # Never pair hidden with flex/inline-flex (Tailwind conflict)
    assert "flex" not in classes
    assert "inline-flex" not in classes


def test_anonymous_faq_auth_controls_hidden_guest_controls_visible():
    client = TestClient(app)
    try:
        response = client.get("/faq")
    finally:
        client.close()

    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")

    logout = soup.find(id="logout-btn")
    assert logout is not None
    assert "hidden" in (logout.get("class") or [])

    profile = soup.find(id="profile-badge")
    assert profile is not None
    assert "hidden" in (profile.get("class") or [])

    for href in ("/dashboard", "/settings", "/history"):
        link = soup.select_one(f'a.auth-only[href="{href}"]')
        assert link is not None
        assert "hidden" in (link.get("class") or [])

    get_started = soup.find(id="get-started-btn")
    assert get_started is not None
    gs_classes = get_started.get("class") or []
    assert "hidden" not in gs_classes
    assert "inline-flex" in gs_classes

    github = soup.find(id="github-link")
    assert github is not None
    gh_classes = github.get("class") or []
    assert "hidden" not in gh_classes
    assert "inline-flex" in gh_classes


def test_anonymous_faq_still_allows_public_cdn_cache():
    """Anon marketing HTML may use short public CDN cache."""
    client = TestClient(app)
    try:
        response = client.get("/faq")
    finally:
        client.close()

    assert response.status_code == 200
    cc = response.headers.get("cache-control", "")
    assert "public" in cc
    assert "s-maxage=300" in cc
    assert "no-store" not in cc


def test_authenticated_faq_ssr_nav_and_private_cache():
    """Authed GET /faq: personalized nav + never public CDN cache."""
    display_name = "Nav SSR Tester"
    token = secrets.token_hex(32)
    db = SessionLocal()
    try:
        user = User(
            email=f"nav_ssr_{secrets.token_hex(4)}@example.com",
            udemy_display_name=display_name,
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
        response = client.get("/faq")
    finally:
        client.close()

    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")

    logout = soup.find(id="logout-btn")
    assert logout is not None
    logout_classes = logout.get("class") or []
    assert "inline-flex" in logout_classes
    assert "hidden" not in logout_classes

    user_info = soup.find(id="user-info")
    assert user_info is not None
    assert display_name in user_info.get_text()

    cc = response.headers.get("cache-control", "").lower()
    assert "public" not in cc
    assert "s-maxage" not in cc
    assert "no-store" in cc or "private" in cc

    vary_parts = {
        p.strip().lower()
        for p in response.headers.get("vary", "").split(",")
        if p.strip()
    }
    assert "cookie" in vary_parts


def test_base_template_has_no_hidden_flex_conflict():
    """Static guard: class lists must not contain both token 'hidden' and 'flex'."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "app/templates/components/base.html"
    ).read_text(encoding="utf-8")
    for match in re.finditer(r'class="([^"]*)"', source):
        tokens = match.group(1).split()
        # Exact class tokens only (ignore overflow-hidden, flex-grow, etc.)
        has_hidden = "hidden" in tokens
        has_flex = "flex" in tokens or "inline-flex" in tokens
        assert not (has_hidden and has_flex), (
            f"Conflicting hidden+flex tokens in class={match.group(1)!r}"
        )
