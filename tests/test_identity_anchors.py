"""Fix #8: Person identity anchors — sameAs must be exactly the 8 canonical anchors.

Pure-source assertions (no DB writes): the base.html template literal, the
app/routers/seo.py PERSON_SAME_AS constant, and the rendered output via
TestClient (homepage Person node + /ai-profile.json Person nodes).
"""

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.routers import seo
from main import app

CANONICAL_SAME_AS = [
    "https://www.wikidata.org/wiki/Q139807441",
    "https://github.com/madhu2456",
    "https://www.linkedin.com/in/madhu-dadi-54684531",
    "https://x.com/madhu245",
    "https://medium.com/@madhu.kumar245",
    "https://dev.to/madhudadi",
    "https://www.youtube.com/@madhukumar245",
    "https://maps.google.com/?cid=CXaUijPkQhVkEBM",
]

# Sites/products must never appear inside a Person sameAs array (Fix #8).
FORBIDDEN_IN_SAME_AS = [
    "madhudadi.in/blog",
    "deals.madhudadi.in",
    "udemyenroller.madhudadi.in",
    "adticks.com",
]

BASE_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "templates" / "components" / "base.html"
)


def _extract_json_array(text: str, marker: str) -> str:
    """Return the JSON array literal that follows `marker`, honoring strings."""
    idx = text.index(marker)
    open_bracket = text.index("[", idx)
    depth = 0
    in_string = False
    i = open_bracket
    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return text[open_bracket : i + 1]
        i += 1
    raise AssertionError(f"unterminated JSON array after marker {marker!r}")


def _person_same_as_from_source(source: str) -> list[str]:
    """Extract the Person node's sameAs literal from the template source."""
    person_marker = '"@type": "Person"'
    assert person_marker in source, "base.html must define a Person node"
    # sameAs after the Person node — the only sameAs in base.html.
    array_literal = _extract_json_array(source, '"sameAs": [')
    return json.loads(array_literal)


def _collect_same_as(node) -> list[list[str]]:
    """Recursively collect every sameAs list in a JSON-LD document."""
    found: list[list[str]] = []

    def walk(value) -> None:
        if isinstance(value, dict):
            same = value.get("sameAs")
            if isinstance(same, list):
                found.append(same)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    return found


class TestBaseTemplateSource:
    """(a) base.html literal contains the 8 anchors inside the Person sameAs block."""

    def test_person_same_as_is_exactly_the_8_canonical_anchors(self):
        source = BASE_TEMPLATE_PATH.read_text(encoding="utf-8")
        assert _person_same_as_from_source(source) == CANONICAL_SAME_AS

    def test_person_same_as_block_contains_no_site_or_product_domains(self):
        source = BASE_TEMPLATE_PATH.read_text(encoding="utf-8")
        block = _extract_json_array(source, '"sameAs": [')
        for forbidden in FORBIDDEN_IN_SAME_AS:
            assert forbidden not in block, f"forbidden domain in Person sameAs: {forbidden}"


class TestSeoRouterConstant:
    """(b) app/routers/seo.py defines PERSON_SAME_AS == the 8 canonical anchors."""

    def test_person_same_as_constant_is_exactly_the_8_canonical_anchors(self):
        assert list(seo.PERSON_SAME_AS) == CANONICAL_SAME_AS

    def test_person_same_as_constant_contains_no_site_or_product_domains(self):
        for url in seo.PERSON_SAME_AS:
            for forbidden in FORBIDDEN_IN_SAME_AS:
                assert forbidden not in url, f"forbidden domain in PERSON_SAME_AS: {url}"


class TestRenderedOutput:
    """(c) Rendered pages emit the 8 anchors in order for every Person sameAs."""

    def _assert_same_as_lists(self, lists: list[list[str]]) -> None:
        assert lists, "expected at least one sameAs list"
        for same_as in lists:
            assert same_as == CANONICAL_SAME_AS
            for url in same_as:
                for forbidden in FORBIDDEN_IN_SAME_AS:
                    assert forbidden not in url, f"forbidden domain in sameAs: {url}"

    def _ld_json_documents(self, html: str) -> list[dict]:
        docs = []
        for match in re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.S
        ):
            docs.append(json.loads(match))
        return docs

    def test_homepage_person_same_as_is_the_8_canonical_anchors(self):
        client = TestClient(app)
        try:
            response = client.get("/", follow_redirects=False)
        finally:
            client.close()
        assert response.status_code == 200

        lists = [
            same_as
            for doc in self._ld_json_documents(response.text)
            for same_as in _collect_same_as(doc)
        ]
        self._assert_same_as_lists(lists)

    def test_ai_profile_json_both_person_same_as_lists_are_the_8_canonical_anchors(self):
        client = TestClient(app)
        try:
            response = client.get("/ai-profile.json")
        finally:
            client.close()
        assert response.status_code == 200

        lists = _collect_same_as(response.json())
        assert len(lists) == 2, f"expected 2 sameAs lists in ai-profile.json, got {len(lists)}"
        self._assert_same_as_lists(lists)


HUB_JOB_TITLE = "AI Engineer, RAG & Analytics Consultant"


class TestVisibleIdentityCopy:
    """F015: visible job title matches the hub headline."""

    def test_homepage_visible_title_matches_hub(self):
        client = TestClient(app)
        try:
            response = client.get("/", follow_redirects=False)
        finally:
            client.close()
        assert response.status_code == 200
        assert HUB_JOB_TITLE in response.text
        assert "AI Developer" not in response.text


class TestFooterSiblingLinks:
    """F037: footer lists Deals + hub/profile; Adticks stays; products stay out of sameAs."""

    def test_footer_has_deals_hub_profile_and_adticks(self):
        source = BASE_TEMPLATE_PATH.read_text(encoding="utf-8")
        footer = source[source.index("<footer") : source.index("</footer>")]
        assert 'href="https://deals.madhudadi.in"' in footer
        assert ">Deals<" in footer
        assert 'href="https://madhudadi.in"' in footer
        assert 'href="https://madhudadi.in/profile/"' in footer
        assert ">Profile<" in footer
        assert 'href="https://adticks.com"' in footer

    def test_footer_products_are_not_in_person_same_as(self):
        source = BASE_TEMPLATE_PATH.read_text(encoding="utf-8")
        block = _extract_json_array(source, '"sameAs": [')
        for forbidden in FORBIDDEN_IN_SAME_AS:
            assert forbidden not in block
