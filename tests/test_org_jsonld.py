"""D6: Organization JSON-LD present on public pages (base.html graph).

Rendered-HTML assertions via TestClient, following the JSON-LD extraction
pattern from tests/test_identity_anchors.py.
"""

import json
import re

import pytest
from fastapi.testclient import TestClient

from main import app

PUBLIC_PAGES = [
    "/",
    "/faq",
    "/about",
    "/guides",
    "/privacy",
    "/terms",
    "/accessibility",
    "/contact",
    "/udemycoupons",
]


def _ld_docs(html: str) -> list[dict]:
    docs = []
    for match in re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S
    ):
        docs.append(json.loads(match))
    return docs


def _organizations(html: str) -> list[dict]:
    orgs = []
    for doc in _ld_docs(html):
        graph = doc.get("@graph")
        if not isinstance(graph, list):
            continue
        for node in graph:
            if isinstance(node, dict) and node.get("@type") == "Organization":
                orgs.append(node)
    return orgs


def test_organization_jsonld_on_home():
    client = TestClient(app)
    try:
        response = client.get("/")
    finally:
        client.close()
    assert response.status_code == 200
    orgs = _organizations(response.text)
    assert len(orgs) == 1
    org = orgs[0]
    assert org["name"] == "Udemy Enroller"
    assert org["url"] == "https://udemyenroller.madhudadi.in/"
    assert org["@id"] == "https://udemyenroller.madhudadi.in/#organization"
    # founder -> madhudadi.in/#person (person identity anchor hub)
    assert org["founder"]["@id"] == "https://madhudadi.in/#person"
    assert org["founder"]["name"] == "Madhu Dadi"
    # parentOrganization -> portfolio hub
    assert org["parentOrganization"]["@id"] == "https://madhudadi.in/#organization"


@pytest.mark.parametrize("path", PUBLIC_PAGES[1:])
def test_organization_jsonld_on_public_pages(path):
    client = TestClient(app)
    try:
        response = client.get(path)
    finally:
        client.close()
    assert response.status_code == 200
    orgs = _organizations(response.text)
    assert len(orgs) == 1, f"{path} should carry exactly one Organization node"
    assert orgs[0]["name"] == "Udemy Enroller"
