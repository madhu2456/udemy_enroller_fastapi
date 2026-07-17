"""Regression coverage for the homepage FAQ disclosure controls."""

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from main import app


def test_homepage_faq_disclosures_expose_keyboard_semantics():
    client = TestClient(app)
    try:
        response = client.get("/")
    finally:
        client.close()

    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    buttons = soup.select("button.faq-toggle")

    assert len(buttons) == 8
    assert {control.name for control in soup.find_all(attrs={"onclick": "toggleFaq(this)"})} == {"button"}

    button_ids = [button.get("id") for button in buttons]
    panel_ids = [button.get("aria-controls") for button in buttons]
    assert all(button_ids)
    assert all(panel_ids)
    assert len(button_ids) == len(set(button_ids))
    assert len(panel_ids) == len(set(panel_ids))

    for button, panel_id in zip(buttons, panel_ids, strict=True):
        assert button.get("type") == "button"
        assert button.get("aria-expanded") == "false"

        panel = soup.find(id=panel_id)
        assert panel is not None
        assert "faq-content" in panel.get("class", [])
        assert "hidden" in panel.get("class", [])
        assert panel.find_parent("button") is None

        icon = button.find("svg")
        assert icon is not None
        assert icon.get("aria-hidden") == "true"
        assert icon.get("focusable") == "false"

    scripts = "\n".join(script.get_text() for script in soup.find_all("script"))
    assert "document.getElementById(panelId)" in scripts
    assert "button.setAttribute('aria-expanded', String(nextExpanded))" in scripts
    assert "content.classList.toggle('hidden', !nextExpanded)" in scripts
