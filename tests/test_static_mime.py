"""MIME type registration for self-hosted static assets (Fix 4)."""

import mimetypes

from fastapi.testclient import TestClient

from app.mime import register_extra_mimetypes
from main import app

# Extension -> expected media type for assets served under /static
EXPECTED_MIME_TYPES = {
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".eot": "application/vnd.ms-fontobject",
    ".webp": "image/webp",
}


def test_register_extra_mimetypes_records_all_pairs(monkeypatch):
    """register_extra_mimetypes() registers all six (ext, type) pairs."""
    calls = []
    monkeypatch.setattr(
        mimetypes, "add_type", lambda typ, ext: calls.append((ext, typ))
    )
    register_extra_mimetypes()
    assert len(calls) == len(EXPECTED_MIME_TYPES)
    for ext, expected in EXPECTED_MIME_TYPES.items():
        assert (ext, expected) in calls


def test_guess_type_after_registration():
    """After registration, guess_type resolves every served asset type."""
    register_extra_mimetypes()
    for ext, expected in EXPECTED_MIME_TYPES.items():
        guessed, _ = mimetypes.guess_type(f"sample{ext}")
        assert guessed == expected, f"{ext} resolved to {guessed!r}, expected {expected!r}"


class TestStaticAssetContentTypes:
    """Integration: /static serves the correct Content-Type after registration."""

    def test_woff2_font(self):
        client = TestClient(app)
        try:
            response = client.get("/static/fonts/inter-latin.woff2")
        finally:
            client.close()
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("font/woff2")

    def test_webp_image(self):
        client = TestClient(app)
        try:
            response = client.get("/static/images/icon-512.webp")
        finally:
            client.close()
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/webp")

    def test_css(self):
        client = TestClient(app)
        try:
            response = client.get("/static/fonts/inter.css")
        finally:
            client.close()
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/css")
