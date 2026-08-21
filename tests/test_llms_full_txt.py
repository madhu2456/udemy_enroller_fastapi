"""F250: /llms-full.txt mirrors /llms.txt content.

Both routes share the same content builder; bodies must be identical except
for the dynamic "Last generated" timestamp.
"""

import re

from fastapi.testclient import TestClient

from main import app


def _fetch(path: str) -> str:
    client = TestClient(app)
    try:
        response = client.get(path)
    finally:
        client.close()
    assert response.status_code == 200, f"{path} returned {response.status_code}"
    assert "text/plain" in response.headers.get("content-type", "")
    return response.text


def _normalize_timestamp(text: str) -> str:
    # Two sequential TestClient GETs each stamp "Last generated" independently,
    # so raw bodies are never byte-identical even when both routes share the
    # same builder. Strip that one line so the rest of the document can match.
    return re.sub(r"Last generated: .*", "Last generated: <TS>", text)


def test_llms_full_txt_mirrors_llms_txt():
    canonical = _fetch("/llms.txt")
    full = _fetch("/llms-full.txt")
    assert len(full) > 1000
    assert "Udemy Course Enroller — AI Profile" in full
    # Byte-identical apart from the per-request timestamp.
    assert _normalize_timestamp(full) == _normalize_timestamp(canonical)


def test_llms_full_txt_is_plain_text_utf8():
    client = TestClient(app)
    try:
        response = client.get("/llms-full.txt")
    finally:
        client.close()
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/plain")
