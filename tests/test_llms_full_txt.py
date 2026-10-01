"""F250: /llms-full.txt mirrors /llms.txt content.

Both routes share the same content builder; bodies must be identical except
for the dynamic "Last generated" timestamp.

Both routes serve ``text/markdown`` per llmstxt.org: llms.txt is a Markdown
document, and the spec's own discovery hint is ``rel="alternate"
type="text/markdown"``. It is NOT text/plain.
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
    content_type = response.headers.get("content-type", "")
    assert "text/markdown" in content_type, f"{path} served {content_type!r}"
    assert "text/plain" not in content_type, f"{path} served {content_type!r}"
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


def test_llms_full_txt_is_markdown_utf8():
    client = TestClient(app)
    try:
        response = client.get("/llms-full.txt")
    finally:
        client.close()
    assert response.status_code == 200
    # llmstxt.org declares llms.txt a Markdown document, so the route serves
    # text/markdown (charset utf-8) — not text/plain.
    assert response.headers.get("content-type", "").startswith("text/markdown")
