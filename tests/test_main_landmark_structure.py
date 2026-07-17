"""Regression coverage for a single top-level main landmark per page."""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from main import app


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROUTES = ("/", "/about", "/faq", "/guides", "/privacy")
CHILD_TEMPLATES = (
    "app/templates/pages/login.html",
    "app/templates/pages/about.html",
    "app/templates/pages/faq.html",
    "app/templates/pages/guides.html",
    "app/templates/pages/privacy.html",
    "app/templates/pages/settings.html",
)


@pytest.mark.parametrize("route", PUBLIC_ROUTES)
def test_public_page_has_one_top_level_main_landmark(route):
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
    assert mains[0].find_parent("main") is None


@pytest.mark.parametrize("relative_path", CHILD_TEMPLATES)
def test_base_extending_page_does_not_declare_an_inner_main(relative_path):
    source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
    soup = BeautifulSoup(source, "html.parser")

    assert '{% extends "components/base.html" %}' in source
    assert soup.find("main") is None


def test_base_template_owns_the_main_landmark_and_skip_target():
    source = (PROJECT_ROOT / "app/templates/components/base.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(source, "html.parser")
    mains = soup.find_all("main")

    assert len(mains) == 1
    assert mains[0].get("id") == "main-content"
    assert mains[0].get("role") == "main"
    skip_link = soup.find("a", href="#main-content")
    assert skip_link is not None
