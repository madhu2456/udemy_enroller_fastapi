"""HowTo schema fidelity: JSON-LD step text must match the visible numbered list.

Regression guard for the critic finding on app/templates/pages/free_coupons_guide.html:
the static HowTo JSON-LD block (4 HowToStep entries) must stay byte-faithful to the
visible <ol class="list-decimal"> steps. A future editor adding or rewording an <li>
would silently desync the schema — Google's "schema must match visible content"
policy and answer-engine citation quality punish that with zero signal.

Rendered-HTML assertions via TestClient. JSON-LD extraction pattern copied from
tests/test_identity_anchors.py; HTML parsing with BeautifulSoup (html.parser) as in
tests/test_nav_auth_ssr.py and tests/test_main_landmark_structure.py.
"""

import json
import re

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from main import app

GUIDE_URL = "/guides/free-udemy-coupons"


def _guide_html() -> str:
    client = TestClient(app)
    try:
        response = client.get(GUIDE_URL)
    finally:
        client.close()
    assert response.status_code == 200
    return response.text


def _normalize_text(text: str) -> str:
    """The tag-stripped, entity-decoded, whitespace-trimmed text form.

    JSON-LD ``step[].text`` values are plain strings in exactly this form, so the
    visible <li> texts must be normalized the same way for an apples-to-apples
    comparison (the template's only inline tag, <em>your</em>, renders as "your").
    """
    return re.sub(r"\s+", " ", text).strip()


def _howto_docs(html: str) -> list[dict]:
    """Every JSON-LD document whose @type is HowTo (string or list form)."""
    docs = []
    for match in re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S
    ):
        doc = json.loads(match)
        types = doc.get("@type")
        if types is None:
            continue  # e.g. base.html's @graph Person node — not a HowTo
        if isinstance(types, str):
            types = [types]
        if "HowTo" in types:
            docs.append(doc)
    return docs


def _visible_step_texts(html: str) -> list[str]:
    """Texts of every <li> under the numbered <ol class="list-decimal">."""
    soup = BeautifulSoup(html, "html.parser")
    lists = soup.select("ol.list-decimal")
    assert len(lists) == 1, (
        f"expected exactly one numbered ol.list-decimal on {GUIDE_URL}, "
        f"got {len(lists)}"
    )
    return [
        _normalize_text(li.get_text())
        for li in lists[0].find_all("li", recursive=False)
    ]


def _howto_step_texts(doc: dict) -> list[str]:
    steps = doc["step"]
    for step in steps:
        assert step.get("@type") == "HowToStep", f"step missing HowToStep type: {step!r}"
        assert isinstance(step.get("text"), str), f"step missing text: {step!r}"
    return [_normalize_text(step["text"]) for step in steps]


def test_howto_step_texts_match_visible_numbered_list():
    """Count AND exact text equality between schema steps and visible <li> items."""
    html = _guide_html()

    howtos = _howto_docs(html)
    assert len(howtos) == 1, f"expected exactly one HowTo block, got {len(howtos)}"

    step_texts = _howto_step_texts(howtos[0])
    visible_texts = _visible_step_texts(html)

    assert len(step_texts) == len(visible_texts), (
        f"HowTo step count ({len(step_texts)}) differs from visible <li> count "
        f"({len(visible_texts)})"
    )
    assert step_texts == visible_texts, (
        "HowTo step text desynced from visible list:\n"
        f"  schema:  {step_texts}\n"
        f"  visible: {visible_texts}"
    )


def test_howto_description_includes_disclaimer():
    """S1 disclaimer parity: the HowTo description keeps the affiliation note."""
    howtos = _howto_docs(_guide_html())
    assert len(howtos) == 1, f"expected exactly one HowTo block, got {len(howtos)}"
    assert "Not affiliated with Udemy." in howtos[0]["description"]


def test_howto_name_matches_h1():
    """The HowTo name must equal the visible H1 (guards against "fixing" the name)."""
    html = _guide_html()
    howtos = _howto_docs(html)
    assert len(howtos) == 1, f"expected exactly one HowTo block, got {len(howtos)}"

    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.select_one("h1")
    assert h1 is not None, "page must render an h1"
    assert howtos[0]["name"] == _normalize_text(h1.get_text()), (
        f"HowTo name {howtos[0]['name']!r} differs from h1 "
        f"{_normalize_text(h1.get_text())!r}"
    )
