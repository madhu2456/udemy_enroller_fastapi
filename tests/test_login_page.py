"""Tests for Login Page hero and UI content (Wave 2/3)."""

import re
from fastapi.testclient import TestClient
from main import app


def test_login_page_hero_summary_content_and_word_count():
    """Verify login page renders the updated 48-word hero summary paragraph."""
    client = TestClient(app)
    try:
        response = client.get("/login")
    finally:
        client.close()

    assert response.status_code == 200
    html = response.text

    expected_snippet = (
        'Udemy Enroller is a free, self-hosted open-source automation tool that securely '
        'uses your session cookies to monitor configured coupon aggregator sources and '
        '<strong class="font-semibold text-gray-700">attempt 100% off course enrollment</strong>. '
        'It never collects passwords or payment credentials. Enrollment operates best-effort '
        'and depends strictly on live coupon availability and platform rate constraints.'
    )
    assert expected_snippet in html

    # Extract text content and calculate word count
    # Strip html tags to count words in the hero text
    clean_text = re.sub(r"<[^>]+>", "", expected_snippet)
    words = [w for w in clean_text.split() if w]
    assert len(words) == 48
