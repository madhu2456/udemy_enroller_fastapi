"""Comprehensive verification tests for Desktop GUI and Unified Rich CLI documentation & integration."""

import json
import re
from pathlib import Path
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import pytest

from main import app

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_desktop_cli_hero_banner():
    """Verify dashboard template contains Desktop GUI & CLI hero banner and guide link."""
    dashboard_path = PROJECT_ROOT / "app/templates/pages/dashboard.html"
    source = dashboard_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(source, "html.parser")

    banner = soup.find(id="desktop-cli-banner")
    assert banner is not None, "Dashboard must contain #desktop-cli-banner"

    guide_link = banner.find("a", href="/guides#desktop-gui-cli")
    assert guide_link is not None, "Banner must contain link to /guides#desktop-gui-cli"
    assert "Desktop & CLI Guide" in guide_link.get_text() or "Desktop &amp; CLI Guide" in source

    text = banner.get_text()
    assert "python gui.py" in text
    assert "python cli.py enroll" in text or "python cli.py" in text
    for browser in ("Chrome", "Edge", "Firefox", "Brave", "Opera", "Chromium"):
        assert browser in text, f"Missing browser mention: {browser}"


def test_guides_page_desktop_cli_section():
    """Verify /guides contains #desktop-gui-cli section with GUI and CLI walkthroughs."""
    client = TestClient(app)
    try:
        response = client.get("/guides")
    finally:
        client.close()

    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")

    section = soup.find(id="desktop-gui-cli")
    assert section is not None, "/guides must contain article #desktop-gui-cli"

    section_text = section.get_text()
    assert "python gui.py" in section_text
    assert "python cli.py" in section_text

    # CLI subcommands and options
    for cmd in ("enroll", "scrape", "check", "stats", "server"):
        assert cmd in section_text, f"Missing CLI command: {cmd}"

    for opt in ("--dry-run", "--categories", "--languages", "--min-rating", "--limit", "--discounted-only", "--sites", "--format"):
        assert opt in section_text, f"Missing CLI option: {opt}"

    # GUI features
    assert "CustomTkinter" in section_text or "Custom Tkinter" in section_text
    assert "17-scraper" in section_text or "17" in section_text
    assert "progress bar" in section_text.lower()
    assert "1000-line" in section_text or "ring-buffer" in section_text


def test_guides_itemlist_schema_includes_desktop_cli():
    """Verify ItemList JSON-LD on /guides includes position 6 for desktop-gui-cli."""
    client = TestClient(app)
    try:
        response = client.get("/guides")
    finally:
        client.close()

    assert response.status_code == 200
    json_ld_matches = re.findall(r'<script type="application/ld\+json">(.*?)</script>', response.text, re.S)
    found_itemlist = False

    for match in json_ld_matches:
        try:
            doc = json.loads(match)
        except Exception:
            continue

        graph = doc.get("@graph", [doc])
        for node in graph:
            if node.get("@type") == "ItemList":
                found_itemlist = True
                items = node.get("itemListElement", [])
                assert len(items) >= 6, f"Expected at least 6 ItemList items, found {len(items)}"
                item6 = next((item for item in items if item.get("position") == 6), None)
                assert item6 is not None, "Expected position 6 in ItemList"
                assert "Desktop GUI & Terminal CLI Guide" in item6.get("name", "")
                assert "https://udemyenroller.madhudadi.in/guides#desktop-gui-cli" in item6.get("url", "")

    assert found_itemlist, "Could not find ItemList schema in /guides"


def test_f320_guides_lead_preserved():
    """Ensure F320 lead paragraph constraints remain intact."""
    client = TestClient(app)
    try:
        response = client.get("/guides")
    finally:
        client.close()

    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    h1 = soup.select_one("#guides-hero-heading")
    assert h1 is not None
    lead = h1.find_next_sibling("p")
    assert lead is not None
    text = re.sub(r"\s+", " ", lead.get_text()).strip()
    words = text.split()
    assert 40 <= len(words) <= 60, f"lead word count {len(words)}: {text}"
    assert "session cookies" in text.lower()
    assert "5 minutes" in text
    assert lead.find("a") is None
    assert "best" not in text.lower()


def test_base_footer_desktop_cli_link():
    """Verify footer navigation in base.html contains the desktop & CLI guide link."""
    base_path = PROJECT_ROOT / "app/templates/components/base.html"
    source = base_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(source, "html.parser")

    footer_nav = soup.find("nav", attrs={"aria-label": "Footer navigation"})
    assert footer_nav is not None, "base.html must have footer navigation"

    link = footer_nav.find("a", href="/guides#desktop-gui-cli")
    assert link is not None, "Footer nav must link to /guides#desktop-gui-cli"
    assert "Desktop & CLI Guide" in link.get_text()


def test_faq_jsonld_and_html_desktop_cli_coverage():
    """Verify /faq contains GUI and CLI entries in both JSON-LD FAQPage and visible HTML."""
    client = TestClient(app)
    try:
        response = client.get("/faq")
    finally:
        client.close()

    assert response.status_code == 200

    # 1. JSON-LD Verification
    json_ld_matches = re.findall(r'<script type="application/ld\+json">(.*?)</script>', response.text, re.S)
    faq_questions = []
    for match in json_ld_matches:
        try:
            doc = json.loads(match)
        except Exception:
            continue
        if doc.get("@type") == "FAQPage":
            for q in doc.get("mainEntity", []):
                faq_questions.append(q.get("name", ""))

    assert any("Desktop GUI" in q for q in faq_questions), "FAQPage JSON-LD missing Desktop GUI question"
    assert any("Terminal CLI" in q or "CLI" in q for q in faq_questions), "FAQPage JSON-LD missing CLI question"
    assert any("browsers" in q.lower() and "cookie" in q.lower() for q in faq_questions), "FAQPage JSON-LD missing browser cookie question"

    # 2. Visible HTML Verification
    soup = BeautifulSoup(response.text, "html.parser")
    page_text = soup.get_text()
    assert "python gui.py" in page_text
    assert "python cli.py" in page_text
    for browser in ("Chrome", "Edge", "Firefox", "Brave", "Opera", "Chromium"):
        assert browser in page_text, f"FAQ visible text missing browser: {browser}"


@pytest.mark.parametrize("route", ("/", "/about", "/faq", "/guides", "/privacy", "/contact", "/terms"))
def test_main_landmark_structure_unbroken(route):
    """Verify single top-level main landmark on all public pages."""
    client = TestClient(app)
    try:
        response = client.get(route)
    finally:
        client.close()

    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    mains = soup.find_all("main")
    assert len(mains) == 1
    assert mains[0].get("id") == "main-content"
    assert mains[0].get("role") == "main"
